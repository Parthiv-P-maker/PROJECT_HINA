import sqlite3

from core import memory_store, semantic


def _fill(n=8):
    for i in range(n):
        memory_store.add_fact(f"fact number {i} about topic{i}")
    memory_store.add_fact("my sister Maya plays the violin")


def test_unavailable_without_the_embedding_model():
    _fill()
    assert semantic.relevant_facts("who plays music?") is None


def test_few_facts_are_all_returned_without_embedding(monkeypatch):
    memory_store.add_fact("i like jazz")
    monkeypatch.setattr(semantic, "embed", lambda *a, **k: (_ for _ in ()).throw(AssertionError("embedded")))
    assert [f["text"] for f in semantic.relevant_facts("music")] == ["i like jazz"]


def test_ranks_by_meaning_and_embeds_each_fact_once(monkeypatch):
    _fill()
    calls = []

    def fake_embed(texts, prefix=semantic.DOCUMENT_PREFIX):
        calls.append(list(texts))
        # a 2-D "meaning": music-ish vs everything else
        return [[1.0, 0.0] if ("violin" in t or "music" in t) else [0.0, 1.0] for t in texts]

    monkeypatch.setattr(semantic, "available", lambda: True)
    monkeypatch.setattr(semantic, "embed", fake_embed)
    hits = semantic.relevant_facts("which instrument does my family play, music?")
    assert [f["text"] for f in hits] == ["my sister Maya plays the violin"]
    assert len(calls[0]) == 9  # every fact embedded on the first call
    semantic.relevant_facts("music again")
    assert calls[-1] == ["music again"] and len(calls) == 3  # the facts were not embedded again


def test_embedding_failure_falls_back_to_none(monkeypatch):
    _fill()
    monkeypatch.setattr(semantic, "available", lambda: True)
    monkeypatch.setattr(semantic, "embed", lambda *a, **k: None)
    assert semantic.relevant_facts("anything") is None


def test_chat_uses_keyword_matching_when_semantic_is_unavailable(fake_ollama):
    from core import conversation
    _fill()
    fake_ollama.chat_reply = "Violin, I believe."
    conversation.chat_reply("what instrument does maya play?")
    system = fake_ollama.requests[-1][1]["messages"][0]["content"]
    assert "violin" in system and "topic3" not in system


def test_old_databases_gain_the_embedding_column():
    path = memory_store.db_path()
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
                     "source TEXT NOT NULL, created TEXT NOT NULL)")
        conn.execute("INSERT INTO facts (text, source, created) VALUES ('old fact', 'user', 'then')")
    facts = memory_store.list_facts()
    assert facts[0]["text"] == "old fact" and facts[0]["embedding"] is None
    memory_store.set_fact_embedding(facts[0]["id"], [0.5, 0.5])
    assert memory_store.list_facts()[0]["embedding"] == "[0.5, 0.5]"


def test_cosine():
    assert semantic.cosine([1, 0], [1, 0]) == 1.0
    assert semantic.cosine([1, 0], [0, 1]) == 0.0
    assert semantic.cosine([0, 0], [1, 1]) == 0.0
