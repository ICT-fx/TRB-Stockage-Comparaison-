import pytest
from fastapi.testclient import TestClient

import main
from tests.helpers import build_xlsx


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    return TestClient(main.app)


def test_list_templates_has_builtin(client):
    r = client.get("/templates")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["templates"]]
    assert "basic-stock" in ids


def test_create_list_update_delete(client):
    payload = {"name": "PX", "header_row": 1,
               "columns": {"sku": 0, "lot": 1, "qty": 2, "date": None, "description": None}}
    r = client.post("/templates", json=payload)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]

    assert tid in [t["id"] for t in client.get("/templates").json()["templates"]]

    payload["name"] = "PX2"
    r = client.put(f"/templates/{tid}", json=payload)
    assert r.status_code == 200 and r.json()["name"] == "PX2"

    r = client.delete(f"/templates/{tid}")
    assert r.status_code == 200
    assert tid not in [t["id"] for t in client.get("/templates").json()["templates"]]


def test_create_invalid_returns_400(client):
    r = client.post("/templates", json={"name": "", "header_row": 1,
                                        "columns": {"sku": 0, "lot": 1, "qty": 2}})
    assert r.status_code == 400


def test_update_builtin_returns_400(client):
    r = client.put("/templates/basic-stock", json={"name": "x", "header_row": 1,
                                                   "columns": {"sku": 0, "lot": 1, "qty": 2}})
    assert r.status_code == 400


def test_delete_builtin_returns_400(client):
    assert client.delete("/templates/basic-stock").status_code == 400


def test_delete_missing_returns_404(client):
    assert client.delete("/templates/ghost").status_code == 404


def test_preview_detects_columns(client):
    data = build_xlsx([
        [],
        ["Artikel", "Lagerort", "Bestand"],
        [1349, 462994, 10],
    ])
    r = client.post("/templates/preview",
                    files={"file": ("s.xlsx", data,
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["header_row"] == 2
    assert body["columns"][0]["name"] == "Artikel"


def test_create_non_dict_columns_returns_400(client):
    r = client.post("/templates", json={"name": "X", "header_row": 1,
                                        "columns": [0, 1, 2]})
    assert r.status_code == 400
