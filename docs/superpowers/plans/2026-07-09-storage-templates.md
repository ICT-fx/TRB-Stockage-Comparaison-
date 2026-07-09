# Storage Column Templates — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user create, name, edit, delete and persist custom column-mapping templates for the storage (réel) Excel file, managed entirely in the app.

**Architecture:** A new `backend/templates.py` module owns the template model, the built-in default, `%APPDATA%` persistence, and column detection from a sample file. `backend/main.py` gains a generic template-driven storage parser and CRUD + preview routes; `/compare` takes a `storage_template_id`. The frontend populates the storage dropdown from the API and adds a guided "new template" modal. No template data is bundled in the `.exe`; everything lives in `%APPDATA%`.

**Tech Stack:** Python 3.11, FastAPI, pandas, openpyxl, pydantic (backend); vanilla HTML/CSS/JS (frontend); PyInstaller (packaging); pytest + httpx (tests).

## Global Constraints

- Python **3.11.9**; runtime deps pinned in `backend/requirements.txt` (do NOT add runtime deps for this feature).
- Test-only deps go in `backend/requirements-dev.txt` (never bundled in the `.exe`).
- Persistence dir: Windows `%APPDATA%\TRB-Comparaison-Stock\`, else `~/.trb-comparaison-stock/`. **Never** use `sys._MEIPASS`. Honor `TRB_DATA_DIR` env override (for tests).
- The built-in template id is **`basic-stock`**, non-deletable / non-editable, hard-coded in the backend (not in the JSON file).
- 5 fields: `sku`, `lot`, `qty` (required), `date`, `description` (optional). Column indices are **0-based**; `header_row` is **1-based**.
- Comparison logic (`compare_by_lot`, by SKU + lot) is unchanged. Proconcept parsing is unchanged.
- All user-facing strings in French, matching existing UI tone.
- Frontend: vanilla JS, no new dependencies, dark TRB theme (`#004B87`).
- Run backend tests with: `cd backend && python -m pytest -v`.

---

## File Structure

**Create:**
- `backend/templates.py` — template model, built-in default, persistence, validation, column detection.
- `backend/conftest.py` — puts `backend/` on `sys.path` for tests.
- `backend/requirements-dev.txt` — `pytest`, `httpx`.
- `backend/tests/test_template_store.py` — persistence + model + validation tests.
- `backend/tests/test_detect_columns.py` — sample-file column detection tests.
- `backend/tests/test_storage_parser.py` — generic parser + regression vs `parse_rk_lot`.
- `backend/tests/test_api_templates.py` — CRUD + preview + `/compare` API tests.
- `backend/tests/helpers.py` — shared xlsx builders for tests.

**Modify:**
- `backend/main.py` — generic parser, `_run_comparison` signature, `/compare` + `/compare/download`, new routes.
- `frontend/index.html` — storage template controls + modal markup.
- `frontend/style.css` — modal + mapping styles.
- `frontend/app.js` — fetch/populate templates, modal create/edit/delete, pass `storage_template_id`, remember last selection.
- `windows/trb_stock.spec` — add `templates` to `hiddenimports`.

---

## Task 1: Test harness + data dir + store round-trip

**Files:**
- Create: `backend/conftest.py`, `backend/requirements-dev.txt`, `backend/tests/helpers.py`, `backend/tests/test_template_store.py`
- Create: `backend/templates.py`

**Interfaces:**
- Produces: `data_dir() -> str`, `templates_path() -> str`, `load_user_templates() -> list[dict]`, `save_user_templates(list[dict]) -> None`

- [ ] **Step 1: Create dev deps + conftest**

`backend/requirements-dev.txt`:
```
pytest==8.3.4
httpx==0.28.1
```

`backend/conftest.py`:
```python
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
```

`backend/tests/helpers.py`:
```python
"""Shared helpers to build in-memory .xlsx files for tests."""
import io
from openpyxl import Workbook


def build_xlsx(rows: list[list]) -> bytes:
    """Build an .xlsx from a list of rows (each row a list of cell values)."""
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 2: Write the failing test**

`backend/tests/test_template_store.py`:
```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_template_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'templates'` (or attribute errors).

- [ ] **Step 4: Create `backend/templates.py` (partial — store layer)**

```python
"""
Modèle, persistance et détection de colonnes pour les templates de l'espace
de stockage. Persistance dans %APPDATA% (Windows) — jamais dans le bundle .exe.
"""
import io
import json
import os
import uuid

import pandas as pd

FIELD_KEYS = ["sku", "lot", "date", "description", "qty"]
REQUIRED_FIELDS = ["sku", "lot", "qty"]
OPTIONAL_FIELDS = ["date", "description"]

BUILTIN_TEMPLATE = {
    "id": "basic-stock",
    "name": "Basic template stock",
    "builtin": True,
    "header_row": 2,
    "columns": {"sku": 0, "lot": 1, "date": 2, "description": 3, "qty": 4},
}


def data_dir() -> str:
    override = os.environ.get("TRB_DATA_DIR")
    if override:
        return override
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "TRB-Comparaison-Stock")
    return os.path.join(os.path.expanduser("~"), ".trb-comparaison-stock")


def templates_path() -> str:
    return os.path.join(data_dir(), "templates.json")


def load_user_templates() -> list[dict]:
    path = templates_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        tpls = data.get("templates", [])
        return tpls if isinstance(tpls, list) else []
    except Exception:
        return []  # corrompu -> traité comme vide


def save_user_templates(tpls: list[dict]) -> None:
    d = data_dir()
    os.makedirs(d, exist_ok=True)
    path = templates_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"templates": tpls}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_template_store.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/templates.py backend/conftest.py backend/requirements-dev.txt backend/tests/helpers.py backend/tests/test_template_store.py
