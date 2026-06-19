from __future__ import annotations

from typing import Any


INTERACTIVE_CONTROL_TYPES = {
    "button",
    "image",
    "hyperlink",
    "tabitem",
    "menuitem",
    "edit",
    "textbox",
    "combobox",
    "listitem",
    "treeitem",
    "custom",
}

INPUT_CONTROL_TYPES = {"edit", "textbox", "combobox"}
UNLABELED_LABEL_TYPES = {"button", "image", "hyperlink", "tabitem", "menuitem"}


def assign_screen_element_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return UI items with stable prompt refs and lightweight action metadata."""
    labeled: list[dict[str, Any]] = []
    unlabeled_counts: dict[str, int] = {}

    for index, item in enumerate(items, start=1):
        normalized = dict(item)
        control_type = str(normalized.get("control_type", "") or "").strip()
        control_norm = control_type.lower()
        source = str(normalized.get("source", "") or "").lower()

        normalized["ref"] = str(normalized.get("ref") or f"@e{index}")
        normalized["source"] = source or normalized.get("source", "")
        normalized["control_type"] = control_type
        normalized["clickable"] = bool(
            normalized.get("clickable")
            or control_norm in INTERACTIVE_CONTROL_TYPES
            or source == "uia"
        )
        normalized["input"] = bool(normalized.get("input") or control_norm in INPUT_CONTROL_TYPES)

        if not str(normalized.get("text", "")).strip() and source == "uia" and control_norm in UNLABELED_LABEL_TYPES:
            label_type = control_type or "Control"
            key = label_type.lower()
            unlabeled_counts[key] = unlabeled_counts.get(key, 0) + 1
            normalized["ai_label"] = normalized.get("ai_label") or f"Visible {label_type} {unlabeled_counts[key]}"

        labeled.append(normalized)

    return labeled


def screen_element_name(item: dict[str, Any]) -> str:
    text = str(item.get("text", "")).strip()
    if text:
        return text
    return str(item.get("ai_label", "")).strip()
