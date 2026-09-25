"""Structured AiCut entry point for files received over the Blinky remote."""

from __future__ import annotations

import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

from tools.aicut_tool import resolve_aicut_request, run_aicut


def run_transfer_edit(
    instruction: str,
    input_path: str,
    input_paths: list[str] | None = None,
) -> dict:
    if input_paths:
        sources = [Path(p).resolve(strict=True) for p in input_paths if p]
    elif input_path:
        sources = [Path(input_path).resolve(strict=True)]
    else:
        return {"success": False, "error": "No input files provided for edit."}

    if not sources:
        return {"success": False, "error": "No valid input files provided for edit."}

    for source in sources:
        if not source.is_file():
            return {"success": False, "error": f"The uploaded file is unavailable: {source.name}"}

    primary_source = sources[0]
    output_dir = Path(os.environ["BLINKY_TRANSFER_OUTPUT_DIR"]).resolve()
    transfer_id = os.environ["BLINKY_TRANSFER_ID"]

    isolated_explorer = {
        "active_directory": None,
        "selected_files": [],
        "selected_videos": [],
        "selected_audios": [],
        "media_files_in_folder": [],
    }

    effective_instruction = (instruction or "").strip()
    context_files = [str(s) for s in sources]

    if not effective_instruction:
        vids = [s for s in sources if s.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm"}]
        auds = [s for s in sources if s.suffix.lower() in {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg"}]
        if len(vids) >= 2:
            effective_instruction = "merge these videos"
        elif len(vids) == 1 and len(auds) >= 1:
            effective_instruction = "add this song to the video"
        elif len(vids) == 1:
            effective_instruction = "burn captions"
        else:
            effective_instruction = "merge"

    request = resolve_aicut_request(
        effective_instruction,
        context_files=context_files,
        explorer_context=isolated_explorer,
    )
    if not request:
        return {
            "success": False,
            "error": "AiCut could not identify an edit. Try a supported request such as merging videos, adding audio, trimming, or adding captions.",
        }

    action = request.get("action")
    allowed = {"trim", "subtitles", "transcribe", "pipeline", "merge", "add_song"}
    if action not in allowed:
        return {
            "success": False,
            "error": f"This AiCut action '{action}' is not supported for remote transfers.",
        }

    # Verify that pipeline or composite requests do not resolve non-uploaded desktop files
    if action == "pipeline":
        req_inputs = request.get("input_paths") or ([request.get("video_path")] if request.get("video_path") else [])
        req_song = request.get("song_path")
        for rip in req_inputs:
            if rip and str(Path(rip).resolve()) not in context_files:
                return {
                    "success": False,
                    "error": "This AiCut pipeline resolved external desktop files. Upload all required files first.",
                }
        if req_song and str(Path(req_song).resolve()) not in context_files:
            return {
                "success": False,
                "error": "This AiCut pipeline resolved an external audio file. Upload all required files first.",
            }

    output_dir.mkdir(parents=True, exist_ok=True)
    if action == "transcribe":
        extension = ".srt"
        request["audio_path"] = request.get("audio_path") or str(primary_source)
        request["srt_output"] = str(output_dir / f".{transfer_id}.part{extension}")
    else:
        # Determine the appropriate video extension
        target_video = request.get("video_path")
        if not target_video and request.get("input_paths"):
            target_video = request["input_paths"][0]
        if not target_video:
            for s in sources:
                if s.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
                    target_video = str(s)
                    break

        if target_video:
            extension = Path(target_video).suffix.lower() or ".mp4"
        else:
            extension = primary_source.suffix.lower() or ".mp4"

        # A video edit or merge must never output with an audio extension
        if extension in {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".wma", ".opus"}:
            extension = ".mp4"

        request["output_path"] = str(output_dir / f".{transfer_id}.part{extension}")
        if action == "merge" and not request.get("input_paths"):
            request["input_paths"] = context_files

    result = run_aicut(request)
    if not result.get("success"):
        return result

    output_path = result.get("output_path") or result.get("srt_path")
    if not output_path:
        return {"success": False, "error": "AiCut finished without returning an output path."}
    final_output = Path(output_path).resolve()
    if final_output.parent != output_dir or not final_output.is_file():
        return {"success": False, "error": "AiCut output did not remain inside Blinky’s Edited folder."}

    return {"success": True, "output_path": str(final_output), "action": result.get("action", action)}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        with redirect_stdout(sys.stderr):
            result = run_transfer_edit(
                payload.get("instruction", ""),
                payload.get("input_path", ""),
                payload.get("input_paths"),
            )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("success") else 1
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
