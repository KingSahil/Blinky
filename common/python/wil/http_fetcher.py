import logging
import random
from typing import Optional
import httpx
from bs4 import BeautifulSoup

LOGGER = logging.getLogger("blinky.http_fetcher")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

async def fetch_html(url: str, timeout: float = 5.0) -> Optional[str]:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return response.text
            else:
                LOGGER.warning(f"HTTP fetch failed for {url} with status {response.status_code}")
    except Exception as e:
        LOGGER.warning(f"Error fetching HTTP content for {url}: {e}")
    return None

def extract_text_from_html(html_content: str) -> str:
    if not html_content:
        return ""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()
            
        # Extract readable text content
        lines = []
        for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "span"]):
            text = element.get_text().strip()
            if text:
                # Add prefix for headings for clarity
                if element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                    lines.append(f"\n# {text}\n")
                elif element.name == "li":
                    lines.append(f"- {text}")
                else:
                    lines.append(text)
                    
        cleaned_text = "\n".join(lines)
        # Remove consecutive blank lines
        final_lines = []
        for line in cleaned_text.splitlines():
            line_str = line.strip()
            if line_str:
                final_lines.append(line_str)
            elif final_lines and final_lines[-1] != "":
                final_lines.append("")
                
        return "\n".join(final_lines).strip()
    except Exception as e:
        LOGGER.warning(f"Error parsing HTML content: {e}")
        return ""
