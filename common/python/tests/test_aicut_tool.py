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
    video1 = str((AICUT_ROOT / "sample" / "input" / "dance.mp4").resolve())
    video2 = str((AICUT_ROOT / "sample" / "input" / "dance_trim_1s_3s.mp4").resolve())
    query = f"[Referenced Files: {video1}, {video2}]\nmerge these videos"
    resolved = resolve_aicut_request(query)
    assert resolved is not None
    assert resolved["action"] == "merge"
    assert len(resolved["input_paths"]) >= 2


def test_resolve_add_song_with_referenced_files_and_phrasings():
    video = str((AICUT_ROOT / "sample" / "input" / "dance.mp4").resolve())
    song = str((AICUT_ROOT / "sample" / "input" / "edm.mp3").resolve())
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


def test_resolve_subtitle_no_files_returns_intent(monkeypatch):
    monkeypatch.setattr(
        "tools.aicut_tool.get_active_explorer_context",
        lambda: {"active_directory": None, "selected_files": [], "selected_videos": [], "selected_audios": [], "media_files_in_folder": []},
    )
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


def test_resolve_subtitle_word_by_word_instagram():
    q = "i want word by word instagram like"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res["preset"] == "instagram"


def test_resolve_subtitle_add_hormozi():
    q = "add hormozi subtitles"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res["preset"] == "hormozi"


def test_resolve_subtitle_neon_alias():
    q = "add neon subtitles"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res["preset"] == "neon-blur"


def test_resolve_subtitle_pill_yellow():
    q = "burn pill-yellow captions"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res["preset"] == "pill-yellow"


def test_resolve_subtitle_karaoke():
    q = "word-karaoke captions"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res["preset"] == "word-karaoke"


def test_format_subtitle_summary():
    result = {
        "success": True,
        "action": "subtitles",
        "output_path": "/tmp/out.mp4",
        "preset": "instagram",
    }
    summary = format_aicut_summary(result, "burn subtitles")
    assert "Styled Subtitles Burned" in summary
    assert "instagram" in summary


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


def test_build_ass_instagram_word_by_word():
    from subtitles.presets import build_ass_text
    srt = "1\n00:00:01,000 --> 00:00:03,000\nHello world welcome\n"
    ass = build_ass_text(srt, "instagram")
    assert "[Script Info]" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass
    assert "Dialogue:" in ass
    assert "HELLO" in ass
    assert "\\c&H04C2F7&" in ass  # Yellow active highlight tag


def test_build_ass_instagram_with_whisper_words():
    from subtitles.presets import build_ass_text
    words = [
        {"start": 1.0, "end": 1.4, "word": "Hello"},
        {"start": 1.4, "end": 1.8, "word": "Instagram"},
        {"start": 1.8, "end": 2.3, "word": "Reels"},
    ]
    ass = build_ass_text("", "instagram", words_data=words)
    assert "Dialogue:" in ass
    assert "HELLO" in ass
    assert "INSTAGRAM" in ass
    assert "REELS" in ass
    assert "\\c&H04C2F7&" in ass


def test_build_ass_neon_blur():
    from subtitles.presets import build_ass_text
    srt = "1\n00:00:01,000 --> 00:00:03,000\nCyber punk style\n"
    ass = build_ass_text(srt, "neon-blur")
    assert "CYBER" in ass
    assert "\\c&HFFFF00&" in ass  # Cyan active highlight tag


# ── Composite / Pipeline video editing integration ──────────────────

def test_resolve_merge_with_audio_and_captions_explorer(monkeypatch):
    monkeypatch.setattr(
        "tools.aicut_tool.get_active_explorer_context",
        lambda: {
            "active_directory": "C:\\Users\\sahil\\Downloads\\Video",
            "selected_files": [
                "C:\\Users\\sahil\\Downloads\\Video\\quicksort.mp4",
                "C:\\Users\\sahil\\Downloads\\Video\\scuba.mp4",
                "C:\\Users\\sahil\\Downloads\\Video\\HIP HOP BEATS.mp3",
            ],
            "selected_videos": [
                "C:\\Users\\sahil\\Downloads\\Video\\quicksort.mp4",
                "C:\\Users\\sahil\\Downloads\\Video\\scuba.mp4",
            ],
            "selected_audios": [
                "C:\\Users\\sahil\\Downloads\\Video\\HIP HOP BEATS.mp3",
            ],
            "media_files_in_folder": [],
        },
    )
    q = "merged them all and add captions in the merged video"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "pipeline"
    assert len(res["input_paths"]) == 2
    assert "quicksort.mp4" in res["input_paths"][0]
    assert "scuba.mp4" in res["input_paths"][1]
    assert "HIP HOP BEATS.mp3" in res["song_path"]
    assert res["subtitles"] is True
    assert res["preset"] == "instagram"