git commit -m "feat(templates): store layer with %APPDATA% persistence + tests"
```

---

## Task 2: Built-in template, lookup, validation

**Files:**
- Modify: `backend/templates.py`
- Modify: `backend/tests/test_template_store.py`

**Interfaces:**
- Consumes: `BUILTIN_TEMPLATE`, `load_user_templates`, `save_user_templates`
- Produces: `all_templates() -> list[dict]`, `get_template(id) -> dict | None`, `validate_template(payload) -> dict`

- [ ] **Step 1: Write the failing test (append)**

Append to `backend/tests/test_template_store.py`:
```python
import pytest


def test_all_templates_includes_builtin_first(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    tpls = templates.all_templates()
    assert tpls[0]["id"] == "basic-stock"
    assert tpls[0]["builtin"] is True


def test_get_template_builtin_and_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("TRB_DATA_DIR", str(tmp_path))
    assert templates.get_template("basic-stock")["name"] == "Basic template stock"
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_template_store.py -v`
Expected: FAIL — `AttributeError: module 'templates' has no attribute 'all_templates'`.

- [ ] **Step 3: Implement (append to `backend/templates.py`)**

```python
def all_templates() -> list[dict]:
    return [BUILTIN_TEMPLATE] + load_user_templates()


def get_template(template_id: str) -> dict | None:
    for t in all_templates():
        if t.get("id") == template_id:
            return t
    return None


def validate_template(payload: dict) -> dict:
    """Valide + normalise un template entrant. Lève ValueError sinon."""
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Le nom du template est obligatoire.")

    header_row = payload.get("header_row", 1)
    if not isinstance(header_row, int) or isinstance(header_row, bool) or header_row < 1:
        raise ValueError("La ligne d'en-tête doit être un entier supérieur ou égal à 1.")

    cols = payload.get("columns", {}) or {}
    norm: dict = {}
    for key in REQUIRED_FIELDS:
        val = cols.get(key)
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            raise ValueError(f"Le champ « {key} » est obligatoire et doit désigner une colonne.")
        norm[key] = val
    for key in OPTIONAL_FIELDS:
        val = cols.get(key)
        norm[key] = val if (isinstance(val, int) and not isinstance(val, bool) and val >= 0) else None

    req_vals = [norm[k] for k in REQUIRED_FIELDS]
    if len(set(req_vals)) != len(req_vals):
        raise ValueError("SKU, N° de lot et Quantité doivent être sur des colonnes différentes.")

    return {"name": name, "header_row": header_row, "columns": norm}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_template_store.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/templates.py backend/tests/test_template_store.py
git commit -m "feat(templates): built-in default, lookup, validation"
```

---

## Task 3: Create / update / delete (with built-in protection)

**Files:**
- Modify: `backend/templates.py`
- Modify: `backend/tests/test_template_store.py`

**Interfaces:**
- Consumes: `validate_template`, `load_user_templates`, `save_user_templates`, `BUILTIN_TEMPLATE`
- Produces: `create_template(payload) -> dict`, `update_template(id, payload) -> dict` (raises `KeyError` if missing, `ValueError` if built-in), `delete_template(id) -> None` (same)

- [ ] **Step 1: Write the failing test (append)**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_template_store.py -v`
Expected: FAIL — `AttributeError: module 'templates' has no attribute 'create_template'`.

- [ ] **Step 3: Implement (append to `backend/templates.py`)**

```python
def create_template(payload: dict) -> dict:
    norm = validate_template(payload)
    tpl = {"id": uuid.uuid4().hex[:8], "builtin": False, **norm}
    tpls = load_user_templates()
    tpls.append(tpl)
    save_user_templates(tpls)
    return tpl


def update_template(template_id: str, payload: dict) -> dict:
    if template_id == BUILTIN_TEMPLATE["id"]:
        raise ValueError("Le template intégré ne peut pas être modifié.")
    norm = validate_template(payload)
    tpls = load_user_templates()
    for i, t in enumerate(tpls):
        if t.get("id") == template_id:
            tpls[i] = {"id": template_id, "builtin": False, **norm}
            save_user_templates(tpls)
            return tpls[i]
    raise KeyError(template_id)


def delete_template(template_id: str) -> None:
    if template_id == BUILTIN_TEMPLATE["id"]:
        raise ValueError("Le template intégré ne peut pas être supprimé.")
    tpls = load_user_templates()
    new = [t for t in tpls if t.get("id") != template_id]
    if len(new) == len(tpls):
        raise KeyError(template_id)
    save_user_templates(new)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_template_store.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/templates.py backend/tests/test_template_store.py
git commit -m "feat(templates): create/update/delete with built-in protection"
```

---

## Task 4: Column detection from a sample file

**Files:**
- Modify: `backend/templates.py`
- Create: `backend/tests/test_detect_columns.py`

**Interfaces:**
- Consumes: `pandas`
- Produces: `detect_columns(raw_bytes: bytes, header_row: int | None = None) -> dict` returning `{"header_row": int, "columns": [{"index": int, "name": str, "samples": [str]}]}`. Raises `ValueError` on empty/unreadable input.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_detect_columns.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_detect_columns.py -v`
Expected: FAIL — `AttributeError: module 'templates' has no attribute 'detect_columns'`.

- [ ] **Step 3: Implement (append to `backend/templates.py`)**

```python
def detect_columns(raw_bytes: bytes, header_row: int | None = None) -> dict:
    """Détecte la ligne d'en-tête + décrit chaque colonne d'un fichier exemple."""
    raw = pd.read_excel(io.BytesIO(raw_bytes), header=None)
    if raw.empty:
        raise ValueError("Fichier illisible ou vide.")

    if header_row is None:
        header_row = 1
        for idx in range(len(raw)):
            if raw.iloc[idx].notna().any():
                header_row = idx + 1
                break

    df = pd.read_excel(io.BytesIO(raw_bytes), header=header_row - 1)
    columns = []
    for i, col in enumerate(df.columns):
        label = str(col)
        if label.startswith("Unnamed"):
            label = f"Colonne {i + 1}"
        samples = [str(v) for v in df.iloc[:, i].dropna().head(3).tolist()]
        columns.append({"index": i, "name": label, "samples": samples})
    return {"header_row": header_row, "columns": columns}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_detect_columns.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/templates.py backend/tests/test_detect_columns.py
git commit -m "feat(templates): detect_columns with header auto-detection"
```

---

## Task 5: Generic template-driven storage parser (+ regression)

**Files:**
- Modify: `backend/main.py` (add `parse_storage_with_template`; change `_run_comparison` at lines ~403-408)
- Create: `backend/tests/test_storage_parser.py`

**Interfaces:**
- Consumes: `_is_numeric_code`, `_clean_code`, `_clean_lot`, `_parse_rk_date` (existing in main.py); `parse_rk_lot` (existing, kept for regression)
- Produces: `parse_storage_with_template(raw_bytes: bytes, template: dict) -> tuple[list[dict], pd.DataFrame]`; `_run_comparison(theo_bytes, real_bytes, storage_template) -> tuple[dict, DataFrame, DataFrame]`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_storage_parser.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_storage_parser.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'parse_storage_with_template'`.

- [ ] **Step 3: Implement in `backend/main.py`**

Add this function directly after `parse_rk_lot` (after line 205):
```python
def parse_storage_with_template(raw_bytes: bytes, template: dict) -> tuple[list[dict], pd.DataFrame]:
    """
    Parse un fichier d'espace de stockage selon un template de colonnes.
    template = {"header_row": int(1-based), "columns": {sku,lot,qty,date,description}}
    (date/description peuvent être None). Renvoie la même structure que parse_rk_lot.
    """
    cols = template["columns"]
    header_row = int(template.get("header_row", 1))
    df = pd.read_excel(io.BytesIO(raw_bytes), header=header_row - 1)

    used = [cols["sku"], cols["lot"], cols["qty"]]
    used += [cols[k] for k in ("date", "description") if cols.get(k) is not None]
    max_idx = max(used)
    if len(df.columns) <= max_idx:
        raise ValueError(
            f"Le fichier n'a que {len(df.columns)} colonnes, "
            f"le template en attend au moins {max_idx + 1}."
        )

    products: list[dict] = []
    for _, row in df.iterrows():
        code_raw = row.iloc[cols["sku"]]
        if not _is_numeric_code(code_raw):
            continue
        lot = _clean_lot(row.iloc[cols["lot"]])
        if not lot:
            continue
        code = _clean_code(code_raw)
        qty_cell = row.iloc[cols["qty"]]
        qty = int(qty_cell) if pd.notna(qty_cell) else 0

        date_str = ""
        if cols.get("date") is not None:
            date_str = _parse_rk_date(row.iloc[cols["date"]])

        desc = ""
        if cols.get("description") is not None:
            dv = row.iloc[cols["description"]]
            desc = str(dv).strip() if pd.notna(dv) else ""

        products.append({
            "code": code, "lot": lot, "date": date_str,
            "qty": qty, "description": desc,
        })

    return products, df
```

Then change `_run_comparison` (currently lines ~403-408) to:
```python
def _run_comparison(theo_bytes: bytes, real_bytes: bytes, storage_template: dict) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Parse both files and run lot-based comparison. Returns (result, df_pro, df_rk)."""
    theo_list, df_pro = parse_proconcept_lot(theo_bytes)
    actual_list, df_rk = parse_storage_with_template(real_bytes, storage_template)
    result = compare_by_lot(theo_list, actual_list)
    return result, df_pro, df_rk
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_storage_parser.py -v`
Expected: PASS (4 passed). NOTE: `/compare` routes still call the old `_run_comparison` signature — they are fixed in Task 7; do not run the full suite yet.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_storage_parser.py
git commit -m "feat(parser): generic template-driven storage parser + regression test"
```

---

## Task 6: Template CRUD + preview API routes

**Files:**
- Modify: `backend/main.py` (imports near top; new routes before `/health` at line ~455)
- Create: `backend/tests/test_api_templates.py`

**Interfaces:**
- Consumes: `templates.all_templates/get_template/create_template/update_template/delete_template/detect_columns`
- Produces routes: `GET /templates`, `POST /templates`, `PUT /templates/{id}`, `DELETE /templates/{id}`, `POST /templates/preview`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_api_templates.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api_templates.py -v`
Expected: FAIL — 404 on `/templates` (routes not defined).

- [ ] **Step 3: Implement in `backend/main.py`**

Add near the top imports (after line 18):
```python
import templates as template_store
```

Add these routes immediately before the `@app.get("/health")` route (line ~455):
```python
# ──────────────────────────────────────────────
# Templates d'espace de stockage
# ──────────────────────────────────────────────

@app.get("/templates")
async def list_templates():
    return {"templates": template_store.all_templates()}


@app.post("/templates")
async def create_template_route(payload: dict):
    try:
        return template_store.create_template(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/templates/{template_id}")
async def update_template_route(template_id: str, payload: dict):
    try:
        return template_store.update_template(template_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="Template introuvable.")


@app.delete("/templates/{template_id}")
async def delete_template_route(template_id: str):
    try:
        template_store.delete_template(template_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="Template introuvable.")


@app.post("/templates/preview")
async def preview_template(file: UploadFile = File(...), header_row: int | None = Form(None)):
    try:
        raw = await file.read()
        return template_store.detect_columns(raw, header_row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fichier illisible : {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_api_templates.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_api_templates.py
git commit -m "feat(api): template CRUD + preview routes"
```

---

## Task 7: Wire `storage_template_id` into `/compare` + `/compare/download`

**Files:**
- Modify: `backend/main.py` (`/compare` lines ~415-429, `/compare/download` lines ~432-452)
- Modify: `backend/tests/test_api_templates.py`

**Interfaces:**
- Consumes: `template_store.get_template`, `parse_storage_with_template`, `_run_comparison(theo, real, storage_template)`
- Produces: `/compare` and `/compare/download` accept `storage_template_id: str = Form("basic-stock")`

- [ ] **Step 1: Write the failing test (append to `test_api_templates.py`)**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api_templates.py -v`
Expected: FAIL — `_run_comparison()` missing `storage_template` arg / 422 on unexpected form field.

- [ ] **Step 3: Implement in `backend/main.py`**

Replace the `/compare` route (lines ~415-429) with:
```python
@app.post("/compare")
async def compare(
    file_theorique: UploadFile = File(...),
    file_reel: UploadFile = File(...),
    storage_template_id: str = Form("basic-stock"),
):
    """Compare two Excel files and return JSON results."""
    tpl = template_store.get_template(storage_template_id)
    if tpl is None:
        raise HTTPException(status_code=400, detail=f"Template introuvable : {storage_template_id}")
    try:
        theo_bytes = await file_theorique.read()
        real_bytes = await file_reel.read()
        result, _, _ = _run_comparison(theo_bytes, real_bytes, tpl)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors du traitement : {str(e)}")
```

Replace the `/compare/download` route (lines ~432-452) with:
```python
@app.post("/compare/download")
async def compare_download(
    file_theorique: UploadFile = File(...),
    file_reel: UploadFile = File(...),
    storage_template_id: str = Form("basic-stock"),
):
    """Compare two Excel files and return an Excel report with raw data sheets."""
    tpl = template_store.get_template(storage_template_id)
    if tpl is None:
        raise HTTPException(status_code=400, detail=f"Template introuvable : {storage_template_id}")
    try:
        theo_bytes = await file_theorique.read()
        real_bytes = await file_reel.read()
        result, df_pro, df_rk = _run_comparison(theo_bytes, real_bytes, tpl)
        excel_bytes = build_excel(result, df_pro, df_rk)

        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=comparaison_stock.xlsx"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors du traitement : {str(e)}")
