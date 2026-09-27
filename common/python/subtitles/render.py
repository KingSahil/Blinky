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


_FAST_ENCODER_ARGS: list[str] | None = None


def get_fast_encoder_args() -> list[str]:
    """Detect the fastest available H.264 video encoder.
    Prefers NVIDIA NVENC (GPU), falling back to fast CPU libx264.
    """
    global _FAST_ENCODER_ARGS
    if _FAST_ENCODER_ARGS is not None:
        return list(_FAST_ENCODER_ARGS)

    # Check for NVIDIA NVENC support
    try:
        test_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "nullsrc=s=256x256:d=0.04",
            "-c:v", "h264_nvenc",
            "-f", "null", "-"
        ]
        res = subprocess.run(test_cmd, capture_output=True, timeout=3)
        if res.returncode == 0:
            _FAST_ENCODER_ARGS = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "22", "-pix_fmt", "yuv420p"]
            return list(_FAST_ENCODER_ARGS)
    except Exception:
        pass

    # CPU fallback: preset veryfast (5x faster than default medium)
    _FAST_ENCODER_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
    return list(_FAST_ENCODER_ARGS)


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

        encoder_args = get_fast_encoder_args()
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-vf", filter_str,
            *encoder_args,
            "-c:a", "copy",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        # If hardware encoding failed unexpectedly, retry once with CPU fallback
        if proc.returncode != 0 and "-c:v" in encoder_args and "h264_nvenc" in encoder_args:
            cpu_fallback_cmd = [
                "ffmpeg", "-y",
                "-i", str(video),
                "-vf", filter_str,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                str(out),
            ]
            proc = subprocess.run(cpu_fallback_cmd, capture_output=True, text=True, timeout=600)
            cmd = cpu_fallback_cmd

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
