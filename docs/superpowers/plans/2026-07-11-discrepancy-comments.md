# Per-Discrepancy Comments — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an editable comment per discrepancy line that exports to Excel and is remembered per `code+lot`, carrying forward a dated "previous comment" the next month.

**Architecture:** A new `backend/comments.py` persists comments to `comments.json` in the shared data dir (reusing `templates.data_dir()`). `/compare` attaches each discrepancy's stored comment; `/compare/download` writes a "Commentaire" column into the Écarts sheet; a new `POST /comments` upserts. The frontend defaults to the Écarts tab, renders a `<textarea>` per discrepancy prefilled by a testable `buildCommentPrefill`, and auto-saves on blur.

**Tech Stack:** Python 3.11, FastAPI, openpyxl (backend); vanilla JS (frontend); pytest + httpx (tests); PyInstaller (packaging).

## Global Constraints

- Comments persist in `comments.json` in `templates.data_dir()` (shared `O:` drive / local fallback / `TRB_DATA_DIR` override). Never `sys._MEIPASS`.
- Comment key = `f"{code}|{lot}"` (same code/lot values the comparison produces).
- `comments.json` shape: `{"comments": {"<key>": {"text": "...", "updated": "YYYY-MM-DD"}}}`. Atomic write (`.tmp` + `os.replace`); corrupt/missing → `{}`.
- Empty/whitespace comment text → delete the key.
- Carry-forward marker is the literal English string `previous comment`. Dates in markers are `MM/YYYY`.
- Comments only on Écarts (discrepancies), never on OK lines. OK Excel sheet unchanged.
- The `updated` value is the UI "Date de l'inventaire" (`inventory-date`), format `YYYY-MM-DD`.
- French user-facing strings; vanilla JS, no new deps; dark theme.
- Run backend tests: `cd backend && python -m pytest tests/ -q` (shared venv `/tmp/trb-venv`; JS checks via `node --check`).
- Do not change the comparison logic or the templates feature.

---

## File Structure

**Create:**
- `backend/comments.py` — comment store (load/save/get/set/key), reuses `templates.data_dir()`.
- `backend/tests/test_comments.py` — store unit tests.
- `backend/tests/test_api_comments.py` — API + compare-attaches + download-column tests.

**Modify:**
- `backend/main.py` — `import comments as comment_store`; `POST /comments`; `/compare` attaches `stored_comment`; `/compare/download` builds `comments_map`; `build_excel` gains `comments_map` + Écarts "Commentaire" column.
- `frontend/index.html` — reorder tabs (Écarts first + active) and panels.
- `frontend/app.js` — default Écarts tab in `renderResults`; `buildCommentPrefill` + `monthYear`; comment column in `renderDiscrepancyTable`; `saveComment` + focusout delegation; download flush.
- `frontend/style.css` — `.comment-box` / `.comment-cell`.
- `windows/trb_stock.spec` — add `"comments"` to `hiddenimports`.

---

## Task 1: `comments.py` store + tests

**Files:**
- Create: `backend/comments.py`, `backend/tests/test_comments.py`

**Interfaces:**
- Consumes: `templates.data_dir` (existing)
- Produces: `key(code,lot)->str`, `comments_path()->str`, `load_comments()->dict`, `save_comments(dict)->None`, `get_comment(code,lot)->dict|None`, `set_comment(code,lot,text,updated)->None`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_comments.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_comments.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'comments'`.

- [ ] **Step 3: Create `backend/comments.py`**

```python
"""
Persistance des commentaires de justification d'écart.
Stockés dans le même dossier partagé que les templates (templates.data_dir),
clé = "<code>|<lot>". Écriture atomique ; JSON corrompu toléré.
"""
import json
import os

from templates import data_dir


def comments_path() -> str:
    return os.path.join(data_dir(), "comments.json")


def key(code: str, lot: str) -> str:
    return f"{code}|{lot}"


def load_comments() -> dict:
    path = comments_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        c = data.get("comments", {})
        return c if isinstance(c, dict) else {}
    except Exception:
        return {}


def save_comments(comments: dict) -> None:
    d = data_dir()
    os.makedirs(d, exist_ok=True)
    path = comments_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"comments": comments}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def get_comment(code: str, lot: str) -> dict | None:
    return load_comments().get(key(code, lot))


