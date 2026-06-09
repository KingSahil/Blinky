import json
import sys
import asyncio
from playwright.async_api import async_playwright

async def main():
    try:
        query = json.loads(sys.argv[1])
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto("https://web.whatsapp.com")
            await browser.close()
            print(json.dumps({"success": True}))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python whatsapp_launcher.py <json_query>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main())