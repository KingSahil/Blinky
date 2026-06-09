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
    
    # Format and prune the raw tool output to prevent context window overflow
    if isinstance(tool_output, dict) and "products" in tool_output:
        products = tool_output["products"][:12]  # Limit to top 12 relevant items
        formatted_data = ""
        for idx, p in enumerate(products):
            formatted_data += f"{idx+1}. Product Name: {p.get('name')}\n   Price: {p.get('price')}\n   Link: {p.get('link')}\n   Source: {p.get('source')}\n\n"
    else:
        # Fallback to general JSON format if not a products dictionary
        formatted_data = json.dumps(tool_output, indent=2)[:4000]

    prompt = f"""
You are Blinky, a helpful AI assistant.
The user asked: "{query}"

We gathered this product data from e-commerce sites:
{formatted_data}

Instructions:
1. List ONLY the actual specific products from the data above that match the user's query.
2. For each product, you MUST output it in this exact format:
   * **[Product Name]** - [Price] - [[Link to Product]]([Exact Link URL])
3. Do NOT invent or list other product categories (like keyboards, headsets, controllers) if they are not in the data above.
4. Rely strictly on the gathered e-commerce data. If a product is not listed above, do not recommend it.
5. Keep your tone direct and friendly. Do NOT use placeholders like example.com. Use the exact URLs from the data.
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

def post_process_synthesis(text: str, tool_output) -> str:
    if not isinstance(tool_output, dict) or "products" not in tool_output:
        return text
        
    products = tool_output["products"][:12]
    
    # Replace example.com links
    for idx, p in enumerate(products):
        real_link = p.get("link", "")
        real_name = p.get("name", "")
        if not real_link:
            continue
            
        patterns = [
            rf'https?://example\.com/product/?{idx+1}\b',
            rf'example\.com/product/?{idx+1}\b',
        ]
        for pat in patterns:
            text = re.sub(pat, real_link, text)
            
        text = text.replace(f"Product {idx+1}", real_name)
        text = text.replace(f"product {idx+1}", real_name)

    # General placeholders replacement
    amazon_products = [p for p in products if "amazon" in p.get("source", "").lower()]
    flipkart_products = [p for p in products if "flipkart" in p.get("source", "").lower()]
    
    if amazon_products and "[Amazon Link]" in text:
        text = text.replace("[Amazon Link]", f"[Amazon Link]({amazon_products[0].get('link')})")
    if flipkart_products and "[Flipkart Link]" in text:
        text = text.replace("[Flipkart Link]", f"[Flipkart Link]({flipkart_products[0].get('link')})")

    # Generic title mapping based on link presence
    lines = text.split("\n")
    for i, line in enumerate(lines):
        for p in products:
            real_link = p.get("link", "")
            real_name = p.get("name", "")
            if real_link and real_link in line:
                generic_titles = ["Cosmic Byte Gaming Mouse", "Cosmic Byte mouse", "gaming mouse", "Gaming Mouse"]
                for gt in generic_titles:
                    if gt in line and real_name not in line:
                        lines[i] = line.replace(gt, f"**{real_name}**", 1)
                        break
    text = "\n".join(lines)

    # Clean up any lines that contain generic N/A placeholders or empty headers
    lines = text.split("\n")
    cleaned_lines = []
    for i, line in enumerate(lines):
        # If it ends with a colon, check if it's an empty header
        if line.strip().endswith(":"):
            has_items = False
            for j in range(i + 1, len(lines)):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                if next_line.endswith(":"):
                    break
                if next_line.startswith(("-", "*", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "0.")):
                    if "Price (N/A)" in next_line or "[Link]" in next_line or "N/A" in next_line:
                        continue
                    has_items = True
                    break
                break
            
            lower_line = line.lower()
            if not has_items and any(w in lower_line for w in ["available", "recommend", "mice", "mouse", "list", "result"]):
                continue

        if "Price (N/A)" in line or "[Link]" in line:
            continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines).strip()

    # If the LLM failed to output the links, construct a verified Markdown table and append it
    has_real_links = any(p.get("link", "") in text for p in products)
    if not has_real_links:
        table_md = "\n### 🛒 Verified Product Recommendations\n\n"
        table_md += "| Product Name | Price | Link | Source |\n"
        table_md += "| :--- | :--- | :--- | :--- |\n"
        
        valid_count = 0
        for p in products:
            name = p.get("name", "")
            price = p.get("price", "")
            link = p.get("link", "")
            source = p.get("source", "")
            if name and price and link:
                table_md += f"| {name} | {price} | [View Product]({link}) | {source} |\n"
                valid_count += 1
                if valid_count >= 8:
                    break
        table_md += "\n"
        text = text + "\n" + table_md

    return text

async def run_query_pipeline(
    query: str,
    web_search_enabled: bool,
    conversation_history: list = None,
    on_status = None,
    on_chunk = None
) -> str:
    new_tool_generated = False
    new_tool_name = None
    new_arguments = None
    raw_result = None

    if web_search_enabled:
        from wil.pipeline import WILPipeline
        pipeline = WILPipeline()
        def on_wil_status(phase: str, data: dict):
            if on_status:
                on_status({
                    "status": f"wil_{phase}",
                    "message": data.get("message", f"WIL Stage: {phase}")
                })
        try:
            wil_res = await pipeline.run(
                query=query,
                conversation_history=conversation_history,
                on_status=on_wil_status,
                on_chunk=on_chunk
            )
            from utils.sufficiency_checker import check_sufficiency
            is_sufficient, reason = check_sufficiency(query, wil_res["synthesized_response"])
            if is_sufficient:
                return wil_res["synthesized_response"]
            else:
                if on_status:
                    on_status({
                        "status": "wil_retrying",
                        "message": f"Web search results insufficient ({reason}). Retrying with toolkits..."
                    })
        except Exception as e:
            if on_status:
                on_status({
                    "status": "wil_error",
                    "message": f"WIL search encountered error: {str(e)}. Retrying with toolkits..."
                })

    # Toolkit & Code Gen Fallback/Direct
    if on_status:
        on_status({"message": "Analyzing query and routing..."})

    registry = await load_registry_async()
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
            raise RuntimeError(f"AI routing failed: {str(e)}")

    match = route_decision.get("match", False)
    confidence = int(route_decision.get("confidence", 0))
    reasoning = route_decision.get("reasoning", "")
    
    tool_calls = route_decision.get("tool_calls", [])
    if not tool_calls and route_decision.get("tool_name"):
        tool_calls = [{
            "tool_name": route_decision["tool_name"],
            "arguments": route_decision.get("arguments", {})
        }]

    routing_confidence_low = False
    if match and confidence < 80:
        match = False
        routing_confidence_low = True

    combined_result = None
    successful_results = []
    failed_details = []

    if match and tool_calls:
        tool_calls = tool_calls[:3]
        if on_status:
            on_status({
                "message": f"Routing to {len(tool_calls)} tool call(s) (Confidence: {confidence}%)...",
                "confidence": confidence,
                "reasoning": reasoning
            })
        
        semaphore = asyncio.Semaphore(3)
        
        async def exec_tc(tc):
            t_name = tc.get("tool_name", "")
            t_args = tc.get("arguments", {})
            if t_name not in registry:
                return False, None, f"Tool '{t_name}' not found in registry"
            t_details = registry[t_name]
            filepath = Path(__file__).parent / "tools" / f"{t_name}.py"
            reg_args = t_details.get("arguments", [])
            mapped_args = {}
            for arg in reg_args:
                if arg in t_args:
                    mapped_args[arg] = t_args[arg]
                elif len(reg_args) == 1:
                    val = list(t_args.values())[0] if t_args else query
                    mapped_args[arg] = val
                else:
                    mapped_args[arg] = query
            if on_status:
                on_status({
                    "status": "executing_tool",
                    "tool_name": t_name,
                    "arguments": mapped_args,
                    "message": f"Executing tool '{t_name}' with arguments {mapped_args}..."
                })
            async with semaphore:
                success, res_data, err_details = await execute_script(filepath, mapped_args)
            return success, res_data, err_details

        tasks = [exec_tc(tc) for tc in tool_calls]
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

        if len(successful_results) == 1:
            combined_result = successful_results[0]
        elif len(successful_results) > 1:
            combined_result = {"combined_tool_outputs": successful_results}

    is_sufficient = False
    sufficiency_reason = "No successful tool execution"
    if combined_result:
        from utils.sufficiency_checker import check_sufficiency
        is_sufficient, reason = check_sufficiency(query, combined_result)
        sufficiency_reason = reason

    if is_sufficient:
        raw_result = combined_result
    else:
        if routing_confidence_low:
            msg = f"No confident match (Confidence: {confidence}%). Generating custom script..."
        else:
            msg = f"Tool execution insufficient or unmatched ({sufficiency_reason}). Generating custom script..."
        if on_status:
            on_status({
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
            raise RuntimeError(f"Failed to generate automation code: {str(e)}")

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

        if not new_code or not new_code.strip():
            raise RuntimeError("AI generated empty tool or code block")

        new_code = new_code.strip()
        import uuid
        temp_tool_name = f"temp_candidate_{uuid.uuid4().hex}"
        temp_tool_filepath = Path(__file__).parent / "tools" / f"{temp_tool_name}.py"

        is_safe, audit_msg = audit_code(new_code)
        if not is_safe:
            raise RuntimeError(f"Static safety audit rejected: {audit_msg}")

        temp_tool_filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_tool_filepath, "w") as f:
            f.write(new_code)

        if on_status:
            on_status({"message": "Verifying custom automation execution..."})

        test_args = {}
        for arg in new_arguments:
            test_args[arg] = query

        success, result_data, error_details = await execute_script(temp_tool_filepath, test_args)

        if success:
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
            
            if combined_result:
                raw_result = combined_result
            else:
                raise RuntimeError(f"Generated tool failed verification: {error_details}")

    if raw_result:
        full_synthesis = []
        def chunk_callback(chunk):
            full_synthesis.append(chunk)
            if on_chunk:
                on_chunk(chunk)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, stream_synthesis_llm, query, raw_result, chunk_callback)
        
        if new_tool_generated:
            from utils.generalizer import generalize_tool
            asyncio.create_task(generalize_tool(
                new_tool_name,
                query,
                new_arguments,
                REGISTRY_PATH,
                audit_code
            ))
        synthesized_text = "".join(full_synthesis)
        return post_process_synthesis(synthesized_text, raw_result)
    
    return "No search results could be synthesized."


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

    web_search_enabled = bool(req.get("webSearchEnabled", False) or req.get("web_search_enabled", False))

    def on_status(status_or_data, message=None):
        if isinstance(status_or_data, dict):
            send_response(request_id, "processing", data=status_or_data)
        else:
            send_response(request_id, "processing", data={"status": status_or_data, "message": message})
        
    def on_chunk(chunk):
        send_response(request_id, "processing", data={"message": chunk, "is_chunk": True})

    try:
        final_response = await run_query_pipeline(
            query=query,
            web_search_enabled=web_search_enabled,
            conversation_history=req.get("conversation_history"),
            on_status=on_status,
            on_chunk=on_chunk
        )
        send_response(request_id, "success", data={"response": final_response})
    except Exception as e:
        send_response(request_id, "error", error={"code": "PIPELINE_ERROR", "message": str(e), "details": ""})


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
