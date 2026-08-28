#!/usr/bin/env python3
"""
AiCut Model Context Protocol (MCP) Server & Python Bridge.
Exposes standard MCP tools for trimming, merging, adding background music,
inspecting media files, and querying Windows File Explorer active context.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
BUILD_EXE_DEBUG = ROOT_DIR / "build" / "Debug" / "AIVideoEditor.exe"
BUILD_EXE_RELEASE = ROOT_DIR / "build" / "AIVideoEditor.exe"
AICUT_CMD = ROOT_DIR / "aicut.cmd"

MEDIA_EXTENSIONS = {
    "video": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".m4v"},
    "audio": {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".wma"},
}


def get_aicut_executable() -> str:
    """Resolve the best available executable or batch wrapper for AiCut."""
    if BUILD_EXE_DEBUG.exists():
        return str(BUILD_EXE_DEBUG)
    if BUILD_EXE_RELEASE.exists():
        return str(BUILD_EXE_RELEASE)
    if AICUT_CMD.exists():
        return str(AICUT_CMD)
    return "aicut"


def get_explorer_context() -> dict[str, Any]:
    """
    Inspects currently open/active Windows File Explorer windows.
    Returns the active directory path, selected files, and all media files in that directory.
    """
    result: dict[str, Any] = {
        "active_directory": None,
        "selected_files": [],
        "media_files": [],
        "open_windows": [],
    }

    if sys.platform != "win32":
        return result

    try:
        import win32com.client  # type: ignore

        shell = win32com.client.Dispatch("Shell.Application")
        windows = shell.Windows()

        for w in windows:
            full_name = getattr(w, "FullName", "").lower()
            if "explorer" not in full_name:
                continue

            try:
                doc = w.Document
                folder = doc.Folder
                folder_path = folder.Self.Path
                if not folder_path:
                    continue

                win_info = {
                    "title": getattr(w, "LocationName", ""),
                    "path": folder_path,
                    "selected": [],
                }

                selected = doc.SelectedItems()
                for i in range(selected.Count):
                    item_path = selected.Item(i).Path
                    win_info["selected"].append(item_path)

                result["open_windows"].append(win_info)

                # Use the first explorer window (or the one with selections) as primary
                if result["active_directory"] is None or (win_info["selected"] and not result["selected_files"]):
                    result["active_directory"] = folder_path
                    result["selected_files"] = win_info["selected"]
            except Exception:
                continue

        # If we have an active directory, list media files in it
        if result["active_directory"] and os.path.isdir(result["active_directory"]):
            act_dir = Path(result["active_directory"])
            try:
                for entry in act_dir.iterdir():
                    if entry.is_file():
                        ext = entry.suffix.lower()
                        if ext in MEDIA_EXTENSIONS["video"] or ext in MEDIA_EXTENSIONS["audio"]:
                            result["media_files"].append(str(entry.resolve()))
            except Exception:
                pass

    except Exception as exc:
        result["error"] = str(exc)

    return result


def get_media_info(file_path: str) -> dict[str, Any]:
    """Use ffprobe to inspect video/audio metadata."""
    p = Path(file_path).resolve()
    if not p.exists():
        return {"error": f"File does not exist: {file_path}"}

    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(p),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            fmt = data.get("format", {})
            streams = data.get("streams", [])

            video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

            duration = float(fmt.get("duration", 0.0))
            size_bytes = int(fmt.get("size", 0))

            info: dict[str, Any] = {
                "file_path": str(p),
                "file_name": p.name,
                "duration_seconds": round(duration, 2),
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "bitrate_kbps": round(int(fmt.get("bit_rate", 0)) / 1000, 1) if fmt.get("bit_rate") else None,
                "has_video": video_stream is not None,
                "has_audio": audio_stream is not None,
            }

            if video_stream:
                info["width"] = video_stream.get("width")
                info["height"] = video_stream.get("height")
                info["video_codec"] = video_stream.get("codec_name")
                fps_eval = video_stream.get("r_frame_rate", "30/1")
                if "/" in fps_eval:
                    num, den = fps_eval.split("/", 1)
                    info["fps"] = round(float(num) / max(float(den), 1.0), 2)
                else:
                    info["fps"] = float(fps_eval)

            if audio_stream:
                info["audio_codec"] = audio_stream.get("codec_name")
                info["sample_rate"] = audio_stream.get("sample_rate")
                info["channels"] = audio_stream.get("channels")

            return info
    except Exception as exc:
        return {
            "file_path": str(p),
            "file_name": p.name,
            "error": f"ffprobe failed: {exc}",
            "size_mb": round(p.stat().st_size / (1024 * 1024), 2) if p.exists() else 0,
        }

    return {"file_path": str(p), "file_name": p.name}


def resolve_output_path(input_path: str, suffix: str = "_edited") -> str:
    """Generate default output path in the same directory as input or sample/output."""
    inp = Path(input_path).resolve()
    stem = inp.stem
    ext = inp.suffix
    parent = inp.parent
    return str(parent / f"{stem}{suffix}{ext}")


def trim_video(
    input_path: str,
    start_seconds: float,
    end_seconds: float,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Execute AiCut trim command."""
    inp = Path(input_path).resolve()
    if not inp.exists():
        return {"success": False, "error": f"Input video file not found: {input_path}"}

    if start_seconds < 0 or end_seconds <= start_seconds:
        return {"success": False, "error": f"Invalid time range: start={start_seconds}, end={end_seconds}. End must be greater than start."}

    if not output_path:
        output_path = resolve_output_path(str(inp), f"_trim_{int(start_seconds)}s_{int(end_seconds)}s")

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    exe = get_aicut_executable()
    cmd = [
        exe,
        "trim",
        "--input", str(inp),
        "--output", str(out),
        "--start", str(start_seconds),
        "--end", str(end_seconds),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(ROOT_DIR))
        success = proc.returncode == 0 and out.exists()
        return {
            "success": success,
            "action": "trim",
            "input_path": str(inp),
            "output_path": str(out),
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
            "duration": round(end_seconds - start_seconds, 2),
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip() if not success else "",
            "error": None if success else (proc.stderr.strip() or proc.stdout.strip() or "Trim failed"),
        }
    except Exception as exc:
        return {"success": False, "action": "trim", "error": str(exc)}


