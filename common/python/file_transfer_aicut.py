"""Structured AiCut entry point for files received over the Blinky remote."""

from __future__ import annotations

import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

from tools.aicut_tool import resolve_aicut_request, run_aicut


def run_transfer_edit(instruction: str, input_path: str) -> dict:
    source = Path(input_path).resolve(strict=True)
    output_dir = Path(os.environ["BLINKY_TRANSFER_OUTPUT_DIR"]).resolve()
    transfer_id = os.environ["BLINKY_TRANSFER_ID"]
    if not source.is_file():
        return {"success": False, "error": "The uploaded file is unavailable."}

    isolated_explorer = {
        "active_directory": None,
        "selected_files": [],
        "selected_videos": [],
        "selected_audios": [],
        "media_files_in_folder": [],
    }
    request = resolve_aicut_request(
        instruction,
        context_files=[str(source)],
        explorer_context=isolated_explorer,
    )
    if not request:
        return {
            "success": False,
            "error": "AiCut could not identify an edit. Try a supported request such as trimming by time, adding captions, or transcribing.",
        }

    action = request.get("action")
    allowed = {"trim", "subtitles", "transcribe", "pipeline"}
    if action not in allowed:
        return {
            "success": False,
            "error": "This AiCut request needs additional media files. The mobile transfer currently supplies one uploaded file per edit.",
        }
    if action == "pipeline" and (request.get("song_path") or request.get("input_paths")):
        return {
            "success": False,
            "error": "This AiCut pipeline resolved additional desktop files. Upload each required media file before requesting this edit.",
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    if action == "transcribe":
        extension = ".srt"
        request["audio_path"] = str(source)
        request["srt_output"] = str(output_dir / f".{transfer_id}.part{extension}")
    else:
        extension = source.suffix.lower() or ".mp4"
        request["video_path"] = str(source)
        request["input_paths"] = None
        request["song_path"] = None
        request["output_path"] = str(output_dir / f".{transfer_id}.part{extension}")

    result = run_aicut(request)
    if not result.get("success"):
        return result

    output_path = result.get("output_path") or result.get("srt_path")
    if not output_path:
        return {"success": False, "error": "AiCut finished without returning an output path."}
    final_output = Path(output_path).resolve()
    if final_output.parent != output_dir or not final_output.is_file():
        return {"success": False, "error": "AiCut output did not remain inside Blinky\u2019s Edited folder."}

    return {"success": True, "output_path": str(final_output), "action": result.get("action", action)}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        with redirect_stdout(sys.stderr):
            result = run_transfer_edit(payload.get("instruction", ""), payload.get("input_path", ""))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("success") else 1
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