```

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS (all tests across all files).

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_api_templates.py
git commit -m "feat(api): storage_template_id on /compare + /compare/download"
```

---

## Task 8: Bundle `templates.py` in the PyInstaller build

**Files:**
- Modify: `windows/trb_stock.spec` (hiddenimports list, after the `"main",` entry)

**Interfaces:**
- Consumes: nothing new
- Produces: `templates` module bundled in the `.exe`

- [ ] **Step 1: Edit the spec**

In `windows/trb_stock.spec`, find:
```python
    "main",  # backend/main.py, importé par launcher.py
]
```
Replace with:
```python
    "main",       # backend/main.py, importé par launcher.py
    "templates",  # backend/templates.py, importé par main.py
]
```

- [ ] **Step 2: Verify the source app still boots with templates**

Run:
```bash
cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock"
python -c "import sys; sys.path.insert(0,'backend'); import main; print([r.path for r in main.app.routes if hasattr(r,'path')])"
```
Expected: output includes `/templates`, `/templates/preview`, `/compare`.

- [ ] **Step 3: Commit**

```bash
git add windows/trb_stock.spec
git commit -m "build(windows): bundle templates module in the exe"
```

---

## Task 9: Frontend — storage template controls + modal markup

**Files:**
- Modify: `frontend/index.html` (replace the réel `layout-selector` block, lines ~70-75; add modal before `<script>` at line ~129)

