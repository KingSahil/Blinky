from __future__ import annotations


def build_prompt(question: str, active_app: dict, ocr_items: list[dict]) -> str:
    compact_items = [
        {
            "text": item["text"],
            "x": item["x"],
            "y": item["y"],
            "width": item["width"],
            "height": item["height"],
            "confidence": item["confidence"],
        }
        for item in ocr_items[:180]
    ]

    return f"""
You are Clicky, a free offline AI desktop tutor for students.

The student asks: {question}

Active app:
{active_app}

Visible OCR items:
{compact_items}

Rules:
- ONLY reference visible UI elements from the OCR items.
- NEVER invent buttons, menus, commands, tabs, or labels.
- Use exact visible text names in target_text.
- Give concise beginner-friendly steps.
- Maximum 6 steps.
- Prefer the shortest workflow.
- If the requested action cannot be answered from visible text, say what visible item to click first or explain that the needed item is not visible.
- For codebase questions, visible file names and folder names are valid UI targets.

Return valid JSON only:
{{
  "summary": "One sentence summary.",
  "steps": [
    {{
      "step": 1,
      "instruction": "Click the exact visible thing.",
      "target_text": "Exact visible text"
    }}
  ]
}}
""".strip()
