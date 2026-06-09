import os

from playwright.async_api import async_playwright


class BrowserController:
    def __init__(self, channel: str | None = None, headless: bool | None = None):
        self.channel = channel or os.getenv("BLINKY_BROWSER_CHANNEL", "msedge").strip() or "msedge"
        if headless is None:
            headless_value = os.getenv("BLINKY_BROWSER_HEADLESS", "false").strip().lower()
            headless = headless_value in {"1", "true", "yes", "on"}
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._page = None

    async def _ensure_page(self):
        if self._page and not self._page.is_closed():
            return self._page

        if self._playwright is None:
            self._playwright = await async_playwright().start()

        if self._browser is None or not self._browser.is_connected():
            self._browser = await self._playwright.chromium.launch(
                channel=self.channel,
                headless=self.headless,
            )

        self._page = await self._browser.new_page()
        self._page.set_default_timeout(10000)
        self._page.set_default_navigation_timeout(10000)
        return self._page

    async def open_url(self, url: str) -> dict:
        page = await self._ensure_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=10000)
        title = await page.title()
        return {
            "url": page.url,
            "title": title,
        }

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._page = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


_controller: BrowserController | None = None


def get_browser_controller() -> BrowserController:
    global _controller
    if _controller is None:
        _controller = BrowserController()
    return _controller
