from pathlib import Path

from clipdeck.dialogs import DeleteDataDialog, help_html
from clipdeck.storage import Payload


def test_delete_dialog_counts(qapp, store):
    store.add(Payload("text", "a"))
    pinned = store.add(Payload("text", "b"))
    store.set_pinned(pinned, True)
    d = DeleteDataDialog(store)
    assert "Nothing to delete" in d.summary.text()  # both are new
    d.everything.setChecked(True)
    assert d.summary.text().startswith("1 clip will")
    d.include_kept.setChecked(True)
    assert d.summary.text().startswith("2 clips will")
    assert d.choice() == {"older_than_days": None, "include_kept": True}


def test_help_lists_keys_and_hotkey():
    text = help_html("Ctrl+`")
    assert "Ctrl+`" in text and "Ctrl+A" in text and "<a href=" in text


def test_import_files(qapp, tmp_path):
    from clipdeck.app import Clipdeck
    from clipdeck.clipboard import image_to_png
    from clipdeck.qt import QColor, QImage

    class Cfg:
        def get(self, key):
            return 10
    fake = type("Fake", (), {"cfg": Cfg()})()
    (tmp_path / "note.txt").write_text("Привет")
    img = QImage(20, 10, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    (tmp_path / "pic.png").write_bytes(image_to_png(img))
    (tmp_path / "bin.dat").write_bytes(b"\xff\xfe\x00\x01")
    load = lambda name: Clipdeck._payload_from_file(fake, Path(tmp_path / name))  # noqa: E731
    assert (load("note.txt").kind, load("note.txt").text) == ("text", "Привет")
    assert load("pic.png").text == "Image 20×10"
    assert load("bin.dat") is None
