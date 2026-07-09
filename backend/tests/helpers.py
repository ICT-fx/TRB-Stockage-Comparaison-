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
