import pytest
from pathlib import Path
from tools.aicut_tool import resolve_aicut_request, run_aicut, format_aicut_summary, find_candidate_file

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
