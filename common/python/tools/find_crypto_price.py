import sys
import json
import asyncio
from playwright.async_api import async_playwright

async def find_crypto_price(crypto_name: str):
    """
    Navigates to CoinMarketCap, searches for the specified cryptocurrency,
    and extracts its current price.
    """
    print(f"[DEBUG] Starting browser automation for {crypto_name}...", file=sys.stderr)
    browser = None
    try:
        async with async_playwright() as p:
            # Launch Chromium in headless mode
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # 1. Navigate to CoinMarketCap
            await page.goto("https://coinmarketcap.com/")
            print("[DEBUG] Successfully navigated to CoinMarketCap.", file=sys.stderr)

            # 2. Search for the cryptocurrency
            # We assume the search bar is present and functional.
            # A common selector for search input on CMC is needed.
            search_selector = "#search-input"
            await page.wait_for_selector(search_selector, timeout=10000)
            print(f"[DEBUG] Found search input selector: {search_selector}", file=sys.stderr)

            await page.fill(search_selector, crypto_name)
            await page.click("button[data-testid='search-button']") # Click the search button
            await page.wait_for_selector("div[data-id='crypto-card']", timeout=15000)
            print("[DEBUG] Search initiated and results loaded.", file=sys.stderr)

            # 3. Navigate to the specific coin page
            # The search results usually contain a link to the coin's page.
            # We look for the main link element after searching.
            coin_link_selector = f"a[data-coin-id='{crypto_name.replace(' ', '-')}' or data-id='{crypto_name.lower().replace(' ', '-')}' ]"
            
            # Attempt to find the link on the results page
            try:
                # Wait for the main coin card/link to appear
                await page.wait_for_selector(f'a[href*=".*/{crypto_name.replace(" ", "-")}"]', timeout=15000)
                # Click the link that leads to the coin's dedicated page
                await page.click(f'a[href*=".*/{crypto_name.replace(" ", "-")}"]')
                await page.wait_for_load_state('networkidle')
                print("[DEBUG] Navigated to the coin's dedicated page.", file=sys.stderr)
            except Exception as e:
                print(f"[ERROR] Could not find or click the coin link. Error: {e}", file=sys.stderr)
                return {"error": "Could not navigate to the coin page after search."}

            # 4. Extract the price
            # The price element selector is highly volatile, but typically it's a prominent element.
            # We look for the main price container on the coin page.
            price_selector = "[data-test='price']"
            await page.wait_for_selector(price_selector, timeout=10000)
            
            price_element = await page.inner_text(price_selector)
            
            if price_element:
                # Clean up the price string (remove commas, currency symbols, etc.)
                cleaned_price = price_element.strip().replace(',', '').replace('$', '').replace('USD', '').strip()
                return {"crypto_name": crypto_name, "price": cleaned_price, "source": "CoinMarketCap"}
            else:
                return {"error": "Could not find the price element on the coin page. Selector might be outdated."}

    except Exception as e:
        print(f"[CRITICAL_ERROR] An unexpected error occurred: {e}", file=sys.stderr)
        return {"error": str(e)}
    finally:
        if browser:
            await browser.close()
            print("[DEBUG] Browser closed successfully.", file=sys.stderr)

async def main():
    # The script expects arguments to be passed via sys.argv[1] as a JSON string.
    # We are hardcoding the BTC query as per the prompt requirement, but structure it to accept arguments.
    
    # Check if arguments are provided (optional, but good practice)
    if len(sys.argv) > 1:
        try:
            args = json.loads(sys.argv[1])
            crypto_name = args.get("crypto_name")
        except json.JSONDecodeError:
            print("[ERROR] Invalid JSON input provided via sys.argv[1].", file=sys.stderr)
            sys.exit(1)
    else:
        # Default to the required query: BTC
        crypto_name = "BTC"
        print(f"[DEBUG] No arguments provided. Defaulting to {crypto_name}.", file=sys.stderr)

    # Run the async function and print the result JSON to stdout
    result = await find_crypto_price(crypto_name)
    print(json.dumps(result))

if __name__ == "__main__":
    # Since the execution environment might not support direct asyncio.run(main()), 
    # we use a standard pattern for robustness.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[DEBUG] Script interrupted by user.", file=sys.stderr)
        sys.exit(1)
