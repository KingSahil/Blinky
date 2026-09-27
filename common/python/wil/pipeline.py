import logging
import os
import re
from typing import Dict, Any, List, Callable, Optional
import httpx
from wil.planner import QueryPlanner
from wil.searxng_client import SearXNGClient
from wil.retriever import Retriever
from wil.acquirer import Acquirer
from wil.processor import ContentProcessor
from wil.reasoner import Reasoner

LOGGER = logging.getLogger("blinky.pipeline")

_PUBLIC_SEARXNG_INSTANCES = [
    "https://etsi.me",
    "https://grep.vim.wtf",
    "https://baresearch.org",
    "https://searx.be",
    "https://paulgo.io",
    "https://priv.au",
    "https://searx.work",
    "https://searx.priv.at",
    "https://failsearx.culturanerd.it",
]

SOURCE_SECTION_RE = re.compile(r"\n+\s*(?:Sources|References):\s*\n[\s\S]*$", re.IGNORECASE)

class WILPipeline:
    def __init__(self, base_url: str = None):
        # Priority: explicit arg → env var → local Docker → None (auto-discover)
        self.searxng_url = (
            base_url
            or os.environ.get("BLINKY_SEARXNG_URL")
            or "http://127.0.0.1:8888"
        )
        self._active_url: Optional[str] = None  # resolved after first health-check
        self.planner = QueryPlanner()
        self.client = SearXNGClient(self.searxng_url)
        self.retriever = Retriever(self.client)
        self.acquirer = Acquirer()
        self.processor = ContentProcessor()
        self.reasoner = Reasoner()

    def fallback_summary(self, query: str, sources: List[Dict[str, Any]]) -> str:
        if not sources:
            return "I could not find enough web context to answer that yet."

        lines = [f"I found these web results for: {query}"]
        for source in sources[:3]:
            title = source.get("title") or source.get("url") or "Untitled source"
            url = source.get("url", "")
            text = " ".join(str(source.get("text", "")).split())
            excerpt = text[:280].rstrip()
            if excerpt:
                lines.append(f"- [{self.markdown_link_text(title)}]({url}): {excerpt}")
            else:
                lines.append(f"- [{self.markdown_link_text(title)}]({url})")
        return "\n".join(lines)

    def markdown_link_text(self, value: str) -> str:
        return " ".join(str(value).split()).replace("[", "(").replace("]", ")")

    def append_clickable_sources(self, response: str, sources: List[Dict[str, Any]], limit: int = 5) -> str:
        links = []
        seen_urls = set()
        for source in sources:
            url = str(source.get("url", "")).strip()
            if not url.startswith(("http://", "https://")) or url in seen_urls:
                continue
            seen_urls.add(url)
            title = self.markdown_link_text(source.get("title") or url)
            links.append(f"- [{title}]({url})")
            if len(links) >= limit:
                break

        if not links:
            return response.strip()

        answer = SOURCE_SECTION_RE.sub("", response.strip()).strip()
        return f"{answer}\n\nSources:\n" + "\n".join(links)

    async def _probe_local(self, url: str, timeout: float = 4.0) -> bool:
        """Lenient ping for local instances — just checks the server responds HTTP 200.
        Does NOT require search results since engines warm up after container start."""
        try:
            search_url = f"{url.rstrip('/')}/search"
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(search_url, params={"q": "test", "format": "json"})
                return resp.status_code == 200
        except Exception:
            return False

    async def _probe_public(self, url: str, timeout: float = 4.0) -> bool:
        """Strict probe for public instances — requires actual non-Wikipedia web results."""
        try:
            search_url = f"{url.rstrip('/')}/search"
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(search_url, params={"q": "python programming", "format": "json"})
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

    async def check_searxng_online(self) -> bool:
        """Check if SearXNG is reachable. Tries local first (both 127.0.0.1 and localhost), then public fallbacks."""
        # Re-use previously discovered working URL
        if self._active_url:
            if await self._probe_local(self._active_url):
                return True
            self._active_url = None  # stale, re-discover

        # Try the configured primary URL (local Docker) — lenient check
        if await self._probe_local(self.searxng_url):
            self._active_url = self.searxng_url
            LOGGER.info(f"SearXNG online at primary: {self.searxng_url}")
            self.client.base_url = self._active_url
            return True

        # Try local alternative loopback interface (e.g. swap 127.0.0.1 <-> localhost)
        local_alt = None
        if "127.0.0.1" in self.searxng_url:
            local_alt = self.searxng_url.replace("127.0.0.1", "localhost")
        elif "localhost" in self.searxng_url:
            local_alt = self.searxng_url.replace("localhost", "127.0.0.1")

        if local_alt and await self._probe_local(local_alt):
            self._active_url = local_alt
            LOGGER.info(f"SearXNG online at local alternative: {local_alt}")
            self.client.base_url = self._active_url
            return True

        # Try public fallback instances — strict check (must return real results)
        LOGGER.warning("Local SearXNG not reachable, trying public fallbacks...")
        for instance in _PUBLIC_SEARXNG_INSTANCES:
            if await self._probe_public(instance):
                self._active_url = instance
                LOGGER.info(f"SearXNG primary offline, using public fallback: {instance}")
                self.client.base_url = instance
                return True

        LOGGER.warning("SearXNG unavailable: local and all public fallbacks unreachable.")
        return False

    async def run(
        self,
        query: str,
        conversation_history: List[Dict[str, str]] = None,
        on_status: Callable[[str, Dict[str, Any]], None] = None,
        on_chunk: Callable[[str], None] = None
    ) -> Dict[str, Any]:
        
        def emit_status(phase: str, message: str, details: Dict[str, Any] = None):
            if on_status:
                on_status(phase, {"message": message, "details": details or {}})
                
        # Phase 1: Planning
        emit_status("planning", "Formulating search strategy...")
        plan = self.planner.plan(query, conversation_history)
        LOGGER.info(f"Query plan: {plan}")
        
        if not plan.get("needs_web_search", True):
            emit_status("reasoning", "Synthesizing answer...")
            # Direct reasoning with no context
            synthesized = self.reasoner.synthesize(query, "No web search context requested.", on_chunk)
            return {
                "needs_web_search": False,
                "synthesized_response": synthesized,
                "sources": []
            }
            
        # Check SearXNG availability
        searxng_online = await self.check_searxng_online()
        if not searxng_online:
            emit_status("reasoning", "SearXNG offline, using offline weights...")
            # Fallback to direct reasoning with warning
            if on_chunk:
                on_chunk("\n*(Note: SearXNG offline, using offline weights)*\n\n")
            synthesized = self.reasoner.synthesize(query, "No web search context available because SearXNG search service is offline.", on_chunk)
            return {
                "needs_web_search": True,
                "searxng_offline": True,
                "synthesized_response": synthesized,
                "sources": []
            }
            
        # Phase 2: Retrieving
        emit_status("retrieving", f"Searching SearXNG with terms: {', '.join(plan['search_queries'])}")
        results = await self.retriever.retrieve(plan["search_queries"], plan["categories"])
        LOGGER.info(f"Retrieved {len(results)} URLs")
        
        if not results:
            emit_status("reasoning", "No search results found, answering using offline weights...")
            synthesized = self.reasoner.synthesize(query, "No web search results could be found for queries: " + str(plan["search_queries"]), on_chunk)
            return {
                "needs_web_search": True,
                "synthesized_response": synthesized,
                "sources": []
            }
            
        # Phase 3: Acquiring
        emit_status("acquiring", f"Fetching content from top {min(len(results), 3)} sources...")
        acquired = await self.acquirer.acquire(results, max_urls=3)
        LOGGER.info(f"Acquired text from {len(acquired)} pages")
        
        # Phase 4: Processing
        emit_status("processing", "Cleaning and filtering text content...")
        processed = self.processor.process(query, acquired)
        source_links = processed["sources"] or results
        
        # Phase 5: Reasoning
        emit_status("reasoning", "Synthesizing streamed answer...")
        synthesized = self.reasoner.synthesize(query, processed["context"], on_chunk)
        if synthesized.strip().startswith("[Synthesis Error"):
            synthesized = self.fallback_summary(query, source_links)
        else:
            synthesized = self.append_clickable_sources(synthesized, source_links)
        
        return {
            "needs_web_search": True,
            "synthesized_response": synthesized,
            "sources": source_links
        }
