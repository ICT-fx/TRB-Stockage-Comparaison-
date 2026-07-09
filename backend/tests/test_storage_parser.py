import main
import templates
from tests.helpers import build_xlsx


def _rk_file():
    # Format RK de référence : 1re ligne vide, en-tête ligne 2.
    return build_xlsx([
        [],
        ["Artikel", "Lagerort", "G", "Kurztext", "Bestand", "Einheit"],
        [1349, 462994, "2028-07", "Produit X", 10, "ST"],
        [687, 412561, "2028-07", "Produit Y", 5, "ST"],
    ])


def test_builtin_template_matches_parse_rk_lot():
    data = _rk_file()
    legacy, _ = main.parse_rk_lot(data)
    generic, _ = main.parse_storage_with_template(data, templates.BUILTIN_TEMPLATE)
    assert generic == legacy


def test_reordered_columns_with_extras():
    # Colonnes dans un autre ordre + colonnes en trop à ignorer.
    # Ordre: [interne, Qte, SKU, Lot, Date, Desc]
    data = build_xlsx([
        ["Interne", "Qte", "SKU", "Lot", "Date", "Desc"],
        ["zzz", 7, 1349, 462994, "2028-07", "Produit X"],
    ])
    tpl = {"header_row": 1,
           "columns": {"sku": 2, "lot": 3, "qty": 1, "date": 4, "description": 5}}
    products, _ = main.parse_storage_with_template(data, tpl)
    assert products == [{"code": "1349", "lot": "462994",
                         "date": "01.07.2028", "qty": 7, "description": "Produit X"}]


def test_optional_fields_unmapped():
    data = build_xlsx([
        ["SKU", "Lot", "Qte"],
        [1349, 462994, 10],
    ])
    tpl = {"header_row": 1,
           "columns": {"sku": 0, "lot": 1, "qty": 2, "date": None, "description": None}}
    products, _ = main.parse_storage_with_template(data, tpl)
    assert products == [{"code": "1349", "lot": "462994",
                         "date": "", "qty": 10, "description": ""}]


def test_out_of_range_column_raises():
    data = build_xlsx([
        ["SKU", "Lot", "Qte"],
        [1349, 462994, 10],
    ])
    tpl = {"header_row": 1,
           "columns": {"sku": 0, "lot": 1, "qty": 9, "date": None, "description": None}}
    try:
        main.parse_storage_with_template(data, tpl)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "colonnes" in str(e)
