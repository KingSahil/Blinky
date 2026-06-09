import logging
from typing import List, Dict, Any
from wil.http_fetcher import fetch_html, extract_text_from_html
from wil.browser_engine import fetch_dynamic_html

LOGGER = logging.getLogger("blinky.acquirer")

class Acquirer:
    async def acquire_url(self, item: Dict[str, Any]) -> Dict[str, Any]:
        url = item.get("url")
        title = item.get("title", "")
        LOGGER.info(f"Acquiring content for: {url}")
        
        # 1. Try simple HTTP fetch first
        html = await fetch_html(url)
        text = extract_text_from_html(html)
        
        # Escalation criteria:
        # If the fetched text is too short (< 250 chars) or seems like a CAPTCHA/Error page
        # we escalate to dynamic browser rendering.
        is_thin_or_blocked = (
            not text or
            len(text) < 250 or
            any(k in text.lower() for k in {"captcha", "please enable javascript", "checking your browser"})
        )
        
        method_used = "HTTP"
        if is_thin_or_blocked:
            LOGGER.info(f"Escalating {url} to Playwright (len={len(text) if text else 0}, dynamic checks).")
            dynamic_html = await fetch_dynamic_html(url)
            if dynamic_html:
                html = dynamic_html
                text = extract_text_from_html(html)
                method_used = "Playwright"
            else:
                LOGGER.warning(f"Playwright escalation failed for {url}")
                
        return {
            "url": url,
            "title": title,
            "text": text,
            "method": method_used,
            "success": bool(text and len(text) > 100)
        }

    async def acquire(self, search_results: List[Dict[str, Any]], max_urls: int = 3) -> List[Dict[str, Any]]:
        acquired_contents = []
        # Query top URLs sequentially/concurrently. Let's do them concurrently.
        tasks = []
        for item in search_results[:max_urls]:
            tasks.append(self.acquire_url(item))
            
        acquired_contents = await asyncio.gather(*tasks)
        return [c for c in acquired_contents if c["success"]]

import asyncio
