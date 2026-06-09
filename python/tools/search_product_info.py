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
import re


async def search_amazon_http(query: str) -> list:
    results = []
    try:
        url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
        html = await fetch_html(url)
        if not html:
            return []
            
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".s-result-item")
        for item in items[:8]:
            title_el = item.select_one("h2 a.a-link-normal")
            if not title_el:
                continue
            name = title_el.get_text().strip()
            link = title_el.get("href", "")
            if link and not link.startswith("http"):
                link = f"https://www.amazon.in{link}"
            price_el = item.select_one(".a-price-whole")
            price = price_el.get_text().strip() if price_el else "N/A"
            if name:
                results.append({
                    "name": name,
                    "price": f"Rs. {price}" if price != "N/A" else "Price not listed",
                    "source": "Amazon India (HTTP)",
                    "link": link
                })
    except Exception:
        pass
    return results

async def search_flipkart_http(query: str) -> list:
    results = []
    try:
        url = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}"
        html = await fetch_html(url)
        if not html:
            return []
            
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("[data-id]")
        for item in items[:8]:
            title_el = item.select_one("a.wjcEIp, a.IRpwTa, a._341FlM, div._4rR01T, a._2rpwq5")
            if not title_el:
                continue
            name = title_el.get_text().strip()
            link = title_el.get("href", "") if title_el.name == "a" else ""
            if link and not link.startswith("http"):
                link = f"https://www.flipkart.com{link}"
            price_el = item.select_one("div._30jeq3, div.Nx94hl, div._1vC4OF")
            price = price_el.get_text().replace("₹", "").strip() if price_el else "N/A"
            if name:
                results.append({
                    "name": name,
                    "price": f"Rs. {price}" if price != "N/A" else "Price not listed",
                    "source": "Flipkart (HTTP)",
                    "link": link
                })
    except Exception:
        pass
    return results

async def search_amazon_playwright(query: str) -> list:
    results = []
    try:
        url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
        html = await fetch_dynamic_html(url)
        if not html:
            return []
            
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("[data-component-type='s-search-result']")
        if not items:
            items = soup.select(".s-result-item")
            
        for item in items[:10]:
            title_el = None
            link = ""
            for a in item.find_all("a"):
                href = a.get("href", "")
                if "/dp/" in href or "/gp/product/" in href or "/sspa/click" in href:
                    text = a.get_text().strip()
                    if text and len(text) > 10 and not any(k in text.lower() for k in {"stars", "sponsored", "let us know"}):
                        title_el = a
                        link = href
                        break
                        
            name = title_el.get_text().strip() if title_el else "N/A"
            price_el = item.select_one(".a-price-whole")
            price = price_el.get_text().strip() if price_el else "N/A"
            
            if link and not link.startswith("http"):
                link = f"https://www.amazon.in{link}"
                
            if name != "N/A" and name:
                results.append({
                    "name": name,
                    "price": f"Rs. {price}" if price != "N/A" else "Price not listed",
                    "source": "Amazon India (Playwright)",
                    "link": link
                })
    except Exception:
        pass
    return results

async def search_flipkart_playwright(query: str) -> list:
    results = []
    try:
        url = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}"
        html = await fetch_dynamic_html(url)
        if not html:
            return []
            
        soup = BeautifulSoup(html, "html.parser")
        price_elements = soup.find_all(string=lambda t: t and "₹" in t)
        
        seen_links = set()
        for p_el in price_elements:
            price_text = p_el.strip()
            if not price_text.startswith("₹"):
                continue
                
            price_val = price_text.replace("₹", "").replace(",", "").strip()
            if not price_val.isdigit():
                continue
                
            parent = p_el.parent
            ancestor = parent
            found_product = False
            
            for _ in range(6):
                if not ancestor:
                    break
                a_tags = ancestor.find_all("a")
                for a in a_tags:
                    href = a.get("href", "")
                    title = a.get_text().strip()
                    if href and title and "/p/" in href:
                        if href not in seen_links:
                            seen_links.add(href)
                            link = href
                            if not link.startswith("http"):
                                link = f"https://www.flipkart.com{link}"
                            clean_title = " ".join(title.split())
                            if len(clean_title) > 10 and "₹" not in clean_title:
                                results.append({
                                    "name": clean_title,
                                    "price": f"Rs. {price_val}",
                                    "source": "Flipkart (Playwright)",
                                    "link": link
                                })
                                found_product = True
                                break
                if found_product:
                    break
                ancestor = ancestor.parent
    except Exception:
        pass
    return results

