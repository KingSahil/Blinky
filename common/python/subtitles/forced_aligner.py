"""Forced alignment & speech-to-text audio sync for manual video captions.

Aligns user-provided manual scripts, transcripts, or custom captions directly to
spoken audio extracted from a video/audio track using faster-whisper word-level
timestamps.

Preserves exact user capitalization, punctuation, terminology (e.g. 'StockSense',
'SKUs', 'Kanban', 'A4'), while snapping start/end timestamps precisely to speech.
"""

from __future__ import annotations

import difflib
import math
import os
import re
from pathlib import Path
from typing import Any


def _clean_word(w: str) -> str:
    """Normalize a word for fuzzy phonetic/spelling matching (lowercased alphanumeric)."""
    return re.sub(r"[^a-z0-9]", "", w.lower())


def _sec_to_srt_time(seconds: float) -> str:
    """Convert float seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    ms = int(round(max(seconds, 0.0) * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _parse_time_str(ts_str: str) -> float:
    """Parse time string like '0:12', '1:28', '01:28.5', '88s' into float seconds."""
    s = ts_str.strip().rstrip("sS")
    parts = s.split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2].replace(",", "."))
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1].replace(",", "."))
    else:
        try:
            return float(s.replace(",", "."))
        except ValueError:
            return 0.0


def parse_script_blocks(script_text: str) -> list[dict[str, Any]]:
    """Parse a script that may contain timestamp headers like:
    [0:00 - 0:12] Welcome to StockSense...
    [0:12 - 0:38] Right on the manager dashboard...
    or plain natural text paragraphs.
    """
    clean_text = script_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")

    # Check if raw SRT
    if re.match(r"^\s*1\s*\n\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->", clean_text):
        # Already SRT format
        return [{"type": "srt", "raw": clean_text}]

    timestamp_pattern = re.compile(
        r"^(?:\[|\()?\s*(\d+:\d+(?::\d+)?(?:[,\.]\d+)?)\s*(?:-|–|to)\s*(\d+:\d+(?::\d+)?(?:[,\.]\d+)?)\s*(?:\]|\))?\s*[:\-]?",
        re.MULTILINE,
    )

    blocks: list[dict[str, Any]] = []
    lines = clean_text.splitlines()
    curr_time_window: tuple[float, float] | None = None
    curr_text_lines: list[str] = []

    def flush_block():
        nonlocal curr_text_lines, curr_time_window
        text = " ".join(curr_text_lines).strip()
        if text:
            blocks.append({
                "type": "block",
                "time_window": curr_time_window,
                "text": text,
            })
        curr_text_lines = []
        curr_time_window = None

    for line in lines:
        line_s = line.strip()
        if not line_s:
            if curr_text_lines and curr_time_window:
                flush_block()
            continue

        ts_match = timestamp_pattern.match(line_s)
        if ts_match:
            flush_block()
            t_start = _parse_time_str(ts_match.group(1))
            t_end = _parse_time_str(ts_match.group(2))
            curr_time_window = (t_start, t_end)
            remainder = line_s[ts_match.end():].strip()
            if remainder:
                curr_text_lines.append(remainder)
        else:
            curr_text_lines.append(line_s)

    flush_block()
    return blocks


def extract_tokens_from_script(script_text: str) -> list[str]:
    """Tokenize script into words while preserving attached punctuation.
    Standalone punctuation symbols (like em-dash '—' or '-') are attached
    to the preceding token so they don't consume speech audio duration.
    """
    blocks = parse_script_blocks(script_text)
    tokens: list[str] = []
    for b in blocks:
        t = b.get("text", "")
        # Remove any lingering timestamp markers
        t = re.sub(r"\[\s*\d+:\d+(?:\s*-\s*\d+:\d+)?\s*\]", "", t)
        raw_parts = t.split()
        for part in raw_parts:
            part = part.strip()
            if not part:
                continue
            # If standalone punctuation like em-dash or dash, attach to previous token
            if not re.search(r"\w", part) and tokens:
                tokens[-1] = f"{tokens[-1]} {part}"
            else:
                tokens.append(part)
    return tokens


def align_tokens_to_audio_words(
    user_tokens: list[str],
    audio_words: list[dict[str, Any]],
    total_duration: float = 0.0,
    script_blocks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Align user script tokens to faster-whisper audio word timestamps.

    Uses SequenceMatcher with fuzzy phonetic decomposition.
    Produces a list of aligned user words:
    `[{"word": str, "start": float, "end": float}, ...]`
    """
    if not user_tokens:
        return []

    # If no audio words (e.g. silent video or transcription failed), distribute
    if not audio_words:
        # Check if script_blocks have timestamp windows
        if script_blocks and any(b.get("time_window") for b in script_blocks):
            res: list[dict[str, Any]] = []
            curr_pos = 0.0
            for b in script_blocks:
                b_text = b.get("text", "")
                b_tokens = [w.strip() for w in b_text.split() if w.strip()]
                if not b_tokens:
                    continue
                win = b.get("time_window")
                if win:
                    t_start, t_end = win
                    curr_pos = t_end
                else:
                    t_start = curr_pos
                    t_end = curr_pos + len(b_tokens) * 0.4
                    curr_pos = t_end

                b_dur = max(t_end - t_start, 0.2)
                dt = b_dur / len(b_tokens)
                for i, tok in enumerate(b_tokens):
                    s = round(t_start + i * dt, 2)
                    e = round(t_start + (i + 1) * dt, 2)
                    res.append({"word": tok, "start": s, "end": e})
            if res:
                return res

        dur = max(total_duration, 1.0)
        n = len(user_tokens)
        dt = dur / n
        res = []
        for i, tok in enumerate(user_tokens):
            s = round(i * dt, 2)
            e = round((i + 1) * dt, 2)
            res.append({"word": tok, "start": s, "end": e})
        return res

    clean_user = [_clean_word(tok) for tok in user_tokens]
    clean_audio = [_clean_word(aw.get("word", "")) for aw in audio_words]

    # Pre-build user words aligned array initialized with None timestamps
    aligned: list[dict[str, Any]] = [
        {"word": tok, "start": None, "end": None} for tok in user_tokens
    ]

    sm = difflib.SequenceMatcher(None, clean_user, clean_audio)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            # Direct matches
            for u_idx, a_idx in zip(range(i1, i2), range(j1, j2)):
                aligned[u_idx]["start"] = audio_words[a_idx]["start"]
                aligned[u_idx]["end"] = audio_words[a_idx]["end"]

        elif tag == "replace":
            # e.g. 'StockSense' <-> ['stock', 'sense'] or 'double-entry' <-> ['double', 'entry']
            # Distribute audio span (audio_words[j1].start -> audio_words[j2-1].end) across user_tokens[i1:i2]
            span_start = audio_words[j1]["start"]
            span_end = audio_words[j2 - 1]["end"]
            user_slice = user_tokens[i1:i2]
            n_slice = len(user_slice)

            if n_slice == 1:
                aligned[i1]["start"] = span_start
                aligned[i1]["end"] = span_end
            elif n_slice > 1:
                # Distribute proportionally based on character lengths
                total_chars = sum(max(len(tok), 1) for tok in user_slice)
                curr_s = span_start
                tot_time = max(span_end - span_start, 0.1)
                for u_idx, tok in zip(range(i1, i2), user_slice):
                    w_fraction = max(len(tok), 1) / total_chars
                    w_dur = tot_time * w_fraction
                    aligned[u_idx]["start"] = round(curr_s, 2)
                    aligned[u_idx]["end"] = round(curr_s + w_dur, 2)
                    curr_s += w_dur

        elif tag == "delete":
            # Words in user script not spoken/heard in audio (or em-dashes like '—')
            # Will be interpolated in pass 2
            pass

        elif tag == "insert":
            # Words in audio not present in user script (filler words) - ignore
            pass

    # Pass 2: Interpolate missing timestamps (unaligned user tokens / punctuation)
    # Find contiguous unaligned gaps between anchored words
    last_end = 0.0
    idx = 0
    total_len = len(aligned)

    while idx < total_len:
        if aligned[idx]["start"] is None:
            gap_start_idx = idx
            while idx < total_len and aligned[idx]["start"] is None:
                idx += 1
            gap_end_idx = idx  # exclusive

            # The anchor before this gap
            prev_time = last_end
            # The anchor after this gap
            if gap_end_idx < total_len and aligned[gap_end_idx]["start"] is not None:
                next_time = aligned[gap_end_idx]["start"]
            else:
                next_time = max(prev_time + (gap_end_idx - gap_start_idx) * 0.4, total_duration)

            gap_count = gap_end_idx - gap_start_idx
            time_available = max(next_time - prev_time, 0.05 * gap_count)
            step = time_available / gap_count

            for k in range(gap_count):
                cur_k = gap_start_idx + k
                s = round(prev_time + k * step, 2)
                e = round(prev_time + (k + 1) * step, 2)
                aligned[cur_k]["start"] = s
                aligned[cur_k]["end"] = e
        else:
            last_end = aligned[idx]["end"] or last_end
            idx += 1

    # Guarantee monotonic increasing timestamps
    cur_t = 0.0
    for w in aligned:
        s = max(float(w["start"] or 0.0), cur_t)
        e = max(float(w["end"] or (s + 0.3)), s + 0.05)
        w["start"] = round(s, 2)
        w["end"] = round(e, 2)
        cur_t = s

    return aligned


