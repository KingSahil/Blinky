import json
import logging
import re
import time
import urllib.request
from typing import Any

LOGGER = logging.getLogger("blinky.utils.location")

_CACHED_LOCATION: dict[str, Any] | None = None
_LAST_FETCH_TIME: float = 0.0
_CACHE_TTL_SECONDS: float = 3600.0  # 1 hour cache


def get_user_location() -> dict[str, Any]:
    """
    Resolves the approximate geolocation of the user via fast IP-lookup.
    Caches results in-memory to prevent repeated network overhead.
    """
    global _CACHED_LOCATION, _LAST_FETCH_TIME

    now = time.time()
    if _CACHED_LOCATION is not None and (now - _LAST_FETCH_TIME) < _CACHE_TTL_SECONDS:
        return _CACHED_LOCATION

    try:
        req = urllib.request.Request(
            "http://ip-api.com/json/?fields=status,country,regionName,city,zip,lat,lon",
            headers={"User-Agent": "Blinky-Assistant/1.0"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "success":
                city = str(data.get("city") or "").strip()
                region = str(data.get("regionName") or "").strip()
                country = str(data.get("country") or "").strip()
                zip_code = str(data.get("zip") or "").strip()
                lat = data.get("lat")
                lon = data.get("lon")

                parts = [p for p in [city, region, country] if p]
                display = ", ".join(parts) if parts else "Unknown"

                _CACHED_LOCATION = {
                    "city": city,
                    "region": region,
                    "country": country,
                    "zip": zip_code,
                    "lat": lat,
                    "lon": lon,
                    "display": display,
                }
                _LAST_FETCH_TIME = now
                LOGGER.info("Resolved user location: %s", display)
                return _CACHED_LOCATION
    except Exception as exc:
        LOGGER.debug("Could not resolve IP location: %s", exc)

    if _CACHED_LOCATION is not None:
        return _CACHED_LOCATION

    return {
        "city": "",
        "region": "",
        "country": "",
        "zip": "",
        "lat": None,
        "lon": None,
        "display": "",
    }


NEAR_ME_PATTERN = re.compile(
    r"\b(?:near\s+me|nearby|closest|around\s+here|around\s+me|in\s+my\s+area|near\s+here|locally|in\s+town)\b",
    re.IGNORECASE,
)


CONVERSATIONAL_SEARCH_STRIP = re.compile(
    r"\b(?:and\s+find(?:\s+me)?(?:\s+their)?\s*(?:contact\s+numbers?|phone\s+numbers?|contact\s+details?|numbers?|details?)?|like\s+an?\s+agent|please|can\s+you|could\s+you|find\s+me|tell\s+me)\b",
    re.IGNORECASE,
)


def enrich_query_with_location(query: str, location: dict[str, Any] | None = None) -> str:
    """
    Replaces relative location phrases like 'near me' or 'nearby' with the user's city/region.
    Cleans conversational filler so search queries produce rich local results.
    Example: 'best restaurant near me and find their contact number' -> 'best restaurants in Amritsar Punjab contact numbers'
    """
    if location is None:
        location = get_user_location()

    wants_contact = any(k in query.lower() for k in ["contact", "phone", "number", "call"])

    # Clean conversational filler for crisp search terms
    cleaned = CONVERSATIONAL_SEARCH_STRIP.sub(" ", query).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    city = location.get("city", "").strip()
    region = location.get("region", "").strip()
    country = location.get("country", "").strip()

    loc_str = ""
    if city and region:
        loc_str = f"in {city} {region}"
    elif city:
        loc_str = f"in {city}"
    elif region:
        loc_str = f"in {region}"
    elif country:
        loc_str = f"in {country}"

    result = cleaned
    if loc_str:
        if NEAR_ME_PATTERN.search(cleaned):
            result = NEAR_ME_PATTERN.sub(loc_str, cleaned).strip()
        else:
            lower = cleaned.lower()
            local_keywords = [
                "restaurant", "restaurants", "cafe", "cafes", "coffee shop",
                "food", "pharmacy", "hospital", "gas station", "groceries", "supermarket"
            ]
            if any(k in lower for k in local_keywords) and not any(k in lower for k in [" in ", " at ", " near "]):
                result = f"{cleaned} {loc_str}"

    if wants_contact and not any(k in result.lower() for k in ["contact", "phone", "number"]):
        result = f"{result} contact numbers"

    return re.sub(r"\s+", " ", result).strip()
