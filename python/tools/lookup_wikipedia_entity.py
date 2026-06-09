import asyncio
import json
import sys
from playwright.async_api import async_playwright

async def scrape_search_results(query: str) -> dict:
    """
    Automates a browser search using Playwright to find general search results
    for the given query, focusing on general search results rather than
    fragile e-commerce selectors.
    """
    results = {
        "query": query,
        "products": [],
        "total_found": 0,
        "source": "Google Search",
        "error": None
    }
    
    # Use a general search URL
    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            print(f"DEBUG: Navigating to {search_url}", file=sys.stderr)
            await page.goto(search_url, wait_until="domcontentloaded")
            
            # Wait for general search results to load
            await page.wait_for_selector('div.g', timeout=15000)
            
            # Selectors for general search results (div.g is a common container)
            result_locators = page.locator('div.g')
            
            # Get all result elements
            result_elements = await result_locators.all()
            
            found_products = []
            
            for element in result_elements:
                try:
                    # Extract title and link
                    title_element = element.locator('h3')
                    link_element = element.locator('a')
                    
                    title = await title_element.inner_text()
                    link = await link_element.get_attribute('href')
                    
                    # Only process if we have a valid link and title
                    if link and title:
                        found_products.append({
                            "title": title.strip(),
                            "url": link,
                            "snippet": await element.inner_text()[:200] + "..."
                        })
                except Exception as e:
                    # Skip elements that fail to parse
                    print(f"DEBUG: Failed to parse a result element: {e}", file=sys.stderr)
                    continue

            results["products"] = found_products
            results["total_found"] = len(found_products)

        except Exception as e:
            results["error"] = str(e)
            print(f"ERROR: An error occurred during scraping: {e}", file=sys.stderr)
        finally:
            await browser.close()
            
    return results

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python script.py '<json_input>'"}))
        sys.exit(1)

    try:
        input_json = sys.argv[1]
        
        # Assuming the input JSON contains the query under the 'entity_name' key
        input_data = json.loads(input_json)
        query = input_data.get("entity_name")
        
        if not query:
             raise ValueError("The input JSON must contain the 'entity_name' key.")

    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input provided."}))
        sys.exit(1)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"Initialization error: {e}"}))
        sys.exit(1)

    # Run the scraping logic
    final_data = await scrape_search_results(query)
    
    # Output the final data as a single JSON object to stdout
    print(json.dumps(final_data, indent=2))

if __name__ == "__main__":
    asyncio.run(main())