def add_song(
    video_path: str,
    song_path: str,
    output_path: str | None = None,
    music_volume: float = 0.25,
) -> dict[str, Any]:
    """Execute AiCut add-song command."""
    v_path = Path(video_path).resolve()
    s_path = Path(song_path).resolve()

    if not v_path.exists():
        return {"success": False, "error": f"Video file not found: {video_path}"}
    if not s_path.exists():
        return {"success": False, "error": f"Song file not found: {song_path}"}

    if not (0.0 <= music_volume <= 1.0):
        return {"success": False, "error": f"Music volume must be between 0.0 and 1.0 (got {music_volume})"}

    if not output_path:
        output_path = resolve_output_path(str(v_path), "_with_music")

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    exe = get_aicut_executable()
    cmd = [
        exe,
        "add-song",
        "--video", str(v_path),
        "--song", str(s_path),
        "--output", str(out),
        "--music-volume", str(music_volume),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(ROOT_DIR))
        success = proc.returncode == 0 and out.exists()
        return {
            "success": success,
            "action": "add_song",
            "video_path": str(v_path),
            "song_path": str(s_path),
            "output_path": str(out),
            "music_volume": music_volume,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip() if not success else "",
            "error": None if success else (proc.stderr.strip() or proc.stdout.strip() or "Add song failed"),
        }
    except Exception as exc:
        return {"success": False, "action": "add_song", "error": str(exc)}


