"""Read-only live Windows overlay/taskbar hit-test regression check.

Run while Blinky's AI cursor/highlight overlay is visible, after an action.
No input is injected and no windows are activated or modified.
"""
import ctypes
from ctypes import wintypes as w
import json
import sys

u = ctypes.WinDLL("user32", use_last_error=True)
u.GetWindowLongW.argtypes = [w.HWND, ctypes.c_int]
u.GetWindowLongW.restype = ctypes.c_long
u.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
u.GetForegroundWindow.restype = w.HWND
u.GetAncestor.argtypes = [w.HWND, w.UINT]
u.GetAncestor.restype = w.HWND
u.WindowFromPoint.argtypes = [w.POINT]
u.WindowFromPoint.restype = w.HWND
u.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
u.MonitorFromWindow.restype = w.HMONITOR


class MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD)]


u.GetMonitorInfoW.argtypes = [w.HMONITOR, ctypes.POINTER(MonitorInfo)]


def rect(hwnd):
    r = w.RECT()
    if not u.GetWindowRect(hwnd, ctypes.byref(r)):
        raise ctypes.WinError(ctypes.get_last_error())
    return [r.left, r.top, r.right, r.bottom]


overlays, taskbars = [], []
callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)


@callback_type
def collect(hwnd, _):
    title, class_name = ctypes.create_unicode_buffer(512), ctypes.create_unicode_buffer(128)
    u.GetWindowTextW(hwnd, title, len(title))
    u.GetClassNameW(hwnd, class_name, len(class_name))
    if title.value == "Blinky Highlight Overlay":
        overlays.append(hwnd)
    if class_name.value in {"Shell_TrayWnd", "Shell_SecondaryTrayWnd"}:
        taskbars.append(hwnd)
    return True


u.EnumWindows(collect, 0)
report = {"overlay_count": len(overlays), "taskbar_count": len(taskbars), "checks": [], "passed": False}
for overlay in overlays:
    bounds = rect(overlay)
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    u.GetMonitorInfoW(u.MonitorFromWindow(overlay, 2), ctypes.byref(info))
    work = info.rcWork
    style = u.GetWindowLongW(overlay, -20)
    check = {"visible": bool(u.IsWindowVisible(overlay)), "bounds": bounds,
             "work_area": [work.left, work.top, work.right, work.bottom],
             "click_through": bool(style & 0x20), "non_activating": bool(style & 0x08000000),
             "not_foreground": u.GetForegroundWindow() != overlay,
             "inside_work_area": bounds[0] >= work.left and bounds[1] >= work.top and bounds[2] <= work.right and bounds[3] <= work.bottom,
             "taskbar_hits": []}
    for bar in taskbars:
        left, top, right, bottom = rect(bar)
        for fraction in (.15, .5, .85):
            x, y = int(left + (right - left) * fraction), (top + bottom) // 2
            target = u.WindowFromPoint(w.POINT(x, y))
            root = u.GetAncestor(target, 2) if target else None
            check["taskbar_hits"].append({"point": [x, y], "overlay_blocks": root == overlay,
                                          "shell_receives": root == bar})
    report["checks"].append(check)
report["passed"] = bool(overlays and taskbars) and all(
    all(check[k] for k in ("visible", "click_through", "non_activating", "not_foreground", "inside_work_area"))
    and all(not hit["overlay_blocks"] for hit in check["taskbar_hits"])
    for check in report["checks"])
print(json.dumps(report, indent=2))
sys.exit(0 if report["passed"] else 1)
