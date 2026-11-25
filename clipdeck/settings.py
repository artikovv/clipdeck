"""Configuration (~/.config/clipdeck/clipdeck.conf) and the settings dialog."""
from __future__ import annotations

from .qt import QSettings, Qt
from .qt import QAbstractSocket, QNetworkInterface
from .qt import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QLineEdit, QMessageBox, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

DEFAULTS = {
    "hotkey": "<Primary>grave",          # Ctrl+` like Ditto
    "registered_hotkey": "",
    "max_items": 500,
    "max_image_mb": 10,
    "auto_paste": True,
    "terminal_classes": ("gnome-terminal-server, gnome-terminal, xfce4-terminal, mate-terminal, "
                         "konsole, tilix, terminator, kitty, alacritty, xterm, urxvt, wezterm"),
    "autostart": True,
    "startup_message": True,
    "sync_enabled": False,
    "sync_port": 47811,
    "sync_peers": "",
    "sync_passphrase": "",
    "sync_auto": True,
    "sync_to_clipboard": False,
}


class Config:
    def __init__(self):
        self.s = QSettings("clipdeck", "clipdeck")

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

    def terminal_classes(self) -> set[str]:
        return {c.strip().lower() for c in self.get("terminal_classes").split(",") if c.strip()}


def local_addresses() -> str:
    addrs = [a.toString() for a in QNetworkInterface.allAddresses()
             if a.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol and not a.isLoopback()]
    return ", ".join(addrs) or "unknown"


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None, focus: str | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Clipdeck settings")
        self.setMinimumWidth(520)
        tabs = QTabWidget()

        general = QWidget()
        f = QFormLayout(general)
        self.hotkey = QLineEdit(cfg.get("hotkey"))
        f.addRow("Shortcut", self.hotkey)
        hint = QLabel("For example <Primary>grave (Ctrl+`), "
                      "<Primary><Alt>v or <Super>v.")
        hint.setWordWrap(True)
        f.addRow("", hint)
        self.max_items = QSpinBox(minimum=10, maximum=100_000, value=cfg.get("max_items"))
        f.addRow("Clips to keep", self.max_items)
        self.max_image = QSpinBox(minimum=1, maximum=200, value=cfg.get("max_image_mb"), suffix=" MB")
        f.addRow("Largest image to keep", self.max_image)
        self.auto_paste = QCheckBox("Paste into the window I was using")
        self.auto_paste.setChecked(cfg.get("auto_paste"))
        f.addRow("", self.auto_paste)
        self.terminals = QLineEdit(cfg.get("terminal_classes"))
        f.addRow("Terminals (Ctrl+Shift+V)", self.terminals)
        self.autostart = QCheckBox("Start when I log in")
        self.autostart.setChecked(cfg.get("autostart"))
        f.addRow("", self.autostart)
        tabs.addTab(general, "General")

        sync = QWidget()
        s = QFormLayout(sync)
        self.sync_enabled = QCheckBox("Sync clips with other computers")
        self.sync_enabled.setChecked(cfg.get("sync_enabled"))
        s.addRow("", self.sync_enabled)
        self.port = QSpinBox(minimum=1024, maximum=65535, value=cfg.get("sync_port"))
        s.addRow("Port", self.port)
        self.peers = QLineEdit(cfg.get("sync_peers"))
        self.peers.setPlaceholderText("192.168.1.20, office-pc.local:47811")
        s.addRow("Other computers", self.peers)
        self.passphrase = QLineEdit(cfg.get("sync_passphrase"))
        self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase.setPlaceholderText("Same passphrase on every computer")
        s.addRow("Passphrase", self.passphrase)
        self.sync_auto = QCheckBox("Send every copy automatically")
        self.sync_auto.setChecked(cfg.get("sync_auto"))
        s.addRow("", self.sync_auto)
        self.sync_clip = QCheckBox("Put received clips on my clipboard")
        self.sync_clip.setChecked(cfg.get("sync_to_clipboard"))
        s.addRow("", self.sync_clip)
        me = QLabel(f"This computer: {local_addresses()}")
        me.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        s.addRow("", me)
        tabs.addTab(sync, "Sync")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)
        if focus == "hotkey":
            self.hotkey.setFocus()
            self.hotkey.selectAll()

    def accept(self):
        if self.sync_enabled.isChecked() and not self.passphrase.text():
            QMessageBox.warning(self, "Clipdeck", "Set a passphrase to turn on sync.")
            return
        values = {
            "hotkey": self.hotkey.text().strip() or DEFAULTS["hotkey"],
            "max_items": self.max_items.value(),
            "max_image_mb": self.max_image.value(),
            "auto_paste": self.auto_paste.isChecked(),
            "terminal_classes": self.terminals.text(),
            "autostart": self.autostart.isChecked(),
            "sync_enabled": self.sync_enabled.isChecked(),
            "sync_port": self.port.value(),
            "sync_peers": self.peers.text(),
            "sync_passphrase": self.passphrase.text(),
            "sync_auto": self.sync_auto.isChecked(),
            "sync_to_clipboard": self.sync_clip.isChecked(),
        }
        for k, v in values.items():
            self.cfg.set(k, v)
        super().accept()
