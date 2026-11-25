"""Application controller: tray icon, IPC, and wiring between the parts."""
from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

from .qt import QObject, Qt, QTimer
from .qt import QAction, QColor, QIcon, QImage, QPainter, QPalette, QPixmap
from .qt import QLocalServer
from .qt import QApplication, QFileDialog, QInputDialog, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_ID, __author__, __version__, desktop, x11
from .clipboard import (ClipboardMonitor, app_allowed, combine, filter_types, image_to_png,
                        make_thumb)
from .dialogs import DeleteDataDialog, help_html, project_url
from .popup import Popup
from .settings import SHORTCUT_KEYS, Config, SettingsDialog
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


def apply_theme(mode: str):
    """"system" keeps the desktop's look; "light" and "dark" use Qt's Fusion style."""
    app = QApplication.instance()
    if not hasattr(app, "_clipdeck_default_look"):
        app._clipdeck_default_look = (app.style().name(), QPalette(app.palette()))
    style, palette = app._clipdeck_default_look
    if mode == "system":
        app.setStyle(style)
        app.setPalette(palette)
        return
    app.setStyle("Fusion")
    if mode == "light":
        app.setPalette(app.style().standardPalette())
        return
    p = QPalette()
    R = QPalette.ColorRole
    for role, color in ((R.Window, "#2b2d30"), (R.WindowText, "#e6e6e6"), (R.Base, "#1e1f22"),
                        (R.AlternateBase, "#2b2d30"), (R.Text, "#e6e6e6"), (R.Button, "#393b40"),
                        (R.ButtonText, "#e6e6e6"), (R.Highlight, "#3d7bd9"),
                        (R.HighlightedText, "#ffffff"), (R.ToolTipBase, "#393b40"),
                        (R.ToolTipText, "#e6e6e6"), (R.PlaceholderText, "#8c8f94"),
                        (R.Mid, "#5a5d63"), (R.Midlight, "#45484d"), (R.Dark, "#18191b"),
                        (R.Light, "#4e5157"), (R.Link, "#6ea8ff"), (R.BrightText, "#ff6b6b")):
        p.setColor(role, QColor(color))
    p.setColor(QPalette.ColorGroup.Disabled, R.Text, QColor("#7a7d82"))
    p.setColor(QPalette.ColorGroup.Disabled, R.ButtonText, QColor("#7a7d82"))
    p.setColor(QPalette.ColorGroup.Disabled, R.WindowText, QColor("#7a7d82"))
    app.setPalette(p)


