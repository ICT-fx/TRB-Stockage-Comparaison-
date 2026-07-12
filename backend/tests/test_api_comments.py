import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

import main
from tests.helpers import build_xlsx


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    return TestClient(main.app)


def _proconcept():
    return build_xlsx([
        ["Stock", "Empl", "Desc", "Chrono", "Ref", "Lot", "Version", "Qte"],
        ["STK", "A1", "Produit X", 20280731, 1349, 462994, "", 10],
        ["STK", "A2", "Produit Y", 20280731, 687, 412561, "", 5],
    ])


def _storage():
    # built-in basic-stock layout: empty row0, header row1
    return build_xlsx([
        [],
        ["Artikel", "Lagerort", "G", "Kurztext", "Bestand"],
        [1349, 462994, "2028-07", "Produit X", 8],   # 8 vs 10 -> écart
        [687, 412561, "2028-07", "Produit Y", 5],     # 5 vs 5 -> OK
    ])


def _files():
    return {
        "file_theorique": ("p.xlsx", _proconcept(), "application/vnd.ms-excel"),
        "file_reel": ("s.xlsx", _storage(), "application/vnd.ms-excel"),
    }


def test_compare_attaches_null_then_stored_comment(client):
    r = client.post("/compare", files=_files())
    assert r.status_code == 200
    disc = r.json()["discrepancies"]
    assert len(disc) == 1 and disc[0]["code"] == "1349"
    assert disc[0]["stored_comment"] is None

    rc = client.post("/comments", json={
        "code": "1349", "lot": "462994", "text": "écart vérifié",
        "inventory_date": "2026-06-30"})
    assert rc.status_code == 200 and rc.json()["ok"] is True

    d = client.post("/compare", files=_files()).json()["discrepancies"][0]
    assert d["stored_comment"] == {"text": "écart vérifié", "updated": "2026-06-30"}


def test_save_comment_requires_code_and_lot(client):
    assert client.post("/comments", json={"code": "", "lot": "x", "text": "a"}).status_code == 400
    assert client.post("/comments", json={"code": "x", "lot": "", "text": "a"}).status_code == 400


def test_empty_comment_deletes(client):
    client.post("/comments", json={"code": "1", "lot": "2", "text": "note", "inventory_date": "2026-06-30"})
    client.post("/comments", json={"code": "1", "lot": "2", "text": "  ", "inventory_date": "2026-07-31"})
    import comments
    assert comments.get_comment("1", "2") is None
