from __future__ import annotations


def build_prompt(question: str, active_app: dict, ocr_items: list[dict]) -> str:
    # Filter out any OCR items that belong to Slicky itself (the host tutor app)
    # to prevent Slicky from referencing or recommending clicks inside its own UI.
    slicky_ignored_terms = {
        "slicky app", "slicky command", "ctrl + shift", "space", "enter", "ask anything", 
        "groq", "ollama", "shortcut key", "theme: ember", "about: v1.0.0", "action guide",
        "slicky", "clicky"
    }
    
    cleaned_question = question.lower().strip()
    
    filtered_items = []
    for item in ocr_items:
        text = str(item.get("text", "")).lower().strip()
        # Skip if the item matches any Slicky UI text
        if any(term in text for term in slicky_ignored_terms):
            continue
        # Skip Slicky's input text box content matching the user's question
        if cleaned_question and len(text) > 3 and (text in cleaned_question or cleaned_question in text):
            continue
        filtered_items.append(item)

    compact_items = [
        {
            "text": item["text"],
            "x": item["x"],
            "y": item["y"],
            "width": item["width"],
            "height": item["height"],
            "confidence": item["confidence"],
        }
        for item in filtered_items[:180]
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
- ALWAYS ignore Slicky's own floating window. Slicky is the tutor app itself (labeled "Slicky app" in the header). NEVER suggest actions, clicks, or typing inside Slicky itself!
- NEVER invent buttons, menus, commands, tabs, or labels.
- Use exact visible text names in target_text.
- Give concise beginner-friendly steps.
- Maximum 1 step (only return the immediate next action).
- If a sequence of actions is required, return only the FIRST immediate action for the current screen.
- If the user needs to make a choice (like choosing photo/video vs text), ask them what they want to do in the summary instead of providing a generic step.
- If the requested action cannot be answered from visible text, say what visible item to click first or explain that the needed item is not visible.
- For codebase questions, visible file names and folder names are valid UI targets.
- If the user's request is purely informational (e.g. asking to summarize the screen, explain a concept, read text, or answer a question rather than asking how to do a task), put the full detailed summary/answer in "summary" and return an empty list [] for "steps".


Return valid JSON only.

Select the correct format based on the query type:

Format A (For interactive tasks where a UI element needs to be clicked):
{{
  "summary": "A concise summary of the next action.",
  "steps": [
    {{
      "step": 1,
      "instruction": "Click the exact visible thing.",
      "target_text": "Exact visible text"
    }}
  ]
}}

Format B (For purely informational queries, screen summaries, explaining concepts, or answering questions where NO UI action/click is needed):
{{
  "summary": "Detailed screen summary or comprehensive answer to the student's question.",
  "steps": []
}}
""".strip()
