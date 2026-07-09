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
    if not isinstance(cols, dict):
        raise ValueError("Le champ « columns » doit être un objet.")
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


def _format_sample(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def detect_columns(raw_bytes: bytes, header_row: int | None = None) -> dict:
    """Détecte la ligne d'en-tête + décrit chaque colonne d'un fichier exemple."""
    try:
        raw = pd.read_excel(io.BytesIO(raw_bytes), header=None)
    except Exception:
        raise ValueError("Fichier illisible ou vide.")
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
        samples = [_format_sample(v) for v in df.iloc[:, i].dropna().head(3).tolist()]
        columns.append({"index": i, "name": label, "samples": samples})
    return {"header_row": header_row, "columns": columns}