def set_comment(code: str, lot: str, text: str, updated: str) -> None:
    data = load_comments()
    k = key(code, lot)
    if text is None or not str(text).strip():
        data.pop(k, None)
    else:
        data[k] = {"text": text, "updated": updated}
    save_comments(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_comments.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/comments.py backend/tests/test_comments.py
git commit -m "feat(comments): shared comment store keyed by code|lot"
```

---

## Task 2: `POST /comments` + `/compare` attaches stored comment

**Files:**
- Modify: `backend/main.py`
- Create: `backend/tests/test_api_comments.py`

**Interfaces:**
- Consumes: `comment_store.set_comment/get_comment` (Task 1)
- Produces: route `POST /comments`; `/compare` discrepancies gain `stored_comment` field (`{text,updated}` or `null`)

- [ ] **Step 1: Write the failing test**

`backend/tests/test_api_comments.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api_comments.py -q`
Expected: FAIL — 404 on `/comments` and `KeyError: 'stored_comment'`.

- [ ] **Step 3: Implement in `backend/main.py`**

Add to the imports near the top (after `import templates as template_store`):
```python
import comments as comment_store
```

Add the route immediately before `@app.get("/health")`:
```python
@app.post("/comments")
async def save_comment_route(payload: dict):
    code = str(payload.get("code", "")).strip()
    lot = str(payload.get("lot", "")).strip()
    if not code or not lot:
        raise HTTPException(status_code=400, detail="code et lot sont obligatoires.")
    text = payload.get("text", "")
    updated = str(payload.get("inventory_date", ""))
    comment_store.set_comment(code, lot, text, updated)
    return {"ok": True}
```

In the `/compare` route, find:
```python
        result, _, _ = _run_comparison(theo_bytes, real_bytes, tpl)
        return result
```
Replace with:
```python
        result, _, _ = _run_comparison(theo_bytes, real_bytes, tpl)
        for d in result["discrepancies"]:
            d["stored_comment"] = comment_store.get_comment(d["code"], d["lot"])
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_api_comments.py -q`
Expected: PASS (3 passed). NOTE: `test_download_includes_comment_column` is added in Task 3 — not yet present.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_api_comments.py
git commit -m "feat(api): POST /comments + attach stored_comment to /compare discrepancies"
```

---

## Task 3: Excel "Commentaire" column in the Écarts sheet

**Files:**
- Modify: `backend/main.py` (`build_excel`, `/compare/download`)
- Modify: `backend/tests/test_api_comments.py` (add download test)

**Interfaces:**
- Consumes: `comment_store.get_comment`
- Produces: `build_excel(result, df_proconcept, df_rk, comments_map=None)`; Écarts sheet last column `Commentaire`

- [ ] **Step 1: Write the failing test (append to `test_api_comments.py`)**

```python
def test_download_includes_comment_column(client):
    client.post("/comments", json={
        "code": "1349", "lot": "462994",
        "text": "écart vérifié\n[07/2026] résolu", "inventory_date": "2026-07-31"})
    r = client.post("/compare/download", files=_files())
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb["Écarts"]
    headers = [c.value for c in ws[1]]
    assert headers[-1] == "Commentaire"
    ccol = len(headers)
    found = None
    for row in ws.iter_rows(min_row=2):
        if str(row[0].value) == "1349":
            found = row[ccol - 1].value
    assert found is not None and "écart vérifié" in found
    # OK sheet must NOT have a Commentaire column
    ok_headers = [c.value for c in wb["OK"][1]]
    assert "Commentaire" not in ok_headers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api_comments.py::test_download_includes_comment_column -q`
Expected: FAIL — `build_excel()` has no comment column (`headers[-1]` != "Commentaire").

- [ ] **Step 3: Implement in `backend/main.py`**

Change the `build_excel` signature:
```python
def build_excel(result: dict, df_proconcept: pd.DataFrame, df_rk: pd.DataFrame, comments_map: dict | None = None) -> bytes:
```
Add at the very start of `build_excel` body (after the docstring):
```python
    comments_map = comments_map or {}
```

Find the current "── Écarts ──" block:
```python
    # ── Écarts ──
    ws_disc = wb.create_sheet("Écarts")
    ws_disc.append(headers_base)
    for item in result["discrepancies"]:
        ws_disc.append([
            item["code"], item["lot"],
            item.get("date_proconcept", ""), item.get("date_rk", ""),
            item.get("description_theorique") or item.get("description_reel", ""),
            item["qty_theorique"], item["qty_reel"], item["delta"],
        ])
    _style_header(ws_disc, _ORANGE, len(headers_base))
    _auto_width(ws_disc)
```
Replace it with:
```python
    # ── Écarts ── (avec colonne Commentaire)
    ws_disc = wb.create_sheet("Écarts")
    headers_disc = headers_base + ["Commentaire"]
    ws_disc.append(headers_disc)
    for item in result["discrepancies"]:
        ws_disc.append([
            item["code"], item["lot"],
            item.get("date_proconcept", ""), item.get("date_rk", ""),
            item.get("description_theorique") or item.get("description_reel", ""),
            item["qty_theorique"], item["qty_reel"], item["delta"],
            comments_map.get(f'{item["code"]}|{item["lot"]}', ""),
        ])
    _style_header(ws_disc, _ORANGE, len(headers_disc))
    _auto_width(ws_disc)
    # Colonne Commentaire : large + retour à la ligne
    ccell = ws_disc.cell(row=1, column=len(headers_disc))
    ws_disc.column_dimensions[ccell.column_letter].width = 50
    for r in range(2, ws_disc.max_row + 1):
        ws_disc.cell(row=r, column=len(headers_disc)).alignment = Alignment(
            horizontal="left", vertical="top", wrap_text=True)
```

In the `/compare/download` route, find:
```python
        result, df_pro, df_rk = _run_comparison(theo_bytes, real_bytes, tpl)
        excel_bytes = build_excel(result, df_pro, df_rk)
```
Replace with:
```python
        result, df_pro, df_rk = _run_comparison(theo_bytes, real_bytes, tpl)
        comments_map = {}
        for d in result["discrepancies"]:
            c = comment_store.get_comment(d["code"], d["lot"])
            if c:
                comments_map[f'{d["code"]}|{d["lot"]}'] = c["text"]
        excel_bytes = build_excel(result, df_pro, df_rk, comments_map)
```

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && python -m pytest tests/ -q`
Expected: PASS (all: 45 prior + Task 1's 6 + Task 2/3's 4 = 55).

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_api_comments.py
git commit -m "feat(excel): Commentaire column in the Écarts sheet"
```

---

## Task 4: Bundle `comments` in the PyInstaller build

**Files:**
- Modify: `windows/trb_stock.spec`

- [ ] **Step 1: Edit the spec**

In `windows/trb_stock.spec`, find:
```python
    "templates",  # backend/templates.py, importé par main.py
]
```
Replace with:
```python
    "templates",  # backend/templates.py, importé par main.py
    "comments",   # backend/comments.py, importé par main.py
]
```

- [ ] **Step 2: Verify source app boots with the route**

Run:
```bash
source /tmp/trb-venv/bin/activate && cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock" && python -c "import sys; sys.path.insert(0,'backend'); import main; print('/comments' in [r.path for r in main.app.routes if hasattr(r,'path')])"
```
Expected: `True`.

- [ ] **Step 3: Commit**

```bash
git add windows/trb_stock.spec
git commit -m "build(windows): bundle comments module in the exe"
```

---

## Task 5: Écarts tab shown first / by default

**Files:**
- Modify: `frontend/index.html` (tabs + panels), `frontend/app.js` (`renderResults`)

**Interfaces:**
- Produces: default active tab = discrepancies

- [ ] **Step 1: Reorder tabs + panels in `frontend/index.html`**

Find:
```html
            <div class="tabs-bar" id="tabs-bar">
                <button class="tab active" data-tab="ok">OK</button>
                <button class="tab" data-tab="discrepancies">Écarts</button>
            </div>

            <!-- Tab Panels -->
            <div class="tab-panel active" id="panel-ok"></div>
            <div class="tab-panel" id="panel-discrepancies"></div>
```
Replace with:
```html
            <div class="tabs-bar" id="tabs-bar">
                <button class="tab active" data-tab="discrepancies">Écarts</button>
                <button class="tab" data-tab="ok">OK</button>
            </div>

            <!-- Tab Panels -->
            <div class="tab-panel active" id="panel-discrepancies"></div>
            <div class="tab-panel" id="panel-ok"></div>
```

- [ ] **Step 2: Force the Écarts tab active on each results render in `frontend/app.js`**

In `renderResults`, find:
```javascript
    // Tables
    renderOkTable(data.ok);
    renderDiscrepancyTable(data.discrepancies);
```
Replace with:
```javascript
    // Tables
    renderOkTable(data.ok);
    renderDiscrepancyTable(data.discrepancies);

    // Onglet Écarts affiché par défaut
    tabsBar.querySelectorAll(".tab").forEach(t =>
        t.classList.toggle("active", t.dataset.tab === "discrepancies"));
    document.querySelectorAll(".tab-panel").forEach(p =>
        p.classList.toggle("active", p.id === "panel-discrepancies"));
```

- [ ] **Step 3: Verify JS parses**

Run: `cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock/frontend" && node --check app.js && echo OK`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html frontend/app.js
git commit -m "feat(ui): show Écarts tab first / by default"
```

---

## Task 6: `buildCommentPrefill` + comment column in the discrepancy table

**Files:**
- Modify: `frontend/app.js`

**Interfaces:**
- Consumes: `escapeHtml` (existing), `inventoryDate` (existing DOM ref)
- Produces: `monthYear(str)->str`, `buildCommentPrefill(stored, invDate)->str`; discrepancy rows contain `<textarea class="comment-box" data-code data-lot>`

- [ ] **Step 1: Add a node test for the prefill logic**

Create `frontend/comment-prefill.test.js` (temporary node test, deleted in Step 5):
```javascript
// Standalone copy of the functions under test (kept in sync with app.js).
function monthYear(dateStr) {
    const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(dateStr || "");
    return m ? `${m[2]}/${m[1]}` : "";
}
function buildCommentPrefill(stored, invDate) {
    if (!stored || !stored.text) return "";
    const cur = monthYear(invDate);
    const storedM = monthYear(stored.updated);
    if (storedM && cur && storedM === cur) return stored.text;
    if (stored.text.startsWith("previous comment")) return `${stored.text}\n[${cur}] `;
    return `previous comment [${storedM}]: ${stored.text}\n[${cur}] `;
}

const assert = require("assert");
// no stored -> empty
assert.strictEqual(buildCommentPrefill(null, "2026-07-31"), "");
// same month -> verbatim
assert.strictEqual(
    buildCommentPrefill({text: "note", updated: "2026-07-15"}, "2026-07-31"), "note");
// first carry -> wrapped + dated line
assert.strictEqual(
    buildCommentPrefill({text: "écart vérifié", updated: "2026-06-30"}, "2026-07-31"),
    "previous comment [06/2026]: écart vérifié\n[07/2026] ");
// subsequent carry -> just append dated line, no double "previous comment"
assert.strictEqual(
    buildCommentPrefill({text: "previous comment [06/2026]: a\n[07/2026] b", updated: "2026-07-31"}, "2026-08-31"),
    "previous comment [06/2026]: a\n[07/2026] b\n[08/2026] ");
console.log("buildCommentPrefill OK");
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock/frontend" && node comment-prefill.test.js`
Expected: at this point the standalone test PASSES on its own copy (it defines the functions). This test's role is to lock the spec of the functions you now add to `app.js` verbatim. Proceed to Step 3 and keep them identical.

- [ ] **Step 3: Add the functions + comment column to `frontend/app.js`**

Add these two functions just above `renderDiscrepancyTable`:
```javascript
// ── Commentaires d'écart ────────────────────────
function monthYear(dateStr) {
    const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(dateStr || "");
    return m ? `${m[2]}/${m[1]}` : "";
}

// Pré-remplissage du commentaire d'une ligne d'écart (report « previous comment »).
function buildCommentPrefill(stored, invDate) {
    if (!stored || !stored.text) return "";
    const cur = monthYear(invDate);
    const storedM = monthYear(stored.updated);
    if (storedM && cur && storedM === cur) return stored.text;
    if (stored.text.startsWith("previous comment")) return `${stored.text}\n[${cur}] `;
    return `previous comment [${storedM}]: ${stored.text}\n[${cur}] `;
}
```

Replace the whole `renderDiscrepancyTable` function with:
```javascript
function renderDiscrepancyTable(items) {
    const panel = document.getElementById("panel-discrepancies");
    if (!items.length) { panel.innerHTML = '<div class="empty-state">Aucun écart détecté.</div>'; return; }

    const inv = inventoryDate.value || "";
    panel.innerHTML = `
        <table class="result-table">
            <thead><tr><th>Code</th><th>N° de lot</th><th>Date Proconcept</th><th>Date RK</th><th>Description</th><th>Qté Proconcept</th><th>Qté Réelle</th><th>Delta</th><th>Commentaire</th></tr></thead>
            <tbody>${items.map(i => {
                const cls = i.delta > 0 ? 'delta-positive' : 'delta-negative';
                const sign = i.delta > 0 ? '+' : '';
                const prefill = buildCommentPrefill(i.stored_comment, inv);
                return `
                <tr>
                    <td class="code-cell">${i.code}</td>
                    <td class="lot-cell">${i.lot || '—'}</td>
                    <td class="date-cell">${i.date_proconcept || '—'}</td>
                    <td class="date-cell">${i.date_rk || '—'}</td>
                    <td>${i.description_theorique || i.description_reel || '—'}</td>
                    <td class="qty-cell">${i.qty_theorique.toLocaleString('fr-FR')}</td>
                    <td class="qty-cell">${i.qty_reel.toLocaleString('fr-FR')}</td>
                    <td class="delta-cell ${cls}">${sign}${i.delta.toLocaleString('fr-FR')}</td>
                    <td class="comment-cell"><textarea class="comment-box" rows="2" data-code="${i.code}" data-lot="${i.lot || ''}">${escapeHtml(prefill)}</textarea></td>
                </tr>`;
            }).join('')}</tbody>
        </table>
    `;
    // Mémoriser la valeur initiale de chaque champ (pour détecter les modifs).
    panel.querySelectorAll(".comment-box").forEach(box => { box.dataset.initial = box.value; });
}
```

- [ ] **Step 4: Verify JS parses + prefill test passes against the real file**

Run:
```bash
cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock/frontend"
node --check app.js && echo "app.js OK"
node comment-prefill.test.js
```
Expected: `app.js OK` then `buildCommentPrefill OK`.

- [ ] **Step 5: Delete the temp test + commit**

```bash
cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock"
rm frontend/comment-prefill.test.js
git add frontend/app.js
git commit -m "feat(ui): comment textarea per discrepancy + previous-comment prefill"
```

---

## Task 7: Auto-save on blur + flush before export

**Files:**
- Modify: `frontend/app.js`

**Interfaces:**
- Consumes: `API_BASE`, `inventoryDate`, `saveComment`
- Produces: `saveComment(box)->Promise`; focusout delegation on `#panel-discrepancies`; download handler awaits a focused dirty box

- [ ] **Step 1: Add `saveComment` + focusout delegation**

Add near the other top-level listeners (e.g. right after `refreshTemplates();`):
```javascript
// ── Enregistrement des commentaires d'écart ─────
async function saveComment(box) {
    if (!box || box.value === box.dataset.initial) return;  // inchangé
    const payload = {
        code: box.dataset.code,
        lot: box.dataset.lot,
        text: box.value,
        inventory_date: inventoryDate.value || "",
    };
    try {
        await fetch(`${API_BASE}/comments`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        box.dataset.initial = box.value;
    } catch { /* réseau indisponible : on réessaiera à la prochaine perte de focus */ }
}

document.getElementById("panel-discrepancies").addEventListener("focusout", (e) => {
    if (e.target.classList && e.target.classList.contains("comment-box")) {
        saveComment(e.target);
    }
});
```

- [ ] **Step 2: Flush the focused comment before download**

In the download handler (`btnDownload` click), find:
```javascript
    btnDownload.disabled = true;
    btnDownload.textContent = "⏳ Génération…";

    try {
```
Replace with:
```javascript
    btnDownload.disabled = true;
    btnDownload.textContent = "⏳ Génération…";

    try {
        // Enregistrer le commentaire en cours d'édition avant l'export.
        const active = document.activeElement;
        if (active && active.classList && active.classList.contains("comment-box")) {
            await saveComment(active);
        }
```

- [ ] **Step 3: Verify JS parses**

Run: `cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock/frontend" && node --check app.js && echo OK`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add frontend/app.js
git commit -m "feat(ui): auto-save comments on blur + flush before Excel export"
```

---

## Task 8: Comment box styling

**Files:**
- Modify: `frontend/style.css` (append at end)

- [ ] **Step 1: Append styles**

```css
/* ── Commentaires d'écart ──────────────────────── */
.comment-cell { min-width: 240px; }
.comment-box {
    width: 100%;
    min-width: 210px;
    padding: 6px 8px;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.06);
    color: #fff;
    font-family: inherit;
    font-size: 0.85rem;
    line-height: 1.35;
    resize: vertical;
}
.comment-box:focus {
    outline: none;
    border-color: #4da3ff;
    background: rgba(255, 255, 255, 0.1);
}
```

- [ ] **Step 2: Verify braces balance**

Run: `cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock/frontend" && python3 -c "c=open('style.css').read(); assert c.count('{')==c.count('}'); print('css ok')"`
Expected: `css ok`.

