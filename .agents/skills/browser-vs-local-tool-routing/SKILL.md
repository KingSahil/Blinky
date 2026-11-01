---
name: browser-vs-local-tool-routing
description: Architectural rules and classification safeguards ensuring web URLs and online social media queries (Instagram, TikTok, YouTube, GitHub) route strictly to Browser-Use instead of local media tools like AiCut video editor.
---

# Browser vs Local Tool Routing Safeguards

This skill codifies the architectural rules and deterministic safeguards preventing web URL queries and online tasks from being incorrectly routed to local file tools (e.g. AiCut video editing or local spreadsheet manipulation).

For changes to general intent routing and multi-turn target selection, also apply [generalizable-automation](../generalizable-automation/SKILL.md). Preserve these ownership safeguards without adding a new website or exact-phrase rule for every reported failure; use shared capability resolution and task context for unfamiliar requests.

---

## The Trap

In an agentic desktop system like Blinky:
1. **Keyword Overlap with Web Platforms**:
   - Subtitle presets often share names with major social platforms (e.g., `instagram`, `reels`, `tiktok`).
   - If regex patterns match bare platform names anywhere in the query string without requiring captioning/subtitle intent, a query like:
     `go to https://instagram.com/blinky_ai and tell me the first comment of latest video`
     will falsely trigger the `instagram` subtitle preset in AiCut.
2. **Explorer Context Capture**:
   - Local tools often inspect the active File Explorer window or desktop directory.
   - When a false positive triggers in AiCut, it grabs whatever video happens to be selected in Explorer (or in the active folder) and executes FFmpeg on that local file.
3. **Classification Order Inversion**:
   - If local file tools (`resolve_aicut_request`) are evaluated before web navigation tools (`resolve_browser_use_request`), any URL containing keywords like "video", "clip", or "instagram" is intercepted before the browser agent can see it.
4. **Codec & Container Mismatch in FFmpeg**:
   - When FFmpeg burns subtitles, hardware encoding defaults to H.264 (`h264_nvenc` or `libx264`). If the target container is `.webm`, FFmpeg terminates with `error code: -22 (Invalid argument)` because WebM strictly requires VP8, VP9, or AV1 video streams and Opus/Vorbis audio streams.

---

## The Multi-Layer Architectural Checklist

### 1. Classification Priority Order (`common/python/main.py`)
In `classify_request`:
- **`BROWSER_USE` must always be evaluated first**: Any query containing an external URL (`https?://`, domain) or browser automation verb (`go to <url>`, `navigate to`, `visit`) belongs to the browser agent.
- **Local file tools (AiCut, Spreadsheets) must only be evaluated after** confirming the query is not a web navigation task.

### 2. URL Guard in Local Tools (`common/python/tools/aicut_tool.py`)
At the start of `resolve_aicut_request`:
```python
if (
    re.search(r"https?://|www\.", q, re.IGNORECASE)
    or re.search(r"\b(?:go\s+to|navigate\s+to|visit|browse|open\s+website|open\s+url)\b", q_lower)
):
    return None
```
Local media tools must **never** claim queries containing external URLs or web browser instructions.

### 3. Tightened Subtitle Preset Regexes
- Platform names (`instagram`, `reels`, `tiktok`) must **never** trigger subtitles as bare words.
- They require caption/styling context:
  - `(instagram|reels|tiktok)\s+(style|preset|captions?|subtitles?|subs?|like)`
  - `(preset|style|like)\s+(instagram|reels|tiktok)`
- Disambiguate speech audio sync (`"sync automatically to audio"`) from background music addition (`"add song/music/audio track"`).

### 4. Container & Codec Compatibility in FFmpeg (`common/python/subtitles/render.py`)
- When burning subtitles into `.webm`, select `libvpx-vp9` with `libopus`.
- Default unspecified subtitle outputs for WebM inputs to `.mp4` (`_subtitled.mp4`) for universal hardware playback and GPU NVENC acceleration.

---

## Verification Protocol

Run the automated test suite to ensure zero regressions:
```powershell
& "c:\Projects\Blinky\.venv\Scripts\python.exe" -m pytest common/python/tests/test_browser_use_tool.py common/python/tests/test_aicut_tool.py -v
```
All 55+ tests must pass with 100% success rate.
