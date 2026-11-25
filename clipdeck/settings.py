"""Configuration (~/.config/clipdeck/clipdeck.conf) and the settings window."""
from __future__ import annotations

import html
import platform
import sqlite3
import time
from pathlib import Path

from . import __author__, __version__
from .qt import (BINDING, QAbstractSocket, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                 QFileDialog, QFont, QFontDialog, QFormLayout, QGridLayout, QGroupBox,
                 QHBoxLayout, QLabel, QLineEdit, QMessageBox, QNetworkInterface, QPushButton,
                 QSettings, QSpinBox, Qt, QTabWidget, QVBoxLayout, QWidget, qVersion)

SHORTCUT_KEYS = ["hotkey", "hotkey_plain", "hotkey_save"] + [f"hotkey_pos{n}" for n in range(1, 11)]

DEFAULTS = {
    # General
    "autostart": True,
    "startup_message": True,
    "limit_items": True,
    "max_items": 500,
    "expire_enabled": False,
    "expire_days": 30,
    "theme": "system",             # system | light | dark
    "popup_position": "cursor",    # cursor | center | last
    "popup_geometry": "",          # "x,y,w,h", remembered when the window closes
    "font": "",                    # QFont.toString(); empty = system font
    "db_path": "",                 # empty = ~/.local/share/clipdeck/clips.db
    "auto_paste": True,
    "terminal_classes": ("gnome-terminal-server, gnome-terminal, xfce4-terminal, mate-terminal, "
                         "konsole, tilix, terminator, kitty, alacritty, xterm, urxvt, wezterm"),
    "max_image_mb": 10,
    # Supported types and apps
    "save_text": True,
    "save_html": True,
    "save_images": True,
    "save_files": True,
    "apps_include": "*",
    "apps_exclude": "",
    # Keyboard shortcuts (Cinnamon/GTK accelerator format; empty = none)
    "hotkey": "<Primary>grave",
    **{k: "" for k in SHORTCUT_KEYS[1:]},
    **{f"registered_{k}": "" for k in SHORTCUT_KEYS},
    "positions_send_paste": True,
    "positions_move_to_top": False,
    # Sync
    "sync_enabled": False,
    "sync_port": 47811,
    "sync_peers": "",
    "sync_passphrase": "",
    "sync_auto": True,
    "sync_to_clipboard": False,
    # Stats
    "stats_since": "",
    "stats_copies": 0,
    "stats_pastes": 0,
    "trip_since": "",
    "trip_copies": 0,
    "trip_pastes": 0,
}


class Config:
    def __init__(self):
        self.s = QSettings("clipdeck", "clipdeck")
        now = time.strftime("%Y-%m-%d %H:%M")
        for key in ("stats_since", "trip_since"):
            if not self.get(key):
                self.set(key, now)

    def get(self, key: str):
        default = DEFAULTS[key]
        value = self.s.value(key, default)
        if isinstance(default, bool):
            return value in (True, "true", "1", 1)
        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        return "" if value is None else str(value)

    def set(self, key: str, value):
        self.s.setValue(key, value)
        self.s.sync()

    def bump(self, what: str, n: int = 1):
        """Count a copy or paste in both the overall and the since-reset totals."""
        for prefix in ("stats", "trip"):
            self.set(f"{prefix}_{what}", self.get(f"{prefix}_{what}") + n)

    def terminal_classes(self) -> set[str]:
        return {c.strip().lower() for c in self.get("terminal_classes").split(",") if c.strip()}

    def path(self) -> str:
        return self.s.fileName()


def local_addresses() -> str:
    addrs = [a.toString() for a in QNetworkInterface.allAddresses()
             if a.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol and not a.isLoopback()]
    return ", ".join(addrs) or "unknown"


# ---- shortcut recorder ------------------------------------------------------
# X11 key codes of a standard PC keyboard, by physical position. Using these,
# a shortcut pressed with a Russian, Tajik or Turkish layout active is still
# recorded as the same physical key (Ctrl+V, not Ctrl+М).
_KEYCODES = {**{10 + i: str((i + 1) % 10) for i in range(10)},
             **{24 + i: c for i, c in enumerate("qwertyuiop")},
             **{38 + i: c for i, c in enumerate("asdfghjkl")},
             **{52 + i: c for i, c in enumerate("zxcvbnm")},
             49: "grave", 20: "minus", 21: "equal", 34: "bracketleft", 35: "bracketright",
             47: "semicolon", 48: "apostrophe", 51: "backslash", 59: "comma", 60: "period",
             61: "slash"}
