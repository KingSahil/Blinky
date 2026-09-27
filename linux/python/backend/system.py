"""System profile — DE-agnostic desktop context for the agent loop.

Builds a compact, compositor-agnostic description of the running desktop so
the LLM can reason about WHAT is available (launcher, keybinds, tools)
instead of guessing from hardcoded DE assumptions (e.g. "press Alt+F1").

Detects: desktop environment, session type, compositor, app launcher,
keyboard shortcut hints, and the presence of the Blinky toolchain
(hyprctl/grim/ydotool/wtype/krunner/gio). Every field is optional — the
profile degrades gracefully on any distro.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class SystemProfile:
    de: str = ""                      # XDG_CURRENT_DESKTOP (hyprland, gnome, kde, ...)
    session_type: str = ""            # wayland | x11
    compositor: str = ""              # hyprland, kwin_wayland, mutter, ...
    launcher: str = ""                # recommended app launcher command
    launcher_hint: str = ""           # human hint for the LLM
    keybind_hint: str = ""            # how to summon the launcher / menus
    focus_model: str = ""             # click-to-focus | focus-follows-mouse
    tools: list[str] = field(default_factory=list)  # available automation tools

    def to_prompt_block(self) -> str:
        """Compact DE-agnostic context block injected into the system prompt."""
        lines = ["System environment:"]
        if self.de:
            lines.append(f"- Desktop: {self.de}")
        if self.session_type:
            lines.append(f"- Session: {self.session_type}")
        if self.compositor:
            lines.append(f"- Compositor: {self.compositor}")
        if self.launcher:
            lines.append(f"- App launcher: {self.launcher}")
        if self.keybind_hint:
            lines.append(f"- Launcher keybind hint: {self.keybind_hint}")
        if self.focus_model:
            lines.append(f"- Window focus model: {self.focus_model}")
        if self.tools:
            lines.append(f"- Automation tools available: {', '.join(self.tools)}")
        lines.append(
            "- Use open_app() to launch apps — it resolves names via the desktop "
            "registry (.desktop files), so you do NOT need to know launcher commands."
        )
        if self.focus_model == "focus-follows-mouse":
            lines.append(
                "- FOCUSING (important): this desktop uses focus-follows-mouse — "
                "moving the pointer over a window FOCUSES it. To type into an app, "
                "use mouse(move) to the window's center first (list_windows gives "
                "bounds), THEN press_key/type_text. Keyboard shortcuts only affect "
                "the window under the cursor."
            )
        return "\n".join(lines)


def _detect_launcher(de: str, session_type: str, tools: list[str]) -> tuple[str, str]:
    """Return (launcher_cmd, keybind_hint) for the detected DE."""
    de_l = de.lower()
    if "hyprland" in de_l or "hypr" in de_l:
        # Hyprland: hyprctl dispatch exec is the compositor-native launch path
        return "hyprctl dispatch exec", "Super (Meta) key opens the launcher; no global menu bar"
    if "kde" in de_l or "plasma" in de_l:
        return "krunner", "Alt+F2 or Super opens KRunner"
    if "gnome" in de_l or "unity" in de_l:
        return "gio launch (GNOME Shell)", "Super opens the Activities overview"
    if "xfce" in de_l:
        return "xfce4-appfinder", "Alt+F1 or Super opens the app finder"
    if "cinnamon" in de_l:
        return "cinnamon-launcher", "Super opens the Cinnamon menu"
    if "sway" in de_l or "i3" in de_l:
        return "bindsym exec (window manager)", "Super+D or the configured launcher key"
    # Fallback: XDG standard
    if session_type == "x11" and shutil.which("xdotool"):
        return "xdg-launch via .desktop registry", "No DE detected — use open_app()"
    return "", ""


def get_system_profile() -> SystemProfile:
    """Detect the desktop environment and available toolchain."""
    profile = SystemProfile()

    profile.de = os.environ.get("XDG_CURRENT_DESKTOP", "").strip()
    profile.session_type = os.environ.get("XDG_SESSION_TYPE", "").lower().strip()

    # Compositor detection
    if profile.session_type == "wayland":
        if shutil.which("hyprctl"):
            profile.compositor = "hyprland"
        elif os.environ.get("KDE_FULL_SESSION"):
            profile.compositor = "kwin_wayland"
        elif os.environ.get("GNOME_DESKTOP_SESSION_ID") or os.environ.get("XDG_CURRENT_DESKTOP", "").lower() in ("gnome", "ubuntu:gnome"):
            profile.compositor = "mutter"
        elif os.environ.get("SWAYSOCK"):
            profile.compositor = "sway"
    elif profile.session_type == "x11":
        profile.compositor = "x11"

    # Toolchain presence (Blinky's own automation stack)
    for tool in ("hyprctl", "grim", "ydotool", "wtype", "krunner", "gio", "xdotool", "tesseract"):
        if shutil.which(tool):
            profile.tools.append(tool)

    # Focus model: Hyprland (incl. Caelestia/Quickshell shells) follows the
    # mouse by default — moving the pointer over a window focuses it. GNOME/KDE
    # use click-to-focus. X11 varies; default to click-to-focus.
    if profile.compositor == "hyprland":
        profile.focus_model = "focus-follows-mouse"
    elif profile.session_type == "wayland":
        profile.focus_model = "click-to-focus"
    elif profile.session_type == "x11":
        profile.focus_model = "click-to-focus"

    profile.launcher, profile.keybind_hint = _detect_launcher(
        profile.de, profile.session_type, profile.tools
    )

    return profile


_profile_cache: SystemProfile | None = None


def get_system_profile_cached() -> SystemProfile:
    """Process-wide cached profile (cheap; refreshed per daemon start)."""
    global _profile_cache
    if _profile_cache is None:
        _profile_cache = get_system_profile()
    return _profile_cache
