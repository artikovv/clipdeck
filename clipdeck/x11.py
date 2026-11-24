"""X11 helpers: remember the focused window and paste into it via xdotool."""
from __future__ import annotations

import os
import re
import shutil
import subprocess


def is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def have_xdotool() -> bool:
    return shutil.which("xdotool") is not None


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=1).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def active_window() -> str | None:
    if not have_xdotool():
        return None
    wid = _run(["xdotool", "getactivewindow"])
    return wid if wid.isdigit() else None


def window_classes(wid: str) -> set[str]:
    if shutil.which("xprop"):
        out = _run(["xprop", "-id", wid, "WM_CLASS"])
        return {c.lower() for c in re.findall(r'"([^"]*)"', out)}
    # Newer xdotool can report the class itself (used inside Flatpak).
    name = _run(["xdotool", "getwindowclassname", wid])
    return {name.lower()} if name else set()


def paste_into(wid: str, terminal_classes: set[str]):
    """Focus `wid` and send the paste shortcut. Non-blocking on purpose: the
    target app will ask *us* for the clipboard data, so we must keep our event
    loop running."""
    keys = "ctrl+shift+v" if window_classes(wid) & terminal_classes else "ctrl+v"
    subprocess.Popen(["xdotool", "windowactivate", "--sync", wid, "key", "--clearmodifiers", keys],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def force_focus(wid: int):
    """Cinnamon's focus-stealing prevention sometimes refuses to focus a new
    window; xdotool asks the window manager directly."""
    if have_xdotool():
        subprocess.Popen(["xdotool", "windowactivate", str(wid)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
