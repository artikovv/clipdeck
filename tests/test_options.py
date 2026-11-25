"""Settings window, filters, shortcuts recorder, and the commands behind global shortcuts."""
import pytest

from clipdeck.clipboard import app_allowed, filter_types
from clipdeck.qt import QApplication, QEvent, QKeyEvent, Qt
from clipdeck.storage import Payload


class FakeCfg(dict):
    def get(self, key):
        from clipdeck.settings import DEFAULTS
        return super().get(key, DEFAULTS[key])

    def set(self, key, value):
        self[key] = value

    def bump(self, what, n=1):
        for prefix in ("stats", "trip"):
            self[f"{prefix}_{what}"] = self.get(f"{prefix}_{what}") + n


@pytest.mark.parametrize("classes,include,exclude,ok", [
    ({"firefox"}, "*", "", True),
    ({"keepassxc"}, "*", "keepassxc", False),
    ({"my-bank-app"}, "*", "*bank*", False),
    ({"firefox"}, "libreoffice; firefox", "", True),
    ({"gedit"}, "libreoffice; firefox", "", False),
    (set(), "*", "keepassxc", True),
    ({"KeePassXC".lower()}, "*", "KeePassXC", False),
])
def test_app_allowed(classes, include, exclude, ok):
    assert app_allowed(classes, include, exclude) is ok


def test_filter_types():
    cfg = FakeCfg(save_html=False)
    assert filter_types(Payload("html", "b", "<b>b</b>"), cfg) == Payload("text", "b")
    cfg = FakeCfg(save_images=False)
    assert filter_types(Payload("image", "i", None, b"x"), cfg) is None
    assert filter_types(Payload("files", "/tmp"), FakeCfg(save_files=False)) is None
    assert filter_types(Payload("text", "t"), FakeCfg()) == Payload("text", "t")


def press(widget, key, mods=Qt.KeyboardModifier.NoModifier, scancode=0, text=""):
    ev = QKeyEvent(QEvent.Type.KeyPress, key, mods, scancode, 0, 0, text)
    QApplication.sendEvent(widget, ev)


def test_shortcut_recorder_uses_physical_keys(qapp):
    from clipdeck.settings import ShortcutEdit
    edit = ShortcutEdit("<Primary>grave")
    assert edit.text() == "Ctrl+`"
    ctrl_alt = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
    # Russian layout: the V key produces Cyrillic "м", but key code 55 is still V.
    press(edit, 0x041C, ctrl_alt, scancode=55, text="м")  # Qt key code for "М"
    assert edit.accel() == "<Primary><Alt>v" and edit.text() == "Ctrl+Alt+V"
    press(edit, Qt.Key.Key_1, ctrl_alt, scancode=10)
    assert edit.accel() == "<Primary><Alt>1"
    press(edit, Qt.Key.Key_A, scancode=38, text="a")   # no modifier: ignored
    assert edit.accel() == "<Primary><Alt>1"
    press(edit, Qt.Key.Key_F9)                          # F-keys alone are fine
    assert edit.accel() == "F9"
    press(edit, Qt.Key.Key_Backspace)
    assert edit.accel() == "" and edit.text() == ""


