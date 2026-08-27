#!/usr/bin/env python3
"""
AiCut Video Editor Tool for Blinky.
Provides intelligent video trimming, background music merging, multi-video concatenation,
media metadata inspection, and active Windows File Explorer context resolution.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Add common python directory to path if not present
_COMMON_DIR = Path(__file__).resolve().parent.parent
if str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

_COMMON_ROOT = Path(__file__).resolve().parent.parent.parent
AICUT_ROOT = _COMMON_ROOT / "aicut"
if not AICUT_ROOT.exists():
    AICUT_ROOT = Path(r"C:\Projects\AiCut")
AICUT_MCP_PY = AICUT_ROOT / "aicut_mcp.py"

try:
    from utils.explorer import get_active_explorer_context, MEDIA_EXTENSIONS
except ImportError:
    MEDIA_EXTENSIONS = {
        "video": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".m4v"},
        "audio": {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".wma"},
    }
    def get_active_explorer_context() -> dict[str, Any]:
        return {"active_directory": None, "selected_files": [], "selected_videos": [], "selected_audios": [], "media_files_in_folder": []}


def find_candidate_file(filename_or_path: str, active_dir: str | None = None, file_type: str | None = None) -> str | None:
    """Find the full absolute path of a file across Explorer and project paths."""
    if not filename_or_path:
        return None

    raw_path = Path(filename_or_path)
    if raw_path.is_absolute() and raw_path.exists():
        return str(raw_path.resolve())

    # Candidate directories to search
    candidates_dirs = []
    if active_dir and os.path.isdir(active_dir):
        candidates_dirs.append(Path(active_dir))

    candidates_dirs.extend([
        AICUT_ROOT / "sample" / "input",
        AICUT_ROOT / "sample" / "output",
        AICUT_ROOT / "sample",
        AICUT_ROOT,
        Path.home() / "Videos",
        Path.home() / "Downloads",
        Path.home() / "Desktop",
    ])

    clean_name = raw_path.name.lower()
    for directory in candidates_dirs:
        if not directory.exists():
            continue
        # Direct check
        direct = directory / raw_path.name
        if direct.exists():
            return str(direct.resolve())
        # Fuzzy match inside folder
        try:
            for item in directory.iterdir():
                if item.is_file():
                    if item.name.lower() == clean_name:
                        return str(item.resolve())
                    if item.stem.lower() == raw_path.stem.lower():
                        return str(item.resolve())
        except Exception:
            continue

    return str(raw_path) if raw_path.exists() else None


def _detect_whisper_model(q_lower: str) -> str:
    """Pick a faster-whisper model size from the query ('small model', etc.)."""
    model_match = re.search(r"\b(tiny|base|small|medium|large[-\s]?v3?|large)\b", q_lower)
    if model_match:
        size = model_match.group(1).lower().replace(" ", "-")
        if size == "large-v3" or size == "large":
            return "large-v3"
        return size
    return "tiny"


PRESET_ALIASES: dict[str, str] = {
    "instagram-green": "instagram-green",
    "insta-green": "instagram-green",
    "insta green": "instagram-green",
    "instagram-pop": "instagram-pop",
    "insta-pop": "instagram-pop",
    "insta pop": "instagram-pop",
    "instagram": "instagram",
    "insta": "instagram",
    "reels": "instagram",
    "reel": "instagram",
    "tiktok": "instagram",
    "word-by-word": "instagram",
    "word by word": "instagram",
    "wordbyword": "instagram",
    "hormozi-clean": "hormozi-clean",
    "clean hormozi": "hormozi-clean",
    "hormozi": "hormozi",
    "harumuzi": "hormozi",
    "hormuzi": "hormozi",
    "alex hormozi": "hormozi",
    "word-karaoke": "word-karaoke",
    "karaoke": "word-karaoke",
    "pill-yellow": "pill-yellow",
    "yellow pill": "pill-yellow",
    "yellow box": "pill-yellow",
    "pill-red": "pill-red",
    "red pill": "pill-red",
    "red box": "pill-red",
    "typewriter": "typewriter",
    "type writer": "typewriter",
    "typing": "typewriter",
    "color-switch": "color-switch",
    "color switch": "color-switch",
    "colorful": "color-switch",
    "keyword-green": "keyword-green",
    "green keyword": "keyword-green",
    "lecture-dual": "lecture-dual",
    "lecture": "lecture-dual",
    "documentary": "documentary",
    "docu": "documentary",
    "bbc": "documentary",
    "cinematic-lowerthird": "cinematic-lowerthird",
    "cinematic": "cinematic-lowerthird",
    "lower-third": "cinematic-lowerthird",
    "lower third": "cinematic-lowerthird",
    "quiet-minimal": "quiet-minimal",
    "minimal": "quiet-minimal",
    "quiet": "quiet-minimal",
    "glassmorphism": "glassmorphism",
    "glass": "glassmorphism",
    "frosted": "glassmorphism",
    "neon-blur": "neon-blur",
    "neon": "neon-blur",
    "cyber": "neon-blur",
    "glow": "neon-blur",
    "meme-impact": "meme-impact",
    "meme": "meme-impact",
    "impact": "meme-impact",
    "retro-yellow": "retro-yellow",
    "retro": "retro-yellow",
}


def _detect_preset_name(q_lower: str) -> str | None:
    """Detect named subtitle preset or alias anywhere in query."""
    for alias in sorted(PRESET_ALIASES.keys(), key=len, reverse=True):
        if re.search(r"\b" + re.escape(alias) + r"\b", q_lower):
            return PRESET_ALIASES[alias]

    preset_match = re.search(r"\b(?:preset|style)\s*(?:of|:)?\s*([a-z][a-z0-9\-]+)", q_lower)
    if preset_match:
        val = preset_match.group(1).lower().strip()
        return PRESET_ALIASES.get(val, val)

    known_preset = re.search(r"\b(?:with|in|using|use)\s+([a-z][a-z0-9\-]+)\b", q_lower)
    if known_preset:
        val = known_preset.group(1).lower().strip()
        return PRESET_ALIASES.get(val, val)

    return None


def resolve_aicut_request(query: str) -> dict[str, Any] | None:
    """Deterministically parse and classify an AiCut video editor query."""
    if not query:
        return None
    q = query.strip()
    q_lower = q.lower()

    # Check for explicitly referenced / dragged-in files in query
    referenced_files = []
    ref_match = re.search(r"\[Referenced Files:\s*(.*?)\]", query, re.DOTALL | re.IGNORECASE)
    if ref_match:
        for p in ref_match.group(1).split(","):
            p_clean = p.strip()
            if p_clean and (Path(p_clean).exists() or Path(p_clean).is_file()):
                referenced_files.append(str(Path(p_clean).resolve()))

    ref_videos = [f for f in referenced_files if Path(f).suffix.lower() in MEDIA_EXTENSIONS.get("video", {".mp4", ".mov", ".mkv", ".avi", ".webm"})]
    ref_audios = [f for f in referenced_files if Path(f).suffix.lower() in MEDIA_EXTENSIONS.get("audio", {".mp3", ".wav", ".aac", ".m4a"})]

    # Get active Explorer context
    explorer = get_active_explorer_context()
    active_dir = explorer.get("active_directory")
    selected_videos = ref_videos if ref_videos else explorer.get("selected_videos", [])
    selected_audios = ref_audios if ref_audios else explorer.get("selected_audios", [])
    media_in_folder = explorer.get("media_files_in_folder", [])

    # Check for volume specification
    vol_match = re.search(r"(?:with|at)?\s*(?:volume|music-volume|vol)?\s*(?P<vol>0?\.\d+|\d{1,3}%)\s*(?:volume|vol)?", q_lower)
    music_vol = 0.25
    if vol_match:
        vol_str = vol_match.group("vol")
        if "%" in vol_str:
            music_vol = float(vol_str.replace("%", "")) / 100.0
        else:
            music_vol = float(vol_str)

    # 1. High-priority resolution when files are attached / referenced
    if ref_videos and ref_audios:
        # User attached both a video and a song/audio
        return {
            "action": "add_song",
            "video_path": ref_videos[0],
            "song_path": ref_audios[0],
            "music_volume": music_vol,
            "explorer": explorer,
        }

    # 2. Add Song / Background Music Patterns
    add_song_pattern = r"\b(?:add|put|mix|insert|attach|set|apply|overlay|combine|merge)\b.*?\b(?:song|music|audio|track|sound|bgm|beats)\b|\b(?:background\s+music|bgm)\b|\b(?:song|music|audio)\b.*?\b(?:video|clip)\b|\b(?:video|clip)\b.*?\b(?:with|and)\b.*?\b(?:song|music|audio|sound)\b"
    if re.search(add_song_pattern, q_lower):
        audio_match = re.search(r"([^\s\"\']+\.(?:mp3|wav|aac|m4a|flac|ogg))", q_lower)
        video_match = re.search(r"([^\s\"\']+\.(?:mp4|mov|mkv|avi|webm))", q_lower)

        song_file = find_candidate_file(audio_match.group(1), active_dir) if audio_match else None
        if not song_file and audio_match:
            song_file = audio_match.group(1)

        video_file = find_candidate_file(video_match.group(1), active_dir) if video_match else None
        if not video_file and video_match:
            video_file = video_match.group(1)

        if not song_file and selected_audios:
            song_file = selected_audios[0]
        if not video_file and selected_videos:
            video_file = selected_videos[0]

        if not song_file and media_in_folder:
            audios = [f for f in media_in_folder if Path(f).suffix.lower() in MEDIA_EXTENSIONS.get("audio", {".mp3", ".wav"})]
            if len(audios) == 1:
                song_file = audios[0]
        if not video_file and media_in_folder:
            videos = [f for f in media_in_folder if Path(f).suffix.lower() in MEDIA_EXTENSIONS.get("video", {".mp4", ".mov"})]
            if len(videos) == 1:
                video_file = videos[0]

        if video_file or song_file:
            return {
                "action": "add_song",
                "video_path": video_file,
                "song_path": song_file,
                "music_volume": music_vol,
                "explorer": explorer,
            }

    # 3. Trim / Cut Patterns
    trim_time_match = re.search(
        r"(?:trim|cut)\s+(?:(?:the|this|that|selected|referenced)?\s*(?:video|clip|it)?\s+)?(?:(?P<file>[^\s\"\']+\.(?:mp4|mov|mkv|avi|webm))\s+)?(?:from\s+)?(?P<start>\d+(?:\.\d+)?)\s*(?:s|sec|seconds)?\s*(?:to|till|until|-)\s*(?P<end>\d+(?:\.\d+)?)\s*(?:s|sec|seconds)?",
        q_lower
    )
    if trim_time_match:
        start_sec = float(trim_time_match.group("start"))
        end_sec = float(trim_time_match.group("end"))
        file_spec = trim_time_match.group("file")

        video_file = find_candidate_file(file_spec, active_dir) if file_spec else None
        if not video_file and file_spec:
            video_file = file_spec
        if not video_file and selected_videos:
            video_file = selected_videos[0]
        elif not video_file and media_in_folder:
            videos = [f for f in media_in_folder if Path(f).suffix.lower() in MEDIA_EXTENSIONS.get("video", {".mp4", ".mov"})]
            if len(videos) == 1:
                video_file = videos[0]

        return {
            "action": "trim",
            "video_path": video_file,
            "start_seconds": start_sec,
            "end_seconds": end_sec,
            "explorer": explorer,
        }

    # 4. Merge / Combine Patterns
    merge_pattern = r"\b(?:merge|combine|join|stitch|concat|concatenate)\b"
    if re.search(merge_pattern, q_lower) or (len(ref_videos) >= 2):
        video_matches = re.findall(r"([^\s\"\']+\.(?:mp4|mov|mkv|avi|webm))", q_lower)
        input_files = []
        for v in video_matches:
            found = find_candidate_file(v, active_dir)
            if found:
                if found not in input_files:
                    input_files.append(found)
            else:
                if v not in input_files:
                    input_files.append(v)

        if len(input_files) < 2 and len(selected_videos) >= 2:
            input_files = selected_videos

        if input_files:
            return {
                "action": "merge",
                "input_paths": input_files,
                "explorer": explorer,
            }

    # 5. Media Info Pattern
    if any(k in q_lower for k in ["media info", "inspect media", "video info", "inspect video", "file info"]):
        target = re.search(r"([^\s\"\']+\.(?:mp4|mov|mkv|avi|webm|mp3|wav))", q_lower)
        target_file = find_candidate_file(target.group(1), active_dir) if target else None
        if not target_file and target:
            target_file = target.group(1)
        if not target_file and selected_videos:
            target_file = selected_videos[0]
        return {
            "action": "media_info",
            "file_path": target_file,
            "explorer": explorer,
        }

    known_presets_regex = r"instagram|insta|reels|tiktok|word-by-word|word-karaoke|karaoke|hormozi|pill-yellow|pill-red|typewriter|color-switch|neon-blur|neon|glassmorphism|meme-impact|meme|retro-yellow|retro|documentary|cinematic-lowerthird|quiet-minimal|keyword-green|lecture-dual"
    # 6. Subtitle / caption patterns (preset-aware)
    subtitle_pattern = (
        r"\b(?:burn|add|put|apply|overlay|write|want|need|use|with|in)\b.*?\b(?:subtitle|caption|subs?|subtitles|captions)\b"
        r"|\b(?:" + known_presets_regex + r")\b.*?\b(?:subtitles?|captions?|subs?)\b"
        r"|\b(?:subtitle|caption|subs?|subtitles|captions)\b.*?(?:to|on|into|for|this|that|the|with|in|like)\b.*?\b(?:video|clip|file|mp4|mov|mkv)?"
        r"|\b(?:subtitle|caption)\b\s+(?:this|that|the)?\s*(?:video|clip|file)"
        r"|\b(?:word\s+by\s+word|instagram|reels|tiktok)\b"
    )
    if re.search(subtitle_pattern, q_lower):
        preset_name = _detect_preset_name(q_lower)
        if not preset_name and ("instagram" in q_lower or "word by word" in q_lower or "reels" in q_lower or "tiktok" in q_lower):
            preset_name = "instagram"

        video_match = re.search(r"([^\s\"\']+\.(?:mp4|mov|mkv|avi|webm))", q_lower)
        srt_match = re.search(r"([^\s\"\']+\.(?:srt|vtt))", q_lower)

        video_file = find_candidate_file(video_match.group(1), active_dir) if video_match else None
        srt_file = find_candidate_file(srt_match.group(1), active_dir) if srt_match else None

        if not video_file and video_match:
            video_file = video_match.group(1)
        if not srt_file and srt_match:
            srt_file = srt_match.group(1)

        if not video_file and selected_videos:
            video_file = selected_videos[0]
        if not srt_file and media_in_folder:
            subs = [f for f in media_in_folder if Path(f).suffix.lower() in {".srt", ".vtt"}]
            if len(subs) == 1:
                srt_file = subs[0]

        # Return the intent even with only partial file resolution — run_aicut
        # produces a helpful "missing X" error when a file is absent. When no
        # SRT is found, the burn auto-transcribes the video's audio locally.
        return {
            "action": "subtitles",
            "video_path": video_file,
            "srt_path": srt_file,
            "preset": preset_name or "instagram",
            "transcribe": srt_file is None,
            "model_size": _detect_whisper_model(q_lower),
            "explorer": explorer,
        }

    # 7. Transcribe / caption generation patterns (faster-whisper STT)
    transcribe_pattern = (
        r"\b(?:transcribe|transcript|subtitle|caption)\b.*?\b(?:audio|video|file|recording|clip)\b"
        r"|\b(?:get|make|create|write)\b.*?\b(?:subtitles?|captions?|transcript|srt)\b"
        r"|\btranscribe\b"
    )
    if re.search(transcribe_pattern, q_lower):
        audio_match = re.search(r"([^\s\"\']+\.(?:mp4|mov|mkv|avi|webm|mp3|wav|m4a|flac|ogg))", q_lower)
        audio_file = find_candidate_file(audio_match.group(1), active_dir) if audio_match else None
        if not audio_file and audio_match:
            audio_file = audio_match.group(1)
        if not audio_file and selected_videos:
            audio_file = selected_videos[0]
        if not audio_file and selected_audios:
            audio_file = selected_audios[0]
        if audio_file:
            return {
                "action": "transcribe",
                "audio_path": audio_file,
                "model_size": _detect_whisper_model(q_lower),
                "explorer": explorer,
            }

    # 8. Explorer context fallback when explicitly asking for explorer/folder media info
    if any(k in q_lower for k in ["what videos", "list videos", "show clips", "explorer media", "selected files", "what files are in folder"]):
        return {
            "action": "explorer_context",
            "explorer": explorer,
        }

    return None


def run_aicut(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute AiCut command directly via aicut_mcp module."""
    if not AICUT_ROOT.exists():
        return {"success": False, "error": f"AiCut repository not found at {AICUT_ROOT}"}

    # Import directly from aicut_mcp.py in AiCut directory
    if str(AICUT_ROOT) not in sys.path:
        sys.path.insert(0, str(AICUT_ROOT))

    try:
        import aicut_mcp

        action = payload.get("action", "")
        if action == "trim":
            video_path = payload.get("video_path") or payload.get("input_path")
            if not video_path:
                return {
                    "success": False,
                    "error": "No video file specified or found in File Explorer. Please open a folder in Explorer or specify a video file (e.g. 'trim dance.mp4 from 10 to 25').",
                }
            return aicut_mcp.trim_video(
                input_path=video_path,
                start_seconds=float(payload.get("start_seconds", 0)),
                end_seconds=float(payload.get("end_seconds", 10)),
                output_path=payload.get("output_path"),
            )

        elif action == "add_song":
            video_path = payload.get("video_path")
            song_path = payload.get("song_path")
            if not video_path or not song_path:
                missing = []
                if not video_path: missing.append("video file")
                if not song_path: missing.append("audio/song file")
                return {
                    "success": False,
                    "error": f"Missing {' and '.join(missing)}. Please select them in File Explorer or provide file names (e.g. 'add song edm.mp3 to dance.mp4').",
                }
            return aicut_mcp.add_song(
                video_path=video_path,
                song_path=song_path,
                output_path=payload.get("output_path"),
                music_volume=float(payload.get("music_volume", 0.25)),
            )

        elif action == "merge":
            input_paths = payload.get("input_paths") or payload.get("inputs") or []
            if len(input_paths) < 2:
                return {
                    "success": False,
                    "error": f"Merging requires at least 2 video files. Select multiple video clips in File Explorer or list them (e.g. 'merge clip1.mp4 and clip2.mp4').",
                }
            return aicut_mcp.merge_videos(
                input_paths=input_paths,
                output_path=payload.get("output_path"),
            )

        elif action == "media_info":
            file_path = payload.get("file_path") or payload.get("video_path")
            if not file_path:
                return {"success": False, "error": "No media file specified to inspect."}
            return aicut_mcp.get_media_info(file_path=file_path)

        elif action == "explorer_context":
            return aicut_mcp.get_explorer_context()

        elif action == "subtitles":
            video_path = payload.get("video_path") or payload.get("input_path")
            srt_path = payload.get("srt_path") or payload.get("subtitle_path")
            if not video_path:
                return {
                    "success": False,
                    "error": "No video file specified or found in File Explorer. Please provide a video file (e.g. 'burn subtitles to dance.mp4').",
                }
            if not srt_path and not payload.get("transcribe"):
                return {
                    "success": False,
                    "error": "No SRT subtitle file specified or found, and transcription is off. Please provide a subtitle file (e.g. 'burn subtitles from captions.srt to dance.mp4') or ask to transcribe the video audio.",
                }
            raw_preset = (payload.get("preset") or "instagram").lower().strip()
            resolved_preset = PRESET_ALIASES.get(raw_preset, raw_preset)
            return aicut_mcp.burn_subtitles(
                video_path=video_path,
                srt_path=srt_path,
                preset=resolved_preset,
                output_path=payload.get("output_path"),
                transcribe=payload.get("transcribe", False) or srt_path is None,
                model_size=payload.get("model_size") or "tiny",
                language=payload.get("language"),
            )

        elif action == "transcribe":
            audio_path = payload.get("audio_path") or payload.get("video_path") or payload.get("input_path")
            if not audio_path:
                return {
                    "success": False,
                    "error": "No audio or video file specified or found. Please provide a media file (e.g. 'transcribe this audio').",
                }
            return aicut_mcp.transcribe_audio(
                audio_path=audio_path,
                model_size=payload.get("model_size") or "tiny",
                language=payload.get("language"),
                srt_output=payload.get("srt_output"),
            )

        else:
            return {"success": False, "error": f"Unknown AiCut action: {action}"}

    except Exception as exc:
        return {"success": False, "error": f"Failed to execute AiCut tool: {exc}"}


