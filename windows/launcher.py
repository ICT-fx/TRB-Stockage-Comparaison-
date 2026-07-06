"""
TRB Chemedica — Comparaison de Stock : lanceur "tout-en-un" pour Windows.

Ce fichier est le point d'entrée de l'exécutable autonome (.exe).
Il fusionne les deux services du projet en un seul programme :
  - l'API FastAPI (le moteur de calcul, défini dans backend/main.py) ;
  - l'interface web statique (frontend/), servie par la même API.

Tout tourne sur http://localhost:8000, et le navigateur s'ouvre automatiquement.
Aucune installation de Python n'est nécessaire : l'interpréteur et toutes les
librairies sont embarqués dans le .exe par PyInstaller.
"""

import os
import sys
import socket
import threading
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://localhost:{PORT}/"


# ──────────────────────────────────────────────
# Retour visuel IMMÉDIAT
# ──────────────────────────────────────────────
# Les imports lourds (pandas, FastAPI…) prennent quelques secondes, surtout au
# tout premier lancement du .exe (Windows/macOS scanne le fichier). On affiche
# donc un message TOUT DE SUITE pour que l'utilisateur sache que ça démarre,
# avant de charger ces librairies.

def _enable_line_buffering() -> None:
    """Force l'affichage immédiat des messages (utile en .exe)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)  # type: ignore[union-attr]
        except Exception:
            pass


_enable_line_buffering()
print("=" * 56, flush=True)
print("  TRB Chemedica - Comparaison de Stock", flush=True)
print("=" * 56, flush=True)
print(flush=True)
print("  Demarrage en cours, merci de patienter quelques", flush=True)
print("  secondes (surtout au premier lancement)...", flush=True)
print(flush=True)


# ──────────────────────────────────────────────
# Résolution des chemins (fonctionne "gelé" par PyInstaller ou depuis les sources)
# ──────────────────────────────────────────────

def _base_dir() -> str:
    """Répertoire racine des ressources.

    - En .exe (PyInstaller onefile) : dossier temporaire d'extraction (_MEIPASS).
    - Depuis les sources : la racine du dépôt (parent de windows/).
    """
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = _base_dir()
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Rendre backend/main.py importable quand on lance depuis les sources.
# (En .exe, `main` est déjà embarqué comme module, cet ajout est inoffensif.)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from main import app  # FastAPI app définie dans backend/main.py  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

# On monte l'interface web à la racine "/".
# IMPORTANT : ce montage est ajouté APRÈS les routes API (/compare, /health…)
# déjà déclarées dans main.py, donc les routes API gardent la priorité et
# tout le reste ("/", "/index.html", "/style.css"…) est servi en fichiers statiques.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


# ──────────────────────────────────────────────
# Serveur + navigateur
# ──────────────────────────────────────────────

def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _server_is_up(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _open_browser_when_ready() -> None:
    """Attend que le serveur accepte les connexions, PUIS ouvre le navigateur.

    Évite d'ouvrir une page "connexion refusée" pendant un démarrage lent.
    """
    for _ in range(120):  # ~60 s max
        if _server_is_up(HOST, PORT):
            try:
                webbrowser.open(URL)
            except Exception:
                pass
            return
        threading.Event().wait(0.5)


def main() -> None:
    if not _port_is_free(HOST, PORT):
        print(f"[ERREUR] Le port {PORT} est deja utilise.", flush=True)
        print("  L'outil est peut-etre deja ouvert dans une autre fenetre,", flush=True)
        print("  ou un autre programme occupe ce port.", flush=True)
        print("  Ferme l'autre fenetre puis relance ce fichier.", flush=True)
        print(flush=True)
        try:
            input("Appuie sur Entree pour fermer...")
        except EOFError:
            pass
        return

    print(f"  Interface prete sur : {URL}", flush=True)
    print(flush=True)
    print("  Le navigateur va s'ouvrir automatiquement.", flush=True)
    print("  >>> NE FERME PAS cette fenetre tant que tu utilises l'outil. <<<", flush=True)
    print("  Pour tout arreter : ferme simplement cette fenetre.", flush=True)
    print(flush=True)
    print("=" * 56, flush=True)

    # Ouvre le navigateur dès que le serveur répond (thread en arrière-plan).
    threading.Thread(target=_open_browser_when_ready, daemon=True).start()

    import uvicorn

    # On passe l'objet `app` directement (pas une chaîne d'import) : indispensable
    # en mode "gelé", et cela évite tout rechargement automatique.
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
