"""
TRB Chemedica — Stock Comparison API
Compare theoretical (Proconcept) vs actual (RK Logistik) inventory.
Supports both original and new layout formats with date-based comparison.
"""

import io
import re
import zipfile
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
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


def _format_date_yyyymmdd(val: Any) -> str:
    """Convert a YYYYMMDD integer (e.g. 20280731) to DD.MM.YYYY string."""
    s = str(int(val))
    if len(s) == 8:
        return f"{s[6:8]}.{s[4:6]}.{s[0:4]}"
    return s


def _format_date_generic(val: Any) -> str:
    """Convert various date formats to DD.MM.YYYY string."""
    if pd.isna(val):
        return ""
    # Already a datetime object
    if hasattr(val, "strftime"):
        return val.strftime("%d.%m.%Y")
    # String like "2028-04-30" or similar
    s = str(val).strip()
    try:
        dt = pd.to_datetime(s)
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return s


def _parse_rk_date(val: Any) -> str:
    """Parse RK Logistik date formats to DD.MM.YYYY.
    Handles: '2028-03' (YYYY-MM), '2028-01-12 00:00:00' (datetime string), pandas Timestamp.
    YYYY-MM dates are normalized to the 1st of the month.
    """
    if pd.isna(val):
        return ""
    if hasattr(val, "strftime"):  # pandas Timestamp
        return val.strftime("%d.%m.%Y")
    s = str(val).strip()
    # Format YYYY-MM (month only, e.g. "2028-03")
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return f"01.{s[5:7]}.{s[0:4]}"
    # Format YYYY-MM-DD or DD.MM.YYYY
    try:
        dt = pd.to_datetime(s, dayfirst=True)
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return s


# ──────────────────────────────────────────────
# Original parsers (aggregate by code only)
# ──────────────────────────────────────────────

def parse_proconcept(raw_bytes: bytes) -> list[dict]:
    """
    Parse the Proconcept (theoretical stock) Excel — ORIGINAL layout.
    Date in column D (YYYYMMDD), code in column E, quantity in column F.
    Returns one row per lot (code + expiry date), not aggregated.
    """
    df = pd.read_excel(io.BytesIO(raw_bytes), header=0)

    if len(df.columns) <= 5:
        raise ValueError(
            f"Fichier Proconcept (Original) invalide. Il a {len(df.columns)} colonnes, "
            "mais on en attend au moins 6 (A à F)."
        )

    col_desc = df.columns[2]  # C: Description courte
    col_date = df.columns[3]  # D: Chronologie (YYYYMMDD int)
    col_code = df.columns[4]  # E: Référence principale
    col_qty  = df.columns[5]  # F: Qté effective

    # Forward-fill descriptions so that sub-rows of a product inherit it
    df[col_desc] = df[col_desc].ffill()

    products: list[dict] = []

    for _, row in df.iterrows():
        code_raw = row[col_code]
        date_raw = row[col_date]
        if not _is_numeric_code(code_raw):
            continue
        # Skip subtotal rows (date is a string like "20280531 Total") and NaN dates
        if pd.isna(date_raw) or not str(date_raw).strip().replace(".0", "").isdigit():
            continue

        code = str(int(float(str(code_raw))))
        qty = int(row[col_qty]) if pd.notna(row[col_qty]) else 0
        desc = str(row[col_desc]).strip() if pd.notna(row[col_desc]) else ""
        date_str = _format_date_yyyymmdd(date_raw)

        products.append({"code": code, "date": date_str, "qty": qty, "description": desc})

    return products


