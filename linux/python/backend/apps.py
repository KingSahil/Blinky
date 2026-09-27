"""Application registry for Linux: .desktop file scanning + launching.

The .desktop file is the universal app registry on Linux — its Exec line
encodes the launch method (flatpak run / native binary / snap), so we never
need to detect "how it was installed". `gio launch <file.desktop>` handles
Exec parsing, field codes (%U %F), env, and flatpak wrappers for us.

Search priority (user overrides system):
  1. ~/.local/share/applications            (user-installed, flatpak --user)
  2. /var/lib/flatpak/exports/share/applications   (system flatpak)
  3. /usr/local/share/applications
  4. /usr/share/applications                (native packages)
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from utils.logging import get_logger

from .abc import ActionResult

LOGGER = get_logger("blinky.backend.apps")

DESKTOP_DIRS = [
    Path.home() / ".local" / "share" / "applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
]


@dataclass
class DesktopEntry:
    """Parsed .desktop file (the subset Blinky needs)."""

    name: str
    desktop_id: str  # filename stem, e.g. "com.vivaldi.Vivaldi"
    exec_line: str
    path: Path
    source: str = "native"  # native | flatpak | user
    startup_wm_class: str = ""
    categories: list[str] = field(default_factory=list)

    def is_flatpak(self) -> bool:
        return "flatpak run" in self.exec_line or self.source == "flatpak"


def _parse_desktop(path: Path) -> DesktopEntry | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None

    name = ""
    exec_line = ""
    wm_class = ""
    categories: list[str] = []
    in_entry = False
    for line in lines:
        line = line.strip()
        if line.startswith("[Desktop Entry]"):
            in_entry = True
            continue
        if not in_entry or line.startswith("[") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "Name" and not name:  # first Name = localized default
            name = value
        elif key == "Exec":
            exec_line = value
        elif key == "StartupWMClass":
            wm_class = value
        elif key == "Categories":
            categories = [c.strip() for c in value.split(";") if c.strip()]

    if not name or not exec_line:
        return None

    # Skip non-application entries (MimeType handlers, links, etc.)
    if any(c in categories for c in ("System", "Settings")):
        pass  # settings apps are launchable too — keep

    source = "flatpak" if "flatpak" in str(path) else (
        "user" if str(path).startswith(str(Path.home())) else "native"
    )
    return DesktopEntry(
        name=name,
        desktop_id=path.stem,
        exec_line=exec_line,
        path=path,
        source=source,
        startup_wm_class=wm_class,
        categories=categories,
    )


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


def scan_apps() -> list[DesktopEntry]:
    """Scan all desktop dirs; later dirs lose on name collisions (user wins)."""
    entries: dict[str, DesktopEntry] = {}
    for directory in DESKTOP_DIRS:
        if not directory.is_dir():
            continue
        try:
            for f in sorted(directory.glob("*.desktop")):
                entry = _parse_desktop(f)
                if entry:
                    # dedupe by desktop_id, keep the higher-priority (earlier dir)
                    entries.setdefault(entry.desktop_id, entry)
        except OSError as exc:
            LOGGER.debug("desktop scan failed for %s: %s", directory, exc)
    return list(entries.values())


def find_entry(app_name: str) -> DesktopEntry | None:
    """Match by Name= (exact, then case-insensitive), then desktop_id stem."""
    target = _normalize(app_name)
    if not target:
        return None

    entries = scan_apps()
    # 1. exact Name match
    for e in entries:
        if _normalize(e.name) == target:
            return e
    # 2. desktop_id / filename stem match
    for e in entries:
        if _normalize(e.desktop_id) == target:
            return e
    # 3. substring on Name (shortest match wins — avoids "Video" matching "Video Editor")
    candidates = [e for e in entries if target in _normalize(e.name)]
    if candidates:
        return min(candidates, key=lambda e: len(_normalize(e.name)))
    return None


def launch_entry(entry: DesktopEntry) -> ActionResult:
    """Launch via `gio launch <file.desktop>` — handles flatpak/native/snap.

    NOTE: never use capture_output here — gio hands its stdout pipe to the
    launched app, so subprocess.run would block until the app exits. DEVNULL
    returns in ~10ms and returncode is still available.
    """
    try:
        result = subprocess.run(
            ["gio", "launch", str(entry.path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except FileNotFoundError:
        # Fallback: parse Exec manually (strip field codes)
        import shlex

        parts = shlex.split(entry.exec_line)
        cmd = [p for p in parts if not p.startswith("%")]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return ActionResult(
                True, "launch_app", f"Launched {entry.name} (raw exec fallback)",
                {"name": entry.name, "method": "raw_exec"},
            )
        except Exception as exc:
            return ActionResult(False, "launch_app", f"Failed to launch {entry.name}: {exc}")
    except subprocess.TimeoutExpired:
        return ActionResult(False, "launch_app", f"Launch of {entry.name} timed out")

    if result.returncode == 0:
        return ActionResult(
            True,
            "launch_app",
            f"Launched {entry.name} ({entry.source})",
            {"name": entry.name, "desktop_id": entry.desktop_id, "source": entry.source},
        )
    return ActionResult(
        False, "launch_app", f"gio launch failed for {entry.name} (rc={result.returncode})",
        {"name": entry.name},
    )


def launch_by_name(app_name: str) -> ActionResult:
    """Full cascade: .desktop scan → gio launch."""
    entry = find_entry(app_name)
    if entry is None:
        return ActionResult(
            False, "launch_app", f"Could not find an installed app named '{app_name}'",
            {"name": app_name},
        )
    return launch_entry(entry)


def get_desktop_path(app_name: str) -> str | None:
    """Resolve a .desktop path for apps that need it (e.g. flatpak run)."""
    entry = find_entry(app_name)
    return str(entry.path) if entry else None


def is_app_installed(app_name: str) -> bool:
    return find_entry(app_name) is not None
