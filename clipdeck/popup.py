"""The searchable history window that opens on the hotkey."""
from __future__ import annotations

import html
import os

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QToolButton, QVBoxLayout, QWidget)

from . import x11
from .storage import Storage

ROLE_ID = Qt.UserRole

STYLE = """
#frame { background: palette(window); border: 1px solid palette(mid); border-radius: 8px; }
QListWidget { border: 1px solid palette(midlight); border-radius: 4px; background: palette(base); }
QListWidget::item { padding: 5px 4px; }
#hint { color: palette(mid); }
"""


def preview(text: str, limit: int = 140) -> str:
    s = " ".join(text[:2000].split())
    return s if len(s) <= limit else s[:limit - 1] + "…"


class Popup(QWidget):
    paste_requested = Signal(int, bool)  # clip id, as plain text
    send_requested = Signal(int)

    def __init__(self, store: Storage):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.store = store
        self._modal = False
        self._thumbs: dict[int, QIcon] = {}
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self.resize(500, 560)

        frame = QFrame(objectName="frame")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 8, 8, 6)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.currentIndexChanged.connect(self.refresh)
        self.groups_btn = QToolButton(text="Groups")
        self.groups_btn.setPopupMode(QToolButton.InstantPopup)
        gm = QMenu(self.groups_btn)
        gm.addAction("New group…", self._new_group)
        self.rename_act = gm.addAction("Rename group…", self._rename_group)
        self.delete_act = gm.addAction("Delete group…", self._delete_group)
        gm.aboutToShow.connect(self._update_group_menu)
        self.groups_btn.setMenu(gm)
        top.addWidget(self.scope, 1)
        top.addWidget(self.groups_btn)
        lay.addLayout(top)

        self.search = QLineEdit(placeholderText="Search clips")
        self.search.setClearButtonEnabled(True)
        self._debounce = QTimer(self, singleShot=True, interval=120)
        self._debounce.timeout.connect(self.refresh)
        self.search.textChanged.connect(self._debounce.start)
        lay.addWidget(self.search)

        self.list = QListWidget()
        self.list.setIconSize(QSize(48, 48))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemActivated.connect(lambda it: self.paste_requested.emit(it.data(ROLE_ID), False))
        lay.addWidget(self.list, 1)

        hint = QLabel("Enter paste   Shift+Enter plain text   Ctrl+1–9 quick paste   "
                      "Ctrl+P pin   Shift+Del delete   Esc close", objectName="hint")
        hint.setWordWrap(True)
        f = hint.font()
        f.setPointSizeF(f.pointSizeF() * 0.85)
        hint.setFont(f)
        lay.addWidget(hint)

        self.search.installEventFilter(self)
        self.list.installEventFilter(self)
        self.rebuild_scopes()

    # ---- showing ---------------------------------------------------------
    def present(self):
        self._modal = False
        self.search.clear()
        self.rebuild_scopes()
        self.refresh()
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = min(max(pos.x(), geo.left()), geo.right() - self.width())
        y = min(max(pos.y(), geo.top()), geo.bottom() - self.height())
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()
        QTimer.singleShot(80, self._ensure_focus)

    def _ensure_focus(self):
        if self.isVisible() and not self.isActiveWindow():
            x11.force_focus(int(self.winId()))

    def changeEvent(self, e):
        if e.type() == QEvent.ActivationChange and not self.isActiveWindow():
            QTimer.singleShot(200, self._hide_if_unfocused)
        super().changeEvent(e)

    def _hide_if_unfocused(self):
        if (self.isVisible() and not self.isActiveWindow() and not self._modal
                and QApplication.activePopupWidget() is None
                and QApplication.activeModalWidget() is None):
            self.hide()

    # ---- list ------------------------------------------------------------
    def rebuild_scopes(self):
        current = self.scope.currentData()
        self.scope.blockSignals(True)
        self.scope.clear()
        self.scope.addItem("All clips", "all")
        self.scope.addItem("📌 Pinned", "pinned")
        for gid, name in self.store.groups():
            self.scope.addItem(f"🗂 {name}", gid)
        self.scope.setCurrentIndex(max(self.scope.findData(current), 0))
        self.scope.blockSignals(False)

    def refresh(self):
        scope = self.scope.currentData() or "all"
        clips = self.store.search(self.search.text(), scope)
        self.list.clear()
        for c in clips:
            label = preview(c.text)
            if c.kind == "files":
                n = len(c.text.splitlines())
                label = (f"{n} files: " if n > 1 else "File: ") + label
            if c.pinned:
                label = "📌 " + label
            if c.origin:
                label += f"   ⇄ {c.origin}"
            item = QListWidgetItem(label)
            item.setData(ROLE_ID, c.id)
            icon = self._icon(c)
            if icon:
                item.setIcon(icon)
            tip = c.text[:1500] + ("…" if len(c.text) > 1500 else "")
            item.setToolTip(f"<p style='white-space:pre-wrap'>{html.escape(tip)}</p>")
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _icon(self, c) -> QIcon | None:
        if c.kind == "image" and c.thumb:
            if c.id not in self._thumbs:
                pm = QPixmap()
                pm.loadFromData(c.thumb, "PNG")
                self._thumbs[c.id] = QIcon(pm)
            return self._thumbs[c.id]
        if c.kind == "files":
            first = c.text.splitlines()[0] if c.text else ""
            return QIcon.fromTheme("folder" if os.path.isdir(first) else "text-x-generic")
        return None

    def _current_id(self) -> int | None:
        it = self.list.currentItem()
        return it.data(ROLE_ID) if it else None

    # ---- keyboard --------------------------------------------------------
    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.KeyPress:
            return False
        key, mods = ev.key(), ev.modifiers()
        ctrl, shift = bool(mods & Qt.ControlModifier), bool(mods & Qt.ShiftModifier)

        if key == Qt.Key_Escape:
            self.hide()
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter):
            cid = self._current_id()
            if cid is not None:
                self.paste_requested.emit(cid, shift)
            return True
        if ctrl and Qt.Key_1 <= key <= Qt.Key_9:
            row = int(key) - int(Qt.Key_1)
            if row < self.list.count():
                self.paste_requested.emit(self.list.item(row).data(ROLE_ID), shift)
            return True
        if ctrl and key == Qt.Key_P:
            cid = self._current_id()
            if cid is not None:
                clip = self.store.get(cid)
                self._set_pin(cid, not clip.pinned)
            return True
        if shift and key == Qt.Key_Delete:
            cid = self._current_id()
            if cid is not None:
                self._delete(cid)
            return True
        if obj is self.search and key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            QApplication.sendEvent(self.list, ev)
            return True
        if obj is self.list and ev.text() and ev.text().isprintable() and not ctrl:
            self.search.setFocus()
            self.search.insert(ev.text())
            return True
        return False

    # ---- actions ---------------------------------------------------------
    def _keep_row(self, fn):
        row = self.list.currentRow()
        fn()
        self.refresh()
        if self.list.count():
            self.list.setCurrentRow(min(max(row, 0), self.list.count() - 1))

    def _set_pin(self, cid: int, pinned: bool):
        self._keep_row(lambda: self.store.set_pinned(cid, pinned))

    def _delete(self, cid: int):
        self._thumbs.pop(cid, None)
        self._keep_row(lambda: self.store.delete(cid))

    def _move(self, cid: int, gid: int | None):
        self._keep_row(lambda: self.store.set_group(cid, gid))

    def _context_menu(self, pos):
        item = self.list.itemAt(pos)
        if not item:
            return
        cid = item.data(ROLE_ID)
        clip = self.store.get(cid)
        m = QMenu(self)
        m.addAction("Paste", lambda: self.paste_requested.emit(cid, False))
        if clip.kind != "image":
            m.addAction("Paste as plain text", lambda: self.paste_requested.emit(cid, True))
        m.addAction("Unpin" if clip.pinned else "Pin", lambda: self._set_pin(cid, not clip.pinned))
        gm = m.addMenu("Move to group")
        none = gm.addAction("No group", lambda: self._move(cid, None))
        none.setCheckable(True)
        none.setChecked(clip.group_id is None)
        for gid, name in self.store.groups():
            a = gm.addAction(name, lambda _=False, g=gid: self._move(cid, g))
            a.setCheckable(True)
            a.setChecked(clip.group_id == gid)
        gm.addSeparator()
        gm.addAction("New group…", lambda: self._move_to_new_group(cid))
        m.addAction("Send to other computers", lambda: self.send_requested.emit(cid))
        m.addSeparator()
        m.addAction("Delete", lambda: self._delete(cid))
        m.exec(self.list.viewport().mapToGlobal(pos))

    # ---- groups ----------------------------------------------------------
    def _ask(self, title: str, label: str, text: str = "") -> str | None:
        self._modal = True
        try:
            value, ok = QInputDialog.getText(self, title, label, text=text)
        finally:
            self._modal = False
            self.activateWindow()
            self.search.setFocus()
        value = value.strip()
        return value if ok and value else None

    def _update_group_menu(self):
        is_group = isinstance(self.scope.currentData(), int)
        self.rename_act.setEnabled(is_group)
        self.delete_act.setEnabled(is_group)

    def _new_group(self):
        name = self._ask("New group", "Group name:")
        if name:
            gid = self.store.add_group(name)
            self.rebuild_scopes()
            self.scope.setCurrentIndex(self.scope.findData(gid))

    def _move_to_new_group(self, cid: int):
        name = self._ask("New group", "Group name:")
        if name:
            gid = self.store.add_group(name)
            self.store.set_group(cid, gid)
            self.rebuild_scopes()
            self.refresh()

    def _rename_group(self):
        gid = self.scope.currentData()
        if not isinstance(gid, int):
            return
        old = dict(self.store.groups()).get(gid, "")
        name = self._ask("Rename group", "Group name:", old)
        if name:
            self.store.rename_group(gid, name)
            self.rebuild_scopes()

    def _delete_group(self):
        gid = self.scope.currentData()
        if not isinstance(gid, int):
            return
        name = dict(self.store.groups()).get(gid, "")
        self._modal = True
        try:
            answer = QMessageBox.question(
                self, "Delete group",
                f"Delete the group “{name}”? Its clips move back to the main history.")
        finally:
            self._modal = False
            self.activateWindow()
        if answer == QMessageBox.Yes:
            self.store.delete_group(gid)
            self.rebuild_scopes()
            self.refresh()
