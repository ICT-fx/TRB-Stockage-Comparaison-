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
