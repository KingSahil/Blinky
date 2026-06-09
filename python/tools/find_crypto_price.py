import sys
import os
import json
import asyncio
from pathlib import Path

# Add root folder to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wil.http_fetcher import fetch_html
from wil.browser_engine import fetch_dynamic_html
from bs4 import BeautifulSoup

async def find_crypto_price(crypto_name: str):
    """
    Finds cryptocurrency price using HTTP first, falling back to Playwright if needed.
    """
    slug = crypto_name.lower().replace(' ', '-')
    url = f"https://coinmarketcap.com/currencies/{slug}/"
    print(f"[DEBUG] Fetching crypto page for {crypto_name} via HTTP first...", file=sys.stderr)
    
    html = await fetch_html(url)
    price = None
    source = "CoinMarketCap (HTTP)"
    
    if html:
        soup = BeautifulSoup(html, "html.parser")
        # Try to find price using standard selector
        price_element = soup.select_one("[data-test='price']")
        if price_element:
            price = price_element.get_text().strip()
            
    # Check if we need to escalate to Playwright
    if not price:
        print(f"[DEBUG] HTTP failed or price not found, escalating to Playwright for {crypto_name}...", file=sys.stderr)
        html = await fetch_dynamic_html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            price_element = soup.select_one("[data-test='price']")
            if price_element:
                price = price_element.get_text().strip()
                source = "CoinMarketCap (Playwright)"
                
    if price:
        cleaned_price = price.strip().replace('$', '').replace(',', '')
        return {"crypto_name": crypto_name, "price": cleaned_price, "source": source}
    else:
        # Fallback if both failed
        return {"error": f"Could not retrieve price for {crypto_name} from CoinMarketCap"}

async def main():
    if len(sys.argv) > 1:
        try:
            args = json.loads(sys.argv[1])
            crypto_name = args.get("crypto_name") or args.get("query")
        except json.JSONDecodeError:
            crypto_name = sys.argv[1]
    else:
        crypto_name = "BTC"
        
    result = await find_crypto_price(crypto_name)
    print(json.dumps(result))

if __name__ == "__main__":
    asyncio.run(main())
