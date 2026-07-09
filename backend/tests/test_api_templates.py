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


def _proconcept_file():
    # 8 colonnes attendues par parse_proconcept_lot.
    return build_xlsx([
        ["Stock", "Empl", "Desc", "Chrono", "Ref", "Lot", "Version", "Qte"],
        ["STK", "A1", "Produit X", 20280731, 1349, 462994, "", 10],
        ["STK", "A2", "Produit Y", 20280731, 687, 412561, "", 5],
    ])


def test_compare_with_custom_reordered_template(client):
    # Storage file with reordered columns; create a matching template.
    storage = build_xlsx([
        ["Qte", "SKU", "Lot"],
        [10, 1349, 462994],
        [3, 687, 412561],
    ])
    tpl = client.post("/templates", json={
        "name": "Reordonne", "header_row": 1,
        "columns": {"sku": 1, "lot": 2, "qty": 0, "date": None, "description": None},
    }).json()

    files = {
        "file_theorique": ("p.xlsx", _proconcept_file(), "application/vnd.ms-excel"),
        "file_reel": ("s.xlsx", storage, "application/vnd.ms-excel"),
    }
    r = client.post("/compare", data={"storage_template_id": tpl["id"]}, files=files)
    assert r.status_code == 200, r.text
    stats = r.json()["stats"]
    # 1349: 10 vs 10 OK ; 687: 5 vs 3 -> écart
    assert stats["ok_count"] == 1
    assert stats["discrepancy_count"] == 1


def test_compare_unknown_template_returns_400(client):
    files = {
        "file_theorique": ("p.xlsx", _proconcept_file(), "application/vnd.ms-excel"),
        "file_reel": ("s.xlsx", _proconcept_file(), "application/vnd.ms-excel"),
    }
    r = client.post("/compare", data={"storage_template_id": "ghost"}, files=files)
    assert r.status_code == 400


def test_compare_default_template_still_works(client):
    # No storage_template_id -> built-in basic-stock (RK layout).
    storage = build_xlsx([
        [],
        ["Artikel", "Lagerort", "G", "Kurztext", "Bestand"],
        [1349, 462994, "2028-07", "Produit X", 10],
        [687, 412561, "2028-07", "Produit Y", 5],
    ])
    files = {
        "file_theorique": ("p.xlsx", _proconcept_file(), "application/vnd.ms-excel"),
        "file_reel": ("s.xlsx", storage, "application/vnd.ms-excel"),
    }
    r = client.post("/compare", files=files)
    assert r.status_code == 200, r.text
    assert r.json()["stats"]["total_products"] == 2
