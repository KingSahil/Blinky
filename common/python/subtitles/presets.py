"""Subtitle style presets — CapCut & Instagram Reels grade styles for SRT→ASS burning.

Each preset is a dict of ASS style parameters + per-word/per-line effects.
Supports true Instagram/Reels word-by-word active highlighting with exact timestamps.

Usage:
    from subtitles.presets import PRESETS, build_ass
    ass_text = build_ass("my.srt", "instagram")
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

PLAY_RES = (1920, 1080)

# ── PRESET PALETTE (CapCut / Instagram color constants in ASS &HBBGGRR format) ──
YELLOW = "&H04C2F7"     # #F7C204 → &H04C2F7 (BGR)
GREEN = "&H23FB02"      # #02FB23 → &H23FB02 (Emerald Green)
RED = "&H0000FF"        # #FF0000 → &H0000FF
WHITE = "&H00FFFFFF"
BLACK = "&H00000000"
CYAN = "&HFFFF00"       # #00FFFF → &HFFFF00
MAGENTA = "&HFF00FF"    # #FF00FF → &HFF00FF
ORANGE = "&H0084FF"     # #FF8400
LAVENDER = "&HFA70E5"   # #E570FA
CREAM = "&H00E0E0E0"
PINK = "&HFA70FF"


# ── ASS helpers ──────────────────────────────────────────────────────

def _style_entry(style: dict[str, Any]) -> str:
    """One ASS `Style:` line from a preset dict."""
    box = style.get("box")
    borderstyle = 3 if box else style.get("borderstyle", 1)
    return (
        f"Style: {style['name']},"
        f"{style.get('font', 'Montserrat, Arial, DejaVu Sans')},"
        f"{style.get('size', 42)},"
        f"{style.get('primary', '&H00FFFFFF')},"
        f"{style.get('secondary', '&H04C2F7')},"
        f"{style.get('outline', '&H00000000')},"
        f"{style.get('back', '&H80000000')},"
        f"{1 if style.get('bold', True) else 0},"
        f"{1 if style.get('italic') else 0},"
        f"0,0,"
        f"{style.get('scalex', 100)},{style.get('scaley', 100)},"
        f"{style.get('spacing', 0)},0,"
        f"{borderstyle},"
        f"{style.get('outline_width', 2.5)},"
        f"{style.get('shadow', 1.0)},"
        f"{style.get('alignment', 2)},"
        f"{style.get('margin_l', 60)},{style.get('margin_r', 60)},"
        f"{style.get('margin_v', 65)},1"
    )


def _ass_header(play_res: tuple[int, int] = PLAY_RES) -> str:
    w, h = play_res
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {w}\n"
        f"PlayResY: {h}\n"
        "ScaledBorderAndShadow: yes\n"
        "WrapStyle: 0\n"
        "\n"
    )


def _styles_block(preset: dict[str, Any]) -> str:
    lines = [
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    ]
    for style in preset.get("styles", []):
        lines.append(_style_entry(style))
    return "\n".join(lines) + "\n\n"


def _sec_to_ass_ts(seconds: float) -> str:
    """Convert float seconds to ASS timestamp H:MM:SS.cs (centiseconds)."""
    ms = int(round(max(seconds, 0.0) * 100))
    h, rem = divmod(ms, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _parse_srt(srt_text: str) -> list[tuple[str, str, str]]:
    text = srt_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    parsed: list[tuple[str, str, str]] = []
    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 2:
            continue
        idx = lines[0].strip()
        timing = lines[1].strip() if len(lines) >= 3 else lines[0].strip()
        body = "\n".join(lines[2:]).strip() if len(lines) >= 3 else lines[1].strip()
        if " --> " in timing and body:
            parsed.append((idx, timing, body))
    return parsed


def _parse_srt_to_word_list(srt_text: str) -> list[dict[str, Any]]:
    """Convert SRT subtitle blocks to structured word timestamps."""
    blocks = _parse_srt(srt_text)
    words: list[dict[str, Any]] = []
    for _, timing, body in blocks:
        s_str, e_str = timing.replace(",", ".").split(" --> ")
        def to_sec(ts: str) -> float:
            parts = ts.strip().split(":")
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            return 0.0
        t_start = to_sec(s_str)
        t_end = to_sec(e_str)
        w_list = body.split()
        if not w_list:
            continue
        dur = max(t_end - t_start, 0.1)
        w_dur = dur / len(w_list)
        for idx, w in enumerate(w_list):
            words.append({
                "start": round(t_start + idx * w_dur, 2),
                "end": round(t_start + (idx + 1) * w_dur, 2),
                "word": w,
            })
    return words


# ── Transformations ──────────────────────────────────────────────────

def _apply_emphasis(text: str, marker: str, emph_style: str = "Emph") -> str:
    """Wrap *word* segments in Emph style tags."""
    def repl(m: re.Match) -> str:
        return "{\\r" + emph_style + "}" + m.group(1) + "{\\rDefault}"
    pattern = re.escape(marker) + r"([^" + re.escape(marker) + r"]+)" + re.escape(marker)
    return re.sub(pattern, repl, text)


def _apply_karaoke(text: str, words_per_syllable: int = 1) -> str:
    """Convert words into \\k tags for timed karaoke fill."""
    def k(m: re.Match) -> str:
        return "{\\k30}" + m.group(0)
    return re.sub(r"\S+", k, text)


def _apply_word_pop(text: str) -> str:
    def pop(m: re.Match) -> str:
        word = m.group(0)
        return "{\\t(0,80,\\fscx112\\fscy112)}" + word
    return re.sub(r"\S+", pop, text)


def _apply_color_switch(text: str, colors: list[str]) -> str:
    words = re.findall(r"\S+", text)
    out: list[str] = []
    for i, w in enumerate(words):
        out.append("{\\1c" + colors[i % len(colors)] + "}" + w)
    return " ".join(out)


def _apply_typewriter(text: str, cps: int = 15) -> str:
    def ch(m: re.Match) -> str:
        return "{\\k1}" + m.group(0)
    return re.sub(r".", ch, text)


def _apply_allcaps(text: str) -> str:
    return text.upper()


def _ass_dialogue(text: str) -> str:
    return text.replace("\n", "\\N")


def _build_standard_ass_events(header_styles: str, srt_text: str, preset: dict[str, Any]) -> str:
    """Standard line-by-line ASS event builder."""
    out = header_styles
    effect = preset.get("effect", {})
    for _, timing, body in _parse_srt(srt_text):
        start, end = timing.replace(",", ".").split(" --> ")
        processed = body

        if effect.get("allcaps"):
            processed = _apply_allcaps(processed)
        if effect.get("lowercase"):
            processed = processed.lower()
        if effect.get("emphasis_marker"):
            processed = _apply_emphasis(processed, effect["emphasis_marker"])
        if effect.get("karaoke"):
            processed = _apply_karaoke(processed, effect.get("karaoke_words", 1))
        if effect.get("word_pop"):
            processed = _apply_word_pop(processed)
        if effect.get("color_switch"):
            processed = _apply_color_switch(processed, effect["color_switch"])
        if effect.get("typewriter"):
            processed = _apply_typewriter(processed, effect.get("cps", 15))

        blur = preset["styles"][0].get("blur")
        if blur:
            processed = "{\\be" + str(blur) + "}" + processed

        out += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{_ass_dialogue(processed)}\n"
    return out


def build_ass_text(srt_text: str, preset_name: str, words_data: list[dict[str, Any]] | None = None) -> str:
    """Build the full ASS document from SRT text or word timestamps using a preset."""
    preset_key = preset_name.lower().strip() if preset_name else "instagram"
    preset = PRESETS.get(preset_key) or PRESETS.get("instagram") or PRESETS["hormozi"]

    out = _ass_header()
    out += _styles_block(preset)
    out += "[Events]\n"
    out += "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"

    effect = preset.get("effect", {})

    # 1. Instagram / Word-by-Word active highlight or single word pop
    if effect.get("word_by_word") or effect.get("single_word_pop"):
        words = words_data if (words_data and len(words_data) > 0) else _parse_srt_to_word_list(srt_text)
        if not words:
            return _build_standard_ass_events(out, srt_text, preset)

        h_color = effect.get("highlight_color", YELLOW)
        allcaps = effect.get("allcaps", True)
        chunk_size = effect.get("chunk_size", 3)

        # Single-Word Center Pop (TikTok punchy style)
        if effect.get("single_word_pop"):
            for w in words:
                w_text = w["word"].upper() if allcaps else w["word"]
                s_ts = _sec_to_ass_ts(w["start"])
                e_ts = _sec_to_ass_ts(w["end"])
                out += f"Dialogue: 0,{s_ts},{e_ts},Default,,0,0,0,,{{\\c{h_color}&\\t(0,60,\\fscx118\\fscy118)}}{w_text}\n"
            return out

        # Word-by-word phrase active highlight (Instagram Reels / CapCut style)
        chunks: list[list[dict[str, Any]]] = []
        curr: list[dict[str, Any]] = []
        for w in words:
            curr.append(w)
            w_str = w["word"]
            if len(curr) >= chunk_size or w_str.endswith((".", "!", "?")) or len(curr) >= 4:
                chunks.append(curr)
                curr = []
        if curr:
            chunks.append(curr)

        for chunk in chunks:
            for i, w_active in enumerate(chunk):
                t_start = w_active["start"]
                t_end = chunk[i + 1]["start"] if i + 1 < len(chunk) else (w_active["end"] + 0.15)
                s_ts = _sec_to_ass_ts(t_start)
                e_ts = _sec_to_ass_ts(t_end)

                line_parts: list[str] = []
                for j, w in enumerate(chunk):
                    w_clean = w["word"].upper() if allcaps else w["word"]
                    if j == i:
                        line_parts.append("{\\c" + h_color + "&\\t(0,70,\\fscx114\\fscy114)}" + w_clean + "{\\rDefault}")
                    else:
                        line_parts.append(w_clean)
                line_text = " ".join(line_parts)
                out += f"Dialogue: 0,{s_ts},{e_ts},Default,,0,0,0,,{line_text}\n"
        return out

    # 2. Standard line-based presets
    return _build_standard_ass_events(out, srt_text, preset)


def build_ass(srt_path: str | Path, preset_name: str, words_data: list[dict[str, Any]] | None = None) -> str:
    return build_ass_text(
        Path(srt_path).read_text(encoding="utf-8", errors="replace"),
        preset_name,
        words_data=words_data,
    )


# ──────────────────────────────────────────────────────────────────────
# PRESETS — 18 styles across 5 families
# ──────────────────────────────────────────────────────────────────────

PRESETS: dict[str, dict[str, Any]] = {
    # ── Family 1: Viral (Instagram / TikTok / Reels / Shorts) ────────
    "instagram": {
        "name": "instagram",
        "description": "Viral Instagram Reels / TikTok dynamic word-by-word yellow active highlight pop in 2-3 word chunks.",
        "effect": {"word_by_word": True, "highlight_color": YELLOW, "chunk_size": 3, "allcaps": True},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 46,
                "primary": WHITE, "secondary": YELLOW, "outline": BLACK, "back": BLACK,
                "bold": True, "outline_width": 2.8, "shadow": 1.5,
                "alignment": 2, "margin_l": 50, "margin_r": 50, "margin_v": 70,
            }
        ],
    },
    "instagram-green": {
        "name": "instagram-green",
        "description": "Viral Instagram Reels word-by-word active emerald green highlight pop.",
        "effect": {"word_by_word": True, "highlight_color": GREEN, "chunk_size": 3, "allcaps": True},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 46,
                "primary": WHITE, "secondary": GREEN, "outline": BLACK, "back": BLACK,
                "bold": True, "outline_width": 2.8, "shadow": 1.5,
                "alignment": 2, "margin_l": 50, "margin_r": 50, "margin_v": 70,
            }
        ],
    },
    "instagram-pop": {
        "name": "instagram-pop",
        "description": "Punchy TikTok 1-word-at-a-time center pop with animated bounce.",
        "effect": {"single_word_pop": True, "highlight_color": YELLOW, "allcaps": True},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 52,
                "primary": WHITE, "secondary": YELLOW, "outline": BLACK, "back": BLACK,
                "bold": True, "outline_width": 3.0, "shadow": 2.0,
                "alignment": 2, "margin_l": 40, "margin_r": 40, "margin_v": 75,
            }
        ],
    },
    "hormozi": {
        "name": "hormozi",
        "description": "Alex Hormozi ALL CAPS Montserrat Black + yellow active word pop + heavy outline.",
        "effect": {"word_by_word": True, "highlight_color": YELLOW, "chunk_size": 3, "allcaps": True},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 46,
                "primary": WHITE, "outline": BLACK, "back": BLACK,
                "bold": True, "outline_width": 3.0, "shadow": 1.5,
                "alignment": 2, "margin_l": 60, "margin_r": 60, "margin_v": 65,
            }
        ],
    },
    "word-karaoke": {
        "name": "word-karaoke",
        "description": "Montserrat Bold word-by-word karaoke fill with yellow fill and white base.",
        "effect": {"karaoke": True, "karaoke_words": 1},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 44,
                "primary": WHITE, "secondary": YELLOW, "outline": BLACK, "back": BLACK,
                "bold": True, "outline_width": 2.2, "shadow": 1.0,
                "alignment": 2, "margin_v": 65,
            }
        ],
    },
    "pill-yellow": {
        "name": "pill-yellow",
        "description": "Black text in a solid high-contrast yellow pill box.",
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 40,
                "primary": BLACK, "outline": BLACK, "back": YELLOW,
                "bold": True, "outline_width": 0, "shadow": 0,
                "box": True, "margin_l": 26, "margin_r": 26, "margin_v": 50,
                "alignment": 2,
            }
        ],
    },
    "pill-red": {
        "name": "pill-red",
        "description": "White in a solid red pill box — hook/emphasis captions.",
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 40,
                "primary": WHITE, "outline": WHITE, "back": RED,
                "bold": True, "outline_width": 0, "shadow": 0,
                "box": True, "margin_l": 26, "margin_r": 26, "margin_v": 50,
                "alignment": 2,
            }
        ],
    },
    "neon-blur": {
        "name": "neon-blur",
        "description": "Cyber magenta glowing caption with cyan active word highlight.",
        "effect": {"word_by_word": True, "highlight_color": CYAN, "chunk_size": 3, "allcaps": True},
        "styles": [
            {
                "name": "Default", "font": "Noto Sans Mono", "size": 42,
                "primary": MAGENTA, "outline": "&H00000000", "back": MAGENTA,
                "bold": True, "outline_width": 0, "shadow": 8,
                "alignment": 2, "margin_v": 65,
            }
        ],
    },
    "glassmorphism": {
        "name": "glassmorphism",
        "description": "Frosted look: dark semi-transparent box + light border + soft shadow.",
        "effect": {"word_by_word": True, "highlight_color": YELLOW, "chunk_size": 3, "allcaps": False},
        "styles": [
            {
                "name": "Default", "font": "Poppins", "size": 38,
                "primary": WHITE, "outline": "&H00FFFFFF", "back": "&H40000000",
                "bold": True, "outline_width": 0.5, "shadow": 2,
                "box": True, "margin_l": 40, "margin_r": 40, "margin_v": 50,
                "alignment": 2,
            }
        ],
    },
    "typewriter": {
        "name": "typewriter",
        "description": "JetBrains Mono char-by-char reveal. Storytelling rhythm.",
        "effect": {"typewriter": True, "cps": 15},
        "styles": [
            {
                "name": "Default", "font": "JetBrains Mono", "size": 38,
                "primary": WHITE, "outline": BLACK, "back": BLACK,
                "bold": False, "outline_width": 1.5, "shadow": 0,
                "alignment": 2, "margin_v": 55,
            }
        ],
    },
    "color-switch": {
        "name": "color-switch",
        "description": "Words alternate white/yellow/red — high energy.",
        "effect": {"color_switch": [WHITE, YELLOW, RED]},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 42,
                "primary": WHITE, "outline": BLACK, "back": BLACK,
                "bold": True, "outline_width": 2.0, "shadow": 0,
                "alignment": 2, "margin_v": 60,
            }
        ],
    },
    "meme-impact": {
        "name": "meme-impact",
        "description": "Anton ALL CAPS, top-center, thick black outline.",
        "effect": {"allcaps": True},
        "styles": [
            {
                "name": "Default", "font": "Anton", "size": 56,
                "primary": WHITE, "outline": BLACK, "back": "&H80000000",
                "bold": True, "outline_width": 3.5, "shadow": 0,
                "alignment": 8, "margin_l": 40, "margin_r": 40, "margin_v": 60,
            }
        ],
    },
    "retro-yellow": {
        "name": "retro-yellow",
        "description": "Bebas Neue condensed, yellow on black pill. Classic retro.",
        "styles": [
            {
                "name": "Default", "font": "Bebas Neue", "size": 48,
                "primary": YELLOW, "outline": BLACK, "back": "&HC0000000",
                "bold": False, "outline_width": 1.0, "shadow": 0,
                "box": True, "margin_l": 34, "margin_r": 34, "margin_v": 45,
                "alignment": 2,
            }
        ],
    },
    # ── Family 2: Business / educational ──────────────────────────────
    "hormozi-clean": {
        "name": "hormozi-clean",
        "description": "Montserrat Black ALL CAPS, white/black outline, static.",
        "effect": {"allcaps": True},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 44,
                "primary": WHITE, "outline": BLACK, "back": BLACK,
                "bold": True, "outline_width": 2.5, "shadow": 0,
                "alignment": 2, "margin_l": 70, "margin_r": 70, "margin_v": 55,
            }
        ],
    },
    "keyword-green": {
        "name": "keyword-green",
        "description": "White body + green keyword per line, clean box, business/edu.",
        "effect": {"word_by_word": True, "highlight_color": GREEN, "chunk_size": 3, "allcaps": False},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 38,
                "primary": WHITE, "outline": BLACK, "back": "&H80000000",
                "bold": True, "outline_width": 1.5, "shadow": 0,
                "box": True, "margin_l": 40, "margin_r": 40, "margin_v": 40,
                "alignment": 2,
            }
        ],
    },
    "lecture-dual": {
        "name": "lecture-dual",
        "description": "Clean BBC-compliant white body + one colored keyword (no box).",
        "effect": {"emphasis_marker": "*"},
        "styles": [
            {
                "name": "Default", "font": "Noto Sans", "size": 36,
                "primary": WHITE, "outline": BLACK, "back": "&H00000000",
                "bold": False, "outline_width": 1.0, "shadow": 0,
                "alignment": 2, "margin_v": 50,
            },
            {
                "name": "Emph", "font": "Noto Sans", "size": 36,
                "primary": LAVENDER, "outline": BLACK, "back": "&H00000000",
                "bold": True, "outline_width": 1.0, "shadow": 0,
                "alignment": 2, "margin_v": 50,
            },
        ],
    },
    # ── Family 3: Documentary / cinematic ─────────────────────────────
    "documentary": {
        "name": "documentary",
        "description": "Noto Sans, 42-char lines, white 21:1, thin outline, 90% safe area.",
        "styles": [
            {
                "name": "Default", "font": "Noto Sans", "size": 34,
                "primary": WHITE, "outline": BLACK, "back": "&H00000000",
                "bold": False, "outline_width": 1.0, "shadow": 0,
                "alignment": 2, "margin_l": 120, "margin_r": 120, "margin_v": 55,
            }
        ],
    },
    "cinematic-lowerthird": {
        "name": "cinematic-lowerthird",
        "description": "Condensed warm off-white, slight box, lower-third position.",
        "styles": [
            {
                "name": "Default", "font": "DejaVu Sans Condensed", "size": 32,
                "primary": CREAM, "outline": BLACK, "back": "&H40000000",
                "bold": False, "outline_width": 1.0, "shadow": 0,
                "box": True, "margin_l": 55, "margin_r": 55, "margin_v": 45,
                "alignment": 2,
            }
        ],
    },
    "quiet-minimal": {
        "name": "quiet-minimal",
        "description": "Small lowercase white, no outline, no animation.",
        "effect": {"lowercase": True},
        "styles": [
            {
                "name": "Default", "font": "Inter", "size": 26,
                "primary": WHITE, "outline": "&H00000000", "back": "&H00000000",
                "bold": False, "outline_width": 0, "shadow": 0,
                "alignment": 2, "margin_v": 50,
            }
        ],
    },
}

# Aliases
PRESETS["word-by-word"] = PRESETS["instagram"]
PRESETS["reels"] = PRESETS["instagram"]
PRESETS["tiktok"] = PRESETS["instagram"]


def list_presets() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": preset["description"]}
        for name, preset in PRESETS.items()
        if name not in {"word-by-word", "reels", "tiktok"}
    ]
