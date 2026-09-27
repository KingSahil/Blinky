import sys
import json
import os
import re
import requests

SESSION_ID = "blinky-default-session"

def resolve_whatsapp_request(query: str) -> tuple[str, str | None] | None:
    """Deterministically parse and resolve WhatsApp action and chat name from a user query."""
    if not query:
        return None
    q = query.strip().rstrip("?.!,;:").strip()
    q_lower = q.lower()

    if "whatsapp" not in q_lower and "wa " not in q_lower:
        return None

    # Status checks
    if re.search(r"\b(whatsapp\s+status|check\s+whatsapp\s+status|is\s+whatsapp\s+connected|whatsapp\s+connection\s+status|whatsapp\s+state)\b", q_lower):
        return ("status", None)

    # Chat list checks
    if re.search(r"\b(list\s+(all\s+)?(my\s+)?whatsapp\s+chats|show\s+(all\s+)?(my\s+)?whatsapp\s+chats|get\s+(my\s+)?whatsapp\s+chats|whatsapp\s+chats|my\s+whatsapp\s+chats|list\s+whatsapp\s+groups)\b", q_lower):
        return ("chats", None)

    # Summarize patterns
    # Pattern 1: summarize [chat] in/on whatsapp
    m = re.search(r"^(?:please\s+)?(?:summarize|summarise|give\s+a\s+summary\s+of|give\s+me\s+a\s+summary\s+of|recap)\s+(?:the\s+|my\s+)?(.+?)\s*(?:chat|group\s+chat|group|messages)?\s+(?:in|on|via|using|from|with)\s+whatsapp\s*(?:chat|group)?$", q, re.IGNORECASE)
    if m:
        chat = m.group(1).strip()
        chat = re.sub(r"^(?:the|my)\s+", "", chat, flags=re.IGNORECASE).strip()
        chat = re.sub(r"\s+(?:chat|group\s+chat|group|messages)$", "", chat, flags=re.IGNORECASE).strip()
        return ("summarize", chat if chat else None)

    # Pattern 2: whatsapp summarize [chat]
    m = re.search(r"^(?:on|in|via)?\s*whatsapp\s+(?:please\s+)?(?:summarize|summarise|recap)\s+(?:the\s+|my\s+)?(?:chat|group\s+chat|group)?\s*(.+)$", q, re.IGNORECASE)
    if m:
        chat = m.group(1).strip()
        chat = re.sub(r"^(?:the|my)\s+", "", chat, flags=re.IGNORECASE).strip()
        chat = re.sub(r"\s+(?:chat|group\s+chat|group|messages)$", "", chat, flags=re.IGNORECASE).strip()
        return ("summarize", chat if chat else None)

    # Pattern 3: summarize whatsapp [chat]
    m = re.search(r"^(?:please\s+)?(?:summarize|summarise|recap)\s+whatsapp\s+(?:chat|group\s+chat|group|messages)?\s*(?:of|for|with)?\s*(.+)$", q, re.IGNORECASE)
    if m:
        chat = m.group(1).strip()
        chat = re.sub(r"^(?:the|my)\s+", "", chat, flags=re.IGNORECASE).strip()
        chat = re.sub(r"\s+(?:chat|group\s+chat|group|messages)$", "", chat, flags=re.IGNORECASE).strip()
        return ("summarize", chat if chat else None)

    # Pattern 4: general summarize query mentioning whatsapp
    if re.search(r"\b(summarize|summarise|recap)\b", q_lower) and "whatsapp" in q_lower:
        cleaned = re.sub(r"\b(please|summarize|summarise|give\s+a\s+summary\s+of|give\s+me\s+a\s+summary\s+of|recap|in|on|via|using|from|for|with|whatsapp|group\s+chat|group|chat|messages|the|my)\b", " ", q, flags=re.IGNORECASE)
        chat = " ".join(cleaned.split()).strip()
        return ("summarize", chat if chat else None)

    return None

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
        resp = requests.get(f"{base_url}/api/chats", headers=headers, timeout=30.0)
        if resp.status_code == 200:
            return {"chats": resp.json()}
        else:
            # If not connected, give a friendly message
            data = resp.json() if resp.status_code in [400, 404, 503] else {}
            error_msg = data.get("error", resp.text)
            return {"error": error_msg}
    except Exception as e:
        return {"error": f"Failed to retrieve chats: {e}"}

def score_match(query, candidate):
    """Calculate similarity score between query and candidate chat name."""
    stop_words = {"group", "of", "in", "the", "a", "and", "to", "chat", "for", "with", "community"}
    
    def clean_and_tokenize(text):
        if not text:
            return []
        text = text.lower()
        cleaned = "".join(c if c.isalnum() else " " for c in text)
        return [w for w in cleaned.split() if w and w not in stop_words]

    q_words = clean_and_tokenize(query)
    c_words = clean_and_tokenize(candidate)
    
    if not q_words or not c_words:
        return 0.0
        
    q_clean = " ".join(q_words)
    c_clean = " ".join(c_words)
    
    if q_clean == c_clean:
        return 100.0
        
    if q_clean in c_clean:
        return 80.0 + (len(q_clean) / len(c_clean) * 10.0)
    if c_clean in q_clean:
        return 70.0 + (len(c_clean) / len(q_clean) * 10.0)
        
    q_set = set(q_words)
    c_set = set(c_words)
    overlap = q_set.intersection(c_set)
    if not overlap:
        return 0.0
        
    score = (len(overlap) / len(q_set)) * 60.0
    
    for i in range(len(q_words) - 1):
        bigram = q_words[i] + " " + q_words[i+1]
        if bigram in c_clean:
            score += 10.0
            break
            
    return score

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
        
        scored_chats = []
        for chat in chats_result.get("chats", []):
            score = score_match(chat_name, chat.get("name", ""))
            if score >= 20.0:
                scored_chats.append((score, chat))
 
        if not scored_chats:
            return {"error": f"No chat found matching name '{chat_name}'. Please ensure the name is correct or check the chat list."}
        
        # Sort by score descending
        scored_chats.sort(key=lambda x: x[0], reverse=True)
        best_score, best_chat = scored_chats[0]
        
        # Subgroup redirection for COMMUNITY parent groups and LINKED_ANNOUNCEMENT_GROUPs
        group_type = best_chat.get("groupType")
        if group_type in ["COMMUNITY", "LINKED_ANNOUNCEMENT_GROUP"]:
            query_lower = chat_name.lower()
            if "community" not in query_lower and "announcement" not in query_lower:
                parent_id = best_chat["id"] if group_type == "COMMUNITY" else best_chat.get("parentGroup")
                if parent_id:
                    parent_chat = next((ch for ch in chats_result.get("chats", []) if ch.get("id") == parent_id), None)
                    subgroups = (parent_chat.get("joinedSubgroups") or []) if parent_chat else (best_chat.get("joinedSubgroups") or [])
                    subgroup_chats = []
                    for sub_id in subgroups:
                        sub_chat = next((ch for ch in chats_result.get("chats", []) if ch.get("id") == sub_id), None)
                        if sub_chat:
                            subgroup_chats.append(sub_chat)
                    # Find general/discussion group
                    general_chat = next((ch for ch in subgroup_chats if any(word in ch.get("name", "").lower() for word in ["general", "discussion", "chat"])), None)
                    if general_chat:
                        best_chat = general_chat
                        best_score = 100.0 # Override score
        
        chat_id = best_chat["id"]
        print(f"[DEBUG] Resolved chat name '{chat_name}' to ID: {chat_id} (Matched: '{best_chat.get('name')}' with score {best_score:.1f})", file=sys.stderr)

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
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

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
