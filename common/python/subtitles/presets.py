"""Subtitle style presets — CapCut-grade named styles for SRT→ASS burning.

Each preset is a dict of ASS style parameters + optional per-line effects.
Presets differ across 6 dimensions so no two look alike:
  - font weight (Anton Black vs Noto Light)
  - case (ALL CAPS vs lowercase)
  - keyword highlighting (one colored word per line)
  - background treatment (pill box / translucent box / outline / none / blur)
  - animation (word-pop \\t, karaoke \\k, typewriter, color-switch)
  - position (bottom-center, top, lower-third)

Usage:
    from subtitles.presets import PRESETS, build_ass
    ass_text = build_ass("my.srt", "hormozi")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

PLAY_RES = (1920, 1080)

# ── ASS helpers ──────────────────────────────────────────────────────

def _style_entry(style: dict[str, Any]) -> str:
    """One ASS `Style:` line from a preset dict.

    `box: true` → BorderStyle=3 (semi-transparent background pill/box),
    `box: 'pill'` → BorderStyle=3 with tighter margins (chip look),
    `blur: N` → \\be blur on the whole style.
    """
    box = style.get("box")
    borderstyle = 3 if box else style.get("borderstyle", 1)
    return (
        f"Style: {style['name']},"
        f"{style.get('font', 'DejaVu Sans')},"
        f"{style.get('size', 36)},"
        f"{style.get('primary', '&H00FFFFFF')},"
        f"{style.get('secondary', '&H00FFFFFF')},"
        f"{style.get('outline', '&H00000000')},"
        f"{style.get('back', '&H80000000')},"
        f"{1 if style.get('bold') else 0},"
        f"{1 if style.get('italic') else 0},"
        f"0,0,"
        f"{style.get('scalex', 100)},{style.get('scaley', 100)},"
        f"{style.get('spacing', 0)},0,"
        f"{borderstyle},"
        f"{style.get('outline_width', 1.5)},"
        f"{style.get('shadow', 0)},"
        f"{style.get('alignment', 2)},"
        f"{style.get('margin_l', 80)},{style.get('margin_r', 80)},"
        f"{style.get('margin_v', 50)},1"
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
    lines = ["[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"]
    for style in preset["styles"]:
        lines.append(_style_entry(style))
    return "\n".join(lines) + "\n\n"


def _parse_srt(srt_text: str) -> list[tuple[str, str, str]]:
    text = srt_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    parsed: list[tuple[str, str, str]] = []
    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 2:
            continue
        idx = lines[0].strip()
        timing = lines[1].strip()
        body = "\n".join(lines[2:]).strip()
        if timing and body:
            parsed.append((idx, timing, body))
    return parsed


# ── emphasis / animation transformations ─────────────────────────────

def _apply_emphasis(text: str, marker: str, emph_style: str = "Emph") -> str:
    """Wrap *word* segments in Emph style tags."""
    import re
    def repl(m: re.Match) -> str:
        return "{\\r" + emph_style + "}" + m.group(1) + "{\\rDefault}"
    pattern = re.escape(marker) + r"([^" + re.escape(marker) + r"]+)" + re.escape(marker)
    return re.sub(pattern, repl, text)


def _apply_karaoke(text: str, words_per_syllable: int = 1) -> str:
    """Convert *word* (or every word) into \\k tags for timed fill."""
    import re
    def k(m: re.Match) -> str:
        return "{\\k" + str(25 * max(words_per_syllable, 1)) + "}" + m.group(0)
    return re.sub(r"\S+", k, text)


def _apply_word_pop(text: str, highlight: str | None = None) -> str:
    """Wrap each word in \\t scale-in (pop) — basic version: fade-in per word."""
    import re
    def pop(m: re.Match) -> str:
        word = m.group(0)
        return "{\\fad(120,0)\\t(0,200,0.5,\\fscx115\\fscy115)}" + word
    return re.sub(r"\S+", pop, text)


def _apply_color_switch(text: str, colors: list[str]) -> str:
    """Alternate word colors rhythmically."""
    import re
    words = re.findall(r"\S+", text)
    out: list[str] = []
    for i, w in enumerate(words):
        out.append("{\\1c" + colors[i % len(colors)] + "}" + w)
    return " ".join(out)


def _apply_typewriter(text: str, cps: int = 15) -> str:
    """Per-character reveal via sequential fades (best-effort; full effect in player)."""
    # libass supports \t but true per-char typewriter needs \k; approximate with karaoke per char
    import re
    def ch(m: re.Match) -> str:
        return "{\\k1}" + m.group(0)
    return re.sub(r".", ch, text)


def _apply_allcaps(text: str) -> str:
    return text.upper()


def _ass_dialogue(text: str) -> str:
    return text.replace("\n", "\\N")


def build_ass_text(srt_text: str, preset_name: str) -> str:
    """Build the full ASS document from SRT text using a preset."""
    preset = PRESETS[preset_name]
    out = _ass_header()
    out += _styles_block(preset)
    out += "[Events]\n"
    out += "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"

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

        # Per-line blur override from the Default style (\\beN)
        blur = preset["styles"][0].get("blur")
        if blur:
            processed = "{\\be" + str(blur) + "}" + processed

        out += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{_ass_dialogue(processed)}\n"
    return out


def build_ass(srt_path: str | Path, preset_name: str) -> str:
    return build_ass_text(Path(srt_path).read_text(encoding="utf-8", errors="replace"), preset_name)


# ── PRESET PALETTE (CapCut-ish color constants) ──────────────────────
YELLOW = "&H04C2F7"     # #F7C204 → &H04C2F7 (BGR)
RED = "&H0000FF"        # #FF0000 → &H0000FF
GREEN = "&H23FB02"      # #02FB23 → &H23FB02
WHITE = "&H00FFFFFF"
BLACK = "&H00000000"
CYAN = "&HFFFF00"       # #00FFFF → &HFFFF00
MAGENTA = "&HFF00FF"    # #FF00FF → &HFF00FF
ORANGE = "&H0084FF"     # #FF8400
LAVENDER = "&HFA70E5"   # #E570FA
CREAM = "&H00E0E0E0"
PINK = "&HFA70FF"


# ──────────────────────────────────────────────────────────────────────
# PRESETS — 16 styles across 5 families
# ──────────────────────────────────────────────────────────────────────

PRESETS: dict[str, dict[str, Any]] = {
    # ── Family 1: Viral (TikTok/Reels/Shorts) ────────────────────────
    "hormozi": {
        "name": "hormozi",
        "description": "ALL CAPS Montserrat Black + one yellow keyword per line, black outline, word-pop.",
        "effect": {"allcaps": True, "emphasis_marker": "*", "word_pop": True},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 44,
                "primary": WHITE, "outline": BLACK, "back": BLACK,
                "bold": True, "outline_width": 2.5, "shadow": 0,
                "alignment": 2, "margin_l": 70, "margin_r": 70, "margin_v": 55,
            },
            {
                "name": "Emph", "font": "Montserrat", "size": 46,
                "primary": YELLOW, "outline": BLACK, "back": BLACK,
                "bold": True, "outline_width": 2.5, "shadow": 0,
                "alignment": 2, "margin_l": 70, "margin_r": 70, "margin_v": 55,
            },
        ],
    },
    "word-karaoke": {
        "name": "word-karaoke",
        "description": "Montserrat Bold word-by-word \\k fill, white/black outline, speech-synced.",
        "effect": {"karaoke": True, "karaoke_words": 1},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 42,
                "primary": WHITE, "outline": BLACK, "back": BLACK,
                "bold": True, "outline_width": 2.0, "shadow": 0,
                "alignment": 2, "margin_v": 55,
            }
        ],
    },
    "pill-yellow": {
        "name": "pill-yellow",
        "description": "White text in a solid yellow pill, no outline. Works on any background.",
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 40,
                "primary": BLACK, "outline": BLACK, "back": YELLOW,
                "bold": True, "outline_width": 0, "shadow": 0,
                "box": True, "margin_l": 26, "margin_r": 26, "margin_v": 34,
                "alignment": 2,
            }
        ],
    },
    "pill-red": {
        "name": "pill-red",
        "description": "White in a solid red pill — hook/emphasis captions.",
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 40,
                "primary": WHITE, "outline": WHITE, "back": RED,
                "bold": True, "outline_width": 0, "shadow": 0,
                "box": True, "margin_l": 26, "margin_r": 26, "margin_v": 34,
                "alignment": 2,
            }
        ],
    },
    "typewriter": {
        "name": "typewriter",
        "description": "JetBrains Mono char-by-char reveal (\\k per char). Storytelling rhythm.",
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
        "description": "Words alternate white/yellow/red — high energy, use for hooks.",
        "effect": {"color_switch": [WHITE, YELLOW, RED]},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 40,
                "primary": WHITE, "outline": BLACK, "back": BLACK,
                "bold": True, "outline_width": 1.8, "shadow": 0,
                "alignment": 2, "margin_v": 55,
            }
        ],
    },
    # ── Family 2: Business / educational ──────────────────────────────
    "hormozi-clean": {
        "name": "hormozi-clean",
        "description": "Montserrat Black ALL CAPS, white/black outline, static (no highlight).",
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
        "effect": {"emphasis_marker": "*"},
        "styles": [
            {
                "name": "Default", "font": "Montserrat", "size": 38,
                "primary": WHITE, "outline": BLACK, "back": "&H80000000",
                "bold": True, "outline_width": 1.5, "shadow": 0,
                "box": True, "margin_l": 40, "margin_r": 40, "margin_v": 40,
                "alignment": 2,
            },
            {
                "name": "Emph", "font": "Montserrat", "size": 38,
                "primary": GREEN, "outline": BLACK, "back": "&H80000000",
                "bold": True, "outline_width": 1.5, "shadow": 0,
                "box": True, "margin_l": 40, "margin_r": 40, "margin_v": 40,
                "alignment": 2,
            },
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
    # ── Family 3: Documentary / cinematic (BBC/Netflix compliant) ─────
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
        "description": "Small lowercase white, no outline, no animation. The counter-trend.",
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
    "glassmorphism": {
        "name": "glassmorphism",
        "description": "Frosted look: dark semi-transparent box + light border + soft shadow.",
        "styles": [
            {
                "name": "Default", "font": "Poppins", "size": 36,
                "primary": WHITE, "outline": "&H00FFFFFF", "back": "&H40000000",
                "bold": True, "outline_width": 0.5, "shadow": 2,
                "box": True, "margin_l": 40, "margin_r": 40, "margin_v": 42,
                "alignment": 2,
            }
        ],
    },
    # ── Family 4: Stylized ────────────────────────────────────────────
    "neon-blur": {
        "name": "neon-blur",
        "description": "Noto Sans Mono magenta with colored shadow glow (\\shad + \\4c). Real neon.",
        "styles": [
            {
                "name": "Default", "font": "Noto Sans Mono", "size": 38,
                "primary": MAGENTA, "outline": "&H00000000", "back": MAGENTA,
                "bold": True, "outline_width": 0, "shadow": 8,
                "alignment": 2, "margin_v": 55,
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
                "name": "Default", "font": "Bebas Neue", "size": 46,
                "primary": YELLOW, "outline": BLACK, "back": "&HC0000000",
                "bold": False, "outline_width": 1.0, "shadow": 0,
                "box": True, "margin_l": 34, "margin_r": 34, "margin_v": 36,
                "alignment": 2,
            }
        ],
    },
}


def list_presets() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": preset["description"]}
        for name, preset in PRESETS.items()
    ]
