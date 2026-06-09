import sys
import json
import asyncio
import httpx

async def lookup_wikipedia_entity(entity_name: str) -> dict:
    """
    Fetches details for the given entity name from Wikipedia API directly using HTTP.
    """
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|info",
        "exintro": True,
        "explaintext": True,
        "inprop": "url",
        "titles": entity_name,
        "redirects": 1
    }
    print(f"DEBUG: Querying Wikipedia API for {entity_name}...", file=sys.stderr)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return {"error": f"No Wikipedia page found for {entity_name}"}
            
            page_id = list(pages.keys())[0]
            if page_id == "-1":
                return {"error": f"No Wikipedia page found for {entity_name}"}
                
            page_data = pages[page_id]
            return {
                "title": page_data.get("title"),
                "extract": page_data.get("extract", ""),
                "url": page_data.get("fullurl"),
                "source": "Wikipedia API"
            }
    except Exception as e:
        return {"error": f"Failed to retrieve data from Wikipedia API: {str(e)}"}

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python script.py '<json_input>'"}))
        sys.exit(1)

    try:
        input_json = sys.argv[1]
        input_data = json.loads(input_json)
        query = input_data.get("entity_name") or input_data.get("query")
        if not query:
             raise ValueError("The input JSON must contain the 'entity_name' or 'query' key.")
    except Exception:
        query = sys.argv[1]

    final_data = await lookup_wikipedia_entity(query)
    print(json.dumps(final_data, indent=2))

if __name__ == "__main__":
    asyncio.run(main())