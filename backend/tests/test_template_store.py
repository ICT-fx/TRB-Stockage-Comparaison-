import json
import os

import templates


def test_data_dir_honors_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    assert templates.data_dir() == str(tmp_path)
    assert templates.templates_path() == os.path.join(str(tmp_path), "templates.json")


def test_save_then_load_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    data = [{"id": "x1", "name": "T1", "builtin": False,
             "header_row": 1, "columns": {"sku": 0, "lot": 1, "qty": 2,
                                          "date": None, "description": None}}]
    templates.save_user_templates(data)
    assert templates.load_user_templates() == data


def test_load_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path / "nope"))
    assert templates.load_user_templates() == []


def test_load_corrupted_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    os.makedirs(str(tmp_path), exist_ok=True)
    with open(templates.templates_path(), "w", encoding="utf-8") as f:
        f.write("{ this is not valid json ")
    assert templates.load_user_templates() == []


def test_save_is_atomic_no_tmp_left(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    templates.save_user_templates([])
    leftovers = [p for p in os.listdir(str(tmp_path)) if p.endswith(".tmp")]
    assert leftovers == []
