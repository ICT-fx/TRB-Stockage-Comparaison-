"""
TRB Chemedica — Stock Comparison API
Compare theoretical (Proconcept) vs actual (RK Logistik) inventory.
"""

import io
import re
import zipfile
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Patch zipfile to ignore CRC-32 errors commonly found in ERP-exported Excel files
zipfile.ZipExtFile._update_crc = lambda *args, **kwargs: None

app = FastAPI(title="TRB Stock Compare API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _is_numeric_code(val: Any) -> bool:
    """Return True if *val* looks like a numeric product code (e.g. '1349')."""
    if val is None:
        return False
    s = str(val).strip()
    return bool(re.fullmatch(r"\d+", s))


def parse_proconcept(raw_bytes: bytes) -> dict[str, dict]:
    """
    Parse the Proconcept (theoretical stock) Excel.

    Relevant rows have a numeric product code in column E ('Référence principale')
    and a quantity in column F ('La somme totale de Qté effective').
    Multiple rows with the same code (different expiry dates) are summed.
    The product description comes from column C ('Description courte') of the
    *first* row for that code that has a non-empty description.
    """
    df = pd.read_excel(io.BytesIO(raw_bytes), header=0)

    # Columns by position (E=4, F=5, C=2)
    col_code = df.columns[4]  # Référence principale
    col_qty  = df.columns[5]  # Qté effective
    col_desc = df.columns[2]  # Description courte

    products: dict[str, dict] = {}

    for _, row in df.iterrows():
        code_raw = row[col_code]
        if not _is_numeric_code(code_raw):
            continue
        code = str(int(float(str(code_raw))))
        qty = int(row[col_qty]) if pd.notna(row[col_qty]) else 0
        desc = str(row[col_desc]).strip() if pd.notna(row[col_desc]) else ""

        if code in products:
            products[code]["qty"] += qty
            if not products[code]["description"] and desc:
                products[code]["description"] = desc
        else:
            products[code] = {"qty": qty, "description": desc}

    return products


def parse_rk_logistik(raw_bytes: bytes) -> dict[str, dict]:
    """
    Parse the RK Logistik (actual stock) Excel.

    Relevant rows have a numeric product code in column A ('Lagerort')
    and a quantity in column F ('Bestand').
    Header is on the 1st row (index 0, 0-indexed).
    Multiple rows with the same code (different lots) are summed.
    """
    df = pd.read_excel(io.BytesIO(raw_bytes), header=0)

    col_code = df.columns[0]  # Lagerort
    col_qty  = df.columns[5]  # Bestand
    col_desc = df.columns[4]  # Kurztext

    products: dict[str, dict] = {}

    for _, row in df.iterrows():
        code_raw = row[col_code]
        if not _is_numeric_code(code_raw):
            continue
        code = str(int(float(str(code_raw))))
        qty = int(row[col_qty]) if pd.notna(row[col_qty]) else 0
        desc = str(row[col_desc]).strip() if pd.notna(row[col_desc]) else ""

        if code in products:
            products[code]["qty"] += qty
            if not products[code]["description"] and desc:
                products[code]["description"] = desc
        else:
            products[code] = {"qty": qty, "description": desc}

    return products


def compare_stocks(
    theoretical: dict[str, dict],
    actual: dict[str, dict],
) -> dict:
    """
    Compare two stock dictionaries and return categorised results.
    """
    ok = []
    discrepancies = []
    missing_actual = []    # in theoretical but not in actual
    missing_theoretical = []  # in actual but not in theoretical

    all_codes = set(theoretical) | set(actual)

    for code in sorted(all_codes):
        in_theo = code in theoretical
        in_real = code in actual

        if in_theo and in_real:
            qty_theo = theoretical[code]["qty"]
            qty_real = actual[code]["qty"]
            delta = qty_real - qty_theo
            entry = {
                "code": code,
                "description_theorique": theoretical[code]["description"],
                "description_reel": actual[code]["description"],
                "qty_theorique": qty_theo,
                "qty_reel": qty_real,
                "delta": delta,
            }
            if delta == 0:
                ok.append(entry)
            else:
                discrepancies.append(entry)
        elif in_theo and not in_real:
            missing_actual.append({
                "code": code,
                "description": theoretical[code]["description"],
                "qty_theorique": theoretical[code]["qty"],
            })
        else:
            missing_theoretical.append({
                "code": code,
                "description": actual[code]["description"],
                "qty_reel": actual[code]["qty"],
            })

    stats = {
        "total_products": len(all_codes),
        "ok_count": len(ok),
        "discrepancy_count": len(discrepancies),
        "missing_actual_count": len(missing_actual),
        "missing_theoretical_count": len(missing_theoretical),
        "match_rate": round(len(ok) / len(all_codes) * 100, 1) if all_codes else 0,
    }

    return {
        "ok": ok,
        "discrepancies": discrepancies,
        "missing_actual": missing_actual,
        "missing_theoretical": missing_theoretical,
        "stats": stats,
    }


# ──────────────────────────────────────────────
# Excel export
# ──────────────────────────────────────────────

_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center")
_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
_TRB_BLUE = "004B87"


def _style_header(ws, fill_color: str, col_count: int):
    fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
    for col in range(1, col_count + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = _HEADER_FONT
        cell.fill = fill
        cell.alignment = _HEADER_ALIGNMENT
        cell.border = _BORDER


def _auto_width(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_len + 4, 50)


def build_excel(result: dict) -> bytes:
    """Build a styled .xlsx workbook from comparison results."""
    wb = Workbook()

    # ----- OK -----
    ws_ok = wb.active
    ws_ok.title = "OK"
    ws_ok.append(["Code", "Description", "Quantité"])
    for item in result["ok"]:
        ws_ok.append([item["code"], item["description_theorique"] or item["description_reel"], item["qty_theorique"]])
    _style_header(ws_ok, "2E7D32", 3)  # green
    _auto_width(ws_ok)

    # ----- Écarts -----
    ws_disc = wb.create_sheet("Écarts")
    ws_disc.append(["Code", "Description", "Qté Théorique", "Qté Réelle", "Delta"])
    for item in result["discrepancies"]:
        ws_disc.append([
            item["code"],
            item["description_theorique"] or item["description_reel"],
            item["qty_theorique"],
            item["qty_reel"],
            item["delta"],
        ])
    _style_header(ws_disc, "F57F17", 5)  # orange
    _auto_width(ws_disc)

    # ----- Manquants Réel -----
    ws_mr = wb.create_sheet("Manquants Réel")
    ws_mr.append(["Code", "Description", "Qté Théorique"])
    for item in result["missing_actual"]:
        ws_mr.append([item["code"], item["description"], item["qty_theorique"]])
    _style_header(ws_mr, "C62828", 3)  # red
    _auto_width(ws_mr)

    # ----- Manquants Théorique -----
    ws_mt = wb.create_sheet("Manquants Théorique")
    ws_mt.append(["Code", "Description", "Qté Réelle"])
    for item in result["missing_theoretical"]:
        ws_mt.append([item["code"], item["description"], item["qty_reel"]])
    _style_header(ws_mt, "1565C0", 3)  # blue
    _auto_width(ws_mt)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ──────────────────────────────────────────────
# API Routes
# ──────────────────────────────────────────────

@app.post("/compare")
async def compare(
    file_theorique: UploadFile = File(...),
    file_reel: UploadFile = File(...),
):
    """Compare two Excel files and return JSON results."""
    try:
        theo_bytes = await file_theorique.read()
        real_bytes = await file_reel.read()

        theoretical = parse_proconcept(theo_bytes)
        actual = parse_rk_logistik(real_bytes)
        result = compare_stocks(theoretical, actual)

        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors du traitement : {str(e)}")


@app.post("/compare/download")
async def compare_download(
    file_theorique: UploadFile = File(...),
    file_reel: UploadFile = File(...),
):
    """Compare two Excel files and return an Excel report."""
    try:
        theo_bytes = await file_theorique.read()
        real_bytes = await file_reel.read()

        theoretical = parse_proconcept(theo_bytes)
        actual = parse_rk_logistik(real_bytes)
        result = compare_stocks(theoretical, actual)

        excel_bytes = build_excel(result)

        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=comparaison_stock.xlsx"
            },
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors du traitement : {str(e)}")


@app.get("/health")
async def health():
    return {"status": "ok"}