def test_resolve_merge_and_audio_explicit_query():
    q = "merge clip1.mp4 and clip2.mp4 with beats.mp3"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "pipeline"
    assert len(res["input_paths"]) == 2
    assert res["song_path"] is not None
    assert "beats.mp3" in res["song_path"]


def test_resolve_merge_and_subtitles_explicit_query():
    q = "merge clip1.mp4 and clip2.mp4 and add captions with hormozi"
    res = resolve_aicut_request(q)
    assert res is not None
    assert res["action"] == "pipeline"
    assert len(res["input_paths"]) == 2
    assert res["subtitles"] is True
    assert res["preset"] == "hormozi"


def test_format_pipeline_summary():
    result = {
        "success": True,
        "action": "pipeline",
        "output_path": "C:\\Video\\final_merged.mp4",
        "steps_completed": [
            {"action": "merge", "input_paths": ["C:\\Video\\clip1.mp4", "C:\\Video\\clip2.mp4"]},
            {"action": "add_song", "song_path": "C:\\Video\\beats.mp3", "music_volume": 0.25},
            {"action": "subtitles", "preset": "instagram", "transcription": {"language": "en", "text": "QuickSort algorithm demonstration"}},
        ],
    }
    summary = format_aicut_summary(result)
    assert "Video Edited Successfully" in summary
    assert "Combined 2 Clips" in summary
    assert "clip1.mp4" in summary
    assert "Audio Track Added" in summary
    assert "beats.mp3" in summary
    assert "final_merged.mp4" in summary


def test_build_ass_no_overlapping_captions():
    from subtitles.presets import build_ass_text
    words = [
        {"start": 1.0, "end": 1.4, "word": "Hello"},
        {"start": 1.4, "end": 1.8, "word": "Instagram"},
        {"start": 1.8, "end": 2.3, "word": "Reels"},
        {"start": 2.3, "end": 2.7, "word": "This"},
        {"start": 2.7, "end": 3.1, "word": "Is"},
        {"start": 3.1, "end": 3.5, "word": "Blinky"},
    ]
    ass = build_ass_text("", "instagram", words_data=words)
    dialogue_lines = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogue_lines) == 6

    # Parse timestamps of all dialogue lines: Format is Dialogue: Layer,Start,End,...
    def parse_ts(ts_str):
        parts = ts_str.split(":")
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

    for k in range(len(dialogue_lines) - 1):
        fields_curr = dialogue_lines[k].split(",")
        fields_next = dialogue_lines[k + 1].split(",")
        curr_end = parse_ts(fields_curr[2])
        next_start = parse_ts(fields_next[1])
        # Current caption must end at or before the next caption begins!
        assert curr_end <= next_start, f"Overlap detected between line {k} ({curr_end}) and line {k+1} ({next_start})"


def test_get_fast_video_encoder_args():
    from subtitles.render import get_fast_encoder_args
    args = get_fast_encoder_args()
    assert "-c:v" in args
    assert any(codec in args for codec in ("h264_nvenc", "libx264"))
    assert "-preset" in args


