from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from utils.screen_elements import assign_screen_element_refs


DEFAULT_CACHE_DIR = Path("python/cache/ui_maps")


def window_signature(active_app: dict[str, Any], screenshot: Any, target_pid: int | None = None) -> dict[str, Any]:
    """Build a small signature for the currently mapped top-level window."""
    return {
        "title": str(active_app.get("title", "")),
        "process": str(active_app.get("process", "")),
        "target_pid": target_pid,
        "width": int(getattr(screenshot, "width", 0) or 0),
        "height": int(getattr(screenshot, "height", 0) or 0),
        "screen_width": int(getattr(screenshot, "screen_width", 0) or 0),
        "screen_height": int(getattr(screenshot, "screen_height", 0) or 0),
    }


def preserve_stable_refs(previous_items: list[dict[str, Any]], current_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign refs to current items while reusing refs from equivalent previous items."""
    previous = [dict(item) for item in previous_items]
    used_previous: set[int] = set()
    next_ref = _next_ref_number(previous)
    output: list[dict[str, Any]] = []

    for current in current_items:
        item = dict(current)
        match_index = _find_equivalent_previous(item, previous, used_previous)
        if match_index is not None:
            item["ref"] = previous[match_index].get("ref")
            used_previous.add(match_index)
        else:
            item["ref"] = item.get("ref") or f"@e{next_ref}"
            next_ref += 1
        output.append(item)

    return assign_screen_element_refs(output)


def merge_changed_regions(
    previous_items: list[dict[str, Any]],
    refreshed_items: list[dict[str, Any]],
    changed_regions: list[dict[str, int]],
) -> list[dict[str, Any]]:
    """Merge a partial refresh into the previous map, replacing only changed regions."""
    if not changed_regions:
        return preserve_stable_refs(previous_items, refreshed_items)

    unchanged = [
        dict(item)
        for item in previous_items
        if not any(_rects_overlap(_item_rect(item), _region_rect(region)) for region in changed_regions)
    ]
    merged = unchanged + [dict(item) for item in refreshed_items]
    return preserve_stable_refs(previous_items, merged)


class UiMapCache:
    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR, ttl_seconds: float = 2.0) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds

    def get_or_build(self, signature: dict[str, Any], builder: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]]:
        cached = self.load(signature)
        if cached is not None:
            return cached

        previous = self.load(signature, allow_stale=True) or []
        items = preserve_stable_refs(previous, builder())
        self.save(signature, items)
        return items

    def load(self, signature: dict[str, Any], allow_stale: bool = False) -> list[dict[str, Any]] | None:
        path = self.path_for(signature)
        if not path.exists():
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        if payload.get("signature") != signature:
            return None

        if not allow_stale:
            age_seconds = time.time() - float(payload.get("updated_at", 0) or 0)
            if age_seconds > self.ttl_seconds:
                return None

        items = payload.get("items")
        if not isinstance(items, list):
            return None
        return [dict(item) for item in items if isinstance(item, dict)]

    def save(self, signature: dict[str, Any], items: list[dict[str, Any]]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "signature": signature,
            "updated_at": time.time(),
            "items": [dict(item) for item in items],
        }
        self.path_for(signature).write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    def path_for(self, signature: dict[str, Any]) -> Path:
        process = _slug(str(signature.get("process", "app")) or "app")
        title = _slug(str(signature.get("title", "window")) or "window")
        digest = hashlib.sha1(json.dumps(signature, sort_keys=True).encode("utf-8")).hexdigest()[:10]
        return self.cache_dir / f"{process}-{title}-{digest}.json"


def _find_equivalent_previous(
    current: dict[str, Any],
    previous_items: list[dict[str, Any]],
    used_previous: set[int],
) -> int | None:
    for index, previous in enumerate(previous_items):
        if index in used_previous:
            continue
        if _strong_identity(current, previous):
            return index

    best_index: int | None = None
    best_score = 0.0
    for index, previous in enumerate(previous_items):
        if index in used_previous:
            continue
        score = _similarity_score(current, previous)
        if score > best_score:
            best_score = score
            best_index = index
    return best_index if best_score >= 0.78 else None


def _strong_identity(current: dict[str, Any], previous: dict[str, Any]) -> bool:
    automation_id = _norm(current.get("automation_id"))
    previous_automation_id = _norm(previous.get("automation_id"))
    if automation_id and automation_id == previous_automation_id:
        return _same_control_family(current, previous)
    return False


def _similarity_score(current: dict[str, Any], previous: dict[str, Any]) -> float:
    if not _same_control_family(current, previous):
        return 0.0

    current_name = _element_name(current)
    previous_name = _element_name(previous)
    overlap = _intersection_over_union(_item_rect(current), _item_rect(previous))
    center_distance = _center_distance(current, previous)
    distance_score = max(0.0, 1.0 - min(center_distance, 120.0) / 120.0)
    name_score = 1.0 if current_name and previous_name == current_name else 0.0
    return (overlap * 0.55) + (distance_score * 0.25) + (name_score * 0.20)


def _same_control_family(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _norm(left.get("control_type")) == _norm(right.get("control_type")) and _norm(left.get("source")) == _norm(
        right.get("source")
    )


def _element_name(item: dict[str, Any]) -> str:
    return _norm(item.get("text") or item.get("ai_label"))


def _item_rect(item: dict[str, Any]) -> tuple[float, float, float, float]:
    x = float(item.get("x", 0) or 0)
    y = float(item.get("y", 0) or 0)
    width = max(0.0, float(item.get("width", 0) or 0))
    height = max(0.0, float(item.get("height", 0) or 0))
    return (x, y, x + width, y + height)


def _region_rect(region: dict[str, int]) -> tuple[float, float, float, float]:
    return _item_rect(region)


def _rects_overlap(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> bool:
    return left[0] < right[2] and left[2] > right[0] and left[1] < right[3] and left[3] > right[1]


def _intersection_over_union(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    if not _rects_overlap(left, right):
        return 0.0
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def _center_distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_rect = _item_rect(left)
    right_rect = _item_rect(right)
    left_x = (left_rect[0] + left_rect[2]) / 2
    left_y = (left_rect[1] + left_rect[3]) / 2
    right_x = (right_rect[0] + right_rect[2]) / 2
    right_y = (right_rect[1] + right_rect[3]) / 2
    return ((left_x - right_x) ** 2 + (left_y - right_y) ** 2) ** 0.5


def _next_ref_number(items: list[dict[str, Any]]) -> int:
    highest = 0
    for item in items:
        match = re.match(r"^@e(\d+)$", str(item.get("ref", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:48] or "window"
