"""Canonical backend ABC for Blinky desktop automation.

Contract adopted from the Hermes harness (`tools/computer_use/backend.py`),
trimmed to Blinky's needs: no cua-driver baggage (element_token, delivery
ladders) at the interface level, plus Blinky-specific shapes (Screenshot
parity, window bounds).

This module is the single source of truth for the interface. It used to live
only under `linux/python/backend/abc.py`; it now lives here so that non-Linux
backends (cua-driver on Windows) can implement the same contract. The old path
re-exports from here, so existing imports keep working.

Implementations:
  - CuaDriverBackend  (Windows / macOS / Linux — via cua-driver MCP daemon)
  - HyprlandBackend   (Hyprland / wlroots)
  - GnomeBackend      (GNOME Shell / Mutter)
  - KdeBackend        (KDE Plasma / KWin)

Everything above this ABC (main.py, loop.py, tools.py, Rust commands) is
platform-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Core dataclasses ───────────────────────────────────────────────


@dataclass
class UIElement:
    """One interactable element on screen (OCR box, AT-SPI node, or UIA node)."""

    text: str  # visible text / accessible name
    x: int  # screen-absolute logical px (top-left)
    y: int
    width: int
    height: int
    source: str = "ocr"  # "ocr" | "atspi" | "uia"
    role: str = ""  # AT-SPI role / UIA control type; "" for OCR
    automation_id: str = ""  # stable id when available
    confidence: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


@dataclass
class Screenshot:
    """Byte-compatible with common/python/capture/__init__.py::Screenshot."""

    path: Path
    width: int
    height: int
    screen_width: int
    screen_height: int


@dataclass
class WindowInfo:
    """Normalized window descriptor (Windows `active_app` parity)."""

    title: str
    process: str  # app_id class (e.g. "foot", "vivaldi-stable", "chrome")
    supported: bool = True
    x: int = 0  # window bounds, screen-absolute logical px
    y: int = 0
    width: int = 0
    height: int = 0
    pid: int | None = None
    window_id: str = ""  # hyprctl address / cua window_id / HWND


@dataclass
class ActionResult:
    ok: bool
    action: str  # "click" | "type_text" | "key" | "scroll" | "open_app" ...
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


# ── Backend interface ──────────────────────────────────────────────


class ComputerUseBackend(ABC):
    """Desktop automation backend."""

    # ── Lifecycle ──────────────────────────────────────────────
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    # ── Screen ──────────────────────────────────────────────────
    @abstractmethod
    def capture(self, *, window: bool = False) -> Screenshot:
        """Full screen (window=False) or active-window crop (window=True)."""

    @abstractmethod
    def screen_size(self) -> tuple[int, int]:
        """(width, height) of the physical display in logical px."""

    # ── Windows / apps ──────────────────────────────────────────
    @abstractmethod
    def get_active_window(self) -> WindowInfo | None: ...

    @abstractmethod
    def list_windows(self) -> list[WindowInfo]: ...

    @abstractmethod
    def list_apps(self) -> list[dict[str, Any]]:
        """Installed apps: [{name, desktop_id, exec, startup_wm_class, source}]
        source ∈ {"native", "flatpak", "user", "snap"}."""

    @abstractmethod
    def launch_app(self, app_name: str) -> ActionResult:
        """.desktop scan → gio launch (flatpak handled by Exec line)."""

    # ── Input ───────────────────────────────────────────────────
    @abstractmethod
    def click(
        self,
        *,
        x: int,
        y: int,
        button: str = "left",
        click_count: int = 1,
    ) -> ActionResult: ...

    @abstractmethod
    def scroll(
        self,
        *,
        direction: str,
        amount: int = 3,
        x: int | None = None,
        y: int | None = None,
    ) -> ActionResult: ...

    @abstractmethod
    def type_text(self, text: str) -> ActionResult: ...

    @abstractmethod
    def key(self, keys: str) -> ActionResult:
        """Combo like 'ctrl+s' or media keys 'play', 'next', 'prev'."""

    @abstractmethod
    def focus_window(self, window_id: str) -> ActionResult: ...

    # ── Optional: element enumeration ───────────────────────────
    def get_window_elements(self, window_id: str, pid: int | None = None) -> list[UIElement]:
        """Accessibility-tree elements for one window.

        Backends that expose a native tree (UIA / AT-SPI) override this. The
        default returns an empty list so OCR-only backends stay valid.
        """
        return []

    def doctor(self) -> dict[str, Any]:
        """Structured health report. Default: availability only."""
        return {"backend": type(self).__name__, "available": self.is_available()}


__all__ = [
    "ActionResult",
    "ComputerUseBackend",
    "Screenshot",
    "UIElement",
    "WindowInfo",
]
