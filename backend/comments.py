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
