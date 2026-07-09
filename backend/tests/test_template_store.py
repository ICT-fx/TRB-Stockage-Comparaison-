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


import pytest


def test_all_templates_includes_builtin_first(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    tpls = templates.all_templates()
    assert tpls[0]["id"] == "basic-stock"
    assert tpls[0]["builtin"] is True


def test_get_template_builtin_and_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    assert templates.get_template("basic-stock")["name"] == "Template RK Logistics"
    assert templates.get_template("does-not-exist") is None


def test_validate_ok_normalizes_optionals():
    out = templates.validate_template({
        "name": "  T ", "header_row": 2,
        "columns": {"sku": 0, "lot": 1, "qty": 4, "date": 2, "description": 3},
    })
    assert out == {"name": "T", "header_row": 2,
                   "columns": {"sku": 0, "lot": 1, "qty": 4, "date": 2, "description": 3}}


def test_validate_optional_absent_becomes_none():
    out = templates.validate_template({
        "name": "T", "header_row": 1,
        "columns": {"sku": 0, "lot": 1, "qty": 2},
    })
    assert out["columns"]["date"] is None
    assert out["columns"]["description"] is None


def test_validate_rejects_empty_name():
    with pytest.raises(ValueError):
        templates.validate_template({"name": "  ", "header_row": 1,
                                     "columns": {"sku": 0, "lot": 1, "qty": 2}})


def test_validate_rejects_missing_required():
    with pytest.raises(ValueError):
        templates.validate_template({"name": "T", "header_row": 1,
                                     "columns": {"sku": 0, "lot": 1}})


def test_validate_rejects_required_collision():
    with pytest.raises(ValueError):
        templates.validate_template({"name": "T", "header_row": 1,
                                     "columns": {"sku": 0, "lot": 0, "qty": 2}})


def test_validate_rejects_bad_header_row():
    with pytest.raises(ValueError):
        templates.validate_template({"name": "T", "header_row": 0,
                                     "columns": {"sku": 0, "lot": 1, "qty": 2}})


def _payload(name="T"):
    return {"name": name, "header_row": 1,
            "columns": {"sku": 0, "lot": 1, "qty": 2}}


def test_create_assigns_id_and_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    created = templates.create_template(_payload("Partenaire X"))
    assert created["id"] and created["builtin"] is False
    assert created["name"] == "Partenaire X"
    assert templates.get_template(created["id"])["name"] == "Partenaire X"


def test_create_persists_across_new_process_read(monkeypatch, tmp_path):
    # Simule un redémarrage : on écrit, puis on relit depuis le fichier.
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    created = templates.create_template(_payload("Persist"))
    reloaded = templates.load_user_templates()
    assert any(t["id"] == created["id"] for t in reloaded)


def test_update_modifies_existing(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    created = templates.create_template(_payload("Old"))
    updated = templates.update_template(created["id"], _payload("New"))
    assert updated["name"] == "New"
    assert templates.get_template(created["id"])["name"] == "New"


def test_update_missing_raises_keyerror(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    with pytest.raises(KeyError):
        templates.update_template("ghost", _payload())


def test_update_builtin_raises_valueerror(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        templates.update_template("basic-stock", _payload())


def test_delete_removes(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    created = templates.create_template(_payload())
    templates.delete_template(created["id"])
    assert templates.get_template(created["id"]) is None


def test_delete_missing_raises_keyerror(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    with pytest.raises(KeyError):
        templates.delete_template("ghost")


def test_delete_builtin_raises_valueerror(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        templates.delete_template("basic-stock")


def test_data_dir_uses_shared_drive_when_present(monkeypatch):
    monkeypatch.delenv("TRB_DATA_DIR", raising=False)
    monkeypatch.setattr(templates.os, "name", "nt")
    monkeypatch.setattr(templates.os.path, "isdir", lambda p: True)
    assert templates.data_dir() == templates.SHARED_WINDOWS_DIR


def test_data_dir_falls_back_local_when_drive_absent(monkeypatch):
    monkeypatch.delenv("TRB_DATA_DIR", raising=False)
    monkeypatch.setattr(templates.os, "name", "nt")
    monkeypatch.setattr(templates.os.path, "isdir", lambda p: False)
    monkeypatch.setenv("APPDATA", "/tmp/fake-appdata")
    d = templates.data_dir()
    assert d.endswith("TRB-Comparaison-Stock")
    assert templates.SHARED_WINDOWS_DIR not in d