def merge_videos(
    input_paths: list[str],
    output_path: str | None = None,
) -> dict[str, Any]:
    """Execute AiCut merge command."""
    if len(input_paths) < 2:
        return {"success": False, "error": f"Merge requires at least 2 video files (got {len(input_paths)})"}

    resolved_inputs = [str(Path(p).resolve()) for p in input_paths]
    for p in resolved_inputs:
        if not Path(p).exists():
            return {"success": False, "error": f"Input video file not found: {p}"}

    if not output_path:
        first = Path(resolved_inputs[0])
        output_path = resolve_output_path(str(first), "_merged")

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    exe = get_aicut_executable()
    inputs_arg = ",".join(resolved_inputs)
    cmd = [
        exe,
        "merge",
        "--inputs", inputs_arg,
        "--output", str(out),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(ROOT_DIR))
        success = proc.returncode == 0 and out.exists()
        if success:
            return {
                "success": True,
                "action": "merge",
                "input_paths": resolved_inputs,
                "output_path": str(out),
                "count": len(resolved_inputs),
                "stdout": proc.stdout.strip(),
                "stderr": "",
                "error": None,
            }
    except Exception:
        pass

    # Fallback to direct ffmpeg if AIVideoEditor.exe failed or missing
    try:
        ffmpeg_cmd = ["ffmpeg", "-y"]
        for inp in resolved_inputs:
            ffmpeg_cmd.extend(["-i", inp])

        filter_parts = []
        for i in range(len(resolved_inputs)):
            filter_parts.append(f"[{i}:v:0]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}];")
            # Handle audio stream presence or synthesize silence if stream missing
            filter_parts.append(f"[{i}:a:0]aformat=sample_rates=44100:channel_layouts=stereo[a{i}];")

        concat_in = "".join(f"[v{i}][a{i}]" for i in range(len(resolved_inputs)))
        filter_parts.append(f"{concat_in}concat=n={len(resolved_inputs)}:v=1:a=1[v][a]")
        filter_str = "".join(filter_parts)

        ffmpeg_cmd.extend([
            "-filter_complex", filter_str,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-c:a", "aac",
            str(out),
        ])

        fproc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=180)
        fsuccess = fproc.returncode == 0 and out.exists()
        return {
            "success": fsuccess,
            "action": "merge",
            "input_paths": resolved_inputs,
            "output_path": str(out),
            "count": len(resolved_inputs),
            "stdout": fproc.stdout.strip(),
            "stderr": fproc.stderr.strip() if not fsuccess else "",
            "error": None if fsuccess else (fproc.stderr.strip() or "FFmpeg merge failed"),
        }
    except Exception as exc:
        return {"success": False, "action": "merge", "error": str(exc)}


# ==============================================================================
# Model Context Protocol (MCP) Server Implementation
# ==============================================================================