def parse_rk_logistik(raw_bytes: bytes) -> list[dict]:
    """
    Parse the RK Logistik (actual stock) Excel — ORIGINAL layout.
    Code in column A, date in column C (YYYY-MM or YYYY-MM-DD), quantity in column F.
    Returns one row per lot (code + expiry date), not aggregated.
    """
    df = pd.read_excel(io.BytesIO(raw_bytes), header=0)

    if len(df.columns) <= 5:
        raise ValueError(
            f"Fichier RK Logistik (Original) invalide. Il a {len(df.columns)} colonnes, "
            "mais on en attend au moins 6 (A à F)."
        )

    col_code = df.columns[0]  # A: Lagerort (SKU)
    col_date = df.columns[2]  # C: Expiry date (various formats)
    col_desc = df.columns[4]  # E: Kurztext
    col_qty  = df.columns[5]  # F: Bestand

    products: list[dict] = []

    for _, row in df.iterrows():
        code_raw = row[col_code]
        if not _is_numeric_code(code_raw):
            continue
        code = str(int(float(str(code_raw))))
        qty = int(row[col_qty]) if pd.notna(row[col_qty]) else 0
        desc = str(row[col_desc]).strip() if pd.notna(row[col_desc]) else ""
        date_str = _parse_rk_date(row[col_date])

        products.append({"code": code, "date": date_str, "qty": qty, "description": desc})

    return products


# ──────────────────────────────────────────────
# New parsers (keep individual rows with dates)
# ──────────────────────────────────────────────

def parse_proconcept_vcarole_cfh(raw_bytes: bytes) -> list[dict]:
    """
    Parse Proconcept Vcarole CFH layout.
    Code in column C (idx 2), date in column F (idx 5, YYYYMMDD int),
    quantity in column H (idx 7).
    Returns a list of {code, date, qty, description} — NOT aggregated.
    """
    df = pd.read_excel(io.BytesIO(raw_bytes), header=0)

    if len(df.columns) <= 7:
        raise ValueError(
            f"Fichier Proconcept (Vcarole CFH) invalide. Il a {len(df.columns)} colonnes, "
            "mais on en attend au moins 8 (A à H)."
        )

    col_code = df.columns[2]  # C: Référence principale
    col_date = df.columns[5]  # F: Chronologie (YYYYMMDD)
    col_qty  = df.columns[7]  # H: Qté

    products: list[dict] = []

    for _, row in df.iterrows():
        code_raw = row[col_code]
        if not _is_numeric_code(code_raw):
            continue
        code = str(int(float(str(code_raw))))
        qty = int(row[col_qty]) if pd.notna(row[col_qty]) else 0
        date_str = _format_date_yyyymmdd(row[col_date]) if pd.notna(row[col_date]) else ""

        products.append({
            "code": code,
            "date": date_str,
            "qty": qty,
            "description": "",  # No description column in this layout
        })

    return products


def parse_rk_temporaire(raw_bytes: bytes) -> list[dict]:
    """
    Parse RK temporaire layout.
    Code in column C (idx 2), quantity in column G (idx 6),
    date in column H (idx 7).
    Returns a list of {code, date, qty, description} — NOT aggregated.
    """
    df = pd.read_excel(io.BytesIO(raw_bytes), header=0)

    if len(df.columns) <= 7:
        raise ValueError(
            f"Fichier RK Logistik (Temporaire) invalide. Il a {len(df.columns)} colonnes, "
            "mais on en attend au moins 8 (A à H)."
        )

    col_code = df.columns[2]  # C: Artikel Nr.
    col_qty  = df.columns[6]  # G: Lagermenge
    col_date = df.columns[7]  # H: Expiry date
    col_desc = df.columns[3]  # D: Kurztext

    products: list[dict] = []

    for _, row in df.iterrows():
        code_raw = row[col_code]
        if not _is_numeric_code(code_raw):
            continue
        code = str(int(float(str(code_raw))))
        qty = int(row[col_qty]) if pd.notna(row[col_qty]) else 0
        date_str = _format_date_generic(row[col_date])
        desc = str(row[col_desc]).strip() if pd.notna(row[col_desc]) else ""

        products.append({
            "code": code,
            "date": date_str,
            "qty": qty,
            "description": desc,
        })

    return products


