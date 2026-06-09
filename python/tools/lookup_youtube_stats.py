import sys
import json
import asyncio
from playwright.async_api import async_playwright

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing arguments"}))
        sys.exit(1)

    try:
        args = json.loads(sys.argv[1])
    except Exception as e:
        print(json.dumps({"error": f"Failed to parse arguments: {str(e)}"}))
        sys.exit(1)

    channel_name = args.get("channel_name", "").strip()
    if not channel_name:
        print(json.dumps({"error": "channel_name is required"}))
        sys.exit(1)

    # Clean channel handle if it doesn't start with @
    if not channel_name.startswith("@"):
        # If it looks like a URL, extract it
        if "youtube.com/" in channel_name:
            parts = channel_name.split("youtube.com/")
            if len(parts) > 1:
                channel_name = parts[1].split("/")[0]
        # Otherwise if it's just a username/handle, prepend @
        if not channel_name.startswith("@") and "/" not in channel_name:
            channel_name = f"@{channel_name}"

    url = f"https://www.youtube.com/{channel_name}"

    browser = None
    playwright_ctx = None
    try:
        playwright_ctx = await async_playwright().start()
        # Try connecting over CDP for warm browser first, fallback to launch
        try:
            browser = await playwright_ctx.chromium.connect_over_cdp("http://localhost:9222")
        except Exception:
            browser = await playwright_ctx.chromium.launch(headless=True)

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        
        # Give some time for client-side rendering / hydration
        await page.wait_for_timeout(3000)

        # Look for subscriber count and other stats in header
        # selectors can be: yt-content-metadata-view-model, span#subscriber-count, etc.
        stats_text = ""
        selectors = [
            "yt-content-metadata-view-model",
            "#subscriber-count",
            "#subscribers",
            "yt-formatted-string#subscriber-count",
            ".yt-core-attributed-string"
        ]
        
        # Let's extract the header text or meta text
        header_area = await page.query_selector("yt-page-header-renderer")
        if header_area:
            stats_text = await header_area.inner_text()
        else:
            # Fallback to general page body text elements or specific selectors
            for sel in selectors:
                elements = await page.query_selector_all(sel)
                for el in elements:
                    txt = await el.inner_text()
                    if "subscribers" in txt.lower() or "subs" in txt.lower():
                        stats_text += "\n" + txt

        if not stats_text:
            # Get body text or meta description
            desc_meta = await page.query_selector("meta[name='description']")
            if desc_meta:
                stats_text = await desc_meta.get_attribute("content") or ""

        # Parse stats
        subscribers = "N/A"
        videos = "N/A"
        
        # Extract subscriber pattern like "100M subscribers" or "10K subs" or "105M"
        sub_match = re_search(r"([\d\.]+[\s]?[MK]?)[\s]?(subscribers|subs|subscriber)", stats_text, True)
        if not sub_match:
            # Try matching just the number followed by subscribers in meta description
            sub_match = re_search(r"([\d\.,]+[\s]?[MK]?)[\s]?(subscribers|subs)", stats_text, True)

        if sub_match:
            subscribers = sub_match.group(1).strip()

        video_match = re_search(r"([\d\.,]+[\s]?[MK]?)[\s]?(videos|video)", stats_text, True)
        if video_match:
            videos = video_match.group(1).strip()

        # Get channel name/title from title tag or page header
        channel_title = await page.title()
        if " - YouTube" in channel_title:
            channel_title = channel_title.replace(" - YouTube", "")

        result = {
            "channel": channel_title,
            "handle": channel_name,
            "subscribers": subscribers,
            "videos": videos,
            "raw_metadata": stats_text.strip().split("\n")[:10]  # First 10 lines of metadata
        }
        
        print(json.dumps(result))

    except Exception as e:
        print(json.dumps({"error": f"Execution failed: {str(e)}"}))
        sys.exit(1)
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright_ctx:
            try:
                await playwright_ctx.stop()
            except Exception:
                pass

def re_search(pattern, text, ignore_case=False):
    import re
    flags = re.IGNORECASE if ignore_case else 0
    return re.search(pattern, text, flags)

if __name__ == "__main__":
    asyncio.run(main())