_QT_TO_GTK = {"Key_Space": "space", "Key_Return": "Return", "Key_Tab": "Tab",
              "Key_Insert": "Insert", "Key_Delete": "Delete", "Key_Home": "Home", "Key_End": "End",
              "Key_PageUp": "Page_Up", "Key_PageDown": "Page_Down", "Key_Up": "Up",
              "Key_Down": "Down", "Key_Left": "Left", "Key_Right": "Right", "Key_Print": "Print",
              **{f"Key_F{n}": f"F{n}" for n in range(1, 13)}}


class ShortcutEdit(QLineEdit):
    """Click, then press the keys. Backspace or the clear button removes the shortcut."""

    def __init__(self, accel: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText("None")
        self.setClearButtonEnabled(True)
        self.textChanged.connect(lambda t: t or self._set(""))
        self._set(accel)

    def accel(self) -> str:
        return self._accel

    def _set(self, accel: str):
        from .desktop import gtk_to_qt
        self._accel = accel
        self.blockSignals(True)
        self.setText(gtk_to_qt(accel) if accel else "")
        self.blockSignals(False)

    def keyPressEvent(self, ev):
        key, mods = int(ev.key()), ev.modifiers()
        any_mod = bool(mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
                               | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.MetaModifier))
        if key in (Qt.Key.Key_Backspace.value, Qt.Key.Key_Delete.value) and not any_mod:
            self._set("")
            return
        if key in (Qt.Key.Key_Tab.value, Qt.Key.Key_Backtab.value) and not (mods & Qt.KeyboardModifier.ControlModifier):
            return super().keyPressEvent(ev)  # keep Tab for moving between fields
        if key in (Qt.Key.Key_Control.value, Qt.Key.Key_Shift.value, Qt.Key.Key_Alt.value,
                   Qt.Key.Key_Meta.value, Qt.Key.Key_Super_L.value, Qt.Key.Key_Super_R.value,
                   Qt.Key.Key_AltGr.value):
            return  # wait for the real key
        name = _KEYCODES.get(ev.nativeScanCode())
        if name is None:
            qt_name = next((n for n in _QT_TO_GTK if getattr(Qt.Key, n).value == key), None)
            name = _QT_TO_GTK.get(qt_name)
        if name is None:
            return
        prefix = ""
        if mods & Qt.KeyboardModifier.ControlModifier:
            prefix += "<Primary>"
        if mods & Qt.KeyboardModifier.AltModifier:
            prefix += "<Alt>"
        if mods & Qt.KeyboardModifier.ShiftModifier:
            prefix += "<Shift>"
        if mods & Qt.KeyboardModifier.MetaModifier:
            prefix += "<Super>"
        if not prefix and not name.startswith("F"):
            return  # a plain letter would break typing everywhere
        self._set(prefix + name)


# ---- the window ---------------------------------------------------------------
def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * 0.9)
    label.setFont(font)
    return label