def test_file_transfer_aicut_multi_file_merge(tmp_path, monkeypatch):
    import os
    from file_transfer_aicut import run_transfer_edit
    dance_path = find_candidate_file("dance.mp4")
    assert dance_path is not None

    monkeypatch.setenv("BLINKY_TRANSFER_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("BLINKY_TRANSFER_ID", "test-transfer-123")

    # Run transfer edit with 2 videos (using dance.mp4 twice) and merge instruction
    res = run_transfer_edit("", dance_path, input_paths=[dance_path, dance_path])
    assert res.get("success") is True
    assert res.get("action") == "merge"
    assert "output_path" in res
    assert Path(res["output_path"]).is_file()


def test_forced_aligner_tokenization_and_alignment():
    from subtitles.forced_aligner import (
        extract_tokens_from_script,
        align_tokens_to_audio_words,
        words_to_subtitle_segments,
        segments_to_srt,
    )

    script = """Welcome to StockSense — a modern, intelligent ERP and double-entry inventory management system built for real-time warehouse velocity and audit precision. Let's sign in through our secure authentication portal."""

    tokens = extract_tokens_from_script(script)
    assert any("StockSense" in t for t in tokens)
    assert "double-entry" in tokens
    assert "real-time" in tokens

    whisper_words = [
        {"start": 0.1, "end": 0.5, "word": "Welcome"},
        {"start": 0.55, "end": 0.7, "word": "to"},
        {"start": 0.75, "end": 1.1, "word": "stock"},
        {"start": 1.15, "end": 1.5, "word": "sense"},
        {"start": 1.6, "end": 1.7, "word": "a"},
        {"start": 1.75, "end": 2.1, "word": "modern"},
        {"start": 2.15, "end": 2.8, "word": "intelligent"},
        {"start": 2.85, "end": 3.2, "word": "ERP"},
        {"start": 3.25, "end": 3.4, "word": "and"},
        {"start": 3.45, "end": 3.8, "word": "double"},
        {"start": 3.85, "end": 4.2, "word": "entry"},
        {"start": 4.25, "end": 4.8, "word": "inventory"},
        {"start": 4.85, "end": 5.4, "word": "management"},
        {"start": 5.45, "end": 5.9, "word": "system"},
        {"start": 6.0, "end": 6.3, "word": "built"},
        {"start": 6.35, "end": 6.5, "word": "for"},
        {"start": 6.55, "end": 6.8, "word": "real"},
        {"start": 6.85, "end": 7.1, "word": "time"},
        {"start": 7.15, "end": 7.6, "word": "warehouse"},
        {"start": 7.65, "end": 8.1, "word": "velocity"},
        {"start": 8.15, "end": 8.3, "word": "and"},
        {"start": 8.35, "end": 8.7, "word": "audit"},
        {"start": 8.75, "end": 9.3, "word": "precision."},
        {"start": 9.8, "end": 10.1, "word": "Let's"},
        {"start": 10.15, "end": 10.3, "word": "sign"},
        {"start": 10.35, "end": 10.5, "word": "in"},
        {"start": 10.55, "end": 10.8, "word": "through"},
        {"start": 10.85, "end": 11.0, "word": "our"},
        {"start": 11.05, "end": 11.4, "word": "secure"},
        {"start": 11.45, "end": 12.1, "word": "authentication"},
        {"start": 12.15, "end": 12.6, "word": "portal."},
    ]

    aligned = align_tokens_to_audio_words(tokens, whisper_words, 15.0)
    assert len(aligned) == len(tokens)

    # Check that StockSense took audio span from stock + sense
    stocksense_tok = next(w for w in aligned if "StockSense" in w["word"])
    assert stocksense_tok["start"] == 0.75
    assert stocksense_tok["end"] == 1.5

    # Check segments generation
    segs = words_to_subtitle_segments(aligned)
    assert len(segs) >= 2
    srt_text = segments_to_srt(segs)
    assert "StockSense" in srt_text
    assert "-->" in srt_text


def test_resolve_manual_captions_chatbar_multiline():
    query = """Welcome to StockSense — a modern, intelligent ERP and double-entry inventory management system built for real-time warehouse velocity and audit precision. Let's sign in through our secure authentication portal.

Right on the manager dashboard, you get instant visibility across your entire supply chain.

add the ability to add captions by giving captions like this manually by typing into chatbar if specified which sync automatically to audio"""

    res = resolve_aicut_request(query)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res.get("sync_audio") is True
    assert "StockSense" in res.get("manual_script", "")
    assert res.get("preset") in ("instagram", "hormozi")


def test_resolve_manual_captions_explicit_marker():
    query = """burn subtitles on dance.mp4 with captions:
Welcome to StockSense — an intelligent ERP platform."""

    res = resolve_aicut_request(query)
    assert res is not None
    assert res["action"] == "subtitles"
    assert res.get("sync_audio") is True
    assert "StockSense" in res.get("manual_script", "")
    assert "dance.mp4" in res.get("video_path", "").lower()


def test_format_aicut_summary_with_aligned_captions():
    res = {
        "success": True,
        "action": "subtitles",
        "output_path": "C:\\video_subtitled.mp4",
        "preset": "instagram",
        "alignment": {
            "word_count": 42,
            "audio_synced": True,
        },
    }
    summary = format_aicut_summary(res)
    assert "Styled Subtitles Burned" in summary
    assert "42" in summary
    assert "Automatically synced to audio speech" in summary




