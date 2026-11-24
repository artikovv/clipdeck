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
