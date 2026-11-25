"""Desktop integration: keyboard shortcut registration and login autostart.

The desktop itself handles the hotkey and runs `clipdeck --show`. That works
with every keyboard layout (Russian, Tajik, Turkish…) because desktops match
physical keys, which a Python key listener would not.
"""
from __future__ import annotations

import ast
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import APP_ID

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
AUTOSTART_FILE = CONFIG_HOME / "autostart" / f"{APP_ID}.desktop"
LEGACY_AUTOSTART = CONFIG_HOME / "autostart" / "clipdeck.desktop"
LAUNCHER = Path.home() / ".local" / "bin" / "clipdeck"
NAME = "Clipdeck: show clipboard history"


# ---- how we're installed ---------------------------------------------------
def sandbox() -> str | None:
    if os.environ.get("FLATPAK_ID"):
        return "flatpak"
    if os.environ.get("SNAP_NAME"):
        return "snap"
    if os.environ.get("APPIMAGE"):
        return "appimage"
    return None


def launch_command() -> str:
    """The command the desktop should run to start or show Clipdeck."""
    kind = sandbox()
    if kind == "flatpak":
        return f"flatpak run {os.environ['FLATPAK_ID']}"
    if kind == "snap":
        return f"/snap/bin/{os.environ['SNAP_NAME']}"
    if kind == "appimage":
        return shlex.quote(os.environ["APPIMAGE"])
    if LAUNCHER.exists():
        return str(LAUNCHER)
    found = shutil.which("clipdeck")
    if found:
        return found
    pkg_parent = Path(__file__).resolve().parent.parent
    return f"env PYTHONPATH={shlex.quote(str(pkg_parent))} {shlex.quote(sys.executable)} -m clipdeck"


def current_desktop() -> str:
    """One of: cinnamon, gnome, mate, xfce, kde, or the raw name."""
    raw = (os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "").lower()
    for key, name in (("cinnamon", "cinnamon"), ("mate", "mate"), ("xfce", "xfce"),
                      ("kde", "kde"), ("plasma", "kde"), ("gnome", "gnome"),
                      ("unity", "gnome"), ("budgie", "gnome"), ("pantheon", "gnome")):
        if key in raw:
            return name
    return raw or "unknown"


# ---- autostart ---------------------------------------------------------------
def set_autostart(enabled: bool) -> str | None:
    """Returns a message for the user if something needs their attention."""
    if sandbox() == "flatpak":
        return _portal_autostart(enabled)
    if LEGACY_AUTOSTART.exists():
        LEGACY_AUTOSTART.unlink()
    if enabled:
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART_FILE.write_text(
            "[Desktop Entry]\nType=Application\nName=Clipdeck\n"
            "Comment=Clipboard history manager\n"
            f"Exec={launch_command()} --background\nIcon={APP_ID}\n"
            "X-GNOME-Autostart-enabled=true\n")
    elif AUTOSTART_FILE.exists():
        AUTOSTART_FILE.unlink()
    return None


def _portal_autostart(enabled: bool) -> str | None:
    """Flatpak apps ask the Background portal to start them at login."""
    from .qt import dbus
    classes = dbus()
    if classes is None:
        return "Couldn't set up autostart from the Flatpak sandbox."
    QDBusConnection, QDBusMessage = classes
    msg = QDBusMessage.createMethodCall(
        "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Background", "RequestBackground")
    msg.setArguments(["", {"reason": "Keep clipboard history while you work",
                           "autostart": enabled,
                           "commandline": ["clipdeck", "--background"]}])
    reply = QDBusConnection.sessionBus().call(msg)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        return f"Couldn't set up autostart: {reply.errorMessage()}"
    return None


