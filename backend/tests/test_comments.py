import os

import comments


def test_set_get_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    comments.set_comment("1349", "462994", "écart vérifié", "2026-06-30")
    assert comments.get_comment("1349", "462994") == {
        "text": "écart vérifié", "updated": "2026-06-30"}


def test_get_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    assert comments.get_comment("x", "y") is None


def test_set_empty_deletes(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    comments.set_comment("1", "2", "note", "2026-06-30")
    comments.set_comment("1", "2", "   ", "2026-07-31")
    assert comments.get_comment("1", "2") is None


def test_upsert_overwrites(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    comments.set_comment("1", "2", "old", "2026-06-30")
    comments.set_comment("1", "2", "new", "2026-07-31")
    assert comments.get_comment("1", "2") == {"text": "new", "updated": "2026-07-31"}


def test_corrupted_json_tolerated(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    os.makedirs(str(tmp_path), exist_ok=True)
    with open(comments.comments_path(), "w", encoding="utf-8") as f:
        f.write("{ broken json")
    assert comments.load_comments() == {}


def test_key_format():
    assert comments.key("1349", "462994") == "1349|462994"