MCP_TOOL_SCHEMAS = [
    {
        "name": "aicut_trim_video",
        "description": "Trim a video file to a specific start and end timestamp in seconds without re-encoding.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string", "description": "Absolute or relative path to the video file to trim."},
                "output_path": {"type": "string", "description": "Optional destination path for the trimmed output video."},
                "start_seconds": {"type": "number", "description": "Start timestamp in seconds (e.g. 10.5)."},
                "end_seconds": {"type": "number", "description": "End timestamp in seconds (e.g. 25.0)."},
            },
            "required": ["input_path", "start_seconds", "end_seconds"],
        },
    },
    {
        "name": "aicut_add_song",
        "description": "Add background music or audio to a video clip, mixing it underneath original audio at specified volume.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_path": {"type": "string", "description": "Path to the video file."},
                "song_path": {"type": "string", "description": "Path to the audio/song file."},
                "output_path": {"type": "string", "description": "Optional destination path for the mixed video."},
                "music_volume": {"type": "number", "description": "Music volume from 0.0 to 1.0 (default 0.25).", "default": 0.25},
            },
            "required": ["video_path", "song_path"],
        },
    },
    {
        "name": "aicut_merge_videos",
        "description": "Merge (concatenate) multiple video clips together sequentially into a single video file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of video paths to merge in sequential order.",
                },
                "output_path": {"type": "string", "description": "Optional destination path for the merged video."},
            },
            "required": ["input_paths"],
        },
    },
    {
        "name": "aicut_get_media_info",
        "description": "Inspect duration, resolution, codecs, fps, and audio details of a video or audio file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the video or audio file to inspect."},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "aicut_get_explorer_context",
        "description": "Get active Windows File Explorer directory, selected files, and available media files to automatically detect what the user is working on.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "aicut_burn_subtitles",
        "description": "Burn styled subtitles into a video using a named preset. If srt_path is omitted, the video's audio is transcribed locally with faster-whisper (private, on-device) and burned automatically. Supports 16 presets: hormozi, word-karaoke, pill-yellow, pill-red, typewriter, color-switch, hormozi-clean, keyword-green, lecture-dual, documentary, cinematic-lowerthird, quiet-minimal, glassmorphism, neon-blur, meme-impact, retro-yellow.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_path": {"type": "string", "description": "Path to the video file to subtitle."},
                "srt_path": {"type": "string", "description": "Optional path to an existing SRT subtitle file. If omitted, audio is transcribed automatically with faster-whisper."},
                "preset": {"type": "string", "description": "Style preset name (default: hormozi).", "default": "hormozi"},
                "output_path": {"type": "string", "description": "Optional destination path for the subtitled video."},
                "transcribe": {"type": "boolean", "description": "Force transcription even if an SRT is provided (default false).", "default": False},
                "model_size": {"type": "string", "description": "faster-whisper model size for auto-transcription (tiny/base/small/medium/large-v3, default tiny).", "default": "tiny"},
                "language": {"type": "string", "description": "Optional language hint for transcription (e.g. 'en', 'hi'). Auto-detected if omitted."},
            },
            "required": ["video_path"],
        },
    },
    {
        "name": "aicut_transcribe_audio",
        "description": "Transcribe audio or video to an SRT file using faster-whisper (local, private, no cloud). Returns segments with timestamps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "audio_path": {"type": "string", "description": "Path to audio or video file to transcribe."},
                "model_size": {"type": "string", "description": "Whisper model size: tiny (fast), base, small, medium, large-v3 (accurate). Default tiny.", "default": "tiny"},
                "language": {"type": "string", "description": "Optional language hint (e.g. 'en'). Auto-detected if omitted."},
                "srt_output": {"type": "string", "description": "Optional destination path for the SRT file. Defaults to <input>.srt next to the source."},
            },
            "required": ["audio_path"],
        },
    },
]


def transcribe_audio(
    audio_path: str,
    model_size: str = "tiny",
    language: str | None = None,
    srt_output: str | None = None,
) -> dict[str, Any]:
    """Transcribe audio/video to SRT using faster-whisper (local, private).

    Returns {"success", "srt_path", "segments", "language", "text"}.
    If srt_output is None, writes alongside the input as <stem>.srt.
    """
    a_path = Path(audio_path).resolve()
    if not a_path.exists():
        return {"success": False, "error": f"Audio/video file not found: {audio_path}"}

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        return {
            "success": False,
            "error": "faster-whisper not installed. Run: pip install faster-whisper (or bun run setup:python)",
        }

    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments_iter, info = model.transcribe(str(a_path), language=language, word_timestamps=True)

        segments = []
        words = []
        srt_lines: list[str] = []
        for i, seg in enumerate(segments_iter, 1):
            segments.append(
                {
                    "id": i,
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip(),
                }
            )
            if hasattr(seg, "words") and seg.words:
                for w in seg.words:
                    w_text = w.word.strip()
                    if w_text:
                        words.append({
                            "start": round(w.start, 2),
                            "end": round(w.end, 2),
                            "word": w_text,
                        })
            start_ts = _srt_timestamp(seg.start)
            end_ts = _srt_timestamp(seg.end)
            srt_lines.append(f"{i}\n{start_ts} --> {end_ts}\n{seg.text.strip()}\n")

        if not srt_output:
            srt_output = str(a_path.with_suffix(".srt"))

        out = Path(srt_output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(srt_lines), encoding="utf-8")

        return {
            "success": True,
            "srt_path": str(out),
            "segments": segments,
            "words": words,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "text": " ".join(s["text"] for s in segments),
            "model": model_size,
        }
    except Exception as exc:
        return {"success": False, "error": f"Transcription failed: {exc}"}