class Clipdeck(QObject):
    def __init__(self, ipc: QLocalServer):
        super().__init__()
        self.cfg = Config()
        self.started = time.time()
        self.sent = self.received = 0
        self.db_path = self._wanted_db_path()
        try:
            self.store = Storage(Path(self.db_path))
        except Exception as e:  # e.g. a chosen folder that's gone: fall back to the default
            print(f"clipdeck: can't open {self.db_path}: {e}", file=sys.stderr)
            self.db_path = str(DATA_DIR / "clips.db")
            self.store = Storage(Path(self.db_path))
        self.target_window: str | None = None
        self._last_notice: dict[str, float] = {}
        apply_theme(self.cfg.get("theme"))

        self.monitor = ClipboardMonitor(lambda: self.cfg.get("max_image_mb") * 1024 * 1024, self)
        self.monitor.captured.connect(self.on_captured)

        self.sync = SyncService(self)
        self.sync.received.connect(self.on_synced)
        self.sync.status.connect(self.notify)

        self.popup = Popup(self.store, self.cfg)
        self.popup.paste_requested.connect(self.on_paste)
        self.popup.copy_requested.connect(self.on_copy)
        self.popup.send_requested.connect(self.on_send)

        self._build_tray()

        self.ipc = ipc
        self.ipc.newConnection.connect(self._on_ipc)

        self._expiry = QTimer(self, interval=3600 * 1000)
        self._expiry.timeout.connect(self._expire)
        self._expiry.start()
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
        self.startup_action = QAction("Show startup message", menu, checkable=True)
        self.startup_action.setChecked(self.cfg.get("startup_message"))
        self.startup_action.toggled.connect(lambda on: self.cfg.set("startup_message", on))
        menu.addAction(self.startup_action)
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
        info = {"store": self.store, "db_path": self.db_path, "default_db": DATA_DIR / "clips.db",
                "started": self.started, "sent": self.sent, "received": self.received,
                "project_url": project_url()}
        dialog = SettingsDialog(self.cfg, focus=focus, info=info)
        saved = dialog.exec()
        dialog.deleteLater()
        if saved:
            self.apply_settings()
            self.startup_action.setChecked(self.cfg.get("startup_message"))

    def _wanted_db_path(self) -> str:
        return self.cfg.get("db_path") or str(DATA_DIR / "clips.db")

    def _max_items(self) -> int:
        return self.cfg.get("max_items") if self.cfg.get("limit_items") else 10**9

    def _expire(self):
        if self.cfg.get("expire_enabled"):
            if self.store.delete_matching(older_than_days=self.cfg.get("expire_days")) and \
                    self.popup.isVisible():
                self.popup.refresh()

    def _switch_history_file(self):
        wanted = self._wanted_db_path()
        if wanted == self.db_path:
            return
        try:
            target = Path(wanted)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                self.store.backup(str(target))  # take the current history along
            new = Storage(target)
        except Exception as e:
            self.cfg.set("db_path", "" if self.db_path == str(DATA_DIR / "clips.db") else self.db_path)
            QMessageBox.warning(None, "Clipdeck", f"Couldn't use {wanted}: {e}")
            return
        self.store.db.close()
        self.store = self.popup.store = new
        self.db_path = wanted
        self.popup.rebuild_scopes()
        self.notify(f"Now using the history file {wanted}")

    def apply_settings(self):
        failed, done = [], []
        command = desktop.launch_command()
        for key in SHORTCUT_KEYS:
            accel, old = self.cfg.get(key), self.cfg.get(f"registered_{key}")
            if accel == old:
                continue
            short_key = {"hotkey": "show", "hotkey_plain": "plain", "hotkey_save": "save"}.get(
                key, key.replace("hotkey_", ""))
            ok, msg = desktop.register_shortcut(accel, command, old, key=short_key)
            # Remember failures too, so the same message doesn't repeat every start.
            self.cfg.set(f"registered_{key}", accel)
            (done if ok else failed).append(msg)
        if failed:
            self.notify(failed[0] + (f" ({len(failed) - 1} more like this.)" if len(failed) > 1 else ""))
        elif any(done):
            self.notify(next(m for m in done if m) if len([m for m in done if m]) == 1
                        else "Keyboard shortcuts updated.")
        try:
            msg = desktop.set_autostart(self.cfg.get("autostart"))
            if msg:
                self.notify(msg)
        except OSError as e:
            self.notify(f"Couldn't update autostart: {e}")
        self._switch_history_file()
        apply_theme(self.cfg.get("theme"))
        self.popup.apply_font(self.cfg.get("font"))
        self.store.trim(self._max_items())
        self._expire()
        if self.cfg.get("sync_enabled"):
            self.sync.start(self.cfg.get("sync_port"), self.cfg.get("sync_peers"),
                            self.cfg.get("sync_passphrase"))
        else:
            self.sync.stop()

    # ---- clips -----------------------------------------------------------
    def _store(self, p: Payload, origin: str | None = None):
        thumb = make_thumb(p.data) if p.kind == "image" else None
        self.store.add(p, thumb, origin, self._max_items())
        if self.popup.isVisible():
            self.popup.refresh()

    def _copied_from_allowed_app(self) -> bool:
        include, exclude = self.cfg.get("apps_include"), self.cfg.get("apps_exclude")
        if include.strip() in ("", "*") and not exclude.strip():
            return True  # no filter: skip the window lookup
        wid = x11.active_window()
        return app_allowed(x11.window_classes(wid) if wid else set(), include, exclude)

    def on_captured(self, p: Payload):
        p = filter_types(p, self.cfg)
        if p is None or not self._copied_from_allowed_app():
            return
        self.cfg.bump("copies")
        self._store(p)
        if self.sync.running and self.cfg.get("sync_auto"):
            self.sync.send(p)
            self.sent += 1

    def on_synced(self, p: Payload, origin: str):
        self.received += 1
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
                self.sent += 1

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
        self.cfg.bump("pastes")
        if len(ids) == 1:
            self.store.touch(ids[0])  # a single pasted clip moves to the top, as in Ditto
        self.popup.hide()
        self._paste_now(self.target_window)

    # ---- IPC (clipdeck --show / --quit) -----------------------------------
    def _on_ipc(self):
        while self.ipc.hasPendingConnections():
            s = self.ipc.nextPendingConnection()
            s.readyRead.connect(lambda s=s: self._ipc_read(s))
            s.disconnected.connect(s.deleteLater)
            if s.bytesAvailable():
                self._ipc_read(s)

    def _ipc_read(self, s):
        for line in bytes(s.readAll()).decode(errors="ignore").splitlines():
            self.run_command(line.strip())

    def run_command(self, cmd: str):
        """Commands from the command line: show, quit, save, paste-plain, paste N."""
        parts = cmd.split()
        if not parts:
            return
        if parts[0] == "show":
            self.show_popup()
        elif parts[0] == "quit":
            self.quit()
        elif parts[0] == "save":
            self._save_current()
        elif parts[0] == "paste-plain":
            self.paste_clipboard_plain()
        elif parts[0] == "paste" and len(parts) == 2 and parts[1].isdigit():
            self.paste_position(int(parts[1]))

    def _paste_now(self, target: str | None):
        if target and self.cfg.get("auto_paste") and x11.have_xdotool():
            terminals = self.cfg.terminal_classes()
            QTimer.singleShot(120, lambda: x11.paste_into(target, terminals))

    def paste_position(self, n: int):
        """Paste the n-th clip of the history (pinned first), as Ditto's "last ten" keys do."""
        clips = self.store.search("", "all", limit=n)
        if not 1 <= n <= len(clips):
            return
        clip = self.store.get(clips[n - 1].id)
        target = None if x11.is_wayland() else x11.active_window()
        self.monitor.set_clipboard(clip.payload)
        self.store.mark_used([clip.id])
        self.cfg.bump("pastes")
        if self.cfg.get("positions_move_to_top"):
            self.store.touch(clip.id)
        if self.cfg.get("positions_send_paste"):
            self._paste_now(target)

    def paste_clipboard_plain(self):
        """Paste what's on the clipboard now, without formatting."""
        payload = self.monitor.read_now()
        if not payload or payload.kind == "image":
            return
        target = None if x11.is_wayland() else x11.active_window()
        self.monitor.set_clipboard(payload, plain=True)
        self.cfg.bump("pastes")
        self._paste_now(target)

    def quit(self):
        self.sync.stop()
        self.ipc.close()
        self.tray.hide()
        QApplication.quit()


def run(ipc_path: str, command: str = "", background: bool = False) -> int:
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
    if command:
        QTimer.singleShot(0, lambda: controller.run_command(command))
    if controller.cfg.get("startup_message"):
        hotkey = desktop.gtk_to_qt(controller.cfg.get("hotkey"))
        controller.notify(f"Clipdeck is running. Press {hotkey} to open your clipboard history.")
    return app.exec()
