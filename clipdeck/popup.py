"""The searchable history window that opens on the hotkey."""
from __future__ import annotations

import html
import os

from .qt import QEvent, QItemSelectionModel, QPoint, QSize, Qt, QTimer, Signal
from .qt import QCursor, QFont, QFontMetrics, QGuiApplication, QIcon, QPixmap
from .qt import (QAbstractItemView, QApplication, QComboBox, QFrame, QHBoxLayout,
                 QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                 QMessageBox, QPlainTextEdit, QSizeGrip, QStackedWidget, QToolButton, QVBoxLayout,
                 QWidget)

from . import x11
from .storage import Storage

ROLE_ID = Qt.ItemDataRole.UserRole
QUICK_KEYS = 9  # Ctrl+1 … Ctrl+9

STYLE = """
#frame { background: palette(window); border: 1px solid palette(mid); border-radius: 8px; }
QListWidget { border: 1px solid palette(midlight); border-radius: 4px; background: palette(base); }
QListWidget::item { padding: 5px 4px; }
#hint { color: palette(mid); }
"""

HINT = ("Enter paste   Shift+Enter plain text   Del delete   Ctrl+A select all   "
        "Ctrl+C copy   Ctrl+E edit   Ctrl+P pin   F3 preview   Esc close")


def one_line(text: str) -> str:
    return " ".join(text[:2000].split())


def K(name: str) -> int:
    return getattr(Qt.Key, name).value