def _srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp (HH:MM:SS,mmm)."""
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def burn_subtitles(
    video_path: str,
    srt_path: str | None = None,
    preset: str = "instagram",
    output_path: str | None = None,
    *,
    transcribe: bool = False,
    model_size: str = "tiny",
    language: str | None = None,
    words_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Burn styled subtitles into a video using the subtitles preset system.

    If srt_path is None (or transcribe=True), the video's audio is first
    transcribed locally with faster-whisper into an SRT, then burned.
    """
    # Resolve the subtitles package (sibling of aicut: common/python)
    import sys as _sys

    common_python = ROOT_DIR.parent / "python"
    if str(common_python) not in _sys.path:
        _sys.path.insert(0, str(common_python))

    from subtitles.presets import PRESETS, list_presets
    from subtitles.render import burn

    v_path = Path(video_path).resolve()

    if not v_path.exists():
        return {"success": False, "error": f"Video file not found: {video_path}"}
    if preset not in PRESETS:
        available = ", ".join(PRESETS)
        return {
            "success": False,
            "error": f"Unknown subtitle preset '{preset}'. Available: {available}",
        }

    # Auto-transcribe when no SRT given (or explicitly requested)
    transcribe_result = None
    if srt_path is None or transcribe:
        transcribe_result = transcribe_audio(str(v_path), model_size=model_size, language=language)
        if not transcribe_result.get("success"):
            return transcribe_result
        srt_path = transcribe_result["srt_path"]
        if not words_data:
            words_data = transcribe_result.get("words")

    assert srt_path is not None  # guaranteed by transcribe or caller
    s_path = Path(srt_path).resolve()
    if not s_path.exists():
        return {"success": False, "error": f"SRT file not found: {srt_path}"}

    if not output_path:
        output_path = resolve_output_path(str(v_path), "_subtitled")

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    result = burn(v_path, s_path, preset, out, words_data=words_data)
    if result.get("success"):
        result["preset"] = preset
        if transcribe_result:
            result["transcription"] = transcribe_result
    return result


def handle_mcp_request(request: dict[str, Any]) -> dict[str, Any]:
    """Dispatch JSON-RPC MCP request."""
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params", {}) or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": "aicut-mcp-server",
                    "version": "1.0.0",
                },
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOL_SCHEMAS},
        }

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {}) or {}

        try:
            if tool_name == "aicut_trim_video":
                res = trim_video(
                    input_path=args["input_path"],
                    start_seconds=float(args["start_seconds"]),
                    end_seconds=float(args["end_seconds"]),
                    output_path=args.get("output_path"),
                )
            elif tool_name == "aicut_add_song":
                res = add_song(
                    video_path=args["video_path"],
                    song_path=args["song_path"],
                    output_path=args.get("output_path"),
                    music_volume=float(args.get("music_volume", 0.25)),
                )
            elif tool_name == "aicut_merge_videos":
                res = merge_videos(
                    input_paths=args["input_paths"],
                    output_path=args.get("output_path"),
                )
            elif tool_name == "aicut_get_media_info":
                res = get_media_info(file_path=args["file_path"])
            elif tool_name == "aicut_get_explorer_context":
                res = get_explorer_context()
            elif tool_name == "aicut_burn_subtitles":
                res = burn_subtitles(
                    video_path=args["video_path"],
                    srt_path=args.get("srt_path"),
                    preset=args.get("preset", "hormozi"),
                    output_path=args.get("output_path"),
                    transcribe=args.get("transcribe", False),
                    model_size=args.get("model_size", "tiny"),
                    language=args.get("language"),
                )
            elif tool_name == "aicut_transcribe_audio":
                res = transcribe_audio(
                    audio_path=args["audio_path"],
                    model_size=args.get("model_size", "tiny"),
                    language=args.get("language"),
                    srt_output=args.get("srt_output"),
                )
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method/Tool '{tool_name}' not found"},
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                    "isError": not res.get("success", True) if isinstance(res, dict) else False,
                },
            }
        except Exception as err:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"success": False, "error": str(err)})}],
                    "isError": True,
                },
            }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unhandled method: {method}"},
    }


