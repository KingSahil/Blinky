import sys
import json
import os
import requests

SESSION_ID = "blinky-default-session"

def get_backend_url():
    """Discover the port of the WhatsApp Node backend."""
    # Check if PORT environment variable is set
    port = os.getenv("PORT")
    if port:
        return f"http://localhost:{port}"

    # Try reading from .env file in the workspace root
    env_path = os.path.join(os.getcwd(), '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('PORT='):
                        p = line.split('=', 1)[1].strip()
                        if p:
                            return f"http://localhost:{p}"
        except Exception as e:
            print(f"[DEBUG] Error reading .env: {e}", file=sys.stderr)

    # Scan ports 3000 to 3005 to locate the running backend
    print("[DEBUG] Scanning ports 3000-3005 to discover WhatsApp backend...", file=sys.stderr)
    for p in range(3000, 3006):
        url = f"http://localhost:{p}"
        try:
            # Call api/sessions to verify if it's our backend
            resp = requests.post(f"{url}/api/sessions", json={"sessionId": SESSION_ID}, timeout=1.0)
            if resp.status_code in [200, 400]:
                print(f"[DEBUG] WhatsApp backend discovered on port {p}", file=sys.stderr)
                return url
        except requests.RequestException:
            continue

    # Default fallback
    return "http://localhost:3000"

def get_headers():
    return {
        "X-Session-Id": SESSION_ID,
        "Content-Type": "application/json"
    }

def run_status(base_url):
    """Ensure session is registered and check connection status."""
    headers = get_headers()
    
    # 1. Post to sessions to register/start the client if not already done
    try:
        requests.post(f"{base_url}/api/sessions", json={"sessionId": SESSION_ID}, headers=headers, timeout=5.0)
    except Exception as e:
        return {"error": f"Failed to connect to backend server: {e}"}

    # 2. Get status
    try:
        resp = requests.get(f"{base_url}/api/status", headers=headers, timeout=5.0)
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"error": f"Backend returned status {resp.status_code}: {resp.text}"}
    except Exception as e:
        return {"error": f"Failed to fetch status: {e}"}

def run_chats(base_url):
    """List recent WhatsApp chats."""
    headers = get_headers()
    try:
        resp = requests.get(f"{base_url}/api/chats", headers=headers, timeout=10.0)
        if resp.status_code == 200:
            return {"chats": resp.json()}
        else:
            # If not connected, give a friendly message
            data = resp.json() if resp.status_code in [400, 404, 503] else {}
            error_msg = data.get("error", resp.text)
            return {"error": error_msg}
    except Exception as e:
        return {"error": f"Failed to retrieve chats: {e}"}

def run_summarize(base_url, chat_name=None, chat_id=None, limit=50):
    """Find the chat by name or ID, and run the summarizer."""
    headers = get_headers()
    
    # Resolve chat_id if only name is provided
    if not chat_id:
        if not chat_name:
            return {"error": "Either chat_name or chat_id must be provided to summarize."}
        
        # Get chats and search for the name
        print(f"[DEBUG] Fetching chats to locate chat matching name '{chat_name}'...", file=sys.stderr)
        chats_result = run_chats(base_url)
        if "error" in chats_result:
            return {"error": f"Could not fetch chats to resolve name: {chats_result['error']}"}
        
        matched_chats = []
        target_name_lower = chat_name.lower().strip()
        for chat in chats_result.get("chats", []):
            name = chat.get("name", "").lower().strip()
            if target_name_lower == name:
                matched_chats.insert(0, chat) # exact match takes precedence
            elif target_name_lower in name:
                matched_chats.append(chat)

        if not matched_chats:
            return {"error": f"No chat found matching name '{chat_name}'. Please ensure the name is correct or check the chat list."}
        
        chat_id = matched_chats[0]["id"]
        print(f"[DEBUG] Resolved chat name '{chat_name}' to ID: {chat_id} (Matched: {matched_chats[0]['name']})", file=sys.stderr)

    # Perform summarization
    safe_limit = 50
    if limit is not None:
        try:
            safe_limit = int(limit)
        except (ValueError, TypeError):
            pass
    print(f"[DEBUG] Requesting summary for chat ID {chat_id} with limit {safe_limit}...", file=sys.stderr)
    try:
        resp = requests.post(
            f"{base_url}/api/summarise",
            json={"chatId": chat_id, "limit": safe_limit},
            headers=headers,
            timeout=120.0 # Summarization calls might take time due to LLM response
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            data = resp.json() if resp.status_code in [400, 404, 500, 503] else {}
            error_msg = data.get("error", resp.text)
            return {"error": f"Summarization failed: {error_msg}"}
    except Exception as e:
        return {"error": f"HTTP request failed: {e}"}

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing JSON argument string."}))
        sys.exit(1)

    try:
        args = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    action = args.get("action", "status").lower().strip()
    chat_name = args.get("chat_name")
    chat_id = args.get("chat_id")
    limit = args.get("limit")
    if limit is None:
        limit = 50

    base_url = get_backend_url()
    print(f"[DEBUG] Using WhatsApp backend URL: {base_url}", file=sys.stderr)

    if action == "status":
        result = run_status(base_url)
    elif action == "chats" or action == "list":
        result = run_chats(base_url)
    elif action == "summarize" or action == "summarise":
        result = run_summarize(base_url, chat_name=chat_name, chat_id=chat_id, limit=limit)
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result))

if __name__ == "__main__":
    main()