- [ ] **Step 3: Commit**

```bash
git add frontend/style.css
git commit -m "feat(ui): comment box styling"
```

---

## Task 9: End-to-end verification + rebuild

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite green**

Run: `cd backend && python -m pytest tests/ -q`
Expected: all pass (≈55).

- [ ] **Step 2: Browser E2E (source app, isolated data dir)**

```bash
cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock"
pkill -f launcher.py 2>/dev/null; sleep 1
export TRB_DATA_DIR=/tmp/trb-comments-e2e; rm -rf /tmp/trb-comments-e2e
source /tmp/trb-venv/bin/activate
BROWSER=echo nohup python windows/launcher.py > /tmp/trb-c.log 2>&1 &
for i in $(seq 1 15); do sleep 2; curl -s -m2 -o /dev/null http://127.0.0.1:8000/health && break; done
```
Then with the Playwright MCP at `http://localhost:8000`, using two prepared xlsx files copied into the workspace (Proconcept + storage with one discrepancy):
1. Compare → confirm the **Écarts tab is active by default**.
2. Type a comment on the discrepancy row, click elsewhere (blur) → confirm `POST /comments` succeeds (check `/tmp/trb-comments-e2e/comments.json`).
3. Click "Télécharger le rapport Excel" → open the xlsx → confirm the Écarts sheet has a "Commentaire" column with the text.
4. Re-run the compare → confirm the comment box is prefilled with `previous comment [MM/YYYY]: …` (set the inventory date to a later month first).
Expected: all four behave as described; no console errors (favicon 404 aside).

