"""Application controller: tray icon, IPC, and wiring between the parts."""
from __future__ import annotations

import signal
import sys
import time

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import __author__, __version__, desktop, x11
from .clipboard import ClipboardMonitor, make_thumb
from .popup import Popup
from .settings import Config, SettingsDialog
from .storage import DATA_DIR, Payload, Storage
from .sync import SyncService


def app_icon() -> QIcon:
    icon = QIcon.fromTheme("edit-paste")
    if not icon.isNull():
        return icon
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#4a7fc1"))
    p.drawRoundedRect(8, 6, 48, 54, 8, 8)
    p.setBrush(QColor("#ffffff"))
    for y in (20, 30, 40):
        p.drawRoundedRect(16, y, 32, 5, 2, 2)
    p.end()
    return QIcon(pm)


class Clipdeck(QObject):
    def __init__(self, ipc: QLocalServer):
        super().__init__()
        self.cfg = Config()
        self.store = Storage(DATA_DIR / "clips.db")
        self.target_window: str | None = None
        self._last_notice: dict[str, float] = {}

        self.monitor = ClipboardMonitor(lambda: self.cfg.get("max_image_mb") * 1024 * 1024, self)
        self.monitor.captured.connect(self.on_captured)

        self.sync = SyncService(self)
        self.sync.received.connect(self.on_synced)
        self.sync.status.connect(self.notify)

        self.popup = Popup(self.store)
        self.popup.paste_requested.connect(self.on_paste)
        self.popup.send_requested.connect(self.on_send)

        self._build_tray()

        self.ipc = ipc
        self.ipc.newConnection.connect(self._on_ipc)

        self.apply_settings()
        if x11.is_wayland():
            self.notify("You're in a Wayland session. Clipdeck is built for X11 (Cinnamon's default), "
                        "so capturing and auto-paste may not work.")
        elif not x11.have_xdotool():
            self.notify("Install xdotool to paste automatically: sudo apt install xdotool")

    # ---- tray ------------------------------------------------------------
    def _build_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Clipdeck")
        menu = QMenu()
        about = menu.addAction(f"Clipdeck {__version__} by {__author__}")
        about.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Show history", lambda: self.show_popup(from_tray=True))
        self.pause_action = QAction("Pause capturing", menu, checkable=True)
        self.pause_action.toggled.connect(self._set_paused)
        menu.addAction(self.pause_action)
        menu.addSeparator()
        menu.addAction("Clear history…", self._clear_history)
        menu.addAction("Settings…", self.open_settings)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self._menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_popup(from_tray=True)
            if reason == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def notify(self, message: str):
        """Show a tray notification, at most once per 5 minutes for the same text."""
        now = time.monotonic()
        if now - self._last_notice.get(message, -1e9) < 300:
            return
        self._last_notice[message] = now
        print(f"clipdeck: {message}", file=sys.stderr)
        self.tray.showMessage("Clipdeck", message, QSystemTrayIcon.Information, 6000)

    def _set_paused(self, paused: bool):
        self.monitor.paused = paused
        self.tray.setToolTip("Clipdeck (paused)" if paused else "Clipdeck")

    def _clear_history(self):
        answer = QMessageBox.question(None, "Clear history",
                                      "Delete all clips except pinned and grouped ones?")
        if answer == QMessageBox.Yes:
            self.store.clear_loose()
            if self.popup.isVisible():
                self.popup.refresh()

    def open_settings(self):
        self.popup.hide()
        if SettingsDialog(self.cfg).exec():
            self.apply_settings()

    def apply_settings(self):
        hotkey = self.cfg.get("hotkey")
        if hotkey != self.cfg.get("registered_hotkey"):
            ok, msg = desktop.register_shortcut(hotkey, desktop.launch_command() + " --show")
            if ok:
                self.cfg.set("registered_hotkey", hotkey)
            self.notify(msg)
        try:
            desktop.set_autostart(self.cfg.get("autostart"))
        except OSError as e:
            self.notify(f"Couldn't update autostart: {e}")
        self.store.trim(self.cfg.get("max_items"))
        if self.cfg.get("sync_enabled"):
            self.sync.start(self.cfg.get("sync_port"), self.cfg.get("sync_peers"),
                            self.cfg.get("sync_passphrase"))
        else:
            self.sync.stop()

    # ---- clips -----------------------------------------------------------
    def _store(self, p: Payload, origin: str | None = None):
        thumb = make_thumb(p.data) if p.kind == "image" else None
        self.store.add(p, thumb, origin, self.cfg.get("max_items"))
        if self.popup.isVisible():
            self.popup.refresh()

    def on_captured(self, p: Payload):
        self._store(p)
        if self.sync.running and self.cfg.get("sync_auto"):
            self.sync.send(p)

    def on_synced(self, p: Payload, origin: str):
        self._store(p, origin)
        if self.cfg.get("sync_to_clipboard"):
            self.monitor.set_clipboard(p)

    def on_send(self, cid: int):
        clip = self.store.get(cid)
        if not clip:
            return
        if not (self.sync.running and self.sync.peers):
            self.notify("Turn on sync and add other computers in Settings → Sync first.")
            return
        self.sync.send(clip.payload)

    def show_popup(self, from_tray: bool = False):
        if self.popup.isVisible():
            self.popup.hide()  # the hotkey toggles the window
            return
        self.target_window = None if from_tray or x11.is_wayland() else x11.active_window()
        self.popup.present()

    def on_paste(self, cid: int, plain: bool):
        clip = self.store.get(cid)
        if not clip:
            return
        self.monitor.set_clipboard(clip.payload, plain)
        self.store.touch(cid)
        self.popup.hide()
        target = self.target_window
        if target and self.cfg.get("auto_paste") and x11.have_xdotool():
            terminals = self.cfg.terminal_classes()
            QTimer.singleShot(120, lambda: x11.paste_into(target, terminals))

    # ---- IPC (clipdeck --show / --quit) -----------------------------------
    def _on_ipc(self):
        while self.ipc.hasPendingConnections():
            s = self.ipc.nextPendingConnection()
            s.readyRead.connect(lambda s=s: self._ipc_read(s))
            s.disconnected.connect(s.deleteLater)
            if s.bytesAvailable():
                self._ipc_read(s)

    def _ipc_read(self, s):
        for cmd in bytes(s.readAll()).decode(errors="ignore").split():
            if cmd == "show":
                self.show_popup()
            elif cmd == "quit":
                self.quit()

    def quit(self):
        self.sync.stop()
        self.ipc.close()
        self.tray.hide()
        QApplication.quit()


def run(ipc_path: str, show_now: bool = False, background: bool = False) -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Clipdeck")
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    QLocalServer.removeServer(ipc_path)  # a stale socket from a crash
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    if not server.listen(ipc_path):
        print(f"clipdeck: can't listen on {ipc_path}: {server.errorString()}", file=sys.stderr)
        return 1

    controller = Clipdeck(server)
    if show_now:
        QTimer.singleShot(0, controller.show_popup)
    elif not background:
        controller.notify("Clipdeck is running. Press your shortcut to open clipboard history.")
    return app.exec()
