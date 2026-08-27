"""Subtitle render + burn — turn SRT into styled ASS, then burn into video.

High-level API:
    render_ass(srt_path, preset) -> str          # ASS text (for preview/manual)
    burn(video, srt, preset, out, fontdir=None)  # ffmpeg burn with libass
    preview(srt, preset, out_png, bg=... )       # single-frame render for inspection

The burn uses ffmpeg's `ass=` filter (styled output). Falls back to
`subtitles=` when no preset applies. Audio is stream-copied.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .presets import PRESETS, build_ass, build_ass_text


def render_ass(srt_path: str | Path, preset_name: str, words_data: list[dict] | None = None) -> str:
    """Generate the styled ASS document for a preset."""
    if preset_name not in PRESETS:
        raise KeyError(f"Unknown preset '{preset_name}'. Available: {', '.join(PRESETS)}")
    return build_ass(srt_path, preset_name, words_data=words_data)


def _write_temp_ass(srt_path: str | Path, preset_name: str, words_data: list[dict] | None = None) -> Path:
    import tempfile

    fd, tmp = tempfile.mkstemp(suffix=".ass", prefix="blinky_subs_")
    import os

    os.close(fd)
    Path(tmp).write_text(render_ass(srt_path, preset_name, words_data=words_data), encoding="utf-8")
    return Path(tmp)


def burn(
    video_path: str | Path,
    srt_path: str | Path,
    preset_name: str,
    out_path: str | Path,
    *,
    words_data: list[dict] | None = None,
    preset_overrides: dict | None = None,
    font_dir: str | None = None,
) -> dict:
    """Burn styled subtitles into a video via ffmpeg (libass).

    Returns {"success", "output_path", "command", "stderr"}.
    """
    video = Path(video_path)
    srt = Path(srt_path)
    out = Path(out_path)
    if not video.exists():
        return {"success": False, "error": f"Video not found: {video}"}
    if not srt.exists():
        return {"success": False, "error": f"SRT not found: {srt}"}
    if preset_name not in PRESETS:
        return {"success": False, "error": f"Unknown preset: {preset_name}"}

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_ass = _write_temp_ass(srt, preset_name, words_data=words_data)
    try:
        # Quote/escape the ASS path for the filter string
        ass_escaped = str(tmp_ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        filter_str = f"ass=filename='{ass_escaped}'"
        if font_dir:
            font_dir_escaped = str(font_dir).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            filter_str += f":fontsdir='{font_dir_escaped}'"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-vf", filter_str,
            "-c:a", "copy",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return {
            "success": proc.returncode == 0 and out.exists(),
            "output_path": str(out),
            "command": " ".join(cmd),
            "stderr": proc.stderr.strip() if proc.returncode != 0 else "",
            "error": None if proc.returncode == 0 else (proc.stderr.strip()[-500:] or "Burn failed"),
        }
    finally:
        try:
            tmp_ass.unlink()
        except OSError:
            pass


def preview(
    srt_path: str | Path,
    preset_name: str,
    out_png: str | Path,
    *,
    bg: str = "darkgray",
    text_size: int = 1920,
    at_seconds: float = 2.0,
) -> dict:
    """Render one frame of subtitles to a PNG for visual inspection.

    Uses a plain colored background (default darkgray). `at_seconds` seeks
    into the timeline so the first subtitle line is on screen.
    Returns {"success", "output_path", "command"}.
    """
    srt = Path(srt_path)
    out = Path(out_png)
    if not srt.exists():
        return {"success": False, "error": f"SRT not found: {srt}"}
    if preset_name not in PRESETS:
        return {"success": False, "error": f"Unknown preset: {preset_name}"}

    tmp_ass = _write_temp_ass(srt, preset_name)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        ass_escaped = str(tmp_ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        filter_str = f"ass=filename='{ass_escaped}'"
        # colorsrc generates a constant-color frame; length covers all subs
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={bg}:s={text_size}x1080:d=4",
            "-vf", filter_str,
            "-ss", str(at_seconds),
            "-frames:v", "1",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return {
            "success": proc.returncode == 0 and out.exists(),
            "output_path": str(out),
            "command": " ".join(cmd),
            "stderr": proc.stderr.strip() if proc.returncode != 0 else "",
        }
    finally:
        try:
            tmp_ass.unlink()
        except OSError:
            pass


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None
