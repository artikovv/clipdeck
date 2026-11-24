"""Encrypted clip sync between computers on the same network.

Each clip is sent as one frame: a 4-byte big-endian length, then a Fernet
token (AES-128-CBC + HMAC-SHA256) holding JSON. The key comes from a shared
passphrase, so only computers with the same passphrase can read or inject clips.
Received clips are never re-broadcast, so two computers can't loop.
"""
from __future__ import annotations

import base64
import json
import re
import socket
import struct
import uuid

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from .qt import QObject, Signal
from .qt import QHostAddress, QTcpServer, QTcpSocket

from .storage import Payload

MAX_FRAME = 40 * 1024 * 1024
TOKEN_TTL = 300  # seconds; rejects replayed messages (keep clocks in sync)
INSTANCE_ID = uuid.uuid4().hex
HOSTNAME = socket.gethostname()


def make_fernet(passphrase: str) -> Fernet:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=b"clipdeck-sync-v1", iterations=390_000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(passphrase.encode())))


def parse_peers(text: str, default_port: int) -> list[tuple[str, int]]:
    peers = []
    for entry in re.split(r"[,\s]+", text.strip()):
        if not entry:
            continue
        host, sep, port = entry.rpartition(":")
        if sep and port.isdigit():
            peers.append((host, int(port)))
        else:
            peers.append((entry, default_port))
    return peers


class SyncService(QObject):
    received = Signal(object, str)  # Payload, origin computer name
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server: QTcpServer | None = None
        self.fernet: Fernet | None = None
        self.peers: list[tuple[str, int]] = []
        self._outgoing: set = set()
        self._buffers: dict[int, bytearray] = {}
        self._incoming: dict[int, QTcpSocket] = {}

    @property
    def running(self) -> bool:
        return self.server is not None

    def start(self, port: int, peers: str, passphrase: str) -> bool:
        self.stop()
        if not passphrase:
            self.status.emit("Sync is off: set a passphrase in Settings → Sync.")
            return False
        self.fernet = make_fernet(passphrase)
        self.peers = parse_peers(peers, port)
        self.server = QTcpServer(self)
        self.server.newConnection.connect(self._on_connection)
        if not self.server.listen(QHostAddress.SpecialAddress.Any, port):
            self.status.emit(f"Sync couldn't listen on port {port}: {self.server.errorString()}")
            self.server = None
            return False
        return True

    def stop(self):
        if self.server:
            self.server.close()
            self.server.deleteLater()
        self.server = None
        for s in list(self._incoming.values()):
            s.abort()
        self._incoming.clear()
        self._buffers.clear()

    # ---- sending ---------------------------------------------------------
    def send(self, p: Payload):
        if not (self.fernet and self.peers):
            return
        msg = {"v": 1, "id": INSTANCE_ID, "name": HOSTNAME, "kind": p.kind, "text": p.text,
               "html": p.html, "data": base64.b64encode(p.data).decode() if p.data else None}
        token = self.fernet.encrypt(json.dumps(msg).encode())
        if len(token) > MAX_FRAME:
            self.status.emit("Clip too large to sync.")
            return
        frame = struct.pack(">I", len(token)) + token
        for host, port in self.peers:
            s = QTcpSocket(self)
            self._outgoing.add(s)
            s.connected.connect(lambda s=s: (s.write(frame), s.disconnectFromHost()))
            s.disconnected.connect(lambda s=s: self._drop(s))
            s.errorOccurred.connect(lambda _err, s=s, h=host: self._send_failed(s, h))
            s.connectToHost(host, port)

    def _send_failed(self, s: QTcpSocket, host: str):
        if s.error() != QTcpSocket.SocketError.RemoteHostClosedError:
            self.status.emit(f"Couldn't sync to {host}: {s.errorString()}")
        self._drop(s)

    def _drop(self, s: QTcpSocket):
        if s in self._outgoing:
            self._outgoing.discard(s)
            s.deleteLater()

    # ---- receiving -------------------------------------------------------
    def _on_connection(self):
        while self.server and self.server.hasPendingConnections():
            s = self.server.nextPendingConnection()
            key = id(s)
            self._incoming[key] = s
            self._buffers[key] = bytearray()
            s.readyRead.connect(lambda k=key: self._read(k))
            s.disconnected.connect(lambda k=key: self._close(k))

    def _close(self, key: int):
        s = self._incoming.pop(key, None)
        self._buffers.pop(key, None)
        if s:
            s.deleteLater()

    def _read(self, key: int):
        s, buf = self._incoming.get(key), self._buffers.get(key)
        if s is None or buf is None:
            return
        buf += bytes(s.readAll())
        while len(buf) >= 4:
            n = struct.unpack(">I", buf[:4])[0]
            if n > MAX_FRAME:
                s.abort()
                return
            if len(buf) < 4 + n:
                break
            token = bytes(buf[4:4 + n])
            del buf[:4 + n]
            self._handle(token, s.peerAddress().toString())

    def _handle(self, token: bytes, addr: str):
        try:
            msg = json.loads(self.fernet.decrypt(token, ttl=TOKEN_TTL))
        except InvalidToken:
            self.status.emit(f"Rejected a clip from {addr}: wrong passphrase, or the clocks differ by over 5 minutes.")
            return
        except ValueError:
            return
        if msg.get("id") == INSTANCE_ID or msg.get("kind") not in ("text", "html", "image", "files"):
            return
        data = base64.b64decode(msg["data"]) if msg.get("data") else None
        p = Payload(msg["kind"], msg.get("text") or "", msg.get("html"), data)
        self.received.emit(p, msg.get("name") or addr)
