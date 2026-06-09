import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright

LOGGER = logging.getLogger("blinky.browser_engine")

# Enforce semaphore lock to prevent concurrent browser resource exhaustion
browser_semaphore = asyncio.Semaphore(2)

async def fetch_dynamic_html(url: str, timeout_ms: int = 10000) -> Optional[str]:
    LOGGER.info(f"Acquiring browser lock for URL: {url}")
    async with browser_semaphore:
        LOGGER.info(f"Lock acquired. Launching Playwright browser for URL: {url}")
        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                # Set reasonable timeout
                page.set_default_timeout(timeout_ms)
                
                await page.goto(url, wait_until="domcontentloaded")
                
                # Wait a little for potential dynamic scripts/SPA loads
                await asyncio.sleep(1.0)
                
                content = await page.content()
                return content
        except Exception as e:
            LOGGER.error(f"Playwright browser engine failed to fetch {url}: {e}")
        finally:
            if browser:
                await browser.close()
                LOGGER.info("Playwright browser closed.")
    return None