# ---- keyboard shortcut -------------------------------------------------------
def _run(*cmd: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def _gv(s: str) -> str:
    """Quote a string as GVariant text for `gsettings set`."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _gs_list(schema: str, key: str) -> list[str]:
    out = _run("gsettings", "get", schema, key).stdout.strip()
    if out.startswith("@as"):
        out = out[3:].strip()
    try:
        return list(ast.literal_eval(out)) if out else []
    except (ValueError, SyntaxError):
        return []


def _ok(results) -> str | None:
    failed = [r for r in results if r.returncode != 0]
    return failed[0].stderr.strip() or "unknown error" if failed else None


# Every shortcut Clipdeck can register: key -> (command-line flag, name shown in settings).
SHORTCUTS = {
    "show": ("--show", "Clipdeck: show clipboard history"),
    "plain": ("--paste-plain", "Clipdeck: paste clipboard as plain text"),
    "save": ("--save", "Clipdeck: save current clipboard"),
    **{f"pos{n}": (f"--paste {n}", f"Clipdeck: paste clip {n}") for n in range(1, 11)},
}


def _slug(key: str) -> str:
    return "clipdeck" if key == "show" else f"clipdeck-{key}"


def _cinnamon(key: str, accel: str, command: str, _old: str) -> str | None:
    schema = "org.cinnamon.desktop.keybindings"
    rel = "org.cinnamon.desktop.keybindings.custom-keybinding"
    base = "/org/cinnamon/desktop/keybindings/custom-keybindings/"
    flag = SHORTCUTS[key][0]
    ids = _gs_list(schema, "custom-list")
    target = None
    for i in ids:
        if i == "__dummy__":
            continue
        current = _run("gsettings", "get", f"{rel}:{base}{i}/", "command").stdout.strip()
        if "clipdeck" in current.lower() and current.endswith(f"{flag}'"):
            target = i
            break
    if not accel:  # remove
        if target:
            return _ok([_run("gsettings", "set", schema, "custom-list",
                             "[" + ", ".join(_gv(i) for i in ids if i != target) + "]")])
        return None
    if target is None:
        n = 0
        while f"custom{n}" in ids:
            n += 1
        target = f"custom{n}"
    path = f"{rel}:{base}{target}/"
    results = [_run("gsettings", "set", path, "name", _gv(SHORTCUTS[key][1])),
               _run("gsettings", "set", path, "command", _gv(command)),
               _run("gsettings", "set", path, "binding", f"[{_gv(accel)}]")]
    if target not in ids:
        dummy = ["__dummy__"] if "__dummy__" in ids else []
        new = [i for i in ids if i != "__dummy__"] + [target] + dummy
        results.append(_run("gsettings", "set", schema, "custom-list",
                            "[" + ", ".join(_gv(i) for i in new) + "]"))
    return _ok(results)


def _gnome(key: str, accel: str, command: str, _old: str) -> str | None:
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    path = f"/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/{_slug(key)}/"
    rel = f"{schema}.custom-keybinding:{path}"
    paths = _gs_list(schema, "custom-keybindings")
    if not accel:
        if path in paths:
            return _ok([_run("gsettings", "set", schema, "custom-keybindings",
                             "[" + ", ".join(_gv(p) for p in paths if p != path) + "]")])
        return None
    results = [_run("gsettings", "set", rel, "name", _gv(SHORTCUTS[key][1])),
               _run("gsettings", "set", rel, "command", _gv(command)),
               _run("gsettings", "set", rel, "binding", _gv(accel))]
    if path not in paths:
        results.append(_run("gsettings", "set", schema, "custom-keybindings",
                            "[" + ", ".join(_gv(p) for p in paths + [path]) + "]"))
    return _ok(results)


def _mate(key: str, accel: str, command: str, _old: str) -> str | None:
    dpath = f"/org/mate/desktop/keybindings/{_slug(key)}/"
    if not accel:
        return _ok([_run("dconf", "reset", "-f", dpath)])
    rel = f"org.mate.control-center.keybinding:{dpath}"
    return _ok([_run("gsettings", "set", rel, "name", _gv(SHORTCUTS[key][1])),
                _run("gsettings", "set", rel, "action", _gv(command)),
                _run("gsettings", "set", rel, "binding", _gv(accel))])


def _xfce(key: str, accel: str, command: str, old: str) -> str | None:
    channel = "xfce4-keyboard-shortcuts"
    if old and old != accel:
        _run("xfconf-query", "-c", channel, "-p", f"/commands/custom/{old}", "-r")
    if not accel:
        return None
    return _ok([_run("xfconf-query", "-c", channel, "-p", f"/commands/custom/{accel}",
                     "-n", "-t", "string", "-s", command)])


QT_KEY_NAMES = {"grave": "`", "space": "Space", "return": "Return", "tab": "Tab",
                "escape": "Esc", "insert": "Ins", "delete": "Del", "minus": "-",
                "equal": "=", "comma": ",", "period": ".", "slash": "/", "backslash": "\\",
                "semicolon": ";", "apostrophe": "'", "bracketleft": "[", "bracketright": "]"}


def gtk_to_qt(accel: str) -> str:
    """'<Primary><Alt>v' -> 'Ctrl+Alt+V' (the format KDE uses)."""
    mods = {"primary": "Ctrl", "control": "Ctrl", "ctrl": "Ctrl", "alt": "Alt",
            "shift": "Shift", "super": "Meta", "meta": "Meta"}
    parts = [mods.get(m.lower(), m) for m in re.findall(r"<([^>]+)>", accel)]
    key = re.sub(r"<[^>]+>", "", accel)
    key = QT_KEY_NAMES.get(key.lower(), key.upper() if len(key) == 1 else key)
    return "+".join(parts + [key])


def _kde(key: str, accel: str, command: str, _old: str) -> str | None:
    # KDE runs shortcuts attached to .desktop files listed in kglobalshortcutsrc.
    tool = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
    if not tool:
        return "kwriteconfig6 not found"
    apps = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "applications"
    name = "clipdeck-show.desktop" if key == "show" else f"{_slug(key)}.desktop"
    args = [tool, "--file", "kglobalshortcutsrc", "--group", "services", "--group", name, "--key", "_launch"]
    if not accel:
        (apps / name).unlink(missing_ok=True)
        _run(*args, "--delete")
        return None
    apps.mkdir(parents=True, exist_ok=True)
    (apps / name).write_text(f"[Desktop Entry]\nType=Application\nName={SHORTCUTS[key][1]}\n"
                             f"Exec={command}\nIcon={APP_ID}\nNoDisplay=true\n"
                             f"X-KDE-Shortcuts={gtk_to_qt(accel)}\n")
    err = _ok([_run(*args, gtk_to_qt(accel))])
    return err or "log out and back in to activate it"


HANDLERS = {"cinnamon": _cinnamon, "gnome": _gnome, "mate": _mate, "xfce": _xfce, "kde": _kde}


def register_shortcut(accel: str, command: str, old_accel: str = "",
                      key: str = "show") -> tuple[bool, str]:
    """Bind `accel` (GTK format, e.g. <Primary>grave) to `command` plus the flag for `key`.
    An empty `accel` removes the shortcut."""
    full = f"{command} {SHORTCUTS[key][0]}"
    manual = f"Add a custom shortcut in your desktop's keyboard settings that runs: {full}"
    if sandbox() in ("flatpak", "snap"):
        if not accel:
            return True, ""
        return False, f"Clipdeck can't set shortcuts from inside a {sandbox()} sandbox. {manual}"
    desktop = current_desktop()
    handler = HANDLERS.get(desktop)
    if handler is None:
        return (True, "") if not accel else \
            (False, f"Clipdeck doesn't know how to set shortcuts on {desktop}. {manual}")
    note = handler(key, accel, full, old_accel)
    if note and note != "log out and back in to activate it":
        return False, f"Couldn't set the shortcut ({note}). {manual}"
    if not accel:
        return True, ""
    msg = f"Shortcut {gtk_to_qt(accel)} set."
    return True, msg + (f" On KDE, {note}." if note else "")