def parse_rk_nouveau_template(raw_bytes: bytes) -> list[dict]:
    """
    Parse the new standardized storage template imposed to warehouse partners.
    A (idx 0): SKU (code), B (idx 1): Shelf life (YYYY-MM), C (idx 2): Description, D (idx 3): Quantity.
    Returns a list of {code, date, qty, description} — NOT aggregated.
    """
    df = pd.read_excel(io.BytesIO(raw_bytes), header=0)

    if len(df.columns) <= 3:
        raise ValueError(
            f"Fichier RK Logistik (Nouveau Template) invalide. Il a {len(df.columns)} colonnes, "
            "mais on en attend au moins 4 (A à D)."
        )

    col_code = df.columns[0]  # A: SKU
    col_date = df.columns[1]  # B: Shelf life (YYYY-MM or similar)
    col_desc = df.columns[2]  # C: Description
    col_qty  = df.columns[3]  # D: Quantity

    products: list[dict] = []

    for _, row in df.iterrows():
        code_raw = row[col_code]
        if not _is_numeric_code(code_raw):
            continue
        code = str(int(float(str(code_raw))))
        qty = int(row[col_qty]) if pd.notna(row[col_qty]) else 0
        date_str = _parse_rk_date(row[col_date])
        desc = str(row[col_desc]).strip() if pd.notna(row[col_desc]) else ""

        products.append({
            "code": code,
            "date": date_str,
            "qty": qty,
            "description": desc,
        })

    return products


# ──────────────────────────────────────────────
# Comparison logic
# ──────────────────────────────────────────────

def compare_stocks(
    theoretical: dict[str, dict],
    actual: dict[str, dict],
) -> dict:
    """Compare two stock dictionaries by code only (original mode)."""
    ok = []
    discrepancies = []
    missing_actual = []
    missing_theoretical = []

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
            qty_theo = theoretical[code]["qty"]
            qty_real = 0
            discrepancies.append({
                "code": code,
                "description_theorique": theoretical[code]["description"],
                "description_reel": "",
                "qty_theorique": qty_theo,
                "qty_reel": qty_real,
                "delta": qty_real - qty_theo,
            })
        else:
            qty_theo = 0
            qty_real = actual[code]["qty"]
            discrepancies.append({
                "code": code,
                "description_theorique": "",
                "description_reel": actual[code]["description"],
                "qty_theorique": qty_theo,
                "qty_reel": qty_real,
                "delta": qty_real - qty_theo,
            })

    stats = {
        "total_products": len(all_codes),
        "ok_count": len(ok),
        "discrepancy_count": len(discrepancies),
        "missing_actual_count": 0,
        "missing_theoretical_count": 0,
        "match_rate": round(len(ok) / len(all_codes) * 100, 1) if all_codes else 0,
    }

    return {
        "has_dates": False,
        "ok": ok,
        "discrepancies": discrepancies,
        "missing_actual": [],
        "missing_theoretical": [],
        "stats": stats,
    }


def _parse_ddmmyyyy(date_str: str):
    """Parse a DD.MM.YYYY string to a date object, or None if invalid."""
    from datetime import datetime
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").date()
    except Exception:
        return None


