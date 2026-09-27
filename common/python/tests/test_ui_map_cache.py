from __future__ import annotations

import json
import time
from pathlib import Path

from utils.ui_map_cache import (
    UiMapCache,
    merge_changed_regions,
    preserve_stable_refs,
    window_signature,
)


class ScreenshotStub:
    path = Path("screen.png")
    width = 1280
    height = 720
    screen_width = 1280
    screen_height = 720


def test_ui_map_cache_reuses_fresh_snapshot_without_builder(tmp_path: Path) -> None:
    cache = UiMapCache(tmp_path, ttl_seconds=60)
    signature = window_signature({"title": "Editor", "process": "Code.exe"}, ScreenshotStub(), target_pid=123)
    items = [
        {
            "ref": "@e1",
            "text": "Extensions",
            "control_type": "Button",
            "x": 16,
            "y": 170,
            "width": 24,
            "height": 24,
            "source": "uia",
        }
    ]
    cache.save(signature, items)

    reused = cache.get_or_build(
        signature,
        builder=lambda: (_ for _ in ()).throw(AssertionError("builder should not run for fresh cache")),
    )

    assert reused == items
    snapshot = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert snapshot["signature"]["process"] == "Code.exe"
    assert snapshot["items"][0]["ref"] == "@e1"


def test_ui_map_cache_rebuilds_stale_snapshot(tmp_path: Path) -> None:
    cache = UiMapCache(tmp_path, ttl_seconds=0.01)
    signature = window_signature({"title": "Editor", "process": "Code.exe"}, ScreenshotStub(), target_pid=123)
    cache.save(signature, [{"ref": "@e1", "text": "Old", "x": 1, "y": 1, "width": 5, "height": 5}])
    time.sleep(0.02)

    rebuilt = cache.get_or_build(
        signature,
        builder=lambda: [{"text": "New", "x": 1, "y": 1, "width": 5, "height": 5}],
    )

    assert rebuilt[0]["text"] == "New"
    assert rebuilt[0]["ref"] == "@e1"


def test_preserve_stable_refs_matches_automation_id_and_bounds() -> None:
    previous = [
        {
            "ref": "@e4",
            "text": "Search Extensions in Marketplace",
            "automation_id": "search-box",
            "control_type": "Edit",
            "x": 80,
            "y": 90,
            "width": 320,
            "height": 30,
            "source": "uia",
        },
        {
            "ref": "@e7",
            "text": "Install",
            "control_type": "Button",
            "x": 420,
            "y": 210,
            "width": 80,
            "height": 28,
            "source": "uia",
        },
    ]
    current = [
        {
            "text": "Search Extensions in Marketplace",
            "automation_id": "search-box",
            "control_type": "Edit",
            "x": 82,
            "y": 92,
            "width": 320,
            "height": 30,
            "source": "uia",
        },
        {
            "text": "Install",
            "control_type": "Button",
            "x": 425,
            "y": 212,
            "width": 80,
            "height": 28,
            "source": "uia",
        },
        {
            "text": "Reload",
            "control_type": "Button",
            "x": 520,
            "y": 212,
            "width": 80,
            "height": 28,
            "source": "uia",
        },
    ]

    stable = preserve_stable_refs(previous, current)

    assert [item["ref"] for item in stable] == ["@e4", "@e7", "@e8"]


def test_merge_changed_regions_keeps_unchanged_old_elements() -> None:
    previous = [
        {"ref": "@e1", "text": "Explorer", "x": 16, "y": 50, "width": 24, "height": 24},
        {"ref": "@e2", "text": "Old Result", "x": 120, "y": 200, "width": 200, "height": 32},
    ]
    refreshed = [
        {"text": "New Result", "x": 120, "y": 200, "width": 200, "height": 32},
    ]

    merged = merge_changed_regions(
        previous,
        refreshed,
        changed_regions=[{"x": 100, "y": 180, "width": 260, "height": 80}],
    )

    assert len(merged) == 2
    assert merged[0]["ref"] == "@e1"
    assert merged[0]["text"] == "Explorer"
    assert merged[1]["ref"] == "@e2"
    assert merged[1]["text"] == "New Result"
