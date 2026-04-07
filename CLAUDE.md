# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Inventory reconciliation tool for TRB Chemedica. Compares theoretical stock (from Proconcept ERP) vs. actual physical stock (from RK Logistik warehouse partner) by processing Excel exports from each system.

## Commands

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
# or with auto-reload for development:
uvicorn main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/health`

### Frontend

No build step. Serve the `frontend/` directory with any static file server:
```bash
cd frontend
python -m http.server 3000
```

The frontend auto-detects `localhost` vs production and sets the API base URL accordingly.

## Architecture

**Mono-repo** with two independent services deployed on Render.com (`render.yaml`):
- `backend/` — FastAPI (Python 3.11.9) at `https://trb-stock-compare-api.onrender.com`
- `frontend/` — Static HTML/CSS/JS (no framework, no build)

### Backend (`backend/main.py`)

Two comparison modes, each with its own pair of parsers and comparison function:

| Mode | Parsers | Comparison fn | Use case |
|------|---------|---------------|----------|
| Code-only | `parse_proconcept()`, `parse_rk_logistik()` | `compare_stocks()` | Original layout, aggregates by product code |
| Date-aware | `parse_proconcept_vcarole_cfh()`, `parse_rk_temporaire()` | `compare_stocks_by_date()` | Newer layouts, matches by code + date with ±92-day tolerance |

**API routes:**
- `POST /compare` — returns JSON with `ok`, `discrepancies`, and stats
- `POST /compare/download` — streams a styled `.xlsx` report
- `GET /health`

**Notable implementation details:**
- CRC-32 zipfile patch applied at startup to handle corrupt-but-readable ERP Excel exports
- Excel column positions are hardcoded per layout type (e.g. Proconcept: Code=col E, Qty=col F)
- `build_excel()` produces a two-sheet report: "OK" (green) and "Écarts" (orange)

### Frontend (`frontend/`)

Pure vanilla JS with no dependencies. Key files:
- `index.html` — structure with dual upload zones, layout selectors, results tabs
- `app.js` — all logic: drag-and-drop upload, API calls, dynamic table rendering, Excel download
- `style.css` — dark theme with TRB blue (`#004B87`) branding

The layout format selectors in the UI control which parser pair the backend uses. The frontend passes `proconcept_layout` and `rk_layout` form fields to the API.

### Data Flow

1. User uploads two Excel files + selects layout formats + picks inventory date
2. `POST /compare` receives files, selects parser pair based on layout params
3. Backend aggregates/matches quantities, returns JSON
4. Frontend renders stats and color-coded tables (green delta = OK, orange = discrepancy)
5. `POST /compare/download` re-runs comparison and streams `.xlsx`

## Deployment

Defined in `render.yaml`. Two services:
- Backend: Python web service, `pip install -r requirements.txt` + `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Frontend: Static site from `frontend/`, no build command

Excel files (`*.xlsx`, `*.xls`) are gitignored — never commit inventory data.
