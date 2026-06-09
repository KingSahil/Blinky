import sys
import json
import asyncio
import re
from pathlib import Path

# Add root folder to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wil.http_fetcher import fetch_html
from wil.browser_engine import fetch_dynamic_html
from bs4 import BeautifulSoup

def re_search(pattern, text, ignore_case=False):
    flags = re.IGNORECASE if ignore_case else 0
    return re.search(pattern, text, flags)

async def get_youtube_stats(channel_name: str) -> dict:
    # Clean channel handle if it doesn't start with @
    if not channel_name.startswith("@"):
        if "youtube.com/" in channel_name:
            parts = channel_name.split("youtube.com/")
            if len(parts) > 1:
                channel_name = parts[1].split("/")[0]
        if not channel_name.startswith("@") and "/" not in channel_name:
            channel_name = f"@{channel_name}"

    url = f"https://www.youtube.com/{channel_name}"
    print(f"DEBUG: Fetching Youtube stats for {channel_name} via HTTP...", file=sys.stderr)
    
    html = await fetch_html(url)
    stats_text = ""
    source = "YouTube (HTTP)"
    
    if html:
        soup = BeautifulSoup(html, "html.parser")
        desc_meta = soup.find("meta", {"name": "description"})
        if desc_meta:
            stats_text = desc_meta.get("content", "")
            
    # Escalate if stats_text doesn't contain subscriber keyword
    if not stats_text or "subscriber" not in stats_text.lower():
        print(f"DEBUG: HTTP description check thin/missing, escalating to Playwright...", file=sys.stderr)
        html = await fetch_dynamic_html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            desc_meta = soup.find("meta", {"name": "description"})
            if desc_meta:
                stats_text = desc_meta.get("content", "")
            else:
                stats_text = soup.get_text()
            source = "YouTube (Playwright)"

    subscribers = "N/A"
    videos = "N/A"
    
    sub_match = re_search(r"([\d\.,]+[\s]?[MK]?)[\s]?(subscribers|subs)", stats_text, True)
    if sub_match:
        subscribers = sub_match.group(1).strip()

    video_match = re_search(r"([\d\.,]+[\s]?[MK]?)[\s]?(videos|video)", stats_text, True)
    if video_match:
        videos = video_match.group(1).strip()

    return {
        "channel": channel_name,
        "handle": channel_name,
        "subscribers": subscribers,
        "videos": videos,
        "raw_metadata": stats_text.strip(),
        "source": source
    }

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing arguments"}))
        sys.exit(1)

    try:
        args = json.loads(sys.argv[1])
        channel_name = args.get("channel_name", "").strip()
    except Exception:
        channel_name = sys.argv[1]

    result = await get_youtube_stats(channel_name)
    print(json.dumps(result))

if __name__ == "__main__":
    asyncio.run(main())
