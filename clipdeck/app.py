"""Application controller: tray icon, IPC, and wiring between the parts."""
from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

from .qt import QObject, Qt, QTimer, QUrl
from .qt import QAction, QColor, QDesktopServices, QIcon, QImage, QPainter, QPixmap
from .qt import QLocalServer
from .qt import QApplication, QFileDialog, QInputDialog, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_ID, __author__, __version__, desktop, x11
from .clipboard import ClipboardMonitor, combine, image_to_png, make_thumb
from .dialogs import DeleteDataDialog, help_html
from .popup import Popup
from .settings import Config, SettingsDialog
from .storage import DATA_DIR, Payload, Storage
from .sync import SyncService


def app_icon() -> QIcon:
    for name in (APP_ID, "edit-paste"):
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
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
        self.popup.copy_requested.connect(self.on_copy)
        self.popup.send_requested.connect(self.on_send)

        self._build_tray()

        self.ipc = ipc
        self.ipc.newConnection.connect(self._on_ipc)

        self.apply_settings()
        if x11.is_wayland():
            self.notify("You're in a Wayland session. Clipdeck is built for X11 (Cinnamon's default), "
                        "so capturing and auto-paste may not work.")
        elif not x11.have_xdotool() and self.cfg.get("auto_paste"):
            self.notify("Install xdotool to paste automatically: sudo apt install xdotool")

    # ---- tray ------------------------------------------------------------
    def _build_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Clipdeck")
        menu = QMenu()
        show = menu.addAction("Show history", lambda: self.show_popup(from_tray=True))
        menu.setDefaultAction(show)  # shown in bold, as in Ditto
        menu.addAction("Settings…", lambda: self.open_settings())
        menu.addSeparator()
        startup = QAction("Show startup message", menu, checkable=True)
        startup.setChecked(self.cfg.get("startup_message"))
        startup.toggled.connect(lambda on: self.cfg.set("startup_message", on))
        menu.addAction(startup)
        menu.addAction("Keyboard shortcut…", lambda: self.open_settings(focus="hotkey"))
        menu.addAction("Delete clip data…", self._delete_clip_data)
        menu.addAction("Delete unused clips…", self._delete_unused)
        menu.addSeparator()
        menu.addAction("Back up history…", self._backup)
        menu.addAction("Restore history…", self._restore)
        menu.addSeparator()
        menu.addAction("Import clips…", self._import)
        menu.addAction("New clip…", self._new_clip)
        menu.addSeparator()
        menu.addAction("Help", self._help)
        menu.addSeparator()
        self.pause_action = QAction("Pause capturing", menu, checkable=True)
        self.pause_action.toggled.connect(self._set_paused)
        menu.addAction(self.pause_action)
        menu.addAction("Save current clipboard", self._save_current)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self._menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_popup(from_tray=True)
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def notify(self, message: str):
        """Show a tray notification, at most once per 5 minutes for the same text."""
        now = time.monotonic()
        if now - self._last_notice.get(message, -1e9) < 300:
            return
        self._last_notice[message] = now
        print(f"clipdeck: {message}", file=sys.stderr)
        self.tray.showMessage("Clipdeck", message, QSystemTrayIcon.MessageIcon.Information, 6000)

    def _set_paused(self, paused: bool):
        self.monitor.paused = paused
        self.tray.setToolTip("Clipdeck (paused)" if paused else "Clipdeck")

    def _changed(self, message: str | None = None):
        if self.popup.isVisible():
            self.popup.refresh()
        if message:
            self.tray.showMessage("Clipdeck", message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def _confirm(self, title: str, text: str) -> bool:
        return QMessageBox.question(None, title, text) == QMessageBox.StandardButton.Yes

    def _delete_clip_data(self):
        dialog = DeleteDataDialog(self.store)
        if dialog.exec():
            n = self.store.delete_matching(**dialog.choice())
            self._changed(f"Deleted {n} clip{'s' if n != 1 else ''}.")

    def _delete_unused(self):
        n = self.store.count_matching(unused_only=True)
        if n == 0:
            QMessageBox.information(None, "Delete unused clips",
                                    "Every clip has been pasted or copied at least once.")
            return
        if self._confirm("Delete unused clips",
                         f"Delete {n} clip{'s' if n != 1 else ''} you've never pasted or copied? "
                         "Pinned and grouped clips are kept."):
            self._changed(f"Deleted {self.store.delete_matching(unused_only=True)} clips.")

    def _backup(self):
        name = f"clipdeck-backup-{time.strftime('%Y-%m-%d')}.db"
        path, _ = QFileDialog.getSaveFileName(None, "Back up history", str(Path.home() / name),
                                              "Clipdeck backups (*.db)")
        if path:
            try:
                self.store.backup(path)
                self._changed("History backed up.")
            except Exception as e:
                QMessageBox.warning(None, "Back up history", f"Couldn't save the backup: {e}")

    def _restore(self):
        path, _ = QFileDialog.getOpenFileName(None, "Restore history", str(Path.home()),
                                              "Clipdeck backups (*.db);;All files (*)")
        if not path:
            return
        count = self.store.is_backup(path)
        if count is None:
            QMessageBox.warning(None, "Restore history", "That file isn't a Clipdeck backup.")
            return
        if self._confirm("Restore history",
                         f"Replace your whole clipboard history with this backup ({count} clips)? "
                         "Your current history will be lost."):
            try:
                self.store.restore(path)
                self.popup.rebuild_scopes()
                self._changed(f"Restored {count} clips.")
            except Exception as e:
                QMessageBox.warning(None, "Restore history", f"Couldn't restore the backup: {e}")

    def _import(self):
        paths, _ = QFileDialog.getOpenFileNames(
            None, "Import clips", str(Path.home()),
            "Text and images (*.txt *.md *.csv *.json *.html *.png *.jpg *.jpeg *.gif *.webp *.bmp);;"
            "All files (*)")
        added, skipped = 0, []
        for path in paths:
            payload = self._payload_from_file(Path(path))
            if payload:
                self._store(payload)
                added += 1
            else:
                skipped.append(Path(path).name)
        if paths:
            msg = f"Imported {added} clip{'s' if added != 1 else ''}."
            if skipped:
                msg += f" Skipped: {', '.join(skipped[:3])}{'…' if len(skipped) > 3 else ''}"
            self._changed(msg)

    def _payload_from_file(self, path: Path) -> Payload | None:
        max_bytes = self.cfg.get("max_image_mb") * 1024 * 1024
        try:
            if path.stat().st_size > max_bytes:
                return None
            img = QImage(str(path))
            if not img.isNull():
                return Payload("image", f"Image {img.width()}×{img.height()}", None, image_to_png(img))
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None  # unreadable, or not text
        return Payload("text", text) if text.strip() else None

    def _new_clip(self):
        text, ok = QInputDialog.getMultiLineText(None, "New clip", "Text:")
        if ok and text.strip():
            self._store(Payload("text", text))
            self._changed("Clip added.")

    def _save_current(self):
        payload = self.monitor.read_now()
        if payload:
            self._store(payload)
            self._changed("Saved the current clipboard.")
        else:
            self._changed("The clipboard is empty, or holds something Clipdeck can't save.")

    def _help(self):
        box = QMessageBox()
        box.setWindowTitle("Clipdeck help")
        box.setIconPixmap(app_icon().pixmap(64, 64))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(help_html(desktop.gtk_to_qt(self.cfg.get("hotkey"))))
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        box.exec()

    def open_settings(self, focus: str | None = None):
        self.popup.hide()
        if SettingsDialog(self.cfg, focus=focus).exec():
            self.apply_settings()

    def apply_settings(self):
        hotkey, old = self.cfg.get("hotkey"), self.cfg.get("registered_hotkey")
        if hotkey != old:
            ok, msg = desktop.register_shortcut(hotkey, desktop.launch_command(), old)
            # Remember failures too, so the same message doesn't repeat every start.
            self.cfg.set("registered_hotkey", hotkey)
            self.notify(msg)
        try:
            msg = desktop.set_autostart(self.cfg.get("autostart"))
            if msg:
                self.notify(msg)
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

    def _payload(self, ids: list[int]) -> Payload | None:
        clips = [c for c in (self.store.get(i) for i in ids) if c]
        return combine([c.payload for c in clips]) if clips else None

    def on_copy(self, ids: list[int]):
        payload = self._payload(ids)
        if payload:
            self.monitor.set_clipboard(payload)
        self.store.mark_used(ids)

    def on_send(self, ids: list[int]):
        if not (self.sync.running and self.sync.peers):
            self.notify("Turn on sync and add other computers in Settings → Sync first.")
            return
        for clip in (self.store.get(i) for i in ids):
            if clip:
                self.sync.send(clip.payload)

    def show_popup(self, from_tray: bool = False):
        if self.popup.isVisible():
            self.popup.hide()  # the hotkey toggles the window
            return
        self.target_window = None if from_tray or x11.is_wayland() else x11.active_window()
        self.popup.present()

    def on_paste(self, ids: list[int], plain: bool):
        payload = self._payload(ids)
        if not payload:
            self.popup.flash("Images can't be pasted together with other clips")
            return
        self.monitor.set_clipboard(payload, plain)
        self.store.mark_used(ids)
        if len(ids) == 1:
            self.store.touch(ids[0])  # a single pasted clip moves to the top, as in Ditto
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
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    QLocalServer.removeServer(ipc_path)  # a stale socket from a crash
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(ipc_path):
        print(f"clipdeck: can't listen on {ipc_path}: {server.errorString()}", file=sys.stderr)
        return 1

    controller = Clipdeck(server)
    if show_now:
        QTimer.singleShot(0, controller.show_popup)
    if controller.cfg.get("startup_message"):
        hotkey = desktop.gtk_to_qt(controller.cfg.get("hotkey"))
        controller.notify(f"Clipdeck is running. Press {hotkey} to open your clipboard history.")
    return app.exec()
