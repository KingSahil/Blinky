"""HyprlandBackend — the primary Linux backend (Hyprland-first).

Phase 1 scope: capture (grim) + window introspection (hyprctl).
Input methods (click/scroll/type/key/focus) and app launching land in
phases 2 and 4 per the roadmap; they raise NotImplementedError until then.
"""

from __future__ import annotations

import time
from pathlib import Path

from utils.logging import get_logger

from .abc import ActionResult, ComputerUseBackend, Screenshot, WindowInfo
from .capture import CaptureStrategyFactory
from .window import get_active_window, list_windows, screen_size

LOGGER = get_logger("blinky.backend.hyprland")


class HyprlandBackend(ComputerUseBackend):
    """Desktop automation backend for Hyprland (wlroots)."""

    def __init__(self) -> None:
        self._started = False

    # ── Lifecycle ──────────────────────────────────────────────
    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def is_available(self) -> bool:
        import shutil

        return all(
            shutil.which(tool) is not None
            for tool in ("hyprctl", "grim")
        )

    # ── Screen ──────────────────────────────────────────────────
    def capture(self, *, window: bool = False) -> Screenshot:
        strategy = CaptureStrategyFactory.get_strategy()
        image = strategy.capture()

        # Save like common/python/capture/__init__.py::capture_screen so the
        # Screenshot shape is byte-compatible with what main.py expects.
        captures_dir = Path("screenshots")
        captures_dir.mkdir(parents=True, exist_ok=True)
        path = captures_dir / f"screen-{int(time.time() * 1000)}.jpg"

        screen_w, screen_h = image.width, image.height
        try:
            resample = image.Resampling.LANCZOS
        except AttributeError:
            resample = image.LANCZOS
        image.thumbnail((1920, 1080), resample=resample)
        image = image.convert("RGB")
        image.save(path, format="JPEG", quality=75, optimize=True)

        return Screenshot(
            path=path,
            width=image.width,
            height=image.height,
            screen_width=screen_w,
            screen_height=screen_h,
        )

    def screen_size(self) -> tuple[int, int]:
        return screen_size()

    # ── Windows / apps ──────────────────────────────────────────
    def get_active_window(self) -> WindowInfo | None:
        return get_active_window()

    def list_windows(self) -> list[WindowInfo]:
        return list_windows()

    def list_apps(self) -> list[dict[str, object]]:
        from .apps import scan_apps

        return [
            {
                "name": e.name,
                "desktop_id": e.desktop_id,
                "exec": e.exec_line,
                "startup_wm_class": e.startup_wm_class,
                "source": e.source,
            }
            for e in scan_apps()
        ]

    def launch_app(self, app_name: str) -> ActionResult:
        from .apps import launch_by_name

        return launch_by_name(app_name)

    # ── Input ───────────────────────────────────────────────────
    def click(
        self,
        *,
        x: int,
        y: int,
        button: str = "left",
        click_count: int = 1,
    ) -> ActionResult:
        from .input import click as _click

        return _click(x, y, button=button, click_count=click_count)

    def scroll(
        self,
        *,
        direction: str,
        amount: int = 3,
        x: int | None = None,
        y: int | None = None,
    ) -> ActionResult:
        from .input import scroll as _scroll

        return _scroll(direction, amount=amount, x=x, y=y)

    def type_text(self, text: str) -> ActionResult:
        from .input import type_text as _type_text

        return _type_text(text)

    def key(self, keys: str) -> ActionResult:
        from .input import key as _key

        return _key(keys)

    def focus_window(self, window_id: str) -> ActionResult:
        from .input import focus_window as _focus_window

        return _focus_window(window_id)


# ── Singleton accessor ────────────────────────────────────────────────

_backend: HyprlandBackend | None = None


def get_backend() -> HyprlandBackend:
    """Process-wide singleton so multiple callers share one backend instance."""
    global _backend
    if _backend is None:
        _backend = HyprlandBackend()
    return _backend