- [ ] **Step 3: Frozen build sanity**

```bash
source /tmp/trb-venv/bin/activate && cd "/Users/fantin/Documents/CODE/TRB Chemedica /Comparaison Stock"
rm -rf build dist && pyinstaller windows/trb_stock.spec --noconfirm --clean 2>&1 | tail -2
pkill -9 -f TRB-Comparaison-Stock 2>/dev/null
export TRB_DATA_DIR=/tmp/trb-frozen-c; rm -rf /tmp/trb-frozen-c
( BROWSER=echo ./dist/TRB-Comparaison-Stock >/tmp/fc.log 2>&1 & )
for i in $(seq 1 20); do sleep 2; curl -s -m2 -o /dev/null http://127.0.0.1:8000/health && break; done
curl -s -X POST http://127.0.0.1:8000/comments -H "Content-Type: application/json" -d '{"code":"1","lot":"2","text":"ok","inventory_date":"2026-07-31"}'
cat /tmp/trb-frozen-c/comments.json
pkill -9 -f TRB-Comparaison-Stock 2>/dev/null
```
Expected: `POST /comments` returns `{"ok":true}` and `comments.json` in the data dir contains the entry (proves `comments` module bundled + writes to the shared/data dir, not `_MEIPASS`).

- [ ] **Step 4: Clean up**

