import asyncio
import json
import sys
import re
from playwright.async_api import async_playwright

async def search_amazon(page, query: str) -> list:
    results = []
    try:
        url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
        print(f"Searching Amazon.in: {url}", file=sys.stderr)
        
        # Go to Amazon
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Wait for product items
        await page.wait_for_selector(".s-result-item", timeout=10000)
        items = await page.locator(".s-result-item").all()
        
        for item in items[:8]:  # Get top 8 items
            try:
                title_el = item.locator("h2 a.a-link-normal")
                if await title_el.count() == 0:
                    continue
                name = (await title_el.first.inner_text()).strip()
                
                # Check link
                link = await title_el.first.get_attribute("href")
                if link and not link.startswith("http"):
                    link = f"https://www.amazon.in{link}"
                
                # Check price
                price_el = item.locator(".a-price-whole")
                price = "N/A"
                if await price_el.count() > 0:
                    price = (await price_el.first.inner_text()).strip().replace("\n", "")
                
                if name:
                    results.append({
                        "name": name,
                        "price": f"Rs. {price}" if price != "N/A" else "Price not listed",
                        "source": "Amazon India",
                        "link": link or ""
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"Amazon scraping encountered an issue or CAPTCHA: {e}", file=sys.stderr)
    return results

async def search_flipkart(page, query: str) -> list:
    results = []
    try:
        url = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}"
        print(f"Searching Flipkart: {url}", file=sys.stderr)
        
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Flipkart has two main grid selectors depending on layout
        # Selector 1: Grid items (usually ._7573eb or similar)
        # Selector 2: Row items (usually ._1AtVb2 or custom row classes)
        # Let's wait for general text container that exists in product cards
        await page.wait_for_selector("[data-id]", timeout=10000)
        
        items = await page.locator("[data-id]").all()
        for item in items[:8]:
            try:
                # Look for product title (usually the link containing product text)
                title_locator = item.locator("a.wjcEIp, a.IRpwTa, a._341FlM")
                if await title_locator.count() == 0:
                    title_locator = item.locator("div._4rR01T, a._2rpwq5")
                
                if await title_locator.count() == 0:
                    continue
                    
                name = (await title_locator.first.inner_text()).strip()
                
                # Link
                link = await title_locator.first.get_attribute("href")
                if link and not link.startswith("http"):
                    link = f"https://www.flipkart.com{link}"
                
                # Price
                price_locator = item.locator("div._30jeq3, div.Nx94hl, div._1vC4OF")
                price = "N/A"
                if await price_locator.count() > 0:
                    price = (await price_locator.first.inner_text()).strip()
                    # Clean currency symbol
                    price = price.replace("₹", "").strip()
                
                if name:
                    results.append({
                        "name": name,
                        "price": f"Rs. {price}" if price != "N/A" else "Price not listed",
                        "source": "Flipkart",
                        "link": link or ""
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"Flipkart scraping encountered an issue or CAPTCHA: {e}", file=sys.stderr)
    return results

async def search_google_fallback(page, query: str) -> list:
    results = []
    try:
        url = f"https://www.google.com/search?q=buy+{query.replace(' ', '+')}+India"
        print(f"Searching Google Fallback: {url}", file=sys.stderr)
        
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_selector("#search", timeout=10000)
        
        # Extract top 5 search result headings and snippets
        search_blocks = await page.locator("div.g").all()
        for idx, block in enumerate(search_blocks[:6]):
            try:
                heading = block.locator("h3")
                if await heading.count() == 0:
                    continue
                title = (await heading.first.inner_text()).strip()
                
                link_el = block.locator("a")
                link = await link_el.first.get_attribute("href") if await link_el.count() > 0 else ""
                
                snippet_el = block.locator("div.VwiC3b, div.yDAB2d")
                snippet = ""
                if await snippet_el.count() > 0:
                    snippet = (await snippet_el.first.inner_text()).strip()
                
                results.append({
                    "name": title,
                    "price": "Check website for pricing",
                    "source": "Google Search Fallback",
                    "link": link,
                    "details": snippet
                })
            except Exception:
                continue
    except Exception as e:
        print(f"Google Fallback search failed: {e}", file=sys.stderr)
    return results

async def solve_query(query: str) -> str:
    print(f"Initializing browser for product query: '{query}'", file=sys.stderr)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Setup modern headers and viewport
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        
        amazon_products = []
        flipkart_products = []
        
        # Try both stores
        amazon_products = await search_amazon(page, query)
        flipkart_products = await search_flipkart(page, query)
        
        combined = amazon_products + flipkart_products
        
        # Fallback to general Google search if empty
        if not combined:
            print("E-commerce scrapers returned no listings. Checking general search indexes...", file=sys.stderr)
            combined = await search_google_fallback(page, query)
            
        await browser.close()
        
        final_data = {
            "query": query,
            "products": combined,
            "total_found": len(combined)
        }
        return json.dumps(final_data, indent=2)

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing input JSON."}), file=sys.stderr)
        sys.exit(1)
        
    try:
        input_json = sys.argv[1]
        params = json.loads(input_json)
        query = params.get("product_query")
        
        if not query:
            print(json.dumps({"error": "Input JSON must contain a 'product_query' field."}), file=sys.stderr)
            sys.exit(1)
            
        result = await solve_query(query)
        print(result)
    except Exception as e:
        print(json.dumps({"error": f"Execution crashed: {str(e)}"}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())