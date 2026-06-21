import asyncio
import logging
import random
import sys
from typing import List, Dict, Any
import httpx

LOGGER = logging.getLogger("blinky.searxng_client")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

class SearXNGClient:
    def __init__(self, base_url: str = None):
        self.base_url = base_url or "http://localhost:8888"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json",
        }

    async def search_category(self, query: str, category: str, limit: int = 5) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/search"
        params = {
            "q": query,
            "categories": category,
            "format": "json",
        }
        
        # Retry logic: 3 attempts with exponential backoff for 503 or request errors
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    response = await client.get(url, params=params, headers=self._get_headers())
                    if response.status_code == 503:
                        LOGGER.warning(f"SearXNG returned 503 for category {category}, retrying... (attempt {attempt + 1})")
                        await asyncio.sleep(0.2 * (2 ** attempt))
                        continue
                    
                    response.raise_for_status()
                    
                    # Verify content-type
                    content_type = response.headers.get("content-type", "")
                    if "application/json" not in content_type:
                        LOGGER.warning(f"SearXNG response content-type is not JSON: {content_type}")
                        # If we can parse as json anyway, do it
                        try:
                            data = response.json()
                        except Exception:
                            raise ValueError(f"Expected JSON from SearXNG, got {content_type}")
                    else:
                        data = response.json()
                        
                    results = data.get("results", [])
                    return results[:limit]
            except Exception as e:
                LOGGER.warning(f"Error searching SearXNG category {category}: {e}")
                if attempt == 2:
                    break
                await asyncio.sleep(0.1 * (2 ** attempt))
        return []

    async def search_multi(self, query: str, categories: List[str], limit_per_category: int = 5) -> List[Dict[str, Any]]:
        tasks = []
        for cat in categories:
            tasks.append(self.search_category(query, cat, limit_per_category))
        
        # Concurrent execution with a bounded timeout that still allows
        # freshly-started local SearXNG containers to answer.
        try:
            results_lists = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=12.0)
        except asyncio.TimeoutError:
            LOGGER.warning("SearXNG search_multi timed out after 12 seconds.")
            # Gather whatever completed if possible (can't easily do with wait_for directly unless we shield)
            results_lists = []
            
        merged: Dict[str, Dict[str, Any]] = {}
        for res in results_lists:
            if isinstance(res, list):
                for item in res:
                    url = item.get("url")
                    if not url:
                        continue
                    # Deduplicate URLs while merging results, summing and scaling relevance scores
                    score = float(item.get("score", 1.0))
                    if url in merged:
                        merged[url]["score"] = merged[url].get("score", 1.0) + score
                        # Merge other keys if missing
                        for key in ["title", "content", "engines", "category"]:
                            if key not in merged[url] and key in item:
                                merged[url][key] = item[key]
                    else:
                        merged[url] = item
                        
        sorted_results = sorted(merged.values(), key=lambda x: x.get("score", 0.0), reverse=True)
        return sorted_results
