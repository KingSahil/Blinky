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
        return {
            "success": success,
            "action": "merge",
            "input_paths": resolved_inputs,
            "output_path": str(out),
            "count": len(resolved_inputs),
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip() if not success else "",
            "error": None if success else (proc.stderr.strip() or proc.stdout.strip() or "Merge failed"),
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
]


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
        else:
            res = {"error": f"Unknown action: {action}", "available_actions": ["trim", "add_song", "merge", "media_info", "explorer_context"]}

        print(json.dumps(res, indent=2))
    except Exception as err:
        print(json.dumps({"success": False, "error": str(err)}))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_cli_direct(sys.argv[1])
    else:
        run_stdio_server()
