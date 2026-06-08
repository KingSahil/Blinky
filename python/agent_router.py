import sys
import os
import json
import ast
import re
import asyncio
import subprocess
import requests
from pathlib import Path
from ai.client import ask_text_model

REGISTRY_PATH = Path(__file__).parent / "tools" / "registry.json"
REGISTRY_LOCK = asyncio.Lock()
ROUTE_CACHE = {}

async def load_registry_async():
    async with REGISTRY_LOCK:
        if not REGISTRY_PATH.exists():
            return {}
        try:
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, REGISTRY_PATH.read_text)
            return json.loads(content)
        except Exception:
            return {}

async def save_registry_async(registry):
    async with REGISTRY_LOCK:
        try:
            REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            loop = asyncio.get_running_loop()
            content = json.dumps(registry, indent=2)
            await loop.run_in_executor(None, REGISTRY_PATH.write_text, content)
        except Exception:
            pass


def send_response(request_id, status, data=None, error=None):
    response = {
        "requestId": request_id,
        "status": status,
        "data": data or {},
        "error": error
    }
    print(json.dumps(response), flush=True)

def audit_code(code_str):
    try:
        tree = ast.parse(code_str)
    except Exception as e:
        return False, f"AST parsing failed: {str(e)}"

    forbidden_imports = {"subprocess", "shutil", "os.system", "os.popen", "pty"}
    forbidden_calls = {"exec", "eval", "system", "popen", "spawn"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_imports:
                    return False, f"Forbidden import found: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module in forbidden_imports:
                return False, f"Forbidden import found: {node.module}"
            for alias in node.names:
                if f"{node.module}.{alias.name}" in forbidden_imports:
                    return False, f"Forbidden import found: {node.module}.{alias.name}"
        
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in forbidden_calls:
                    return False, f"Forbidden function call: {node.func.id}"
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in forbidden_calls:
                    return False, f"Forbidden attribute call: {node.func.attr}"

    return True, ""

async def execute_script(filepath, args_json, timeout=30):
    cmd = [sys.executable, str(filepath), json.dumps(args_json)]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return False, "TIMEOUT", "Process execution timed out after 30 seconds"

        stdout_decoded = stdout.decode().strip()
        stderr_decoded = stderr.decode().strip()

        if proc.returncode != 0:
            return False, "CRASH", f"Exit code {proc.returncode}. Stderr: {stderr_decoded}"

        try:
            data = json.loads(stdout_decoded)
            return True, data, ""
        except json.JSONDecodeError:
            return True, {"raw_output": stdout_decoded}, ""

    except Exception as e:
        return False, "SPAWN_ERROR", str(e)

def stream_synthesis_llm(query, tool_output, callback):
    provider = (os.getenv("BLINKY_AI_PROVIDER", "ollama").strip() or "ollama").lower()
    
    prompt = f"""
You are Blinky, a helpful AI assistant.
The user asked: "{query}"

We executed a web browser automation search and gathered this raw data:
{json.dumps(tool_output, indent=2)}

Synthesize a professional, user-friendly final response answering the user's request. Avoid mentioning system internal details (like "Playwright script output"). Give direct details.
"""

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        model = os.getenv("BLINKY_GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct").strip()
        groq_url = os.getenv("BLINKY_GROQ_URL", "https://api.groq.com/openai/v1/chat/completions").strip()
        
        try:
            response = requests.post(
                groq_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True
                },
                stream=True,
                timeout=30
            )
            response.raise_for_status()
            for chunk in response.iter_lines():
                if chunk:
                    line = chunk.decode("utf-8").strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                callback(delta)
                        except Exception:
                            pass
        except Exception as e:
            callback(f"\n[Synthesis Error: {str(e)}]")
    else:
        # Ollama
        ollama_url = os.getenv("BLINKY_OLLAMA_URL", "http://localhost:11434/api/generate").strip()
        model = os.getenv("BLINKY_OLLAMA_MODEL", "gemma4:e4b").strip()
        
        try:
            response = requests.post(
                ollama_url,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": 0.3
                    }
                },
                stream=True,
                timeout=45
            )
            response.raise_for_status()
            for chunk in response.iter_lines():
                if chunk:
                    try:
                        data = json.loads(chunk.decode("utf-8"))
                        delta = data.get("response", "")
                        if delta:
                            callback(delta)
                    except Exception:
                        pass
        except Exception as e:
            callback(f"\n[Synthesis Error: {str(e)}]")