**Interfaces:**
- Produces DOM ids consumed by app.js: `layout-reel`, `btn-template-new`, `btn-template-edit`, `btn-template-delete`, `template-modal`, `tpl-file-input`, `tpl-drop`, `tpl-file-name`, `tpl-header-row`, `tpl-mapping`, `tpl-name`, `tpl-save`, `tpl-cancel`, `tpl-error`, `tpl-modal-title`

- [ ] **Step 1: Replace the storage layout selector**

In `frontend/index.html`, replace this block (lines ~70-75):
```html
                        <div class="layout-selector">
                            <label for="layout-reel">Mise en page :</label>
                            <select id="layout-reel" class="layout-select">
                                <option value="rk_nouveau_template">Basic template stock</option>
                            </select>
                        </div>
```
with:
```html
                        <div class="layout-selector">
                            <label for="layout-reel">Template de colonnes :</label>
                            <select id="layout-reel" class="layout-select"></select>
                            <div class="template-actions">
                                <button type="button" id="btn-template-edit" class="tpl-btn" title="Modifier le template">✎</button>
                                <button type="button" id="btn-template-delete" class="tpl-btn" title="Supprimer le template">🗑</button>
                                <button type="button" id="btn-template-new" class="tpl-btn tpl-btn-new" title="Nouveau template">＋ Nouveau</button>
                            </div>
                        </div>
```

- [ ] **Step 2: Add the modal markup**

