import json
import re
from typing import Any, Tuple
from ai.client import ask_text_model

def check_sufficiency(query: str, tool_outputs: Any) -> Tuple[bool, str]:
    """
    Checks if the tool outputs sufficiently answer the user query.
    First runs a fast heuristic check (empty, error, or not found patterns).
    If heuristics pass, invokes an LLM sufficiency audit.
    """
    if tool_outputs is None:
        return False, "Tool output is None"

    # Fast heuristic checks
    if isinstance(tool_outputs, str):
        cleaned = tool_outputs.strip()
        if not cleaned:
            return False, "Tool output is an empty string"
        
        # Check common error/no-results patterns (case insensitive)
        lower_cleaned = cleaned.lower()
        heuristics = [
            "no results", "not found", "404", "error", "no matches", 
            "nothing found", "could not find", "unable to find", 
            "failed to fetch", "empty response", "no search results"
        ]
        for pattern in heuristics:
            if pattern in lower_cleaned:
                return False, f"Heuristic matches failure pattern: '{pattern}'"

    elif isinstance(tool_outputs, (dict, list)):
        serialized = json.dumps(tool_outputs)
        if not tool_outputs or len(serialized.strip()) <= 4:
            return False, "Tool output is empty dict/list/json"
        
        # Check patterns in serialized JSON
        lower_serialized = serialized.lower()
        heuristics = [
            "not found", "error", "no results", "no matches", "failed"
        ]
        for pattern in heuristics:
            if pattern in lower_serialized:
                # We can trigger LLM validation or just return False. Let's trigger LLM validation for keyword matches in structure,
                # or return False if it looks like a clear empty/error structure.
                if "error" in lower_serialized and len(serialized) < 150:
                    return False, f"Heuristic matches error/failure in response: {serialized}"

    # Verify budget/price constraint representation if requested
    query_lower = query.lower()
    has_price_request = any(k in query_lower for k in ["under", "below", "price", "budget", "cost", "rupees", "rs.", "₹", "inr"])
    if has_price_request:
        output_str = tool_outputs if isinstance(tool_outputs, str) else json.dumps(tool_outputs)
        has_prices = any(k in output_str for k in ["Rs.", "₹", "Rs", "rupees", "INR"]) or re.search(r'\b\d{3,5}\b', output_str)
        if not has_prices:
            return False, "Query specifies a price or budget limit, but the response does not contain any prices/numbers to verify."


    # LLM Sufficiency Audit
    prompt = f"""
You are Blinky's Quality Sufficiency Auditor.
Evaluate if the collected tool execution results below sufficiently answer the user's query.

User Query: "{query}"
Tool Execution Results:
{json.dumps(tool_outputs, indent=2) if not isinstance(tool_outputs, str) else tool_outputs}

Decide if the results are sufficient.
Guidelines for sufficiency:
- Be lenient. If the query asks for info, recommendations, prices, or lists of products, and the results contain concrete product listings (names, prices, and links), mark it as sufficient ("sufficient": true).
- Do NOT require detailed descriptions, reviews, or specifications unless the user query explicitly demands deep specs or reviews.
- Only mark as false ("sufficient": false) if the results are completely empty, irrelevant, contain only error messages, or completely fail to match the query.

Return a JSON object containing:
1. "sufficient": boolean
2. "reasoning": string explaining your decision

Respond ONLY with valid JSON.
"""
    try:
        raw_decision = ask_text_model(prompt, max_tokens=200)
        if isinstance(raw_decision, dict):
            decision = raw_decision
        else:
            try:
                decision = json.loads(raw_decision)
            except Exception:
                match_obj = re.search(r"\{.*\}", str(raw_decision), re.DOTALL)
                if match_obj:
                    decision = json.loads(match_obj.group(0))
                else:
                    decision = {"sufficient": True, "reasoning": "Failed to parse sufficiency auditor response, assuming sufficient"}
        
        sufficient = decision.get("sufficient", True)
        reason = decision.get("reasoning", "LLM Audited")
        return sufficient, reason
    except Exception as e:
        # If audit fails, default to True to avoid infinite loops, or False to be safe.
        # Defaulting to True to be resilient, but logging the error.
        return True, f"Sufficiency audit failed: {str(e)}"
