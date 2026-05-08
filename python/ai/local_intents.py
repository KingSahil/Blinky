from __future__ import annotations


def answer_local_question(question: str, visible_items: list[dict]) -> dict | None:
    """Fast deterministic answers for repo/demo questions.

    The hackathon demo often asks "where is frontend?" while VS Code is open.
    Waiting for the model to infer that from noisy OCR is brittle, so we answer
    this directly and let matching point at the visible `frontend` text.
    """
    normalized = question.lower()
    if "frontend" not in normalized:
        return None

    target = _best_visible_frontend_target(visible_items)
    if not target:
        return None

    target_text = target["text"]

    return {
        "summary": "The frontend lives in the `frontend` folder in this project.",
        "steps": [
            {
                "step": 1,
                "instruction": "Open the `frontend` folder in your project tree.",
                "target_text": target_text,
            },
            {
                "step": 2,
                "instruction": "Expand that folder and open the file you want from inside it.",
                "target_text": target_text,
            },
        ],
        "warnings": [],
    }


def _best_visible_frontend_target(visible_items: list[dict]) -> dict | None:
    preferred_terms = [
        "frontend",
        "frontend/src/app.tsx",
        "app.tsx",
        "vite.config.ts",
    ]

    for term in preferred_terms:
        for item in visible_items:
            text = str(item.get("text", "")).lower()
            if text == term:
                return item

    for item in visible_items:
        text = str(item.get("text", "")).lower()
        if "frontend" in text or "app.tsx" in text:
            return item

    return None
