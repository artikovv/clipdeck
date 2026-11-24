"""Watches the system clipboard and converts between QMimeData and Payloads."""
from __future__ import annotations

import time

from .qt import QBuffer, QByteArray, QIODevice, QMimeData, QObject, Qt, QUrl, Signal
from .qt import QGuiApplication, QImage, QPixmap

from .storage import Payload

# Password managers (KeePassXC, etc.) tag secrets with this format; we never record them.
PASSWORD_HINT = "x-kde-passwordManagerHint"
# Nemo/Nautilus use this format for copied files.
GNOME_FILES = "x-special/gnome-copied-files"


def image_to_png(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def make_thumb(png: bytes | None, size: int = 96) -> bytes | None:
    if not png:
        return None
    img = QImage.fromData(png, "PNG")
    if img.isNull():
        return None
    return image_to_png(img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


def payload_from_mime(md: QMimeData | None, max_image_bytes: int) -> Payload | None:
    if md is None or PASSWORD_HINT in md.formats():
        return None

    if md.hasUrls():
        urls = md.urls()
        if urls and all(u.isLocalFile() for u in urls):
            return Payload("files", "\n".join(u.toLocalFile() for u in urls))

    text = md.text() if md.hasText() else ""

    if md.hasImage() and not text.strip():
        img = md.imageData()
        if isinstance(img, QPixmap):
            img = img.toImage()
        if isinstance(img, QImage) and not img.isNull():
            png = image_to_png(img)
            if len(png) > max_image_bytes:
                return None
            return Payload("image", f"Image {img.width()}×{img.height()}", None, png)

    if text.strip():
        if md.hasHtml():
            html = md.html()
            if html.strip():
                return Payload("html", text, html)
        return Payload("text", text)
    return None


def mime_from_payload(p: Payload, plain: bool = False) -> QMimeData:
    md = QMimeData()
    if p.kind == "image" and p.data:
        md.setImageData(QImage.fromData(p.data, "PNG"))
    elif plain or p.kind == "text":
        md.setText(p.text)
    elif p.kind == "html":
        md.setHtml(p.html or "")
        md.setText(p.text)
    elif p.kind == "files":
        urls = [QUrl.fromLocalFile(path) for path in p.text.splitlines() if path]
        md.setUrls(urls)
        gnome = "copy\n" + "\n".join(bytes(u.toEncoded()).decode() for u in urls)
        md.setData(GNOME_FILES, QByteArray(gnome.encode()))
        md.setText(p.text)
    else:
        md.setText(p.text)
    return md


def combine(payloads: list[Payload]) -> Payload | None:
    """Several clips pasted at once become one text, one clip per line (as in Ditto).
    Images can't be joined with text, so they're left out."""
    if len(payloads) == 1:
        return payloads[0]
    texts = [p.text for p in payloads if p.kind != "image"]
    return Payload("text", "\n".join(texts)) if texts else None


class ClipboardMonitor(QObject):
    captured = Signal(object)  # Payload

    def __init__(self, max_image_bytes, parent=None):
        super().__init__(parent)
        self.max_image_bytes = max_image_bytes  # callable returning an int
        self.paused = False
        self._ignore_until = 0.0
        self.cb = QGuiApplication.clipboard()
        self.cb.dataChanged.connect(self._on_change)

    def set_clipboard(self, p: Payload, plain: bool = False):
        """Put a clip on the clipboard without recording it again."""
        self._ignore_until = time.monotonic() + 0.6
        self.cb.setMimeData(mime_from_payload(p, plain))

    def _on_change(self):
        if self.paused or time.monotonic() < self._ignore_until:
            return
        try:
            p = payload_from_mime(self.cb.mimeData(), self.max_image_bytes())
        except Exception as e:  # a misbehaving source app shouldn't kill us
            print(f"clipdeck: could not read clipboard: {e}")
            return
        if p:
            self.captured.emit(p)