In `frontend/index.html`, immediately before `<script src="app.js"></script>` (line ~129), add:
```html
    <!-- Modale : création / modification de template -->
    <div id="template-modal" class="modal-overlay hidden">
        <div class="modal-card glass-card">
            <h2 class="modal-title" id="tpl-modal-title">Nouveau template</h2>

            <div class="tpl-step">
                <p class="tpl-step-label">1. Dépose un fichier exemple de ton espace de stockage :</p>
                <div class="tpl-drop" id="tpl-drop">
                    <label class="upload-btn" for="tpl-file-input">Choisir un fichier</label>
                    <input type="file" id="tpl-file-input" accept=".xlsx,.xls" hidden>
                    <span class="file-name" id="tpl-file-name">Aucun fichier</span>
                </div>
            </div>

            <div class="tpl-step">
                <label class="tpl-step-label" for="tpl-header-row">En-tête sur la ligne :</label>
                <input type="number" id="tpl-header-row" class="tpl-header-input" min="1" value="1" disabled>
            </div>

            <div class="tpl-step">
                <p class="tpl-step-label">2. Associe chaque champ à sa colonne :</p>
                <div id="tpl-mapping" class="tpl-mapping"></div>
            </div>

            <div class="tpl-step">
                <label class="tpl-step-label" for="tpl-name">Nom du template :</label>
                <input type="text" id="tpl-name" class="tpl-name-input" placeholder="Ex : Stock Partenaire X">
            </div>

            <div id="tpl-error" class="error-banner hidden"></div>

            <div class="modal-actions">
                <button type="button" id="tpl-cancel" class="btn-cancel">Annuler</button>
                <button type="button" id="tpl-save" class="btn-primary" disabled>Enregistrer</button>
            </div>
        </div>
    </div>

```

- [ ] **Step 3: Verify markup loads (no JS yet)**

Run:
```bash
cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock/frontend" && python3 -c "import re,sys; h=open('index.html').read(); [sys.exit('MISSING '+i) for i in ['template-modal','tpl-mapping','btn-template-new','layout-reel'] if i not in h]; print('all ids present')"
```
Expected: `all ids present`.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat(ui): storage template selector controls + modal markup"
```

---

## Task 10: Frontend — modal + mapping styles

**Files:**
- Modify: `frontend/style.css` (append at end of file)

**Interfaces:**
- Produces CSS classes used by the markup: `.modal-overlay`, `.modal-card`, `.template-actions`, `.tpl-btn`, `.tpl-mapping`, etc.

- [ ] **Step 1: Append styles**

Append to `frontend/style.css`:
```css
/* ── Template controls ─────────────────────────── */
.template-actions {
    display: flex;
    gap: 6px;
    margin-top: 8px;
    justify-content: center;
    flex-wrap: wrap;
}
.tpl-btn {
    background: rgba(255, 255, 255, 0.08);
    color: #cbd5e1;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 0.85rem;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
}
.tpl-btn:hover:not(:disabled) { background: rgba(255, 255, 255, 0.16); color: #fff; }
.tpl-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.tpl-btn-new { color: #4da3ff; border-color: rgba(77, 163, 255, 0.4); }

/* ── Modal ─────────────────────────────────────── */
.modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 20px;
}
.modal-overlay.hidden { display: none; }
.modal-card {
    width: 100%;
    max-width: 520px;
    max-height: 90vh;
    overflow-y: auto;
    padding: 28px;
    border-radius: 14px;
}
.modal-title { margin: 0 0 18px; font-size: 1.3rem; color: #fff; }
.tpl-step { margin-bottom: 18px; }
.tpl-step-label { font-size: 0.9rem; color: #cbd5e1; margin: 0 0 8px; display: block; }
.tpl-drop {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}
.tpl-header-input {
    width: 80px;
    padding: 6px 8px;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.06);
    color: #fff;
}
.tpl-mapping { display: flex; flex-direction: column; gap: 10px; }
.tpl-map-row {
    display: grid;
    grid-template-columns: 130px 1fr;
    align-items: center;
    gap: 10px;
}
.tpl-map-row label { font-size: 0.88rem; color: #e2e8f0; }
.tpl-map-row select {
    padding: 7px 8px;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.06);
    color: #fff;
    width: 100%;
}
.tpl-name-input {
    width: 100%;
    padding: 9px 10px;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.06);
    color: #fff;
}
.modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 22px;
}
.btn-cancel {
    background: transparent;
    color: #cbd5e1;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 8px;
    padding: 10px 18px;
    cursor: pointer;
}
.btn-cancel:hover { background: rgba(255, 255, 255, 0.08); }
.modal-actions .btn-primary { width: auto; padding: 10px 20px; margin: 0; }
```

- [ ] **Step 2: Verify CSS parses (no syntax errors)**

Run:
```bash
cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock/frontend" && python3 -c "c=open('style.css').read(); assert c.count('{')==c.count('}'), 'brace mismatch'; print('braces balanced:', c.count('{'))"
```
Expected: `braces balanced: N`.

- [ ] **Step 3: Commit**

```bash
git add frontend/style.css
git commit -m "feat(ui): modal + mapping styles"
```

---

## Task 11: Frontend — load templates, populate select, pass id, remember choice

**Files:**
- Modify: `frontend/app.js` (config section ~line 9; add template module logic; extend compare + download bodies)

**Interfaces:**
- Consumes: `GET /templates`; DOM ids from Task 9
- Produces: `state.templates`, `refreshTemplates()`, `selectedTemplateId()`; both fetches send `storage_template_id`

- [ ] **Step 1: Add template state + loader (after line 38, `let lastResult = null;`)**

```javascript
// ── Templates (espace de stockage) ──────────────
// NOTE : `layoutReel` est DÉJÀ déclaré plus haut dans app.js (ligne ~29,
// `const layoutReel = document.getElementById("layout-reel")`). Ne pas le
// re-déclarer ici (sinon SyntaxError : redéclaration de const).
const btnTemplateNew   = document.getElementById("btn-template-new");
const btnTemplateEdit  = document.getElementById("btn-template-edit");
const btnTemplateDel   = document.getElementById("btn-template-delete");
const LAST_TPL_KEY = "trb_last_template";

const tplState = { list: [] };

function selectedTemplateId() {
    return layoutReel.value || "basic-stock";
}