def words_to_subtitle_segments(
    aligned_words: list[dict[str, Any]],
    max_words_per_segment: int = 5,
    max_duration_sec: float = 3.5,
) -> list[dict[str, Any]]:
    """Group aligned word tokens into natural subtitle segments/cards.

    Breaks at:
    - Sentence end punctuation (. ! ?)
    - Major pauses / commas (when segment has >= 3 words)
    - Reaching max_words_per_segment or max_duration_sec
    """
    if not aligned_words:
        return []

    segments: list[dict[str, Any]] = []
    current_words: list[dict[str, Any]] = []

    def flush_segment():
        nonlocal current_words
        if not current_words:
            return
        seg_id = len(segments) + 1
        s_time = current_words[0]["start"]
        e_time = current_words[-1]["end"]
        # Add slight trailing padding so subtitle doesn't vanish too abruptly
        text = " ".join(w["word"] for w in current_words)
        segments.append({
            "id": seg_id,
            "start": round(s_time, 2),
            "end": round(e_time + 0.08, 2),
            "text": text,
            "words": list(current_words),
        })
        current_words = []

    for w in aligned_words:
        current_words.append(w)
        word_raw = w["word"]
        dur = w["end"] - current_words[0]["start"]

        # Check sentence ends
        is_sentence_end = any(word_raw.endswith(p) for p in [".", "!", "?", "...", ":"])
        # Check clause breaks
        is_clause_break = any(word_raw.endswith(p) for p in [",", ";", "—", "-"]) and len(current_words) >= 3

        if is_sentence_end:
            flush_segment()
        elif is_clause_break or len(current_words) >= max_words_per_segment or dur >= max_duration_sec:
            flush_segment()

    flush_segment()
    return segments