def get_query_signature(query: str) -> str:
    cleaned = query.strip().lower()
    cleaned = re.sub(r"[?!.,;]+", "", cleaned)
    return " ".join(cleaned.split())

def parse_routing_decision(raw_decision: str) -> dict:
    if isinstance(raw_decision, dict):
        return raw_decision
    try:
        return json.loads(raw_decision)
    except Exception:
        pass
    
    # Regex search for JSON block
    match_obj = re.search(r"\{.*\}", str(raw_decision), re.DOTALL)
    if match_obj:
        try:
            return json.loads(match_obj.group(0))
        except Exception:
            pass
            
    # Regex fallback parsing
    decision = {"match": False, "tool_calls": [], "confidence": 0, "reasoning": "Failed to parse json response"}
    
    match_match = re.search(r'"match"\s*:\s*(true|false)', str(raw_decision), re.IGNORECASE)
    if match_match:
        decision["match"] = match_match.group(1).lower() == "true"
        
    conf_match = re.search(r'"confidence"\s*:\s*(\d+)', str(raw_decision))
    if conf_match:
        decision["confidence"] = int(conf_match.group(1))
        
    reason_match = re.search(r'"reasoning"\s*:\s*"([^"]*)"', str(raw_decision))
    if reason_match:
        decision["reasoning"] = reason_match.group(1)
        
    tool_calls_match = re.search(r'"tool_calls"\s*:\s*(\[.*?\])', str(raw_decision), re.DOTALL)
    if tool_calls_match:
        try:
            decision["tool_calls"] = json.loads(tool_calls_match.group(1))
        except Exception:
            dicts = re.findall(r"\{[^}]*\}", tool_calls_match.group(1))
            calls = []
            for d in dicts:
                try:
                    calls.append(json.loads(d))
                except Exception:
                    pass
            decision["tool_calls"] = calls
            
    return decision

async def execute_single_tool_call(tool_call, registry, query, semaphore, request_id):
    tool_name = tool_call.get("tool_name", "")
    arguments = tool_call.get("arguments", {})
    if tool_name not in registry:
        return False, None, f"Tool '{tool_name}' not found in registry"
    
    tool_details = registry[tool_name]
    filepath = Path(__file__).parent / "tools" / f"{tool_name}.py"
    
    # Map arguments
    registered_args = tool_details.get("arguments", [])
    mapped_args = {}
    for arg in registered_args:
        if arg in arguments:
            mapped_args[arg] = arguments[arg]
        elif len(registered_args) == 1:
            val = list(arguments.values())[0] if arguments else query
            mapped_args[arg] = val
        else:
            mapped_args[arg] = query
            
    # Granular Status Reporting
    send_response(request_id, "processing", data={
        "status": "executing_tool",
        "tool_name": tool_name,
        "arguments": mapped_args,
        "message": f"Executing tool '{tool_name}' with arguments {mapped_args}..."
    })
    
    async with semaphore:
        success, result_data, error_details = await execute_script(filepath, mapped_args)
        
    return success, result_data, error_details

