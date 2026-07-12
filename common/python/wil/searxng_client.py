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

import os

class SearXNGClient:
    _cached_resolved_url = None

    def __init__(self, base_url: str = None):
        self.configured_url = base_url or os.environ.get("BLINKY_SEARXNG_URL") or "http://127.0.0.1:8888"
        self.base_url = self.configured_url

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json",
        }

    async def _probe_url(self, url: str, timeout: float = 2.5) -> bool:
        try:
            search_url = f"{url.rstrip('/')}/search"
            params = {"q": "test", "format": "json"}
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(search_url, params=params)
                if resp.status_code != 200:
                    return False
                data = resp.json()
                results = data.get("results", [])
                web_results = [
                    r for r in results 
                    if not any(w in r.get("url", "") for w in ["wikipedia.org", "wikidata.org", "wikimedia.org"])
                ]
                return len(web_results) > 0
        except Exception:
            return False

    _resolve_lock = None

    async def _resolve_url(self) -> str:
        if SearXNGClient._resolve_lock is None:
            SearXNGClient._resolve_lock = asyncio.Lock()

        async with SearXNGClient._resolve_lock:
            if SearXNGClient._cached_resolved_url:
                self.base_url = SearXNGClient._cached_resolved_url
                return self.base_url

            # Check configured URL
            if await self._probe_url(self.configured_url, timeout=1.5):
                SearXNGClient._cached_resolved_url = self.configured_url
                self.base_url = self.configured_url
                return self.base_url

            # Try loopback swap alternative
            local_alt = None
            if "127.0.0.1" in self.configured_url:
                local_alt = self.configured_url.replace("127.0.0.1", "localhost")
            elif "localhost" in self.configured_url:
                local_alt = self.configured_url.replace("localhost", "127.0.0.1")

            if local_alt and await self._probe_url(local_alt, timeout=1.5):
                SearXNGClient._cached_resolved_url = local_alt
                self.base_url = local_alt
                return self.base_url

            # Try public fallbacks
            try:
                from wil.pipeline import _PUBLIC_SEARXNG_INSTANCES
                for instance in _PUBLIC_SEARXNG_INSTANCES:
                    if await self._probe_url(instance, timeout=3.0):
                        SearXNGClient._cached_resolved_url = instance
                        self.base_url = instance
                        return self.base_url
            except Exception:
                pass

            self.base_url = self.configured_url
            return self.base_url

    async def search_category(self, query: str, category: str, limit: int = 5) -> List[Dict[str, Any]]:
        # Retry logic: 3 attempts with exponential backoff and dynamic failover
        for attempt in range(3):
            resolved_base = await self._resolve_url()
            url = f"{resolved_base}/search"
            params = {
                "q": query,
                "categories": category,
                "format": "json",
            }
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    response = await client.get(url, params=params, headers=self._get_headers())
                    if response.status_code in [429, 503]:
                        LOGGER.warning(f"SearXNG ({resolved_base}) returned status {response.status_code} for category {category}. Invalidating cached instance and failing over... (attempt {attempt + 1})")
                        SearXNGClient._cached_resolved_url = None
                        await asyncio.sleep(0.1 * (2 ** attempt))
                        continue
                    
                    response.raise_for_status()
                    
                    # Verify content-type
                    content_type = response.headers.get("content-type", "")
                    if "application/json" not in content_type:
                        LOGGER.warning(f"SearXNG response content-type is not JSON: {content_type}")
                        try:
                            data = response.json()
                        except Exception:
                            raise ValueError(f"Expected JSON from SearXNG, got {content_type}")
                    else:
                        data = response.json()
                        
                    results = data.get("results", [])
                    return results[:limit]
            except Exception as e:
                LOGGER.warning(f"Error searching SearXNG ({resolved_base}) category {category}: {e}")
                # Invalidate cache on request/connection errors
                SearXNGClient._cached_resolved_url = None
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
