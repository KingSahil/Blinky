"""Backend package for Blinky Linux desktop automation.

HyprlandBackend is the primary implementation (Hyprland-first per roadmap);
GnomeBackend and KdeBackend follow in phase 8 using the same ABC.
"""

from .abc import ActionResult, ComputerUseBackend, Screenshot, UIElement, WindowInfo
from .hyprland import HyprlandBackend, get_backend

__all__ = [
    "ActionResult",
    "ComputerUseBackend",
    "HyprlandBackend",
    "Screenshot",
    "UIElement",
    "WindowInfo",
    "get_backend",
]
