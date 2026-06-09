import json
import logging
from typing import Dict, Any, List
from ai.client import ask_text_model

LOGGER = logging.getLogger("blinky.planner")

class QueryPlanner:
    def plan(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        prompt = f"""
You are the Blinky Web Intelligence Layer Query Planner.
Your task is to analyze the user's query and formulate a search plan.

We support four specialized Search engines (categories):
- `it`: For code errors, programming language syntax, API documentation, tech libraries.
- `news`: For recent current events, public announcements, dates, or time-sensitive events.
- `science`: For academic, mathematics, biology, chemical formulas, physics, research.
- `general`: For anything else (general knowledge, definitions, history, summaries, locations).

User query: "{query}"

Analyze if this query actually needs an external web search to be answered (e.g., if it requires current/fresh data, factual lookups, external information) or if it's a general greeting, local question, or conversational logic that doesn't need external data.

Respond ONLY with a JSON object in this format:
{{
  "needs_web_search": true or false,
  "search_queries": ["list of refined search terms to search"],
  "categories": ["general", "it", "news", "science"],
  "reasoning": "explanation for the decision"
}}
"""
        try:
            payload = ask_text_model(prompt)
            if not isinstance(payload, dict):
                # Fallback if parsing failed
                return {
                    "needs_web_search": True,
                    "search_queries": [query],
                    "categories": ["general"],
                    "reasoning": "Failed to parse json decision, defaulting to general search"
                }
            
            # Ensure safe fields
            needs_search = bool(payload.get("needs_web_search", True))
            search_queries = payload.get("search_queries", [query])
            if not isinstance(search_queries, list) or not search_queries:
                search_queries = [query]
                
            categories = payload.get("categories", ["general"])
            if not isinstance(categories, list) or not categories:
                categories = ["general"]
                
            # Keep only valid categories
            valid_cats = {"general", "it", "news", "science"}
            categories = [c for c in categories if c in valid_cats]
            if not categories:
                categories = ["general"]
                
            return {
                "needs_web_search": needs_search,
                "search_queries": search_queries,
                "categories": categories,
                "reasoning": payload.get("reasoning", "")
            }
        except Exception as e:
            LOGGER.error(f"Error planning query: {e}")
            return {
                "needs_web_search": True,
                "search_queries": [query],
                "categories": ["general"],
                "reasoning": f"Exception in planner: {e}"
            }