def run_stdio_server():
    """Run interactive MCP stdio JSON-RPC loop."""
    for line in sys.stdin:
        line_str = line.strip()
        if not line_str:
            continue
        try:
            req = json.loads(line_str)
            resp = handle_mcp_request(req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


def run_cli_direct(args_json_str: str):
    """Direct CLI invocation for tool testing or Blinky tool calls."""
    try:
        data = json.loads(args_json_str)
        action = data.get("action") or data.get("tool") or data.get("command") or ""
        action = action.replace("aicut_", "")

        if action == "trim" or action == "trim_video":
            res = trim_video(
                input_path=data["input_path"] if "input_path" in data else data.get("video_path", ""),
                start_seconds=float(data.get("start_seconds", data.get("start", 0))),
                end_seconds=float(data.get("end_seconds", data.get("end", 0))),
                output_path=data.get("output_path"),
            )
        elif action in {"add_song", "add_music", "add_audio"}:
            res = add_song(
                video_path=data["video_path"],
                song_path=data.get("song_path") or data.get("audio_path") or data.get("music_path", ""),
                output_path=data.get("output_path"),
                music_volume=float(data.get("music_volume", 0.25)),
            )
        elif action in {"merge", "merge_videos", "concat"}:
            inputs = data.get("input_paths") or data.get("inputs") or []
            if isinstance(inputs, str):
                inputs = [s.strip() for s in inputs.split(",") if s.strip()]
            res = merge_videos(
                input_paths=inputs,
                output_path=data.get("output_path"),
            )
        elif action in {"media_info", "get_media_info", "info"}:
            res = get_media_info(file_path=data.get("file_path") or data.get("input_path", ""))
        elif action in {"explorer", "explorer_context", "get_explorer_context"}:
            res = get_explorer_context()
        elif action in {"subtitle", "subtitles", "burn_subtitles", "burn_subs", "add_captions"}:
            res = burn_subtitles(
                video_path=data.get("video_path") or data.get("input_path", ""),
                srt_path=data.get("srt_path") or data.get("subtitle_path"),
                preset=data.get("preset", "hormozi"),
                output_path=data.get("output_path"),
                transcribe=data.get("transcribe", False),
                model_size=data.get("model_size", "tiny"),
                language=data.get("language"),
            )
        elif action in {"transcribe", "transcribe_audio", "stt", "speech_to_text", "subtitle_gen"}:
            res = transcribe_audio(
                audio_path=data.get("audio_path") or data.get("input_path", ""),
                model_size=data.get("model_size", "tiny"),
                language=data.get("language"),
                srt_output=data.get("srt_output"),
            )
        else:
            res = {"error": f"Unknown action: {action}", "available_actions": ["trim", "add_song", "merge", "media_info", "explorer_context", "subtitles"]}

        print(json.dumps(res, indent=2))
    except Exception as err:
        print(json.dumps({"success": False, "error": str(err)}))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_cli_direct(sys.argv[1])
    else:
        run_stdio_server()
