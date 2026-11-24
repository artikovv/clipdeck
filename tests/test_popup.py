import pytest

from clipdeck.popup import Popup
from clipdeck.qt import QApplication, QEvent, QKeyEvent, Qt
from clipdeck.storage import Payload

NO = Qt.KeyboardModifier.NoModifier
CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


def key(widget, k, mods=NO, text=""):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, k, mods, text))


@pytest.fixture
def popup(qapp, store):
    # Added oldest first, so the list shows "clip 4" … "clip 0".
    ids = [store.add(Payload("text", f"clip {i}")) for i in range(5)]
    p = Popup(store)
    p.present()
    p.ids = list(reversed(ids))  # ids in list order
    p.pasted, p.copied = [], []
    p.paste_requested.connect(lambda ids, plain: p.pasted.append((ids, plain)))
    p.copy_requested.connect(p.copied.append)
    yield p
    p.hide()


def texts(p):
    return [c.text for c in p.store.search()]


def test_enter_and_quick_paste(popup):
    key(popup.search, Qt.Key.Key_Down)
    key(popup.search, Qt.Key.Key_Return, SHIFT)
    key(popup.search, Qt.Key.Key_3, CTRL, "3")
    assert popup.pasted == [([popup.ids[1]], True), ([popup.ids[2]], False)]


def test_position_numbers_shown(popup):
    assert popup.list.item(0).text().startswith("1 ")
    assert popup.list.item(4).text().startswith("5 ")


def test_delete_key_deletes_selected(popup):
    key(popup.search, Qt.Key.Key_Delete)
    assert texts(popup) == ["clip 3", "clip 2", "clip 1", "clip 0"]
    assert popup.list.currentRow() == 0


def test_delete_key_edits_search_text_while_typing(popup):
    popup.search.setText("clip 1")
    popup.search.setCursorPosition(0)
    key(popup.search, Qt.Key.Key_Delete)
    assert len(texts(popup)) == 5  # nothing deleted; the key went to the search box


def test_ctrl_a_selects_all_then_delete_asks_first(popup, monkeypatch):
    key(popup.search, Qt.Key.Key_A, CTRL)
    assert len(popup.list.selectedItems()) == 5
    asked = []
    monkeypatch.setattr(popup, "_ask_yes", lambda *a: asked.append(a) or False)
    key(popup.search, Qt.Key.Key_Delete)
    assert asked and len(texts(popup)) == 5  # said no
    monkeypatch.setattr(popup, "_ask_yes", lambda *a: True)
    key(popup.search, Qt.Key.Key_Delete)
    assert texts(popup) == []


def test_ctrl_a_selects_search_text_while_typing(popup):
    popup.search.setText("clip")
    key(popup.search, Qt.Key.Key_A, CTRL)
    assert len(popup.list.selectedItems()) <= 1


def test_shift_down_extends_selection_and_enter_pastes_all(popup):
    key(popup.search, Qt.Key.Key_Down, SHIFT)
    key(popup.search, Qt.Key.Key_Down, SHIFT)
    assert popup.selected_ids() == popup.ids[:3]
    key(popup.search, Qt.Key.Key_Return)
    assert popup.pasted == [(popup.ids[:3], False)]


def test_ctrl_c_copies(popup):
    key(popup.search, Qt.Key.Key_C, CTRL)
    assert popup.copied == [[popup.ids[0]]]


def test_ctrl_p_pins_selection(popup):
    key(popup.search, Qt.Key.Key_A, CTRL)
    key(popup.search, Qt.Key.Key_P, CTRL)
    assert all(c.pinned for c in popup.store.search())
    key(popup.search, Qt.Key.Key_P, CTRL)
    assert not any(c.pinned for c in popup.store.search())


def test_escape_clears_search_first(popup):
    popup.search.setText("clip 1")
    key(popup.search, Qt.Key.Key_Escape)
    assert popup.search.text() == "" and popup.isVisible()
    key(popup.search, Qt.Key.Key_Escape)
    assert not popup.isVisible()


def test_f3_preview_shows_full_text(popup):
    key(popup.search, Qt.Key.Key_F3)
    assert popup.preview.isVisible()
    assert popup.preview_text.toPlainText() == "clip 4"


def test_edit_clip(popup, monkeypatch):
    monkeypatch.setattr("clipdeck.popup.QInputDialog.getMultiLineText",
                        lambda *a, **k: ("edited text", True))
    key(popup.search, Qt.Key.Key_E, CTRL)
    assert texts(popup)[0] == "edited text"


def test_long_lines_are_shortened_not_scrolled(popup):
    popup.store.add(Payload("text", "word " * 200))
    popup.refresh()
    assert popup.list.item(0).text().endswith("…")
    assert popup.list.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