async function refreshTemplates(selectId) {
    try {
        const res = await fetch(`${API_BASE}/templates`);
        const data = await res.json();
        tplState.list = data.templates || [];
    } catch {
        tplState.list = [{ id: "basic-stock", name: "Basic template stock", builtin: true }];
    }
    const remembered = selectId || localStorage.getItem(LAST_TPL_KEY) || "basic-stock";
    const exists = tplState.list.some(t => t.id === remembered);
    const target = exists ? remembered : "basic-stock";

    layoutReel.innerHTML = tplState.list
        .map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`)
        .join("");
    layoutReel.value = target;
    onTemplateSelectionChange();
}

function currentTemplate() {
    return tplState.list.find(t => t.id === selectedTemplateId());
}

function onTemplateSelectionChange() {
    const t = currentTemplate();
    const isBuiltin = !t || t.builtin;
    btnTemplateEdit.disabled = isBuiltin;
    btnTemplateDel.disabled = isBuiltin;
    localStorage.setItem(LAST_TPL_KEY, selectedTemplateId());
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

layoutReel.addEventListener("change", onTemplateSelectionChange);
refreshTemplates();
```

- [ ] **Step 2: Send `storage_template_id` in compare**

In the compare handler, find:
```javascript
        const formData = new FormData();
        formData.append("file_theorique", fileTheorique);
        formData.append("file_reel", fileReel);

        const res = await fetch(`${API_BASE}/compare`, {
```
Replace the `formData` lines (the first three) with:
```javascript
        const formData = new FormData();
        formData.append("file_theorique", fileTheorique);
        formData.append("file_reel", fileReel);
        formData.append("storage_template_id", selectedTemplateId());
```

- [ ] **Step 3: Send `storage_template_id` in download**

In the download handler, find the second occurrence of:
```javascript
        const formData = new FormData();
        formData.append("file_theorique", fileTheorique);
        formData.append("file_reel", fileReel);

        const res = await fetch(`${API_BASE}/compare/download`, {
```
Replace the first three `formData` lines with:
```javascript
        const formData = new FormData();
        formData.append("file_theorique", fileTheorique);
        formData.append("file_reel", fileReel);
        formData.append("storage_template_id", selectedTemplateId());
```

- [ ] **Step 4: Verify JS parses**

Run:
```bash
cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock/frontend" && node --check app.js && echo "app.js OK"
```
Expected: `app.js OK`.

- [ ] **Step 5: Commit**

```bash
git add frontend/app.js
git commit -m "feat(ui): load templates, populate select, send storage_template_id, remember choice"
```

---

## Task 12: Frontend — modal create flow (preview + mapping + save)

**Files:**
- Modify: `frontend/app.js` (append modal logic at end of file)

**Interfaces:**
- Consumes: `POST /templates/preview`, `POST /templates`; DOM modal ids; `refreshTemplates`, `escapeHtml`, `tplState`
- Produces: `openTemplateModal(template?)` used by Task 13

- [ ] **Step 1: Append modal logic to `frontend/app.js`**

```javascript
// ── Modale template ─────────────────────────────
const modal          = document.getElementById("template-modal");
const modalTitle     = document.getElementById("tpl-modal-title");
const tplFileInput   = document.getElementById("tpl-file-input");
const tplDrop        = document.getElementById("tpl-drop");
const tplFileName    = document.getElementById("tpl-file-name");
const tplHeaderRow   = document.getElementById("tpl-header-row");
const tplMapping     = document.getElementById("tpl-mapping");
const tplName        = document.getElementById("tpl-name");
const tplSave        = document.getElementById("tpl-save");
const tplCancel      = document.getElementById("tpl-cancel");
const tplError       = document.getElementById("tpl-error");

const FIELDS = [
    { key: "sku",         label: "SKU",             required: true },
    { key: "lot",         label: "N° de lot",       required: true },
    { key: "date",        label: "Date d'expir.",   required: false },
    { key: "description", label: "Description",     required: false },
    { key: "qty",         label: "Quantité",        required: true },
];

const GUESS = {
    sku: ["sku", "artikel", "référence", "reference", "code", "ref"],
    lot: ["lot", "lagerort", "charge", "batch"],
    date: ["date", "exp", "mhd", "verfall", "péremption", "peremption", "g"],
    description: ["desc", "kurztext", "bezeichnung", "libellé", "libelle", "désignation", "designation", "produit"],
    qty: ["qte", "qté", "quantité", "quantite", "menge", "bestand", "stock", "qty"],
};

let modalState = { columns: [], fileBytes: null, editId: null, lastFile: null };

function guessColumn(fieldKey, columns) {
    const kws = GUESS[fieldKey] || [];
    for (const col of columns) {
        const n = String(col.name).toLowerCase();
        if (kws.some(k => n.includes(k))) return col.index;
    }
    return null;
}

function renderMapping(columns, preset) {
    modalState.columns = columns;
    const optionsFor = (allowNone) => {
        let opts = allowNone ? `<option value="">— aucune —</option>` : "";
        opts += columns.map(c => {
            const ex = c.samples && c.samples.length ? ` (ex: ${escapeHtml(c.samples[0])})` : "";
            return `<option value="${c.index}">${escapeHtml(c.name)}${ex}</option>`;
        }).join("");
        return opts;
    };
    tplMapping.innerHTML = FIELDS.map(f => `
        <div class="tpl-map-row">
            <label for="map-${f.key}">${f.label}${f.required ? " *" : ""}</label>
            <select id="map-${f.key}" data-field="${f.key}">${optionsFor(!f.required)}</select>
        </div>`).join("");

    FIELDS.forEach(f => {
        const sel = document.getElementById(`map-${f.key}`);
        let val = preset && preset.columns && preset.columns[f.key];
        if (val === undefined || val === null) {
            const g = guessColumn(f.key, columns);
            val = g === null ? "" : g;
        }
        sel.value = val === null ? "" : String(val);
    });
    validateModal();
}

function validateModal() {
    const named = tplName.value.trim().length > 0;
    const hasCols = modalState.columns.length > 0;
    tplSave.disabled = !(named && hasCols);
}

async function previewFile(file, headerRow) {
    tplError.classList.add("hidden");
    const fd = new FormData();
    fd.append("file", file);
    if (headerRow) fd.append("header_row", String(headerRow));
    const res = await fetch(`${API_BASE}/templates/preview`, { method: "POST", body: fd });
    if (!res.ok) {
        const e = await res.json().catch(() => ({ detail: "Erreur" }));
        throw new Error(e.detail || "Fichier illisible");
    }
    return res.json();
}

async function handleTemplateFile(file, preset) {
    if (!file) return;
    modalState.lastFile = file;
    tplFileName.textContent = file.name;
    try {
        const data = await previewFile(file, null);
        tplHeaderRow.disabled = false;
        tplHeaderRow.value = data.header_row;
        renderMapping(data.columns, preset);
    } catch (err) {
        tplError.textContent = err.message;
        tplError.classList.remove("hidden");
    }
}

tplFileInput.addEventListener("change", e => handleTemplateFile(e.target.files[0], null));

tplDrop.addEventListener("dragover", e => { e.preventDefault(); tplDrop.classList.add("dragover"); });
tplDrop.addEventListener("dragleave", () => tplDrop.classList.remove("dragover"));
tplDrop.addEventListener("drop", e => {
    e.preventDefault(); tplDrop.classList.remove("dragover");
    if (e.dataTransfer.files[0]) handleTemplateFile(e.dataTransfer.files[0], null);
});

tplHeaderRow.addEventListener("change", async () => {
    if (!modalState.lastFile) return;
    try {
        const data = await previewFile(modalState.lastFile, parseInt(tplHeaderRow.value, 10));
        renderMapping(data.columns, null);
    } catch (err) {
        tplError.textContent = err.message;
        tplError.classList.remove("hidden");
    }
});

tplName.addEventListener("input", validateModal);

function collectColumns() {
    const cols = {};
    FIELDS.forEach(f => {
        const v = document.getElementById(`map-${f.key}`).value;
        cols[f.key] = v === "" ? null : parseInt(v, 10);
    });
    return cols;
}

async function saveTemplate() {
    tplError.classList.add("hidden");
    const payload = {
        name: tplName.value.trim(),
        header_row: parseInt(tplHeaderRow.value, 10) || 1,
        columns: collectColumns(),
    };
    const editing = modalState.editId;
    const url = editing ? `${API_BASE}/templates/${editing}` : `${API_BASE}/templates`;
    const method = editing ? "PUT" : "POST";
    try {
        const res = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            const e = await res.json().catch(() => ({ detail: "Erreur" }));
            throw new Error(e.detail || "Enregistrement impossible");
        }
        const saved = await res.json();
        closeTemplateModal();
        await refreshTemplates(saved.id);
    } catch (err) {
        tplError.textContent = err.message;
        tplError.classList.remove("hidden");
    }
}

function openTemplateModal(template) {
    modalState = { columns: [], fileBytes: null, editId: template ? template.id : null, lastFile: null };
    modalTitle.textContent = template ? "Modifier le template" : "Nouveau template";
    tplName.value = template ? template.name : "";
    tplFileName.textContent = "Aucun fichier";
    tplError.classList.add("hidden");
    tplSave.disabled = true;
    if (template) {
        // Pré-remplir sans fichier : colonnes génériques jusqu'à l'indice max connu.
        const maxIdx = Math.max(...Object.values(template.columns).filter(v => v !== null), 0);
        const cols = Array.from({ length: maxIdx + 1 }, (_, i) => ({ index: i, name: `Colonne ${i + 1}`, samples: [] }));
        tplHeaderRow.disabled = false;
        tplHeaderRow.value = template.header_row;
        renderMapping(cols, template);
    } else {
        tplHeaderRow.disabled = true;
        tplHeaderRow.value = 1;
        tplMapping.innerHTML = `<p class="tpl-step-label">Dépose d'abord un fichier exemple ci-dessus.</p>`;
    }
    modal.classList.remove("hidden");
}