def segments_to_srt(segments: list[dict[str, Any]]) -> str:
    """Format subtitle segments into standard SRT text."""
    lines: list[str] = []
    for s in segments:
        idx = s["id"]
        start_ts = _sec_to_srt_time(s["start"])
        end_ts = _sec_to_srt_time(s["end"])
        lines.append(f"{idx}\n{start_ts} --> {end_ts}\n{s['text']}\n")
    return "\n".join(lines)


def align_script_to_media(
    media_path: str | Path,
    script_text: str,
    output_srt: str | Path | None = None,
    *,
    model_size: str = "tiny",
    language: str | None = None,
) -> dict[str, Any]:
    """Transcribe audio from media file, force-align user manual script, and generate SRT.

    Returns:
    {
        "success": bool,
        "srt_path": str,
        "srt_content": str,
        "segments": list[dict],
        "words": list[dict],
        "text": str,
        "word_count": int,
        "audio_synced": bool,
        "language": str,
    }
    """
    m_path = Path(media_path).resolve()
    if not m_path.exists():
        return {"success": False, "error": f"Media file not found: {media_path}"}

    # Tokenize user script
    blocks = parse_script_blocks(script_text)
    user_tokens = extract_tokens_from_script(script_text)
    if not user_tokens:
        return {"success": False, "error": "Provided script is empty or could not be tokenized."}

    # Transcribe audio with faster-whisper to get raw speech words
    from aicut_mcp import transcribe_audio, get_media_info

    info = get_media_info(str(m_path))
    duration = float(info.get("duration_seconds") or 0.0)

    trans_res = transcribe_audio(
        str(m_path),
        model_size=model_size,
        language=language,
    )

    audio_words: list[dict[str, Any]] = []
    detected_lang = "en"

    if trans_res.get("success"):
        audio_words = trans_res.get("words") or []
        detected_lang = trans_res.get("language") or "en"

    # Align script tokens to audio words
    aligned_words = align_tokens_to_audio_words(
        user_tokens=user_tokens,
        audio_words=audio_words,
        total_duration=duration,
        script_blocks=blocks,
    )

    # Group into subtitle segments
    segments = words_to_subtitle_segments(aligned_words)
    srt_content = segments_to_srt(segments)

    if not output_srt:
        output_srt = m_path.with_name(f"{m_path.stem}_aligned.srt")

    out_file = Path(output_srt).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(srt_content, encoding="utf-8")

    return {
        "success": True,
        "srt_path": str(out_file),
        "srt_content": srt_content,
        "segments": segments,
        "words": aligned_words,
        "text": " ".join(w["word"] for w in aligned_words),
        "word_count": len(aligned_words),
        "audio_synced": len(audio_words) > 0,
        "language": detected_lang,
    }