def format_aicut_summary(result: dict[str, Any], query: str = "") -> str:
    """Format rich markdown reply for Blinky's UI."""
    if not result.get("success", True) and "error" in result:
        return f"**AiCut Video Editor Error**\n\n{result.get('error', 'Operation failed.')}"

    action = result.get("action", "")

    if action == "trim":
        inp = result.get("input_path", "")
        out = result.get("output_path", "")
        start = result.get("start_seconds", 0)
        end = result.get("end_seconds", 0)
        dur = result.get("duration", 0)
        return (
            f"**Video Trimmed Successfully** \n\n"
            f"- **Input Video**: `{Path(inp).name}`\n"
            f"- **Trim Range**: `{start}s` to `{end}s` (Duration: `{dur}s`)\n"
            f"- **Saved Output**: `{out}`\n\n"
            f"The video clip was cut precisely using FFmpeg stream copying without loss of quality."
        )

    if action == "add_song":
        vid = result.get("video_path", "")
        song = result.get("song_path", "")
        out = result.get("output_path", "")
        vol = int(result.get("music_volume", 0.25) * 100)
        return (
            f"**Background Music Added** \n\n"
            f"- **Video**: `{Path(vid).name}`\n"
            f"- **Audio Track**: `{Path(song).name}`\n"
            f"- **Music Volume**: `{vol}%` (mixed underneath original audio)\n"
            f"- **Saved Output**: `{out}`\n\n"
            f"Audio mixed and encoded with high-quality AAC."
        )

    if action == "merge":
        inputs = result.get("input_paths", [])
        out = result.get("output_path", "")
        clips_str = "\n".join(f"  {idx+1}. `{Path(p).name}`" for idx, p in enumerate(inputs))
        return (
            f"**Videos Merged Successfully** \n\n"
            f"- **Combined {len(inputs)} Clips**:\n{clips_str}\n"
            f"- **Saved Output**: `{out}`\n\n"
            f"All video clips joined seamlessly into a single sequence."
        )

    if action == "subtitles" or "output_path" in result and "preset" in result:
        vid = result.get("output_path", "")
        preset = result.get("preset", "hormozi")
        lines = [
            f"**Styled Subtitles Burned** \n\n",
            f"- **Preset**: `{preset}`\n",
            f"- **Saved Output**: `{vid}`\n",
        ]
        # If transcription happened as part of the burn, surface the text
        trans = result.get("transcription") or {}
        if trans.get("text"):
            lines.append(f"- **Transcribed ({trans.get('language')}, {trans.get('model')})**: {trans['text'][:200]}\n")
        lines.append("\nSubtitles rendered directly into the video frames with the `{0}` style.".format(preset))
        return "".join(lines)

    if action == "transcribe":
        srt = result.get("srt_path", "")
        lang = result.get("language", "?")
        text = (result.get("text") or "")[:300]
        segs = len(result.get("segments", []))
        return (
            f"**Transcription Complete** \n\n"
            f"- **SRT File**: `{srt}`\n"
            f"- **Language**: `{lang}` · **Segments**: `{segs}`\n"
            f"- **Transcript**: {text}\n\n"
            f"Caption file ready to use or burn with a subtitle preset."
        )

    if "duration_seconds" in result:
        name = result.get("file_name", "")
        dur = result.get("duration_seconds", 0)
        w = result.get("width", "N/A")
        h = result.get("height", "N/A")
        vcodec = result.get("video_codec", "N/A")
        acodec = result.get("audio_codec", "N/A")
        fps = result.get("fps", "N/A")
        size = result.get("size_mb", "N/A")
        return (
            f"**Media Information: `{name}`**\n\n"
            f"- **Duration**: `{dur}s`\n"
            f"- **Resolution**: `{w}x{h}` @ `{fps} fps`\n"
            f"- **Video Codec**: `{vcodec}`\n"
            f"- **Audio Codec**: `{acodec}`\n"
            f"- **File Size**: `{size} MB`"
        )

    return json.dumps(result, indent=2)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        try:
            payload = json.loads(arg)
            res = run_aicut(payload)
            print(json.dumps(res, indent=2))
        except Exception:
            # Assume raw query string
            req = resolve_aicut_request(arg)
            if req:
                res = run_aicut(req)
                print(format_aicut_summary(res, arg))
            else:
                print(json.dumps({"error": "Could not parse query as AiCut command"}))
    else:
        # Default status check
        print(json.dumps(get_active_explorer_context(), indent=2))