async def handle_request(line):
    try:
        req = json.loads(line)
    except Exception as e:
        send_response("unknown", "error", error={"code": "PARSE_ERROR", "message": "Invalid line JSON", "details": str(e)})
        return

    request_id = req.get("requestId", "unknown")
    query = req.get("query", "").strip()

    if not query:
        send_response(request_id, "error", error={"code": "INVALID_QUERY", "message": "Query text cannot be empty", "details": ""})
        return

    send_response(request_id, "processing", data={"message": "Analyzing query and routing..."})

    registry = await load_registry_async()
    
    # 1. Routing Phase
    tools_summary = ""
    for name, details in registry.items():
        tools_summary += f"- Name: {name}\n  Description: {details.get('description', '')}\n  Arguments: {details.get('arguments', [])}\n"

    routing_prompt = f"""
You are the Blinky AI agent router.
Here is a list of registered browser automation tools:
{tools_summary or "No registered tools yet."}

User query: "{query}"

Decide if the user query can be resolved by executing one or more of the registered tools above.
We support executing multiple tools concurrently (either the same tool with different arguments, or different tools) to satisfy the query.
Return a JSON object containing:
1. "match": boolean (true if one or more tools match, false otherwise)
2. "tool_calls": a list of tool call objects. Each object has:
   - "tool_name": string (the name of the matched tool)
   - "arguments": a dictionary of arguments extracted from the user query to pass to the tool
3. "confidence": integer between 0 and 100 representing your confidence level in the match or mismatch
4. "reasoning": string explaining the reasoning for your decision

Example matched response with multiple calls:
{{
  "match": true,
  "tool_calls": [
    {{ "tool_name": "lookup_youtube_stats", "arguments": {{ "channel_name": "@MrBeast" }} }},
    {{ "tool_name": "lookup_youtube_stats", "arguments": {{ "channel_name": "@PewDiePie" }} }}
  ],
  "confidence": 95,
  "reasoning": "The query asks for subscriber stats for MrBeast and PewDiePie, matching two calls to lookup_youtube_stats.",
  "arguments": {{}}
}}

Example unmatched response:
{{
  "match": false,
  "tool_calls": [],
  "confidence": 15,
  "reasoning": "The query asks for the weather, which none of the existing tools can resolve.",
  "arguments": {{}}
}}

Respond ONLY with valid JSON.
"""
    query_sig = get_query_signature(query)
    route_decision = None
    if query_sig in ROUTE_CACHE:
        route_decision = ROUTE_CACHE[query_sig]
    else:
        try:
            raw_decision = ask_text_model(routing_prompt)
            route_decision = parse_routing_decision(raw_decision)
            ROUTE_CACHE[query_sig] = route_decision
        except Exception as e:
            send_response(request_id, "error", error={"code": "LLM_ROUTING_ERROR", "message": "AI routing failed", "details": str(e)})
            return

    match = route_decision.get("match", False)
    confidence = int(route_decision.get("confidence", 0))
    reasoning = route_decision.get("reasoning", "")
    
    # Backward compatibility and extraction
    tool_calls = route_decision.get("tool_calls", [])
    if not tool_calls and route_decision.get("tool_name"):
        tool_calls = [{
            "tool_name": route_decision["tool_name"],
            "arguments": route_decision.get("arguments", {})
        }]

    # Routing confidence threshold check (>= 80)
    routing_confidence_low = False
    if match and confidence < 80:
        match = False
        routing_confidence_low = True

    raw_result = None
    combined_result = None
    new_tool_generated = False
    new_tool_name = None
    new_arguments = None
    
    successful_results = []
    failed_details = []

    if match and tool_calls:
        # Enforce rate-limit and resources: max 3 concurrent executions
        tool_calls = tool_calls[:3]
        
        send_response(request_id, "processing", data={
            "message": f"Routing to {len(tool_calls)} tool call(s) (Confidence: {confidence}%)...",
            "confidence": confidence,
            "reasoning": reasoning
        })
        
        semaphore = asyncio.Semaphore(3)
        tasks = [
            execute_single_tool_call(tc, registry, query, semaphore, request_id)
            for tc in tool_calls
        ]
        
        execution_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for idx, res in enumerate(execution_results):
            if isinstance(res, Exception):
                failed_details.append(f"Tool call {idx} crashed: {str(res)}")
                continue
            success, result_data, error_details = res
            if success:
                successful_results.append(result_data)
            else:
                failed_details.append(f"Tool call {idx} failed: {error_details}")

        # Combine results
        if len(successful_results) == 1:
            combined_result = successful_results[0]
        elif len(successful_results) > 1:
            combined_result = {
                "combined_tool_outputs": successful_results
            }

    # Evaluate sufficiency using sufficiency_checker
    is_sufficient = False
    sufficiency_reason = "No successful tool execution"
    if combined_result:
        from utils.sufficiency_checker import check_sufficiency
        is_sufficient, sufficiency_reason = check_sufficiency(query, combined_result)

    if is_sufficient:
        raw_result = combined_result
    else:
        # 2. Code Generation Phase (Fallback / Unmatched)
        if routing_confidence_low:
            msg = f"No confident match (Confidence: {confidence}%). Generating custom script..."
        else:
            msg = f"Tool execution insufficient or unmatched ({sufficiency_reason}). Generating custom script..."
            
        send_response(request_id, "processing", data={
            "message": msg,
            "confidence": confidence,
            "reasoning": reasoning
        })

        generator_prompt = f"""
You are Blinky's Playwright code generator.
Write a complete, single-file Python script to automate a browser using Playwright to solve this query:
"{query}"
"""
        if combined_result:
            generator_prompt += f"""
Note: We previously tried executing registered tools, but the results were insufficient.
Partial results retrieved: {json.dumps(combined_result, indent=2)}
Reason for insufficiency: {sufficiency_reason}

Please write the custom script targeting specifically the missing details or correcting the insufficiency.
"""

        generator_prompt += """
Standards:
- Use Playwright's async API.
- Run Chromium in headless mode by default.
- Use `try...finally` to guarantee browser closure.
- The script must accept JSON input via `sys.argv[1]` to extract parameters.
- The script MUST output the final retrieved data as a single JSON object to stdout. Print all debugging or log messages to stderr.
- Keep the code highly concise, clean, and avoid verbose comments or redundant logic to ensure the response fits within limits.
- IMPORTANT: Do NOT use fragile Google Shopping-specific selectors (like `div[data-section-title*='Shopping']`). If searching on Google, use general, robust result headers (e.g. `div.g` or `h3`) or query e-commerce sites directly.

Format your output exactly as follows:
TOOL_NAME: <a_descriptive_snake_case_name_relevant_to_the_query>
DESCRIPTION: <a_one_line_description_of_what_this_tool_does>
ARGUMENTS: query
CODE:
```python
# Your full python code here
```
"""
        try:
            provider = (os.getenv("BLINKY_AI_PROVIDER", "ollama").strip() or "ollama").lower()
            if provider == "groq":
                api_key = os.getenv("GROQ_API_KEY", "").strip()
                model = os.getenv("BLINKY_GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct").strip()
                groq_url = os.getenv("BLINKY_GROQ_URL", "https://api.groq.com/openai/v1/chat/completions").strip()
                resp = requests.post(
                    groq_url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "temperature": 0.1,
                        "max_tokens": 3000,
                        "messages": [{"role": "user", "content": generator_prompt}],
                    },
                    timeout=90
                )
                resp.raise_for_status()
                gen_text = resp.json()["choices"][0]["message"]["content"]
            else:
                ollama_url = os.getenv("BLINKY_OLLAMA_URL", "http://localhost:11434/api/generate").strip()
                model = os.getenv("BLINKY_OLLAMA_MODEL", "gemma4:e4b").strip()
                resp = requests.post(
                    ollama_url,
                    json={
                        "model": model,
                        "prompt": generator_prompt,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 4000}
                    },
                    timeout=90
                )
                resp.raise_for_status()
                gen_text = resp.json().get("response", "")
        except Exception as e:
            send_response(request_id, "error", error={"code": "LLM_GENERATION_ERROR", "message": "Failed to generate automation code", "details": str(e)})
            return

        # Parse output fields using regex (robust parsing)
        new_tool_name_match = re.search(r"TOOL_NAME:\s*([a-zA-Z0-9_-]+)", gen_text, re.IGNORECASE)
        if new_tool_name_match:
            new_tool_name = new_tool_name_match.group(1).strip()
        else:
            query_slug = re.sub(r"[^a-zA-Z0-9_]+", "_", query.lower()).strip("_")
            new_tool_name = f"lookup_{query_slug}"[:50]
            if not new_tool_name or new_tool_name == "lookup_":
                new_tool_name = "custom_search_tool"

        new_desc_match = re.search(r"DESCRIPTION:\s*(.*)", gen_text, re.IGNORECASE)
        new_description = new_desc_match.group(1).strip() if new_desc_match else f"Custom automation tool for: {query}"
        
        new_args_match = re.search(r"ARGUMENTS:\s*(.*)", gen_text, re.IGNORECASE)
        if new_args_match:
            raw_args_str = new_args_match.group(1).strip()
            new_arguments = [a.strip() for a in raw_args_str.replace("[", "").replace("]", "").replace("'", "").replace('"', '').split(",") if a.strip()]
        else:
            new_arguments = ["query"]

        new_code = None
        code_match = re.search(r"```python\s*(.*?)\s*```", gen_text, re.DOTALL)
        if code_match:
            new_code = code_match.group(1)
        else:
            code_match = re.search(r"```py\s*(.*?)\s*```", gen_text, re.DOTALL)
            if code_match:
                new_code = code_match.group(1)
            else:
                all_blocks = re.findall(r"```\s*(.*?)\s*```", gen_text, re.DOTALL)
                for block in all_blocks:
                    if "playwright" in block or "import" in block or "async" in block:
                        new_code = block
                        break
                if not new_code and all_blocks:
                    new_code = all_blocks[0]
                
                if not new_code:
                    if "import playwright" in gen_text or "async def " in gen_text:
                        start_idx = gen_text.find("import ")
                        if start_idx == -1:
                            start_idx = gen_text.find("async def ")
                        if start_idx != -1:
                            new_code = gen_text[start_idx:]

        if not new_code or not new_code.strip():
            send_response(request_id, "error", error={"code": "GENERATION_INVALID", "message": "AI generated empty tool or code block", "details": gen_text})
            return

        new_code = new_code.strip()
        
        # Unique staging filename: temp_candidate_{request_id}.py
        temp_tool_name = f"temp_candidate_{request_id}"
        temp_tool_filepath = Path(__file__).parent / "tools" / f"{temp_tool_name}.py"

        # Diagnostic logging of generated code
        from utils.logging import get_logger
        logger = get_logger("blinky.router")
        logger.info(f"Generated custom code for request {request_id}:\n{new_code}")

        # Static Code Audit
        is_safe, audit_msg = audit_code(new_code)
        if not is_safe:
            logger.warning(f"Safety audit rejected request {request_id}. Reason: {audit_msg}")
            send_response(request_id, "error", error={"code": "SAFETY_AUDIT_REJECTED", "message": "Static safety audit rejected the generated script", "details": audit_msg})
            return

        temp_tool_filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_tool_filepath, "w") as f:
            f.write(new_code)

        send_response(request_id, "processing", data={"message": "Verifying custom automation execution..."})

        test_args = {}
        for arg in new_arguments:
            test_args[arg] = query

        success, result_data, error_details = await execute_script(temp_tool_filepath, test_args)

        if success:
            # Move staging file to final file
            new_tool_filepath = Path(__file__).parent / "tools" / f"{new_tool_name}.py"
            try:
                if new_tool_filepath.exists():
                    new_tool_filepath.unlink()
                temp_tool_filepath.rename(new_tool_filepath)
            except Exception:
                with open(new_tool_filepath, "w") as f:
                    f.write(new_code)
                try:
                    temp_tool_filepath.unlink()
                except Exception:
                    pass

            registry[new_tool_name] = {
                "name": new_tool_name,
                "description": new_description,
                "filepath": f"python/tools/{new_tool_name}.py",
                "arguments": new_arguments
            }
            await save_registry_async(registry)
            
            # Combine partial tool results and custom tool results
            if combined_result:
                raw_result = {
                    "partial_tool_results": combined_result,
                    "custom_tool_results": result_data
                }
            else:
                raw_result = result_data
            new_tool_generated = True
        else:
            if temp_tool_filepath.exists():
                try:
                    temp_tool_filepath.unlink()
                except Exception:
                    pass
            
            # If fallback tool also failed and we have partial tools result, use them, otherwise return error
            if combined_result:
                raw_result = combined_result
            else:
                send_response(request_id, "error", error={"code": "VERIFICATION_FAILED", "message": "Generated tool failed verification run", "details": error_details})
                return

    # 3. Real-time Text Streaming Synthesis Phase
    if raw_result:
        send_response(request_id, "processing", data={"message": "", "is_chunk": True})
        
        full_synthesis = []
        def chunk_callback(chunk):
            full_synthesis.append(chunk)
            send_response(request_id, "processing", data={"message": chunk, "is_chunk": True})

        # Run block in threadpool executor to avoid blocking asyncio loop
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, stream_synthesis_llm, query, raw_result, chunk_callback)

        final_text = "".join(full_synthesis)
        send_response(request_id, "success", data={"response": final_text})

        # Launch background tool generalization loop after success response has been sent to client
        if new_tool_generated:
            from utils.generalizer import generalize_tool
            asyncio.create_task(generalize_tool(
                new_tool_name,
                query,
                new_arguments,
                REGISTRY_PATH,
                audit_code
            ))


async def main():
    sys.stdout.reconfigure(line_buffering=True)
    
    # Startup Generalization Check for Legacy/Specific Tools
    try:
        registry = await load_registry_async()
        # Collect all tool names that are already generalized to skip them
        generalized_names = set()
        for name, details in registry.items():
            if details.get("status") == "generalized":
                generalized_names.add(name)
        
        for name, details in list(registry.items()):
            # Skip tools that are already generalized, or known static tools
            if name in generalized_names:
                continue
            if name in ("lookup_youtube_stats", "find_crypto_price"):
                continue
            from utils.generalizer import generalize_tool
            dummy_query = details.get("description", name)
            asyncio.create_task(generalize_tool(
                name,
                dummy_query,
                details.get("arguments", ["query"]),
                REGISTRY_PATH,
                audit_code
            ))
    except Exception:
        pass

    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    tasks = []
    while True:
        line_bytes = await reader.readline()
        if not line_bytes:
            break
        line = line_bytes.decode().strip()
        if not line:
            continue
        t = asyncio.create_task(handle_request(line))
        tasks.append(t)
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())
