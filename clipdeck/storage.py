"""SQLite-backed clip history: clips, pins and groups."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "clipdeck"

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups(
    id   INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS clips(
    id        INTEGER PRIMARY KEY,
    kind      TEXT NOT NULL,              -- text | html | image | files
    text      TEXT NOT NULL DEFAULT '',   -- plain text / file paths / image label
    html      TEXT,
    data      BLOB,                       -- PNG bytes for images
    thumb     BLOB,                       -- small PNG preview for images
    hash      TEXT UNIQUE NOT NULL,
    created   REAL NOT NULL,
    last_used REAL NOT NULL,
    pinned    INTEGER NOT NULL DEFAULT 0,
    group_id  INTEGER,
    origin    TEXT                        -- computer name for synced clips
);
CREATE INDEX IF NOT EXISTS clips_order ON clips(pinned DESC, last_used DESC);
"""


@dataclass
class Payload:
    """Clipboard content independent of where it is stored."""
    kind: str
    text: str
    html: str | None = None
    data: bytes | None = None

    def digest(self) -> str:
        h = hashlib.sha1()
        for part in (self.kind, self.text, self.html or ""):
            h.update(part.encode("utf-8", "replace"))
            h.update(b"\0")
        if self.data:
            h.update(self.data)
        return h.hexdigest()


@dataclass
class Clip:
    id: int
    kind: str
    text: str
    html: str | None
    data: bytes | None
    thumb: bytes | None
    pinned: bool
    group_id: int | None
    origin: str | None
    last_used: float

    @property
    def payload(self) -> Payload:
        return Payload(self.kind, self.text, self.html, self.data)


def _casefind(haystack, needle):
    # Unicode-aware, case-insensitive substring match (SQLite LIKE is ASCII-only,
    # which would break searching Russian/Tajik/Turkish text).
    return 1 if needle in (haystack or "").casefold() else 0


class Storage:
    LIST_COLS = "id, kind, text, html, NULL AS data, thumb, pinned, group_id, origin, last_used"

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.create_function("casefind", 2, _casefind, deterministic=True)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.db.commit()
        try:
            os.chmod(path, 0o600)  # clipboard history can hold sensitive data
        except OSError:
            pass

    @staticmethod
    def _clip(r: sqlite3.Row) -> Clip:
        return Clip(r["id"], r["kind"], r["text"], r["html"], r["data"], r["thumb"],
                    bool(r["pinned"]), r["group_id"], r["origin"], r["last_used"])

    # ---- clips -----------------------------------------------------------
    def add(self, p: Payload, thumb: bytes | None = None, origin: str | None = None,
            max_items: int = 500) -> int:
        """Insert a clip, or move an identical existing one to the top."""
        digest, now = p.digest(), time.time()
        row = self.db.execute("SELECT id FROM clips WHERE hash=?", (digest,)).fetchone()
        if row:
            self.db.execute("UPDATE clips SET last_used=? WHERE id=?", (now, row["id"]))
            self.db.commit()
            return row["id"]
        cur = self.db.execute(
            "INSERT INTO clips(kind, text, html, data, thumb, hash, created, last_used, origin)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (p.kind, p.text, p.html, p.data, thumb, digest, now, now, origin))
        self.db.commit()
        self.trim(max_items)
        return cur.lastrowid

    def trim(self, max_items: int):
        """Keep the newest `max_items` loose clips; pinned and grouped clips are never trimmed."""
        self.db.execute(
            "DELETE FROM clips WHERE id IN (SELECT id FROM clips WHERE pinned=0 AND group_id IS NULL"
            " ORDER BY last_used DESC LIMIT -1 OFFSET ?)", (max_items,))
        self.db.commit()

    def search(self, query: str = "", scope="all", limit: int = 300) -> list[Clip]:
        where, args = [], []
        if scope == "pinned":
            where.append("pinned=1")
        elif isinstance(scope, int):
            where.append("group_id=?")
            args.append(scope)
        for word in query.split():
            where.append("casefind(text, ?)")
            args.append(word.casefold())
        sql = f"SELECT {self.LIST_COLS} FROM clips"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY pinned DESC, last_used DESC LIMIT ?"
        args.append(limit)
        return [self._clip(r) for r in self.db.execute(sql, args)]

    def get(self, clip_id: int) -> Clip | None:
        r = self.db.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
        return self._clip(r) if r else None

    def touch(self, clip_id: int):
        self.db.execute("UPDATE clips SET last_used=? WHERE id=?", (time.time(), clip_id))
        self.db.commit()

    def set_pinned(self, clip_id: int, pinned: bool):
        self.db.execute("UPDATE clips SET pinned=? WHERE id=?", (int(pinned), clip_id))
        self.db.commit()

    def set_group(self, clip_id: int, group_id: int | None):
        self.db.execute("UPDATE clips SET group_id=? WHERE id=?", (group_id, clip_id))
        self.db.commit()

    def delete(self, clip_id: int):
        self.db.execute("DELETE FROM clips WHERE id=?", (clip_id,))
        self.db.commit()

    def clear_loose(self):
        """Delete everything that isn't pinned or in a group."""
        self.db.execute("DELETE FROM clips WHERE pinned=0 AND group_id IS NULL")
        self.db.commit()

    # ---- groups ----------------------------------------------------------
    def groups(self) -> list[tuple[int, str]]:
        return [(r["id"], r["name"]) for r in
                self.db.execute("SELECT id, name FROM groups ORDER BY name COLLATE NOCASE")]

    def add_group(self, name: str) -> int:
        self.db.execute("INSERT OR IGNORE INTO groups(name) VALUES(?)", (name,))
        self.db.commit()
        return self.db.execute("SELECT id FROM groups WHERE name=?", (name,)).fetchone()["id"]

    def rename_group(self, group_id: int, name: str):
        self.db.execute("UPDATE groups SET name=? WHERE id=?", (name, group_id))
        self.db.commit()

    def delete_group(self, group_id: int):
        self.db.execute("UPDATE clips SET group_id=NULL WHERE group_id=?", (group_id,))
        self.db.execute("DELETE FROM groups WHERE id=?", (group_id,))
        self.db.commit()
