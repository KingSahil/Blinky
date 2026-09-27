import logging
from typing import List, Dict, Any
from wil.searxng_client import SearXNGClient

LOGGER = logging.getLogger("blinky.retriever")

class Retriever:
    def __init__(self, client: SearXNGClient = None):
        self.client = client or SearXNGClient()

    async def retrieve(self, queries: List[str], categories: List[str]) -> List[Dict[str, Any]]:
        all_results = []
        for q in queries:
            results = await self.client.search_multi(q, categories)
            all_results.extend(results)
            
        # De-duplicate and sort by score again
        merged: Dict[str, Dict[str, Any]] = {}
        for item in all_results:
            url = item.get("url")
            if not url:
                continue
            score = float(item.get("score", 1.0))
            if url in merged:
                merged[url]["score"] = merged[url].get("score", 1.0) + score
            else:
                merged[url] = item
                
        sorted_results = sorted(merged.values(), key=lambda x: x.get("score", 0.0), reverse=True)
        return sorted_results
