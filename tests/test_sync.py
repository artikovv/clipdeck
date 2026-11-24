import clipdeck.sync as sync
from clipdeck.storage import Payload
from conftest import run_loop


def test_parse_peers():
    assert sync.parse_peers("192.168.1.2, box.local:5000\nx", 47811) == [
        ("192.168.1.2", 47811), ("box.local", 5000), ("x", 47811)]


def _pair(qapp, monkeypatch, port, sender_pass, receiver_pass):
    received, messages = [], []
    receiver, sender = sync.SyncService(), sync.SyncService()
    receiver.received.connect(lambda p, origin: received.append((p.kind, p.text, len(p.data or b""))))
    receiver.status.connect(messages.append)
    assert receiver.start(port, "", receiver_pass)
    assert sender.start(port + 1, f"127.0.0.1:{port}", sender_pass)
    # Both services live in one process here; give the sender its own identity.
    monkeypatch.setattr(sync, "INSTANCE_ID", "sender")
    return receiver, sender, received, messages


def test_encrypted_round_trip(qapp, monkeypatch):
    receiver, sender, received, _ = _pair(qapp, monkeypatch, 47950, "secret", "secret")
    sender.send(Payload("text", "hi over lan"))
    sender.send(Payload("image", "img", None, b"\x89PNG fake"))
    monkeypatch.setattr(sync, "INSTANCE_ID", "receiver")
    run_loop(1500)
    assert sorted(received) == [("image", "img", 9), ("text", "hi over lan", 0)]
    receiver.stop(), sender.stop()


def test_wrong_passphrase_rejected(qapp, monkeypatch):
    receiver, sender, received, messages = _pair(qapp, monkeypatch, 47960, "wrong", "secret")
    sender.send(Payload("text", "bad"))
    monkeypatch.setattr(sync, "INSTANCE_ID", "receiver")
    run_loop(1000)
    assert received == [] and any("wrong passphrase" in m for m in messages)
    receiver.stop(), sender.stop()