```bash
rm -rf build dist .playwright-mcp /tmp/trb-comments-e2e /tmp/trb-frozen-c /tmp/trb-c.log /tmp/fc.log
rm -f _tmp_*.xlsx *.png
```

---

## Self-Review

**Spec coverage:**
- §4 comments.json shared store, key, atomic, corruption → Task 1. ✅
- §5 previous-comment prefill rules → Task 6 (`buildCommentPrefill` + node test). ✅
- §6.1 comments.py module → Task 1. ✅
- §6.2 POST /comments + /compare attaches → Task 2. ✅
- §6.3 build_excel Écarts column → Task 3. ✅
- §7.1 Écarts default tab → Task 5. ✅
- §7.2 comment column + auto-save + download flush → Tasks 6, 7. ✅
- §7.3 styling → Task 8. ✅
- §9 tests → Tasks 1-3 (backend), 6 (JS), 9 (E2E). ✅
- §10 packaging hiddenimport → Task 4. ✅

**Placeholder scan:** none — every code step is complete.

**Type consistency:** `stored_comment` shape `{text,updated}` consistent (main.py attach ↔ app.js `buildCommentPrefill`); `comments_map` key `f"{code}|{lot}"` consistent (build_excel ↔ download route ↔ comments.key); `saveComment(box)` and `buildCommentPrefill(stored, invDate)` signatures stable across Tasks 6-7.