class Popup(QWidget):
    paste_requested = Signal(object, bool)  # list of clip ids (in list order), as plain text
    copy_requested = Signal(object)         # list of clip ids
    send_requested = Signal(object)         # list of clip ids

    def __init__(self, store: Storage, cfg=None):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.store = store
        self.cfg = cfg
        self._modal = False
        self._thumbs: dict[int, QIcon] = {}
        self._labels: dict[int, str] = {}
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
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
        self.groups_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
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
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setWordWrap(False)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemActivated.connect(lambda it: self.paste_requested.emit([it.data(ROLE_ID)], False))
        self.list.currentItemChanged.connect(lambda *_: self._update_preview())
        lay.addWidget(self.list, 1)

        # F3 preview: full text, or the image at a readable size.
        self.preview = QStackedWidget()
        self.preview_text = QPlainTextEdit(readOnly=True)
        self.preview_image = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.preview.addWidget(self.preview_text)
        self.preview.addWidget(self.preview_image)
        self.preview.setFixedHeight(170)
        self.preview.hide()
        lay.addWidget(self.preview)

        self.hint = QLabel(HINT, objectName="hint")
        self.hint.setWordWrap(True)
        f = self.hint.font()
        f.setPointSizeF(f.pointSizeF() * 0.85)
        self.hint.setFont(f)
        self._hint_reset = QTimer(self, singleShot=True, interval=1800)
        self._hint_reset.timeout.connect(lambda: self.hint.setText(HINT))
        bottom = QHBoxLayout()
        bottom.addWidget(self.hint, 1)
        bottom.addWidget(QSizeGrip(self), 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        lay.addLayout(bottom)

        self.search.installEventFilter(self)
        self.list.installEventFilter(self)
        self.rebuild_scopes()
        self.apply_font(cfg.get("font") if cfg else "")

    # ---- showing ---------------------------------------------------------
    def present(self):
        self._modal = False
        self.search.clear()
        self.rebuild_scopes()
        self._place()
        self.show()
        self.refresh()  # after show(), so long lines are shortened to the real width
        self.raise_()
        self.activateWindow()
        self.search.setFocus()
        QTimer.singleShot(80, self._ensure_focus)

    def _saved_geometry(self) -> list[int] | None:
        try:
            x, y, w, h = (int(v) for v in self.cfg.get("popup_geometry").split(","))
            return [x, y, w, h]
        except (AttributeError, ValueError):
            return None

    def _place(self):
        """Position the window as chosen in Settings, keeping it fully on screen."""
        saved = self._saved_geometry()
        if saved:
            self.resize(max(saved[2], 320), max(saved[3], 300))
        mode = self.cfg.get("popup_position") if self.cfg else "cursor"
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        if mode == "last" and saved:
            x, y = saved[0], saved[1]
            here = QGuiApplication.screenAt(QPoint(x + 10, y + 10))
            geo = (here or screen).availableGeometry()
        elif mode == "center":
            x = geo.center().x() - self.width() // 2
            y = geo.center().y() - self.height() // 2
        else:
            x, y = pos.x(), pos.y()
        self.resize(min(self.width(), geo.width()), min(self.height(), geo.height()))
        x = min(max(x, geo.left()), geo.right() - self.width())
        y = min(max(y, geo.top()), geo.bottom() - self.height())
        self.move(x, y)

    def hideEvent(self, e):
        if self.cfg is not None:
            g = self.geometry()
            self.cfg.set("popup_geometry", f"{g.x()},{g.y()},{g.width()},{g.height()}")
        super().hideEvent(e)

    def mousePressEvent(self, e):
        # Drag the window by its edges or the hint line (it has no title bar).
        if e.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()
        super().mousePressEvent(e)

    def apply_font(self, spec: str):
        font = QFont()
        if spec:
            font.fromString(spec)
        for widget in (self.list, self.search, self.preview_text):
            widget.setFont(font)
        self._elide_all()

    def _ensure_focus(self):
        if self.isVisible() and not self.isActiveWindow():
            x11.force_focus(int(self.winId()))

    def changeEvent(self, e):
        if e.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            QTimer.singleShot(200, self._hide_if_unfocused)
        super().changeEvent(e)

    def _hide_if_unfocused(self):
        if (self.isVisible() and not self.isActiveWindow() and not self._modal
                and QApplication.activePopupWidget() is None
                and QApplication.activeModalWidget() is None):
            self.hide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide_all()

    def flash(self, message: str):
        """Show a short confirmation where the key hints are."""
        self.hint.setText(message)
        self._hint_reset.start()

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

    def refresh(self, keep_ids: list[int] | None = None, row: int | None = None):
        scope = self.scope.currentData() or "all"
        clips = self.store.search(self.search.text(), scope)
        self.list.blockSignals(True)
        self.list.clear()
        self._labels.clear()
        for n, c in enumerate(clips, start=1):
            label = one_line(c.text)
            if c.kind == "files":
                count = len(c.text.splitlines())
                label = (f"{count} files: " if count > 1 else "File: ") + label
            if c.pinned:
                label = "📌 " + label
            if c.origin:
                label += f"   ⇄ {c.origin}"
            if n <= QUICK_KEYS:
                label = f"{n}   {label}"
            item = QListWidgetItem()
            item.setData(ROLE_ID, c.id)
            self._labels[c.id] = label
            icon = self._icon(c)
            if icon:
                item.setIcon(icon)
            tip = c.text[:1500] + ("…" if len(c.text) > 1500 else "")
            item.setToolTip(f"<p style='white-space:pre-wrap'>{html.escape(tip)}</p>")
            self.list.addItem(item)
        self._elide_all()
        self.list.blockSignals(False)

        if not self.list.count():
            self._update_preview()
            return
        if keep_ids:
            for i in range(self.list.count()):
                if self.list.item(i).data(ROLE_ID) in keep_ids:
                    self.list.item(i).setSelected(True)
            current = next((i for i in range(self.list.count())
                            if self.list.item(i).data(ROLE_ID) in keep_ids), None)
            if current is not None:
                self.list.setCurrentRow(current, QItemSelectionModel.SelectionFlag.NoUpdate)
                self._update_preview()
                return
        self.list.setCurrentRow(min(max(row or 0, 0), self.list.count() - 1))
        self._update_preview()

    def _elide_all(self):
        """Shorten long lines with "…" to fit the window, instead of scrolling sideways."""
        fm = QFontMetrics(self.list.font())
        width = self.list.viewport().width() - 24
        for i in range(self.list.count()):
            item = self.list.item(i)
            label = self._labels.get(item.data(ROLE_ID), "")
            room = width - (self.list.iconSize().width() + 8 if not item.icon().isNull() else 0)
            item.setText(fm.elidedText(label, Qt.TextElideMode.ElideRight, max(room, 50)))

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

    def selected_ids(self) -> list[int]:
        """Selected clips in list order; the current clip if nothing is selected."""
        rows = sorted(self.list.row(it) for it in self.list.selectedItems())
        if not rows and self.list.currentItem():
            rows = [self.list.currentRow()]
        return [self.list.item(r).data(ROLE_ID) for r in rows]

    # ---- preview (F3) ------------------------------------------------------
    def toggle_preview(self):
        self.preview.setVisible(not self.preview.isVisible())
        self._update_preview()

    def _update_preview(self):
        if not self.preview.isVisible():
            return
        item = self.list.currentItem()
        clip = self.store.get(item.data(ROLE_ID)) if item else None
        if clip and clip.kind == "image" and clip.data:
            pm = QPixmap()
            pm.loadFromData(clip.data, "PNG")
            size = self.preview.size()
            if pm.width() > size.width() or pm.height() > size.height():
                pm = pm.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self.preview_image.setPixmap(pm)
            self.preview.setCurrentWidget(self.preview_image)
        else:
            self.preview_text.setPlainText(clip.text if clip else "")
            self.preview.setCurrentWidget(self.preview_text)

    # ---- keyboard --------------------------------------------------------
    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.Type.KeyPress:
            return False
        key, mods = int(ev.key()), ev.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        in_search = obj is self.search
        typing = in_search and bool(self.search.text())

        if key == K("Key_Escape"):
            if self.search.text():
                self.search.clear()
            else:
                self.hide()
            return True
        if key in (K("Key_Return"), K("Key_Enter")):
            ids = self.selected_ids()
            if ids:
                self.paste_requested.emit(ids, shift)
            return True
        if ctrl and K("Key_1") <= key <= K("Key_9"):
            row = key - K("Key_1")
            if row < self.list.count():
                self.paste_requested.emit([self.list.item(row).data(ROLE_ID)], shift)
            return True
        if ctrl and key == K("Key_A"):
            if typing:
                return False  # select the search text
            self.list.selectAll()
            return True
        if ctrl and key == K("Key_C"):
            if in_search and self.search.hasSelectedText():
                return False  # copy the search text
            self._copy(self.selected_ids())
            return True
        if ctrl and key == K("Key_P"):
            self._toggle_pin(self.selected_ids())
            return True
        if (ctrl and key == K("Key_E")) or key == K("Key_F2"):
            self._edit(self.selected_ids())
            return True
        if key == K("Key_F3"):
            self.toggle_preview()
            return True
        if key == K("Key_Delete"):
            # While typing a search, Delete edits the text, except at the very end,
            # where it would do nothing anyway.
            if typing and not shift and self.search.cursorPosition() < len(self.search.text()):
                return False
            self._delete(self.selected_ids())
            return True
        nav = (K("Key_Up"), K("Key_Down"), K("Key_PageUp"), K("Key_PageDown"))
        if in_search and (key in nav or (not typing and key in (K("Key_Home"), K("Key_End")))):
            QApplication.sendEvent(self.list, ev)  # keeps Shift, so Shift+↓ extends the selection
            return True
        if obj is self.list and ev.text() and ev.text().isprintable() and not ctrl:
            self.search.setFocus()
            self.search.insert(ev.text())
            return True
        return False

    # ---- actions ---------------------------------------------------------
    def _ask_yes(self, title: str, question: str) -> bool:
        self._modal = True
        try:
            answer = QMessageBox.question(self, title, question)
        finally:
            self._modal = False
            self.activateWindow()
        return answer == QMessageBox.StandardButton.Yes

    def _copy(self, ids: list[int]):
        if ids:
            self.copy_requested.emit(ids)
            self.flash("Copied" if len(ids) == 1 else f"Copied {len(ids)} clips")

    def _toggle_pin(self, ids: list[int]):
        if not ids:
            return
        clips = [self.store.get(i) for i in ids]
        pin = not all(c.pinned for c in clips if c)  # pin all, unless all are already pinned
        for i in ids:
            self.store.set_pinned(i, pin)
        self.refresh(keep_ids=ids)

    def _delete(self, ids: list[int]):
        if not ids:
            return
        if len(ids) > 1 and not self._ask_yes(
                "Delete clips", f"Delete {len(ids)} clips? This can't be undone."):
            return
        row = min(self.list.row(it) for it in self.list.selectedItems()) \
            if self.list.selectedItems() else self.list.currentRow()
        for i in ids:
            self._thumbs.pop(i, None)
            self.store.delete(i)
        self.refresh(row=row)

    def _move(self, ids: list[int], gid: int | None):
        for i in ids:
            self.store.set_group(i, gid)
        self.refresh(keep_ids=ids)

    def _edit(self, ids: list[int]):
        if len(ids) != 1:
            self.flash("Select one clip to edit")
            return
        clip = self.store.get(ids[0])
        if not clip or clip.kind not in ("text", "html"):
            self.flash("Only text clips can be edited")
            return
        self._modal = True
        try:
            text, ok = QInputDialog.getMultiLineText(self, "Edit clip", "Text:", clip.text)
        finally:
            self._modal = False
            self.activateWindow()
            self.search.setFocus()
        if ok and text.strip() and text != clip.text:
            new_id = self.store.update_text(clip.id, text)
            self.refresh(keep_ids=[new_id])

    def _context_menu(self, pos):
        item = self.list.itemAt(pos)
        if not item:
            return
        if not item.isSelected():  # right-click outside the selection selects just that clip
            self.list.clearSelection()
            item.setSelected(True)
            self.list.setCurrentItem(item)
        ids = self.selected_ids()
        clips = [self.store.get(i) for i in ids]
        n = len(ids)
        m = QMenu(self)
        m.addAction("Paste" if n == 1 else f"Paste {n} clips",
                    lambda: self.paste_requested.emit(ids, False))
        if any(c.kind != "image" for c in clips):
            m.addAction("Paste as plain text", lambda: self.paste_requested.emit(ids, True))
        m.addAction("Copy", lambda: self._copy(ids))
        if n == 1 and clips[0].kind in ("text", "html"):
            m.addAction("Edit…", lambda: self._edit(ids))
        m.addAction("Unpin" if all(c.pinned for c in clips) else "Pin",
                    lambda: self._toggle_pin(ids))
        gm = m.addMenu("Move to group")
        none = gm.addAction("No group", lambda: self._move(ids, None))
        none.setCheckable(True)
        none.setChecked(all(c.group_id is None for c in clips))
        for gid, name in self.store.groups():
            a = gm.addAction(name, lambda _=False, g=gid: self._move(ids, g))
            a.setCheckable(True)
            a.setChecked(all(c.group_id == gid for c in clips))
        gm.addSeparator()
        gm.addAction("New group…", lambda: self._move_to_new_group(ids))
        m.addAction("Send to other computers", lambda: self.send_requested.emit(ids))
        m.addSeparator()
        m.addAction("Delete" if n == 1 else f"Delete {n} clips", lambda: self._delete(ids))
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

    def _move_to_new_group(self, ids: list[int]):
        name = self._ask("New group", "Group name:")
        if name:
            gid = self.store.add_group(name)
            self.rebuild_scopes()
            self._move(ids, gid)

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
        if self._ask_yes("Delete group",
                         f"Delete the group “{name}”? Its clips move back to the main history."):
            self.store.delete_group(gid)
            self.rebuild_scopes()
            self.refresh()