function closeTemplateModal() {
    modal.classList.add("hidden");
}

tplSave.addEventListener("click", saveTemplate);
tplCancel.addEventListener("click", closeTemplateModal);
modal.addEventListener("click", e => { if (e.target === modal) closeTemplateModal(); });
btnTemplateNew.addEventListener("click", () => openTemplateModal(null));
```

- [ ] **Step 2: Verify JS parses**

Run:
```bash
cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock/frontend" && node --check app.js && echo "app.js OK"
```
Expected: `app.js OK`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app.js
git commit -m "feat(ui): new-template modal — preview, guided mapping, save"
```

---

## Task 13: Frontend — edit + delete flows

**Files:**
- Modify: `frontend/app.js` (append handlers for edit/delete)

**Interfaces:**
- Consumes: `openTemplateModal`, `currentTemplate`, `DELETE /templates/{id}`, `refreshTemplates`, `tplState`

- [ ] **Step 1: Append edit/delete handlers to `frontend/app.js`**

```javascript
// ── Modifier / Supprimer ────────────────────────
btnTemplateEdit.addEventListener("click", () => {
    const t = tplState.list.find(x => x.id === selectedTemplateId());
    if (t && !t.builtin) openTemplateModal(t);
});

btnTemplateDel.addEventListener("click", async () => {
    const t = tplState.list.find(x => x.id === selectedTemplateId());
    if (!t || t.builtin) return;
    if (!confirm(`Supprimer le template « ${t.name} » ?`)) return;
    try {
        const res = await fetch(`${API_BASE}/templates/${t.id}`, { method: "DELETE" });
        if (!res.ok) {
            const e = await res.json().catch(() => ({ detail: "Erreur" }));
            throw new Error(e.detail || "Suppression impossible");
        }
        await refreshTemplates("basic-stock");
    } catch (err) {
        errorBanner.textContent = err.message;
        errorBanner.classList.remove("hidden");
    }
});
```