def filter_and_prioritize_products(products, query):
    query_lower = query.lower()
    brands = ["cosmic byte", "logitech", "razer", "corsair", "steelseries", "hyperx", "redragon", "ant esports", "asus", "lenovo", "hp", "dell"]
    target_brand = None
    for brand in brands:
        if brand in query_lower:
            target_brand = brand
            break
            
    price_limit = None
    price_matches = re.findall(r'(?:under|below|less than|rs\.?|rupees|inr)\s*(\d+[\d,.]*)', query_lower)
    if not price_matches:
        price_matches = re.findall(r'(\d+[\d,.]*)\s*(?:rupees|rs\.?|inr|under|below)', query_lower)
    
    for match in price_matches:
        cleaned_num = match.replace(",", "")
        try:
            val = float(cleaned_num)
            if val > 100:
                price_limit = val
                break
        except ValueError:
            pass

    scored_products = []
    for p in products:
        name_lower = p["name"].lower()
        score = 0
        
        if target_brand:
            if target_brand in name_lower:
                score += 100
            elif all(part in name_lower for part in target_brand.split()):
                score += 80
        
        price_str = p["price"]
        price_val = None
        price_digits = "".join(c for c in price_str if c.isdigit())
        if price_digits:
            try:
                price_val = float(price_digits)
            except ValueError:
                pass
                
        if price_limit and price_val is not None:
            if price_val <= price_limit:
                score += 50
            else:
                score -= 100
                
        scored_products.append((score, p))
        
    scored_products.sort(key=lambda x: x[0], reverse=True)
    return [p for score, p in scored_products]

def clean_search_term(query: str) -> str:
    cleaned = query.lower()
    cleaned = re.sub(r'\bmice\b', 'mouse', cleaned)
    cleaned = re.sub(r'\b(?:under|below|less than|rs\.?|rupees|inr|under\s*rs\.?|rupees\s*under)\s*\d+[\d,.]*', '', cleaned)
    cleaned = re.sub(r'\b(?:under|below|less than|rupees|rs\.?|inr|budget|cheap)\b', '', cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned if cleaned else query


async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing input JSON."}), file=sys.stderr)
        sys.exit(1)
        
    try:
        input_json = sys.argv[1]
        params = json.loads(input_json)
        query = params.get("product_query") or params.get("query")
    except Exception:
        query = sys.argv[1]

    if not query:
        print(json.dumps({"error": "Input query must be provided."}))
        sys.exit(1)

    search_query = clean_search_term(query)

    # 1. Try HTTP first
    amazon = await search_amazon_http(search_query)
    flipkart = await search_flipkart_http(search_query)
    
    # 2. Try direct Playwright search on Amazon/Flipkart if HTTP fails/blocked
    if not amazon:
        print(f"DEBUG: Amazon HTTP blocked or empty for '{search_query}'. Escalating to Playwright Amazon search...", file=sys.stderr)
        amazon = await search_amazon_playwright(search_query)
    if not flipkart:
        print(f"DEBUG: Flipkart HTTP blocked or empty for '{search_query}'. Escalating to Playwright Flipkart search...", file=sys.stderr)
        flipkart = await search_flipkart_playwright(search_query)

    combined = amazon + flipkart
    combined = filter_and_prioritize_products(combined, query)

    # 3. If direct e-commerce scrapes fail, escalate to Google Search fallback
    if not combined:
        print("DEBUG: Direct e-commerce search returned no listings. Escalating to Google Search fallback...", file=sys.stderr)
        url = f"https://www.google.com/search?q=buy+{query.replace(' ', '+')}+India"
        html = await fetch_dynamic_html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for block in soup.select("div.g")[:5]:
                heading = block.select_one("h3")
                link_el = block.select_one("a")
                if heading and link_el:
                    title = heading.get_text().strip()
                    link = link_el.get("href", "")
                    combined.append({
                        "name": title,
                        "price": "Check website for pricing",
                        "source": "Google Search Fallback (Playwright)",
                        "link": link
                    })

    final_data = {
        "query": query,
        "products": combined,
        "total_found": len(combined)
    }
    print(json.dumps(final_data, indent=2))

if __name__ == "__main__":
    asyncio.run(main())