def _size(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None, focus: str | None = None, info: dict | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.info = info or {}  # store, db_path, started, sent, received, project_url
        self.setWindowTitle("Clipdeck settings")
        self.setMinimumWidth(600)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._general_tab(), "General")
        self.tabs.addTab(self._types_tab(), "Supported types")
        self.tabs.addTab(self._keys_tab(), "Keyboard shortcuts")
        self.tabs.addTab(self._sync_tab(), "Sync")
        self.tabs.addTab(self._stats_tab(), "Stats")
        self.tabs.addTab(self._about_tab(), "About")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)
        if focus == "hotkey":
            self.tabs.setCurrentIndex(2)
            self.shortcuts["hotkey"].setFocus()

    # ---- General ---------------------------------------------------------
    def _general_tab(self) -> QWidget:
        cfg, w = self.cfg, QWidget()
        f = QFormLayout(w)
        self.autostart = QCheckBox("Start Clipdeck when I log in", checked=cfg.get("autostart"))
        self.startup_msg = QCheckBox("Show a message when Clipdeck starts",
                                     checked=cfg.get("startup_message"))
        f.addRow(self.autostart)
        f.addRow(self.startup_msg)

        self.limit = QCheckBox("Keep at most", checked=cfg.get("limit_items"))
        self.max_items = QSpinBox(minimum=10, maximum=1_000_000, value=cfg.get("max_items"),
                                  suffix=" clips")
        self.expire = QCheckBox("Delete clips not used for", checked=cfg.get("expire_enabled"))
        self.expire_days = QSpinBox(minimum=1, maximum=3650, value=cfg.get("expire_days"),
                                    suffix=" days")
        for box, spin in ((self.limit, self.max_items), (self.expire, self.expire_days)):
            row = QHBoxLayout()
            row.addWidget(box)
            row.addWidget(spin)
            row.addStretch()
            spin.setEnabled(box.isChecked())
            box.toggled.connect(spin.setEnabled)
            f.addRow(row)
        f.addRow(_hint("Pinned and grouped clips are never deleted automatically."))

        self.theme = QComboBox()
        for label, value in (("Same as my desktop", "system"), ("Light", "light"), ("Dark", "dark")):
            self.theme.addItem(label, value)
        self.theme.setCurrentIndex(max(self.theme.findData(cfg.get("theme")), 0))
        f.addRow("Theme", self.theme)

        self.position = QComboBox()
        for label, value in (("At the mouse pointer", "cursor"), ("In the middle of the screen", "center"),
                             ("Where I last left it", "last")):
            self.position.addItem(label, value)
        self.position.setCurrentIndex(max(self.position.findData(cfg.get("popup_position")), 0))
        f.addRow("Window position", self.position)

        self._font = cfg.get("font")
        self.font_btn = QPushButton()
        self.font_btn.clicked.connect(self._pick_font)
        default_font = QPushButton("Default font")
        default_font.clicked.connect(lambda: self._set_font(""))
        row = QHBoxLayout()
        row.addWidget(self.font_btn, 1)
        row.addWidget(default_font)
        f.addRow("Font", row)
        self._set_font(self._font)

        self.db_path = QLineEdit(cfg.get("db_path"))
        self.db_path.setPlaceholderText(str(self.info.get("default_db", "")))
        browse = QPushButton("…")
        browse.setFixedWidth(36)
        browse.clicked.connect(self._pick_db)
        row = QHBoxLayout()
        row.addWidget(self.db_path, 1)
        row.addWidget(browse)
        f.addRow("History file", row)
        f.addRow(_hint("Leave empty for the default. If you choose a new file, your "
                       "current history is copied into it."))

        self.auto_paste = QCheckBox("Paste into the window I was using",
                                    checked=cfg.get("auto_paste"))
        f.addRow(self.auto_paste)
        self.terminals = QLineEdit(cfg.get("terminal_classes"))
        self.terminals.setCursorPosition(0)
        f.addRow("Terminals (Ctrl+Shift+V)", self.terminals)
        self.max_image = QSpinBox(minimum=1, maximum=200, value=cfg.get("max_image_mb"), suffix=" MB")
        f.addRow("Largest image to keep", self.max_image)
        return w

    def _set_font(self, spec: str):
        self._font = spec
        if spec:
            font = QFont()
            font.fromString(spec)
            self.font_btn.setText(f"{font.family()}, {font.pointSize()} pt")
            self.font_btn.setFont(font)
        else:
            self.font_btn.setText("System font")
            self.font_btn.setFont(QFont())

    def _pick_font(self):
        current = QFont()
        if self._font:
            current.fromString(self._font)
        result = QFontDialog.getFont(current, self, "Clipdeck font")
        # PySide6 returns (ok, font); PyQt6 returns (font, ok).
        ok, font = (result if isinstance(result[0], bool) else (result[1], result[0]))
        if ok:
            self._set_font(font.toString())

    def _pick_db(self):
        start = self.db_path.text() or str(self.info.get("default_db", Path.home()))
        path, _ = QFileDialog.getSaveFileName(
            self, "History file", start, "Clipdeck history (*.db)",
            options=QFileDialog.Option.DontConfirmOverwrite)
        if path:
            self.db_path.setText(path)

    # ---- Supported types -------------------------------------------------
    def _types_tab(self) -> QWidget:
        cfg, w = self.cfg, QWidget()
        lay = QVBoxLayout(w)
        kinds = QGroupBox("Save these kinds of copies")
        k = QVBoxLayout(kinds)
        self.types = {}
        for key, label in (("save_text", "Plain text"),
                           ("save_html", "Formatted text (when off, it's saved as plain text)"),
                           ("save_images", "Images"),
                           ("save_files", "Copied files and folders")):
            self.types[key] = QCheckBox(label, checked=cfg.get(key))
            k.addWidget(self.types[key])
        lay.addWidget(kinds)

        apps = QGroupBox("Save copies from these apps")
        a = QFormLayout(apps)
        self.apps_include = QLineEdit(cfg.get("apps_include"))
        self.apps_exclude = QLineEdit(cfg.get("apps_exclude"))
        self.apps_exclude.setPlaceholderText("for example: keepassxc; *bank*")
        a.addRow("Only from", self.apps_include)
        a.addRow("Never from", self.apps_exclude)
        a.addRow(_hint("Separate apps with ; and use * as a wildcard. Use the app's window "
                       "class, usually its name in lowercase: firefox, google-chrome, "
                       "libreoffice, keepassxc. To find one, run xprop WM_CLASS in a terminal "
                       "and click the app's window. Clipdeck checks which window was active "
                       "when you copied."))
        lay.addWidget(apps)
        lay.addStretch()
        return w

    # ---- Keyboard shortcuts ----------------------------------------------
    def _keys_tab(self) -> QWidget:
        cfg, w = self.cfg, QWidget()
        lay = QVBoxLayout(w)
        self.shortcuts: dict[str, ShortcutEdit] = {}
        main = QFormLayout()
        for key, label in (("hotkey", "Open clipboard history"),
                           ("hotkey_plain", "Paste clipboard as plain text"),
                           ("hotkey_save", "Save current clipboard")):
            self.shortcuts[key] = ShortcutEdit(cfg.get(key))
            main.addRow(label, self.shortcuts[key])
        lay.addLayout(main)

        recent = QGroupBox("Shortcuts for the 10 most recent clips")
        r = QVBoxLayout(recent)
        self.send_paste = QCheckBox("Paste right away (otherwise just put the clip on the clipboard)",
                                    checked=cfg.get("positions_send_paste"))
        self.move_top = QCheckBox("Move the clip to the top of the list",
                                  checked=cfg.get("positions_move_to_top"))
        r.addWidget(self.send_paste)
        r.addWidget(self.move_top)
        grid = QGridLayout()
        for n in range(1, 11):
            key = f"hotkey_pos{n}"
            self.shortcuts[key] = ShortcutEdit(cfg.get(key))
            col = 0 if n <= 5 else 2
            grid.addWidget(QLabel(f"Clip {n}"), (n - 1) % 5, col)
            grid.addWidget(self.shortcuts[key], (n - 1) % 5, col + 1)
        r.addLayout(grid)
        lay.addWidget(recent)
        lay.addWidget(_hint("Click a box and press the keys, for example Ctrl+Alt+1. Shortcuts "
                            "work on any keyboard layout. Backspace removes one. Clip numbers "
                            "count pinned clips first, as in the history window."))
        lay.addStretch()
        return w

    # ---- Sync ------------------------------------------------------------
    def _sync_tab(self) -> QWidget:
        cfg, w = self.cfg, QWidget()
        s = QFormLayout(w)
        self.sync_enabled = QCheckBox("Sync clips with other computers", checked=cfg.get("sync_enabled"))
        s.addRow(self.sync_enabled)
        self.port = QSpinBox(minimum=1024, maximum=65535, value=cfg.get("sync_port"))
        s.addRow("Port", self.port)
        self.peers = QLineEdit(cfg.get("sync_peers"))
        self.peers.setPlaceholderText("192.168.1.20, office-pc.local:47811")
        s.addRow("Other computers", self.peers)
        self.passphrase = QLineEdit(cfg.get("sync_passphrase"))
        self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase.setPlaceholderText("Same passphrase on every computer")
        s.addRow("Passphrase", self.passphrase)
        self.sync_auto = QCheckBox("Send every copy automatically", checked=cfg.get("sync_auto"))
        s.addRow(self.sync_auto)
        self.sync_clip = QCheckBox("Put received clips on my clipboard",
                                   checked=cfg.get("sync_to_clipboard"))
        s.addRow(self.sync_clip)
        me = QLabel(f"This computer: {local_addresses()}")
        me.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        s.addRow(me)
        return w

    # ---- Stats -----------------------------------------------------------
    def _stats_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        self.total_box = QGroupBox()
        self.trip_box = QGroupBox()
        self.total_form, self.trip_form = QFormLayout(self.total_box), QFormLayout(self.trip_box)
        row.addWidget(self.total_box)
        row.addWidget(self.trip_box)
        lay.addLayout(row)
        reset = QPushButton("Reset")
        reset.clicked.connect(self._reset_trip)
        self.trip_form.addRow("", reset)

        self.store_form = QFormLayout()
        lay.addLayout(self.store_form)
        remove_all = QPushButton("Delete all clips…")
        remove_all.clicked.connect(self._remove_all)
        lay.addWidget(remove_all, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addStretch()
        self._fill_stats()
        return w

    def _fill_stats(self):
        cfg = self.cfg
        for form, prefix, box in ((self.total_form, "stats", self.total_box),
                                  (self.trip_form, "trip", self.trip_box)):
            while form.rowCount() > (1 if prefix == "trip" else 0):
                form.removeRow(0)
            box.setTitle(("Since " if prefix == "stats" else "Since last reset, ")
                         + cfg.get(f"{prefix}_since"))
            form.insertRow(0, "Copies", QLabel(f"{cfg.get(f'{prefix}_copies'):,}"))
            form.insertRow(1, "Pastes", QLabel(f"{cfg.get(f'{prefix}_pastes'):,}"))

        while self.store_form.rowCount():
            self.store_form.removeRow(0)
        store = self.info.get("store")
        if store is not None:
            self.store_form.addRow("Saved clips", QLabel(f"{store.count_matching(include_kept=True):,}"))
        db = self.info.get("db_path")
        if db and Path(db).exists():
            self.store_form.addRow("History file size", QLabel(_size(Path(db).stat().st_size)))
        started = self.info.get("started")
        if started:
            up = int(time.time() - started)
            self.store_form.addRow("Running since", QLabel(
                f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(started))}  "
                f"({up // 86400} d {up % 86400 // 3600} h {up % 3600 // 60} min)"))
        self.store_form.addRow("Clips sent / received since start",
                               QLabel(f"{self.info.get('sent', 0)} / {self.info.get('received', 0)}"))

    def _reset_trip(self):
        self.cfg.set("trip_since", time.strftime("%Y-%m-%d %H:%M"))
        self.cfg.set("trip_copies", 0)
        self.cfg.set("trip_pastes", 0)
        self._fill_stats()

    def _remove_all(self):
        store = self.info.get("store")
        if store is None:
            return
        n = store.count_matching(include_kept=True)
        if n and QMessageBox.question(
                self, "Delete all clips",
                f"Delete all {n} clips, including pinned and grouped ones? "
                "This can't be undone.") == QMessageBox.StandardButton.Yes:
            store.delete_matching(include_kept=True)
            self._fill_stats()

    # ---- About -----------------------------------------------------------
    def _about_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        url = self.info.get("project_url", "")
        rows = [("Version", __version__), ("Author", __author__),
                ("History file", self.info.get("db_path", "")),
                ("Settings file", self.cfg.path()),
                ("Qt", f"{qVersion()} ({BINDING})"),
                ("Python", platform.python_version()),
                ("SQLite", sqlite3.sqlite_version)]
        table = "".join(f"<tr><td><b>{html.escape(k)}</b>&nbsp;&nbsp;</td>"
                        f"<td>{html.escape(str(v))}</td></tr>" for k, v in rows)
        text = (f"<h3>Clipdeck</h3><table>{table}</table>"
                "<p>Inspired by <a href='https://ditto-cp.sourceforge.io/'>Ditto</a> "
                "for Windows.</p>")
        if url:
            text += (f"<p><a href='{url}'>Project page</a> &nbsp;·&nbsp; "
                     f"<a href='{url}/issues'>Report a problem</a></p>")
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        lay.addWidget(label)
        lay.addStretch()
        return w

    # ---- save ------------------------------------------------------------
    def accept(self):
        if self.sync_enabled.isChecked() and not self.passphrase.text():
            QMessageBox.warning(self, "Clipdeck", "Set a passphrase to turn on sync.")
            self.tabs.setCurrentIndex(3)
            return
        if not self.shortcuts["hotkey"].accel():
            QMessageBox.warning(self, "Clipdeck", "Choose a shortcut for opening the history.")
            self.tabs.setCurrentIndex(2)
            return
        values = {
            "autostart": self.autostart.isChecked(),
            "startup_message": self.startup_msg.isChecked(),
            "limit_items": self.limit.isChecked(),
            "max_items": self.max_items.value(),
            "expire_enabled": self.expire.isChecked(),
            "expire_days": self.expire_days.value(),
            "theme": self.theme.currentData(),
            "popup_position": self.position.currentData(),
            "font": self._font,
            "db_path": self.db_path.text().strip(),
            "auto_paste": self.auto_paste.isChecked(),
            "terminal_classes": self.terminals.text(),
            "max_image_mb": self.max_image.value(),
            "apps_include": self.apps_include.text().strip() or "*",
            "apps_exclude": self.apps_exclude.text().strip(),
            "positions_send_paste": self.send_paste.isChecked(),
            "positions_move_to_top": self.move_top.isChecked(),
            "sync_enabled": self.sync_enabled.isChecked(),
            "sync_port": self.port.value(),
            "sync_peers": self.peers.text(),
            "sync_passphrase": self.passphrase.text(),
            "sync_auto": self.sync_auto.isChecked(),
            "sync_to_clipboard": self.sync_clip.isChecked(),
            **{k: cb.isChecked() for k, cb in self.types.items()},
            **{k: edit.accel() for k, edit in self.shortcuts.items()},
        }
        for k, v in values.items():
            self.cfg.set(k, v)
        super().accept()
