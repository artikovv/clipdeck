from clipdeck.storage import Payload


def test_dedupe_moves_to_top(store):
    a = store.add(Payload("text", "first"))
    store.add(Payload("text", "second"))
    assert store.add(Payload("text", "first")) == a
    assert [c.text for c in store.search()] == ["first", "second"]


def test_search_is_unicode_case_insensitive(store):
    store.add(Payload("text", "Привет МИР"))
    store.add(Payload("text", "İstanbul"))
    store.add(Payload("text", "hello"))
    assert [c.text for c in store.search("мир")] == ["Привет МИР"]
    assert [c.text for c in store.search("ПРИВЕТ мир")] == ["Привет МИР"]


def test_trim_keeps_pinned_and_grouped(store):
    pinned = store.add(Payload("text", "pinned"))
    grouped = store.add(Payload("text", "grouped"))
    store.set_pinned(pinned, True)
    store.set_group(grouped, store.add_group("Replies"))
    for i in range(20):
        store.add(Payload("text", f"t{i}"), max_items=5)
    texts = [c.text for c in store.search()]
    assert len(texts) == 7 and "pinned" in texts and "grouped" in texts


def test_scopes_and_groups(store):
    a = store.add(Payload("text", "a"))
    b = store.add(Payload("text", "b"))
    store.set_pinned(a, True)
    gid = store.add_group("Work")
    store.set_group(b, gid)
    assert [c.id for c in store.search("", "pinned")] == [a]
    assert [c.id for c in store.search("", gid)] == [b]
    store.delete_group(gid)
    assert store.get(b).group_id is None


def test_clear_loose(store):
    keep = store.add(Payload("text", "keep"))
    store.set_pinned(keep, True)
    store.add(Payload("text", "drop"))
    store.clear_loose()
    assert [c.text for c in store.search()] == ["keep"]


def test_update_text(store):
    a = store.add(Payload("html", "bold", "<b>bold</b>"))
    assert store.update_text(a, "plain now") == a
    clip = store.get(a)
    assert (clip.kind, clip.text, clip.html) == ("text", "plain now", None)


def test_update_text_merges_with_existing_duplicate(store):
    keep = store.add(Payload("text", "same"))
    edited = store.add(Payload("text", "other"))
    store.set_pinned(edited, True)
    assert store.update_text(edited, "same") == keep
    assert store.get(edited) is None and store.get(keep).pinned


def test_uses_and_delete_unused(store):
    used = store.add(Payload("text", "used"))
    store.add(Payload("text", "never used"))
    pinned = store.add(Payload("text", "pinned, unused"))
    store.set_pinned(pinned, True)
    store.mark_used([used])
    assert store.count_matching(unused_only=True) == 1
    assert store.delete_matching(unused_only=True) == 1
    assert sorted(c.text for c in store.search()) == ["pinned, unused", "used"]


def test_delete_by_age(store):
    import time
    old = store.add(Payload("text", "old"))
    store.add(Payload("text", "new"))
    store.db.execute("UPDATE clips SET last_used=? WHERE id=?", (time.time() - 40 * 86400, old))
    assert store.count_matching(older_than_days=30) == 1
    store.delete_matching(older_than_days=30)
    assert [c.text for c in store.search()] == ["new"]
    store.set_pinned(store.search()[0].id, True)
    assert store.delete_matching() == 0                 # pinned clips are kept…
    assert store.delete_matching(include_kept=True) == 1  # …unless asked


def test_backup_and_restore(store, tmp_path):
    store.add(Payload("text", "keep me"))
    backup = str(tmp_path / "backup.db")
    store.backup(backup)
    store.add(Payload("text", "added later"))
    assert store.is_backup(backup) == 1
    store.restore(backup)
    assert [c.text for c in store.search()] == ["keep me"]
    assert store.is_backup(str(tmp_path / "missing.db")) is None


def test_migrates_old_database(tmp_path):
    import sqlite3
    from clipdeck.storage import SCHEMA, Storage
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)  # 0.2.0 schema has no "uses" column
    db.execute("INSERT INTO clips(kind,text,hash,created,last_used) VALUES('text','pasted','a',1,100)")
    db.execute("INSERT INTO clips(kind,text,hash,created,last_used) VALUES('text','never','b',1,1)")
    db.commit()
    db.close()
    store = Storage(path)
    assert store.count_matching(unused_only=True) == 1  # "pasted" counts as used