def compare_stocks_by_date(
    theoretical: list[dict],
    actual: list[dict],
    tolerance_days: int = 92,
) -> dict:
    """
    Compare two stock lists by code + expiry date with a tolerance window.
    For each (code, date) in Proconcept, we look for the closest date in RK
    for the same code within tolerance_days. If found, they are matched.
    """
    from datetime import timedelta

    # Build lookup: code → list of {date_str, date_obj, qty, description}
    def _build_map(items: list[dict]) -> dict[str, list[dict]]:
        m: dict[str, list[dict]] = {}
        for item in items:
            code = item["code"]
            date_obj = _parse_ddmmyyyy(item["date"])
            entry = {**item, "date_obj": date_obj, "matched": False}
            m.setdefault(code, []).append(entry)
        # Aggregate duplicate (code+date) entries
        aggregated: dict[str, list[dict]] = {}
        for code, entries in m.items():
            deduped: dict[str, dict] = {}
            for e in entries:
                k = e["date"]
                if k in deduped:
                    deduped[k]["qty"] += e["qty"]
                else:
                    deduped[k] = {**e}
            aggregated[code] = list(deduped.values())
        return aggregated

    theo_by_code = _build_map(theoretical)
    actual_by_code = _build_map(actual)

    ok = []
    discrepancies = []
    missing_actual = []
    missing_theoretical = []

    all_codes = sorted(set(theo_by_code) | set(actual_by_code))

    for code in all_codes:
        theo_entries = theo_by_code.get(code, [])
        actual_entries = actual_by_code.get(code, [])

        # For each theoretical entry, try to find a matching actual entry
        for t in theo_entries:
            best_match = None
            best_diff = None

            if t["date_obj"] is not None:
                for a in actual_entries:
                    if a["matched"]:
                        continue
                    if a["date_obj"] is None:
                        continue
                    diff = abs((t["date_obj"] - a["date_obj"]).days)
                    if diff <= tolerance_days:
                        if best_diff is None or diff < best_diff:
                            best_diff = diff
                            best_match = a
            elif not actual_entries:
                pass  # dealt with below
            else:
                # No date in theoretical — try exact string match
                for a in actual_entries:
                    if not a["matched"] and a["date"] == t["date"]:
                        best_match = a
                        best_diff = 0
                        break

            if best_match is not None:
                best_match["matched"] = True
                qty_theo = t["qty"]
                qty_real = best_match["qty"]
                delta = qty_real - qty_theo
                # Show Proconcept date + RK date if they differ
                date_display = t["date"]
                if best_diff and best_diff > 0:
                    date_display = f"{t['date']} (RK: {best_match['date']})"
                entry = {
                    "code": code,
                    "date": date_display,
                    "description_theorique": t.get("description", ""),
                    "description_reel": best_match.get("description", ""),
                    "qty_theorique": qty_theo,
                    "qty_reel": qty_real,
                    "delta": delta,
                }
                if delta == 0:
                    ok.append(entry)
                else:
                    discrepancies.append(entry)
            else:
                qty_theo = t["qty"]
                qty_real = 0
                discrepancies.append({
                    "code": code,
                    "date": t["date"],
                    "description_theorique": t.get("description", ""),
                    "description_reel": "",
                    "qty_theorique": qty_theo,
                    "qty_reel": qty_real,
                    "delta": qty_real - qty_theo,
                })

        # Remaining unmatched actual entries → missing from theoretical
        for a in actual_entries:
            if not a["matched"]:
                qty_theo = 0
                qty_real = a["qty"]
                discrepancies.append({
                    "code": code,
                    "date": a["date"],
                    "description_theorique": "",
                    "description_reel": a.get("description", ""),
                    "qty_theorique": qty_theo,
                    "qty_reel": qty_real,
                    "delta": qty_real - qty_theo,
                })

    total = len(ok) + len(discrepancies)
    stats = {
        "total_products": total,
        "ok_count": len(ok),
        "discrepancy_count": len(discrepancies),
        "missing_actual_count": 0,
        "missing_theoretical_count": 0,
        "match_rate": round(len(ok) / total * 100, 1) if total else 0,
    }

    return {
        "has_dates": True,
        "ok": ok,
        "discrepancies": discrepancies,
        "missing_actual": [],
        "missing_theoretical": [],
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
    has_dates = result.get("has_dates", False)

    # ----- OK -----
    ws_ok = wb.active
    ws_ok.title = "OK"
    if has_dates:
        ws_ok.append(["Code", "Date péremption", "Description", "Quantité"])
        for item in result["ok"]:
            ws_ok.append([item["code"], item.get("date", ""), item.get("description_theorique") or item.get("description_reel", ""), item["qty_theorique"]])
        _style_header(ws_ok, "2E7D32", 4)
    else:
        ws_ok.append(["Code", "Description", "Quantité"])
        for item in result["ok"]:
            ws_ok.append([item["code"], item.get("description_theorique") or item.get("description_reel", ""), item["qty_theorique"]])
        _style_header(ws_ok, "2E7D32", 3)
    _auto_width(ws_ok)

    # ----- Écarts -----
    ws_disc = wb.create_sheet("Écarts")
    if has_dates:
        ws_disc.append(["Code", "Date péremption", "Description", "Qté Proconcept", "Qté Réelle", "Delta"])
        for item in result["discrepancies"]:
            ws_disc.append([
                item["code"],
                item.get("date", ""),
                item.get("description_theorique") or item.get("description_reel", ""),
                item["qty_theorique"],
                item["qty_reel"],
                item["delta"],
            ])
        _style_header(ws_disc, "F57F17", 6)
    else:
        ws_disc.append(["Code", "Description", "Qté Proconcept", "Qté Réelle", "Delta"])
        for item in result["discrepancies"]:
            ws_disc.append([
                item["code"],
                item.get("description_theorique") or item.get("description_reel", ""),
                item["qty_theorique"],
                item["qty_reel"],
                item["delta"],
            ])
        _style_header(ws_disc, "F57F17", 5)
    _auto_width(ws_disc)



    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ──────────────────────────────────────────────
# API Routes
# ──────────────────────────────────────────────

def _run_comparison(theo_bytes: bytes, real_bytes: bytes,
                    layout_theorique: str, layout_reel: str) -> dict:
    """Select the right parsers and comparison logic based on layouts."""
    use_date_comparison = (
        layout_theorique == "proconcept_vcarole_cfh" or
        layout_reel in ("rk_temporaire", "rk_nouveau_template")
    )

    if use_date_comparison:
        # Date-based parsers (vcarole / temporaire / nouveau template)
        if layout_theorique == "proconcept_vcarole_cfh":
            theo_list = parse_proconcept_vcarole_cfh(theo_bytes)
        else:
            theo_list = parse_proconcept(theo_bytes)

        if layout_reel == "rk_temporaire":
            actual_list = parse_rk_temporaire(real_bytes)
        elif layout_reel == "rk_nouveau_template":
            actual_list = parse_rk_nouveau_template(real_bytes)
        else:
            actual_list = parse_rk_logistik(real_bytes)

        return compare_stocks_by_date(theo_list, actual_list, tolerance_days=92)
    else:
        # Original layout: compare by code + expiry date, 2-month tolerance
        theo_list = parse_proconcept(theo_bytes)
        actual_list = parse_rk_logistik(real_bytes)
        return compare_stocks_by_date(theo_list, actual_list, tolerance_days=61)


@app.post("/compare")
async def compare(
    file_theorique: UploadFile = File(...),
    file_reel: UploadFile = File(...),
    layout_theorique: str = Form("original"),
    layout_reel: str = Form("original"),
):
    """Compare two Excel files and return JSON results."""
    try:
        theo_bytes = await file_theorique.read()
        real_bytes = await file_reel.read()

        result = _run_comparison(theo_bytes, real_bytes,
                                 layout_theorique, layout_reel)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors du traitement : {str(e)}")


@app.post("/compare/download")
async def compare_download(
    file_theorique: UploadFile = File(...),
    file_reel: UploadFile = File(...),
    layout_theorique: str = Form("original"),
    layout_reel: str = Form("original"),
):
    """Compare two Excel files and return an Excel report."""
    try:
        theo_bytes = await file_theorique.read()
        real_bytes = await file_reel.read()

        result = _run_comparison(theo_bytes, real_bytes,
                                 layout_theorique, layout_reel)
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
