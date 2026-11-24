import pytest

from clipdeck.clipboard import image_to_png, make_thumb, mime_from_payload, payload_from_mime
from clipdeck.qt import QColor, QImage, QMimeData
from clipdeck.storage import Payload


@pytest.fixture
def png(qapp):
    img = QImage(300, 200, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    return image_to_png(img)


@pytest.mark.parametrize("payload", [
    Payload("text", "plain"),
    Payload("html", "bold", "<b>bold</b>"),
    Payload("files", "/tmp\n/etc/hosts"),
])
def test_round_trip(qapp, payload):
    back = payload_from_mime(mime_from_payload(payload), 10**8)
    assert (back.kind, back.text) == (payload.kind, payload.text)


def test_image_round_trip_and_thumb(qapp, png):
    back = payload_from_mime(mime_from_payload(Payload("image", "i", None, png)), 10**8)
    assert back.kind == "image" and back.text == "Image 300×200"
    thumb = QImage.fromData(make_thumb(png), "PNG")
    assert max(thumb.width(), thumb.height()) == 96


def test_image_size_limit(qapp, png):
    assert payload_from_mime(mime_from_payload(Payload("image", "i", None, png)), 10) is None


def test_plain_text_paste_drops_html(qapp):
    md = mime_from_payload(Payload("html", "bold", "<b>bold</b>"), plain=True)
    assert md.formats() == ["text/plain"]


def test_files_include_nemo_format(qapp):
    md = mime_from_payload(Payload("files", "/tmp/a b.txt"))
    assert bytes(md.data("x-special/gnome-copied-files")) == b"copy\nfile:///tmp/a%20b.txt"


def test_password_manager_secrets_are_skipped(qapp):
    md = QMimeData()
    md.setText("hunter2")
    md.setData("x-kde-passwordManagerHint", b"secret")
    assert payload_from_mime(md, 10**8) is None


def test_combine_joins_text_and_skips_images(png):
    from clipdeck.clipboard import combine
    joined = combine([Payload("text", "a"), Payload("image", "i", None, png), Payload("html", "b", "<b>b</b>")])
    assert (joined.kind, joined.text) == ("text", "a\nb")
    assert combine([Payload("image", "i", None, png)]).kind == "image"
    assert combine([Payload("image", "i", None, png), Payload("image", "j", None, png)]) is None
