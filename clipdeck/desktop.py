"""Desktop integration: Cinnamon keyboard shortcut and login autostart."""
from __future__ import annotations

import ast
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
AUTOSTART_FILE = CONFIG_HOME / "autostart" / "clipdeck.desktop"
LAUNCHER = Path.home() / ".local" / "bin" / "clipdeck"

KB_SCHEMA = "org.cinnamon.desktop.keybindings"
KB_CUSTOM = "org.cinnamon.desktop.keybindings.custom-keybinding"
KB_BASE = "/org/cinnamon/desktop/keybindings/custom-keybindings/"


def launch_command() -> str:
    if LAUNCHER.exists():
        return str(LAUNCHER)
    found = shutil.which("clipdeck")
    if found:
        return found
    pkg_parent = Path(__file__).resolve().parent.parent
    return f"env PYTHONPATH={shlex.quote(str(pkg_parent))} {shlex.quote(sys.executable)} -m clipdeck"


def set_autostart(enabled: bool):
    if enabled:
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART_FILE.write_text(
            "[Desktop Entry]\nType=Application\nName=Clipdeck\n"
            "Comment=Clipboard history manager\n"
            f"Exec={launch_command()} --background\nIcon=edit-paste\n"
            "X-GNOME-Autostart-enabled=true\n")
    elif AUTOSTART_FILE.exists():
        AUTOSTART_FILE.unlink()


# ---- Cinnamon keyboard shortcut -------------------------------------------
# Cinnamon handles the hotkey itself and runs `clipdeck --show`. That works
# with every keyboard layout (Russian, Tajik, Turkish…) because Cinnamon
# matches physical keys, which a Python key listener would not.

def _gs(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gsettings", *args], capture_output=True, text=True, timeout=3)


def _gvariant_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _custom_list() -> list[str]:
    out = _gs("get", KB_SCHEMA, "custom-list").stdout.strip()
    if out.startswith("@as"):
        out = out[3:].strip()
    try:
        return list(ast.literal_eval(out)) if out else []
    except (ValueError, SyntaxError):
        return []


def register_shortcut(accel: str, command: str) -> tuple[bool, str]:
    manual = f"Add it by hand: System Settings → Keyboard → Shortcuts → Custom, command: {command}"
    if not shutil.which("gsettings") or _gs("list-keys", KB_SCHEMA).returncode != 0:
        return False, f"Couldn't find Cinnamon's shortcut settings. {manual}"

    ids = _custom_list()
    target = None
    for i in ids:
        if i == "__dummy__":
            continue
        cmd = _gs("get", f"{KB_CUSTOM}:{KB_BASE}{i}/", "command").stdout
        if "clipdeck" in cmd and "--show" in cmd:
            target = i
            break
    if target is None:
        n = 0
        while f"custom{n}" in ids:
            n += 1
        target = f"custom{n}"

    path = f"{KB_CUSTOM}:{KB_BASE}{target}/"
    results = [
        _gs("set", path, "name", _gvariant_str("Clipdeck: show clipboard history")),
        _gs("set", path, "command", _gvariant_str(command)),
        _gs("set", path, "binding", f"[{_gvariant_str(accel)}]"),
    ]
    if target not in ids:
        dummy = ["__dummy__"] if "__dummy__" in ids else []
        new_ids = [i for i in ids if i != "__dummy__"] + [target] + dummy
        results.append(_gs("set", KB_SCHEMA, "custom-list",
                           "[" + ", ".join(_gvariant_str(i) for i in new_ids) + "]"))
    failed = [r for r in results if r.returncode != 0]
    if failed:
        return False, f"Couldn't set the shortcut ({failed[0].stderr.strip()}). {manual}"
    return True, f"Shortcut {accel} now opens Clipdeck."
