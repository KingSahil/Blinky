import json
import re
from urllib.parse import quote_plus

from ai.client import ask_text_model
from browser_controller import get_browser_controller


SAFE_BROWSER_ACTIONS = {"open_url", "web_search", "site_search"}


def parse_browser_plan(raw_plan) -> dict:
    if isinstance(raw_plan, dict):
        plan = raw_plan
    else:
        plan = _parse_json_object(str(raw_plan))

    if not plan:
        return _no_match("Could not parse browser plan JSON")

    action = str(plan.get("action", "")).strip().lower()
    if action not in SAFE_BROWSER_ACTIONS:
        return _no_match(f"Unsupported browser action: {action or 'missing'}")

    confidence = _safe_int(plan.get("confidence", 0))
    if not plan.get("match") or confidence < 70:
        return _no_match(str(plan.get("reasoning", "Low confidence browser plan")))

    normalized = {
        "match": True,
        "action": action,
        "confidence": confidence,
    }

    if action == "site_search":
        site = _clean_site(plan.get("site", ""))
        query = _clean_text(plan.get("query", ""))
        if not site or not query:
            return _no_match("Site search requires both site and query")
        normalized["site"] = site
        normalized["query"] = query
        return normalized

    if action == "web_search":
        query = _clean_text(plan.get("query", ""))
        if not query:
            return _no_match("Web search requires query")
        normalized["query"] = query
        return normalized

    url = str(plan.get("url", "")).strip()
    if not re.fullmatch(r"https?://[^\s]+", url):
        return _no_match("Open URL requires a valid http(s) URL")
    normalized["url"] = url
    normalized["label"] = _clean_text(plan.get("label", "")) or url
    return normalized


def plan_browser_action(query: str) -> dict:
    prompt = f"""
You are Blinky's browser action planner.

Convert the user's request into ONE safe browser action. Do not write code.

Allowed actions:
- site_search: search for a user query on or about a named website/app/store.
- web_search: search the web for the query.
- open_url: open a known direct URL.

User request: "{query}"

Return ONLY valid JSON:
{{
  "match": true,
  "action": "site_search",
  "site": "blinkit",
  "query": "gaming chair",
  "confidence": 0-100,
  "reasoning": "short reason"
}}

If the request is not a browser task, return:
{{
  "match": false,
  "action": "",
  "confidence": 0,
  "reasoning": "short reason"
}}
"""
    return parse_browser_plan(ask_text_model(prompt, max_tokens=350))


async def run_browser_plan(plan: dict, controller=None) -> dict:
    controller = controller or get_browser_controller()
    action = plan["action"]

    if action == "site_search":
        site = plan["site"]
        query = plan["query"]
        url = f"https://www.google.com/search?q={quote_plus(f'site:{site} {query}')}"
        result = await controller.open_url(url)
        return {
            "response": f"Opened web search for {query} on {site}.",
            "url": result.get("url", url),
            "title": result.get("title", ""),
        }

    if action == "web_search":
        query = plan["query"]
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        result = await controller.open_url(url)
        return {
            "response": f"Opened web search for {query}.",
            "url": result.get("url", url),
            "title": result.get("title", ""),
        }

    url = plan["url"]
    result = await controller.open_url(url)
    return {
        "response": f"Opened {plan.get('label', url)}.",
        "url": result.get("url", url),
        "title": result.get("title", ""),
    }


def _parse_json_object(raw: str) -> dict:
    try:
        return json.loads(raw)
    except Exception:
        pass

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def _no_match(reasoning: str) -> dict:
    return {
        "match": False,
        "action": "",
        "confidence": 0,
        "reasoning": reasoning,
    }


def _safe_int(value) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _clean_text(value) -> str:
    return " ".join(str(value).strip(" .,!?:;\"'`()[]").split())


def _clean_site(value) -> str:
    site = _clean_text(value).lower()
    site = re.sub(r"^https?://", "", site)
    site = site.strip("/")
    return site