- [ ] **Step 2: Verify JS parses**

Run:
```bash
cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock/frontend" && node --check app.js && echo "app.js OK"
```
Expected: `app.js OK`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app.js
git commit -m "feat(ui): edit + delete template flows"
```

---

## Task 14: End-to-end verification (source + frozen) + persistence

**Files:**
- None modified (verification only)

**Interfaces:**
- Consumes: everything above

- [ ] **Step 1: Full backend suite green**

Run: `cd backend && python -m pytest -v`
Expected: all tests PASS.

- [ ] **Step 2: Drive the merged app from source**

Run:
```bash
cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock"
python3 -m venv /tmp/trb-e2e && source /tmp/trb-e2e/bin/activate
pip install -q -r backend/requirements.txt -r backend/requirements-dev.txt
python windows/launcher.py &
sleep 4
curl -s localhost:8000/templates | python3 -c "import sys,json; print('templates route:', [t['id'] for t in json.load(sys.stdin)['templates']])"
```
Expected: prints `templates route: ['basic-stock']`. Then Ctrl-equivalent: `pkill -f launcher.py`.

- [ ] **Step 3: Browser verification (Playwright MCP or manual)**

With the app running (`python windows/launcher.py`), in the browser at `http://localhost:8000`:
1. Click **＋ Nouveau**, drop a storage xlsx whose columns are reordered, confirm columns are auto-detected and mapping pre-filled, name it "Test Reorder", **Enregistrer**.
2. Confirm the dropdown now shows "Test Reorder" and it is selected; **✎** and **🗑** are enabled.
3. Upload a Proconcept file + the reordered storage file, **Comparer**, confirm stats render.
4. **🗑** delete "Test Reorder", confirm it disappears and selection falls back to "Basic template stock".

Expected: all steps behave as described; no console errors.

- [ ] **Step 4: Persistence across restart**

Run:
```bash
source /tmp/trb-e2e/bin/activate
python - <<'PY'
import os, sys
sys.path.insert(0, "backend")
import templates
tpl = templates.create_template({"name": "Persist", "header_row": 1,
    "columns": {"sku": 0, "lot": 1, "qty": 2}})
print("created:", tpl["id"])
# Simulate restart: fresh import in a new interpreter reads the file
import subprocess
out = subprocess.run([sys.executable, "-c",
    "import sys; sys.path.insert(0,'backend'); import templates;"
    "print([t['name'] for t in templates.load_user_templates()])"],
    capture_output=True, text=True, env={**os.environ})
print("after restart:", out.stdout.strip())
assert "Persist" in out.stdout
templates.delete_template(tpl["id"])
print("cleanup ok")
PY
```
Expected: `after restart: ['Persist']`, then `cleanup ok`.

- [ ] **Step 5: Frozen build sanity (local macOS)**

Run:
```bash
source /tmp/trb-e2e/bin/activate && pip install -q pyinstaller==6.11.1
cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock"
rm -rf build dist && pyinstaller windows/trb_stock.spec --noconfirm --clean 2>&1 | tail -2
pkill -f TRB-Comparaison-Stock 2>/dev/null; ( BROWSER=echo ./dist/TRB-Comparaison-Stock >/tmp/f.log 2>&1 & )
for i in $(seq 1 20); do sleep 2; curl -s localhost:8000/templates -o /dev/null && break; done
curl -s localhost:8000/templates | python3 -c "import sys,json; print('frozen templates:', [t['id'] for t in json.load(sys.stdin)['templates']])"
pkill -f TRB-Comparaison-Stock 2>/dev/null
```
Expected: `frozen templates: ['basic-stock']` (proves `templates.py` is bundled and reachable in the `.exe`).

- [ ] **Step 6: Clean up + commit any nothing**

```bash
rm -rf /tmp/trb-e2e build dist /tmp/f.log
git status --short   # should be clean (verification only)
```

---

## Self-Review

**Spec coverage:**
- §4.1 schema → Tasks 1-3 (model/validation). ✅
- §4.2 %APPDATA% persistence + TRB_DATA_DIR → Task 1. ✅
- §4.3 built-in default → Task 2. ✅
- §5.1 module split (`templates.py`) → Tasks 1-4. ✅
- §5.2 generic parser + regression → Task 5. ✅
- §5.3 CRUD + preview routes + `storage_template_id` → Tasks 6-7. ✅
- §5.4 detect_columns header auto-detect → Task 4. ✅
- §5.5 validation, atomic write, corrupted-json tolerance → Tasks 1-3. ✅
- §6 frontend select + modal + edit/delete + remember → Tasks 9-13. ✅
- §7 edge cases (out-of-range, empty file, builtin protection, missing template fallback) → Tasks 4,5,6,7,13. ✅
- §8 tests (regression, unit, persistence, e2e, frozen) → Tasks 5,1-7,14. ✅
- §9 packaging hiddenimports → Task 8. ✅

**Placeholder scan:** none — every code step has full code. ✅

**Type consistency:** `parse_storage_with_template(raw_bytes, template)` and `_run_comparison(theo, real, storage_template)` used identically in Tasks 5 & 7; `refreshTemplates(selectId)`, `selectedTemplateId()`, `openTemplateModal(template)`, `escapeHtml`, `tplState.list` consistent across Tasks 11-13; template dict shape (`id/name/builtin/header_row/columns`) consistent throughout. ✅
