from pathlib import Path

import file_transfer_aicut


def _run(tmp_path, monkeypatch, names, instruction):
    sources = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"uploaded")
        sources.append(str(path))
    output_dir = tmp_path / "output"
    monkeypatch.setenv("BLINKY_TRANSFER_OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("BLINKY_TRANSFER_ID", "remote-test")
    requests = []

    def fake_run(request):
        requests.append(request)
        target = Path(request.get("output_path") or request.get("srt_output"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"edited")
        return {"success": True, "output_path": str(target), "action": request["action"]}

    monkeypatch.setattr(file_transfer_aicut, "run_aicut", fake_run)
    result = file_transfer_aicut.run_transfer_edit(instruction, sources[0], sources)
    return result, requests, sources


def test_captions_instruction_does_not_merge_multiple_uploaded_videos(tmp_path, monkeypatch):
    result, requests, sources = _run(
        tmp_path, monkeypatch, ["first.mp4", "second.mp4"], "add captions to the first video"
    )
    assert result["success"] is True
    assert requests[0]["action"] == "subtitles"
    assert requests[0]["video_path"] == sources[0]


def test_mixed_batch_uses_video_for_trim_and_keeps_other_uploads_out_of_edit(tmp_path, monkeypatch):
    result, requests, sources = _run(
        tmp_path, monkeypatch, ["clip.mp4", "notes.pdf", "cover.png"], "trim from 1 to 3 seconds"
    )
    assert result["success"] is True
    assert requests[0]["action"] == "trim"
    assert requests[0]["video_path"] == sources[0]


def test_uploaded_audio_is_not_added_to_a_trim_without_audio_request(tmp_path, monkeypatch):
    result, requests, sources = _run(
        tmp_path, monkeypatch, ["clip.mp4", "track.mp3"], "trim from 1 to 3 seconds"
    )
    assert result["success"] is True
    assert requests[0]["action"] == "trim"
    assert requests[0]["video_path"] == sources[0]


def test_explicit_merge_uses_videos_from_a_mixed_batch(tmp_path, monkeypatch):
    result, requests, sources = _run(
        tmp_path, monkeypatch,
        ["first.mp4", "notes.pdf", "second.mp4", "cover.png"],
        "merge these videos",
    )
    assert result["success"] is True
    assert requests[0]["action"] == "merge"
    assert requests[0]["input_paths"] == [sources[0], sources[2]]


def test_explicit_audio_request_uses_uploaded_track(tmp_path, monkeypatch):
    result, requests, sources = _run(
        tmp_path, monkeypatch, ["clip.mp4", "track.mp3", "notes.pdf"],
        "add this song to the video",
    )
    assert result["success"] is True
    assert requests[0]["action"] == "add_song"
    assert requests[0]["video_path"] == sources[0]
    assert requests[0]["song_path"] == sources[1]


def test_explicit_uploaded_audio_filename_requests_adding_it(tmp_path, monkeypatch):
    result, requests, sources = _run(
        tmp_path, monkeypatch, ["clip.mp4", "beat.wav"],
        "add beat.wav to clip.mp4",
    )
    assert result["success"] is True
    assert requests[0]["action"] == "add_song"
    assert requests[0]["song_path"] == sources[1]


def test_edit_without_compatible_media_returns_clear_error(tmp_path, monkeypatch):
    result, requests, _ = _run(tmp_path, monkeypatch, ["notes.pdf", "cover.png"], "merge these files")
    assert result["success"] is False
    assert "video or audio" in result["error"].lower()
    assert requests == []


def test_remote_edit_requires_explicit_instruction(tmp_path, monkeypatch):
    result, requests, _ = _run(tmp_path, monkeypatch, ["first.mp4", "second.mp4"], "")
    assert result["success"] is False
    assert "instruction" in result["error"].lower()
    assert requests == []
