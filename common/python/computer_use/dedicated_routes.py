"""Existing deterministic tools own supported requests before UI-agent fallbacks.

Resolution is side-effect free. In particular, questions and appearance terms
must never be interpreted as commands to physical hardware.
"""
from __future__ import annotations
import re
from urllib.parse import quote_plus


def is_guidance_question(question: str) -> bool:
    return bool(re.match(r"^\s*(?:please\s+)?(?:how\b|why\b|what\b|where\b|can\s+i\b|could\s+i\b|(?:can|could|would)\s+you\s+(?:explain|tell\s+me|show\s+me)\b|(?:tell|show)\s+me\s+how\b|explain\b)", question, re.I))


def appearance_request(question: str) -> bool:
    return bool(re.search(r"\b(?:themes?|appearance|(?:light|dark)\s+mode|colou?r\s+scheme)\b", question, re.I))


def visible_guidance_request(question: str) -> bool:
    """Unscoped visual guidance refers to the visible screen, not cached tasks."""
    if not re.match(r"^\s*(?:please\s+)?(?:highlight|point\s+to|locate)\s+\S", question, re.I):
        return False
    if re.search(r"https?://|\b(?:browser|webpage|website|current\s+tab|active\s+tab|agent[- ]browser)\b", question, re.I):
        return False
    return not re.search(r"\b(?:and|then)\s+(?:click|type|fill|send|open|press|launch|delete)\b", question, re.I)


