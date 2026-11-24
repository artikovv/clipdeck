from clipdeck.popup import Popup
from clipdeck.qt import QApplication, QEvent, QKeyEvent, Qt
from clipdeck.storage import Payload


def key(widget, k, mods=Qt.KeyboardModifier.NoModifier, text=""):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, k, mods, text))


def test_keyboard_paste_pin_delete(qapp, store):
    ids = [store.add(Payload("text", f"clip {i}")) for i in range(5)]
    popup = Popup(store)
    popup.present()
    pasted = []
    popup.paste_requested.connect(lambda cid, plain: pasted.append((cid, plain)))
    assert popup.list.count() == 5

    key(popup.search, Qt.Key.Key_Down)
    key(popup.search, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    key(popup.search, Qt.Key.Key_3, Qt.KeyboardModifier.ControlModifier, "3")
    assert pasted == [(ids[3], True), (ids[2], False)]

    key(popup.search, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier)
    assert store.get(ids[3]).pinned

    key(popup.search, Qt.Key.Key_Delete, Qt.KeyboardModifier.ShiftModifier)
    assert len(store.search()) == 4

    popup.search.setText("clip 1")
    popup.refresh()
    assert popup.list.count() == 1
    popup.hide()
