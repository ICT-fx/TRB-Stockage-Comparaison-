import pytest

import templates
from tests.helpers import build_xlsx


def test_detects_header_on_first_row():
    data = build_xlsx([
        ["SKU", "Lot", "Qte"],
        [1349, 462994, 10],
        [687, 412561, 5],
    ])
    out = templates.detect_columns(data)
    assert out["header_row"] == 1
    names = [c["name"] for c in out["columns"]]
    assert names == ["SKU", "Lot", "Qte"]
    assert out["columns"][0]["samples"][0] == "1349"


def test_autodetects_header_after_empty_first_row():
    # Format RK : 1re ligne vide, en-tête ligne 2.
    data = build_xlsx([
        [],
        ["Artikel", "Lagerort", "G", "Kurztext", "Bestand"],
        [1349, 462994, "2028-07", "Produit X", 10],
    ])
    out = templates.detect_columns(data)
    assert out["header_row"] == 2
    assert out["columns"][0]["name"] == "Artikel"
    assert out["columns"][4]["name"] == "Bestand"


def test_header_row_override():
    data = build_xlsx([
        ["ignore", "these"],
        ["SKU", "Lot"],
        [1349, 462994],
    ])
    out = templates.detect_columns(data, header_row=2)
    assert out["header_row"] == 2
    assert [c["name"] for c in out["columns"]] == ["SKU", "Lot"]


def test_unnamed_columns_get_generic_labels():
    data = build_xlsx([
        ["SKU", None, "Qte"],
        [1349, "x", 10],
    ])
    out = templates.detect_columns(data)
    assert out["columns"][1]["name"] == "Colonne 2"


def test_empty_file_raises():
    with pytest.raises(ValueError):
        templates.detect_columns(build_xlsx([]))