def resolve_dedicated_request(question: str) -> dict | None:
    q = question.strip().rstrip("?.!,;:\\")
    if re.search(r"\bagent[- ](?:desktop|browser)\b", q, re.I):
        return None
    if visible_guidance_request(q):
        return {"kind": "visual_guidance", "query": q}
    if is_guidance_question(q):
        return {"kind": "information", "query": q}
    # Browser chrome actions must not be mistaken for an app named 'new tab'.
    if re.fullmatch(r"(?:please\s+)?(?:open|create|add|click)(?:\s+on)?\s+(?:(?:a|the)\s+)?new\s+(?:browser\s+)?tab(?:\s+(?:button|icon))?", q, re.I):
        return None
    if re.match(r"^(?:(?:please|can you|could you)\s+)?(?:ask|tell|message|send|type|write|reply|open|visit|click|fill)\b", q, re.I) and re.search(r"\b(?:gemini|chatgpt|chat\s+gpt|claude|copilot)\b", q, re.I):
        return None

    from . import agent
    # Preserve the existing Spotify/YouTube media controls, including compound
    # launch+play requests, instead of making a UI model find player buttons.
    spotify = re.match(r"^(?:open|launch|start)\s+spotify\s+(?:and\s+then|and|then)\s+play\s+(.+)$", q, re.I)
    canonical = f"play {spotify[1]} on spotify" if spotify else q
    media_patterns = (agent.PLAY_SPOTIFY_RE, agent.PLAY_YOUTUBE_RE, agent.STOP_SPOTIFY_RE,
                      agent.SEEK_FORWARD_RE, agent.SEEK_BACKWARD_RE, agent.NEXT_TRACK_RE, agent.PREV_TRACK_RE,
                      agent.LIST_WINDOWS_RE, agent.GET_APP_STATE_RE)
    if any(pattern.match(canonical) for pattern in media_patterns):
        return {"kind": "legacy", "query": canonical}
    from .vercel_engine import desktop_enabled
    if not desktop_enabled() and agent.OPEN_AND_TYPE_RE.match(q):
        return {"kind": "legacy", "query": q}

    youtube = re.match(r"^(?:open\s+)?(?:you\s*tube)\s+(?:and\s+|then\s+)?(?:search|find)\s+(?:for\s+)?(.+)$", q, re.I)
    if not youtube:
        youtube = re.match(r"^(?:search|find|look\s+up)\s+(?:for\s+)?(.+?)\s+(?:on|in)\s+you\s*tube$", q, re.I)
    if youtube:
        terms = youtube[1].strip()
        if terms:
            return {"kind": "youtube_search", "query": terms,
                    "url": "https://www.youtube.com/results?search_query=" + quote_plus(terms)}

    app_scoped_search = re.search(r"\b(?:in|on|within)\s+(?:the\s+)?(?:vscode|vs\s+code|visual\s+studio\s+code|spotify|vlc|notepad|file\s+explorer|microsoft\s+store|settings)\b", q, re.I)
    if re.match(r"^(?:search|google|look\s+up)\s+", q, re.I) and not app_scoped_search and not re.search(r"https?://|\b(?:click|fill|upload|youtube|you\s+tube)\b", q, re.I):
        return {"kind": "web_search", "query": re.sub(r"^(?:search|google|look\s+up)\s+(?:for\s+)?", "", q, flags=re.I)}

    simple_open = agent.OPEN_APP_RE.match(q)
    if simple_open:
        name = agent.cleanup_app_name(simple_open.group("app"))
        if not re.search(r"\b(?:and|then)\b", name, re.I):
            from .tools import WEB_DESTINATION_URLS
            destination = WEB_DESTINATION_URLS.get(name.lower())
            if destination:
                return {"kind": "open_link", "query": name, "url": destination}
            if agent.looks_like_app_name(name) and not agent.is_in_app_action(name):
                return {"kind": "legacy", "query": q}
    url_open = re.fullmatch(r"(?:open|visit|browse)\s+(https?://\S+)", q, re.I)
    if url_open:
        return {"kind": "open_link", "query": url_open[1], "url": url_open[1]}

    from .folder_launcher import is_folder_or_explorer_request
    if not re.search(r"\b(?:and|then)\b.*\b(?:click|select|type|fill|press)\b", q, re.I) and is_folder_or_explorer_request(q):
        return {"kind": "legacy", "query": q}
    from .windows_use_engine import resolve_windows_use_request
    if resolve_windows_use_request(q):
        return {"kind": "legacy", "query": q}
    from tools.esp32_light_tool import resolve_light_request
    if resolve_light_request(q):
        return {"kind": "legacy", "query": q}
    from tools.spreadsheet_tool import resolve_spreadsheet_request
    if resolve_spreadsheet_request(q):
        return {"kind": "legacy", "query": q}
    # These tools already have their own main/router runners. Mark ownership
    # here so UI fallbacks cannot intercept them before those runners execute.
    if re.search(r"\bwhats\s*app\b", q, re.I):
        from tools.whatsapp_tool import resolve_whatsapp_request, resolve_whatsapp_send_request
        if resolve_whatsapp_send_request(q) or resolve_whatsapp_request(q):
            return {"kind": "registered", "query": q}
    if re.search(r"\b(?:trim|merge|subtitles?|captions?|transcribe|edit\s+video)\b", q, re.I):
        from tools.aicut_tool import resolve_aicut_request
        media = resolve_aicut_request(q)
        if media and media.get("action") != "explorer_context":
            return {"kind": "registered", "query": q}
    if re.search(r"\bpdf\b", q, re.I):
        from tools.pdf_tool import resolve_pdf_request
        if resolve_pdf_request(q):
            return {"kind": "registered", "query": q}
    return None


def execute_dedicated_request(route: dict):
    """Reuse existing tool implementations; never enter the UI model loop."""
    if route["kind"] == "legacy":
        from .agent import try_run_agent_action
        result = try_run_agent_action(route["query"])
        if result is not None and result.success:
            from .vercel_engine import requested_app, remember_requested_app
            app = requested_app(route["query"])
            if app:
                remember_requested_app(app)
        return result
    if route["kind"] in {"youtube_search", "open_link"}:
        import webbrowser
        from .tools import ToolResult
        success = bool(webbrowser.open(route["url"]))
        if success:
            from .browser_context import remember_browser
            remember_browser(route["url"])
        message = (f"Searched YouTube for {route['query']}." if route["kind"] == "youtube_search" else f"Opened {route['query']}.")
        return ToolResult(success, route["kind"], message if success else "The browser did not accept the request.", {"url": route["url"]})
    return None