def test_settings_dialog_saves(qapp, store, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from clipdeck.settings import Config, SettingsDialog
    cfg = Config()
    d = SettingsDialog(cfg, info={"store": store, "db_path": str(tmp_path / "c.db"), "started": 0})
    assert d.tabs.count() == 6
    assert [d.tabs.tabText(i) for i in range(6)] == [
        "General", "Supported types", "Keyboard shortcuts", "Sync", "Stats", "About"]
    d.expire.setChecked(True)
    d.theme.setCurrentIndex(d.theme.findData("dark"))
    d.types["save_images"].setChecked(False)
    d.apps_exclude.setText("keepassxc")
    d.shortcuts["hotkey_pos1"]._set("<Primary><Alt>1")
    d.accept()
    assert cfg.get("expire_enabled") and cfg.get("theme") == "dark"
    assert not cfg.get("save_images") and cfg.get("apps_exclude") == "keepassxc"
    assert cfg.get("hotkey_pos1") == "<Primary><Alt>1" and cfg.get("hotkey") == "<Primary>grave"


def test_stats_and_trip_reset(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from clipdeck.settings import Config, SettingsDialog
    cfg = Config()
    cfg.bump("copies", 3)
    cfg.bump("pastes")
    assert (cfg.get("stats_copies"), cfg.get("trip_copies"), cfg.get("stats_pastes")) == (3, 3, 1)
    SettingsDialog(cfg)._reset_trip()
    assert (cfg.get("stats_copies"), cfg.get("trip_copies")) == (3, 0)


def test_popup_center_and_remembered_size(qapp, store):
    from clipdeck.popup import Popup
    from clipdeck.qt import QGuiApplication
    cfg = FakeCfg(popup_position="center", popup_geometry="10,10,640,480")
    p = Popup(store, cfg)
    p.present()
    geo = QGuiApplication.primaryScreen().availableGeometry()
    assert (p.width(), p.height()) == (min(640, geo.width()), min(480, geo.height()))
    assert abs(p.geometry().center().x() - geo.center().x()) <= 2
    p.hide()
    assert cfg["popup_geometry"].endswith(f",{p.width()},{p.height()}")


def test_cinnamon_several_shortcuts_and_removal(monkeypatch, tmp_path):
    """Uses a fake gsettings that stores values in a dict."""
    from clipdeck import desktop
    db = {"org.cinnamon.desktop.keybindings custom-list": "['custom0', '__dummy__']",
          "org.cinnamon.desktop.keybindings.custom-keybinding:"
          "/org/cinnamon/desktop/keybindings/custom-keybindings/custom0/ command": "'nemo'"}

    def fake_run(*cmd):
        import subprocess
        _, op, *rest = cmd
        key = " ".join(rest[:2])
        out = ""
        if op == "get":
            out = db.get(key, "''")
        elif op == "set":
            db[key] = rest[2]
        return subprocess.CompletedProcess(cmd, 0, out + "\n", "")
    monkeypatch.setattr(desktop, "_run", fake_run)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "X-Cinnamon")
    for v in ("FLATPAK_ID", "SNAP_NAME", "APPIMAGE"):
        monkeypatch.delenv(v, raising=False)

    assert desktop.register_shortcut("<Primary>grave", "/usr/bin/clipdeck")[0]
    assert desktop.register_shortcut("<Primary><Alt>1", "/usr/bin/clipdeck", key="pos1")[0]
    assert desktop.register_shortcut("<Primary><Alt>0", "/usr/bin/clipdeck", key="pos10")[0]
    ids = eval(db["org.cinnamon.desktop.keybindings custom-list"])
    assert ids == ["custom0", "custom1", "custom2", "custom3", "__dummy__"]
    commands = {i: db[f"org.cinnamon.desktop.keybindings.custom-keybinding:"
                      f"/org/cinnamon/desktop/keybindings/custom-keybindings/{i}/ command"]
                for i in ids[1:4]}
    assert commands == {"custom1": "'/usr/bin/clipdeck --show'",
                        "custom2": "'/usr/bin/clipdeck --paste 1'",
                        "custom3": "'/usr/bin/clipdeck --paste 10'"}
    # Removing clip 1's shortcut leaves clip 10's alone.
    assert desktop.register_shortcut("", "/usr/bin/clipdeck", "<Primary><Alt>1", key="pos1")[0]
    assert eval(db["org.cinnamon.desktop.keybindings custom-list"]) == \
        ["custom0", "custom1", "custom3", "__dummy__"]


def test_paste_position_and_plain_paste(qapp, store, monkeypatch):
    from clipdeck import app as appmod
    sets, pastes = [], []
    fake = type("Fake", (), {})()
    fake.store = store
    fake.cfg = FakeCfg(positions_move_to_top=True)
    fake.monitor = type("M", (), {"set_clipboard": lambda self, p, plain=False: sets.append((p, plain)),
                                  "read_now": lambda self: Payload("html", "bold", "<b>bold</b>")})()
    fake._paste_now = lambda target: pastes.append(target)
    monkeypatch.setattr(appmod.x11, "active_window", lambda: "42")
    monkeypatch.setattr(appmod.x11, "is_wayland", lambda: False)
    first = store.add(Payload("text", "older"))
    store.add(Payload("text", "newer"))
    appmod.Clipdeck.paste_position(fake, 2)
    assert sets[-1][0].text == "older" and pastes == ["42"]
    assert store.search()[0].id == first            # moved to the top
    assert fake.cfg["stats_pastes"] == 1
    appmod.Clipdeck.paste_position(fake, 9)         # no such clip: nothing happens
    assert len(sets) == 1
    appmod.Clipdeck.paste_clipboard_plain(fake)
    assert sets[-1] == (Payload("html", "bold", "<b>bold</b>"), True)
