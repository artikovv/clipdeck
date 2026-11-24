import pytest

from clipdeck import desktop


@pytest.mark.parametrize("gtk,qt", [
    ("<Primary>grave", "Ctrl+`"),
    ("<Primary><Alt>v", "Ctrl+Alt+V"),
    ("<Super>v", "Meta+V"),
    ("<Control><Shift>space", "Ctrl+Shift+Space"),
])
def test_gtk_to_qt(gtk, qt):
    assert desktop.gtk_to_qt(gtk) == qt


@pytest.mark.parametrize("env,name", [
    ("X-Cinnamon", "cinnamon"), ("ubuntu:GNOME", "gnome"), ("MATE", "mate"),
    ("XFCE", "xfce"), ("KDE", "kde"), ("Budgie:GNOME", "gnome"),
])
def test_current_desktop(monkeypatch, env, name):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", env)
    assert desktop.current_desktop() == name


@pytest.mark.parametrize("var,value,expected", [
    ("FLATPAK_ID", "io.github.x.Clipdeck", "flatpak run io.github.x.Clipdeck"),
    ("SNAP_NAME", "clipdeck", "/snap/bin/clipdeck"),
    ("APPIMAGE", "/home/u/Clipdeck.AppImage", "/home/u/Clipdeck.AppImage"),
])
def test_launch_command_in_sandboxes(monkeypatch, var, value, expected):
    for v in ("FLATPAK_ID", "SNAP_NAME", "APPIMAGE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv(var, value)
    assert desktop.launch_command() == expected


def test_shortcut_refused_inside_flatpak(monkeypatch):
    monkeypatch.setenv("FLATPAK_ID", "io.github.x.Clipdeck")
    ok, msg = desktop.register_shortcut("<Primary>grave", "flatpak run io.github.x.Clipdeck")
    assert not ok and "flatpak run io.github.x.Clipdeck --show" in msg
