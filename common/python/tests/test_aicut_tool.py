import pytest
from pathlib import Path
from tools.aicut_tool import AICUT_ROOT, resolve_aicut_request, run_aicut, format_aicut_summary, find_candidate_file

def test_resolve_trim_query():
    q = "trim dance.mp4 from 10 to 25 seconds"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "trim"
    assert res["start_seconds"] == 10.0
    assert res["end_seconds"] == 25.0
    assert res["video_path"] is not None
    assert "dance.mp4" in res["video_path"].lower()

def test_resolve_add_song_query():
    q = "add song edm.mp3 to dance.mp4 with 35% volume"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "add_song"
    assert res["music_volume"] == 0.35
    assert res["song_path"] is not None
    assert res["video_path"] is not None

def test_resolve_merge_query():
    q = "merge clip1.mp4 and clip2.mp4"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "merge"

def test_find_candidate_file_sample():
    found = find_candidate_file("dance.mp4")
    assert found is not None
    assert Path(found).exists()

def test_run_trim_execution():
    dance_path = find_candidate_file("dance.mp4")
    assert dance_path is not None
    res = run_aicut({
        "action": "trim",
        "video_path": dance_path,
        "start_seconds": 1.0,
        "end_seconds": 3.0,
    })
    assert res.get("success") is True
    assert "output_path" in res
    assert Path(res["output_path"]).exists()

def test_run_media_info():
    dance_path = find_candidate_file("dance.mp4")
    res = run_aicut({
        "action": "media_info",
        "file_path": dance_path,
    })
    assert res.get("duration_seconds") is not None
    assert res.get("has_video") is True

def test_format_aicut_summary():
    result = {
        "success": True,
        "action": "trim",
        "input_path": "C:\\dance.mp4",
        "output_path": "C:\\dance_trimmed.mp4",
        "start_seconds": 2,
        "end_seconds": 6,
        "duration": 4,
    }
    summary = format_aicut_summary(result)
    assert "Video Trimmed Successfully" in summary
    assert "dance.mp4" in summary


def test_resolve_merge_with_referenced_files():
    video1 = r"C:\Projects\AiCut\sample\input\dance.mp4"
    video2 = r"C:\Projects\AiCut\sample\input\dance.mp4"
    query = f"[Referenced Files: {video1}, {video2}]\nmerge these videos"
    resolved = resolve_aicut_request(query)
    assert resolved is not None
    assert resolved["action"] == "merge"
    assert len(resolved["input_paths"]) >= 2


def test_resolve_add_song_with_referenced_files_and_phrasings():
    video = r"C:\Projects\AiCut\sample\input\dance.mp4"
    song = r"C:\Projects\AiCut\sample\input\edm.mp3"
    query = f"[Referenced Files: {video}, {song}]\nadd this song in this video"
    resolved = resolve_aicut_request(query)
    assert resolved is not None
    assert resolved["action"] == "add_song"
    assert resolved["video_path"] == video
    assert resolved["song_path"] == song


# ── Subtitle / caption integration ────────────────────────────────────

def test_resolve_subtitle_burn_query():
    q = "burn subtitles to /tmp/test_video.mp4 with hormozi preset"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res["video_path"] == "/tmp/test_video.mp4"
    assert res["preset"] == "hormozi"


def test_resolve_subtitle_subs_shorthand():
    q = "burn subs from /tmp/test_subs.srt to /tmp/test_video.mp4 using pill-yellow"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res["srt_path"] == "/tmp/test_subs.srt"
    assert res["video_path"] == "/tmp/test_video.mp4"
    assert res["preset"] == "pill-yellow"


def test_resolve_subtitle_inline_preset():
    q = "subtitle this video with neon-blur"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res["preset"] == "neon-blur"


def test_resolve_subtitle_no_files_returns_intent():
    # Intent should be returned even when files are unresolved (run_aicut gives
    # a helpful "missing X" error).
    q = "add subtitles to the video"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res["video_path"] is None


def test_run_subtitle_missing_video_error():
    res = run_aicut({"action": "subtitles", "srt_path": "/tmp/test_subs.srt"})
    assert res.get("success") is False
    assert "No video file" in res.get("error", "")


def test_run_subtitle_missing_srt_error():
    res = run_aicut({"action": "subtitles", "video_path": "/tmp/test_video.mp4"})
    assert res.get("success") is False
    assert "No SRT subtitle" in res.get("error", "")


def test_format_subtitle_summary():
    result = {
        "success": True,
        "action": "subtitles",
        "output_path": "/tmp/out.mp4",
        "preset": "hormozi",
    }
    summary = format_aicut_summary(result, "burn subtitles")
    assert "Styled Subtitles Burned" in summary
    assert "hormozi" in summary


# ── faster-whisper transcription integration ─────────────────────────

def test_resolve_transcribe_query():
    q = "transcribe this video /tmp/test_video.mp4"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "transcribe"
    assert res["audio_path"] == "/tmp/test_video.mp4"
    assert res["model_size"] == "tiny"


def test_resolve_make_subtitles_query():
    q = "make subtitles from /tmp/test_video.mp4"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "transcribe"
    assert res["audio_path"] == "/tmp/test_video.mp4"


def test_resolve_subtitle_no_srt_auto_transcribes():
    q = "burn subtitles to /tmp/test_video.mp4 with hormozi"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res["srt_path"] is None
    assert res["transcribe"] is True


def test_resolve_subtitle_with_srt_does_not_transcribe():
    q = "burn subtitles from /tmp/test_subs.srt to /tmp/test_video.mp4 with hormozi"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res["srt_path"] == "/tmp/test_subs.srt"
    assert res["transcribe"] is False


def test_detect_whisper_model():
    from tools.aicut_tool import _detect_whisper_model
    assert _detect_whisper_model("transcribe with small model") == "small"
    assert _detect_whisper_model("use large-v3") == "large-v3"
    assert _detect_whisper_model("just transcribe") == "tiny"


def test_run_transcribe_missing_audio_error():
    res = run_aicut({"action": "transcribe"})
    assert res.get("success") is False
    assert "No audio or video" in res.get("error", "")


def test_format_transcribe_summary():
    result = {
        "success": True,
        "action": "transcribe",
        "srt_path": "/tmp/out.srt",
        "language": "en",
        "text": "hello world",
        "segments": [{"id": 1}],
    }
    summary = format_aicut_summary(result)
    assert "Transcription Complete" in summary
    assert "/tmp/out.srt" in summary
