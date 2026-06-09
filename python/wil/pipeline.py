import logging
from typing import Dict, Any, List, Callable
import httpx
from wil.planner import QueryPlanner
from wil.searxng_client import SearXNGClient
from wil.retriever import Retriever
from wil.acquirer import Acquirer
from wil.processor import ContentProcessor
from wil.reasoner import Reasoner

LOGGER = logging.getLogger("blinky.pipeline")

class WILPipeline:
    def __init__(self, base_url: str = None):
        self.searxng_url = base_url or "http://localhost:8888"
        self.planner = QueryPlanner()
        self.client = SearXNGClient(self.searxng_url)
        self.retriever = Retriever(self.client)
        self.acquirer = Acquirer()
        self.processor = ContentProcessor()
        self.reasoner = Reasoner()

    async def check_searxng_online(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get(self.searxng_url)
                return resp.status_code in [200, 404, 403, 503] # any response implies container is alive
        except Exception:
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
            emit_status("reasoning", "Skipping web search, answering from offline weights...")
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
        
        # Phase 5: Reasoning
        emit_status("reasoning", "Synthesizing streamed answer...")
        synthesized = self.reasoner.synthesize(query, processed["context"], on_chunk)
        
        return {
            "needs_web_search": True,
            "synthesized_response": synthesized,
            "sources": processed["sources"]
        }
