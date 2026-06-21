import sys
import os
import json
import asyncio
import shutil
import re
from pathlib import Path
from ai.client import ask_text_model

# Logger
from utils.logging import get_logger
LOGGER = get_logger("blinky.generalizer")

# Registry Lock (to be shared or local)
REGISTRY_LOCK = asyncio.Lock()

async def read_registry_safe(registry_path: Path) -> dict:
    async with REGISTRY_LOCK:
        if not registry_path.exists():
            return {}
        try:
            # Run blocking I/O in thread pool
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, registry_path.read_text)
            return json.loads(content)
        except Exception as e:
            LOGGER.error(f"Error reading registry: {e}")
            return {}

async def write_registry_safe(registry_path: Path, registry: dict):
    async with REGISTRY_LOCK:
        try:
            loop = asyncio.get_running_loop()
            content = json.dumps(registry, indent=2)
            await loop.run_in_executor(None, registry_path.write_text, content)
        except Exception as e:
            LOGGER.error(f"Error writing registry: {e}")

async def run_verification_script(filepath: Path, args_json: dict, timeout=30) -> tuple[bool, str]:
    cmd = [sys.executable, str(filepath), json.dumps(args_json)]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return False, "Verification timed out"

        stdout_decoded = stdout.decode().strip()
        stderr_decoded = stderr.decode().strip()

        if proc.returncode != 0:
            return False, f"Exit code {proc.returncode}. Stderr: {stderr_decoded}"
        
        # Check if stdout contains valid JSON
        try:
            json.loads(stdout_decoded)
            return True, ""
        except json.JSONDecodeError:
            return True, f"Non-JSON output (warning): {stdout_decoded}"
    except Exception as e:
        return False, str(e)

def parse_llm_json(response_text: str) -> dict:
    """Robust parser for LLM json output."""
    if isinstance(response_text, dict):
        return response_text
    try:
        return json.loads(response_text)
    except Exception:
        # Fallback to regex extraction
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    raise ValueError("Failed to parse LLM response as JSON")

async def generalize_tool(
    original_tool_name: str,
    original_query: str,
    original_arguments: list[str],
    registry_path: Path,
    audit_func
):
    """
    Evaluates, rewrites, and verifies a generalized tool module in the background.
    """
    LOGGER.info(f"Background generalization started for tool '{original_tool_name}' (query: '{original_query}')")
    
    # Load original registry & file
    registry = await read_registry_safe(registry_path)
    tool_details = registry.get(original_tool_name)
    if not tool_details:
        LOGGER.warning(f"Tool {original_tool_name} not found in registry. Aborting generalization.")
        return

    original_filepath = registry_path.parent / f"{original_tool_name}.py"
    if not original_filepath.exists():
        LOGGER.warning(f"File {original_filepath} does not exist. Aborting.")
        return

    try:
        loop = asyncio.get_running_loop()
        code_content = await loop.run_in_executor(None, original_filepath.read_text)
    except Exception as e:
        LOGGER.error(f"Failed to read original code: {e}")
        return

    # Ask the LLM if generalization is viable, and to rewrite the code if it is.
    generalizer_prompt = f"""
You are Blinky's Tool Generalization Assistant.
Your task is to analyze a highly specific browser automation tool script and generalize it.

Specific Tool Name: {original_tool_name}
Description: {tool_details.get('description', '')}
Arguments: {original_arguments}
Original Query: {original_query}

Original Code:
```python
{code_content}
```

Please analyze if this tool can be generalized (e.g. parameterizing the query string to handle any entity of the same category, like people, stock tickers, or cryptos).
If yes:
1. Come up with a generalized name (e.g. `lookup_wikipedia_person` instead of `lookup_mandela_info`). Use snake_case.
2. Formulate a new generalized description.
3. List the required argument key(s) (e.g. `["person_name"]` instead of `["query"]`).
4. Provide a test argument dictionary with a DIFFERENT entity/value (e.g. `{{"person_name": "Albert Einstein"}}` if original query was Nelson Mandela) to verify correct parameter usage.
5. Rewrite the python code to extract and use these arguments dynamically (e.g. `input_data.get("person_name")`). Keep all browser automation, error handling, audit-friendliness, and output formatting intact. Ensure the code is complete and syntax-valid.

Return your decision in the following JSON format:
{{
  "can_generalize": true,
  "generalized_name": "lookup_wikipedia_person",
  "description": "Search about any person on Wikipedia and return page info",
  "arguments": ["person_name"],
  "test_arguments": {{
    "person_name": "Albert Einstein"
  }},
  "code": "REWRITTEN_FULL_PYTHON_CODE"
}}

If generalization is not viable, return:
{{
  "can_generalize": false
}}

Respond ONLY with valid JSON.
"""

    try:
        # Use ask_text_model (will restrict tokens to 1500 to avoid runaway tokens)
        response = ask_text_model(generalizer_prompt, max_tokens=1500)
        decision = parse_llm_json(response)
    except Exception as e:
        LOGGER.error(f"LLM call for generalization failed: {e}")
        return

    if not decision.get("can_generalize"):
        LOGGER.info(f"LLM decided tool '{original_tool_name}' cannot be generalized.")
        return

    gen_name = decision.get("generalized_name", "").strip()
    gen_desc = decision.get("description", "").strip()
    gen_args = decision.get("arguments", [])
    test_args = decision.get("test_arguments", {})
    gen_code = decision.get("code", "")

    if not gen_name or not gen_code:
        LOGGER.error("Generalization decision missing critical fields.")
        return

    # Let's ensure temp candidate path
    temp_filepath = registry_path.parent / "temp_candidate.py"
    final_filepath = registry_path.parent / f"{gen_name}.py"

    # Static audit of rewritten code
    is_safe, audit_msg = audit_func(gen_code)
    if not is_safe:
        LOGGER.warning(f"Generalization static audit failed: {audit_msg}")
        return

    try:
        # Write to temp file
        await loop.run_in_executor(None, temp_filepath.write_text, gen_code)
        
        # Verify script with different test argument
        success, err_msg = await run_verification_script(temp_filepath, test_args)
        if success:
            LOGGER.info(f"Verification of generalized tool '{gen_name}' succeeded!")
            
            # Atomic update of registry & rename temp file to final destination
            registry = await read_registry_safe(registry_path)
            
            # Register new tool
            registry[gen_name] = {
                "name": gen_name,
                "description": gen_desc,
                "filepath": f"common/python/tools/{gen_name}.py",
                "arguments": gen_args,
                "status": "generalized",
                "verification_args": test_args
            }
            
            # Remove original tool
            if original_tool_name in registry:
                del registry[original_tool_name]
            
            await write_registry_safe(registry_path, registry)
            
            # Move temp to final
            if final_filepath.exists():
                await loop.run_in_executor(None, final_filepath.unlink)
            await loop.run_in_executor(None, shutil.move, str(temp_filepath), str(final_filepath))
            
            # Delete original specific file
            if original_filepath.exists() and original_filepath != final_filepath:
                await loop.run_in_executor(None, original_filepath.unlink)
                
            LOGGER.info(f"Successfully registered and cleaned up. Generalized tool '{gen_name}' is ready.")
        else:
            LOGGER.warning(f"Verification of generalized tool '{gen_name}' failed: {err_msg}")
            # Discard and clean up temp file
            if temp_filepath.exists():
                await loop.run_in_executor(None, temp_filepath.unlink)
    except Exception as e:
        LOGGER.error(f"Error during generalization verification/saving: {e}")
        if temp_filepath.exists():
            try:
                await loop.run_in_executor(None, temp_filepath.unlink)
            except Exception:
                pass
