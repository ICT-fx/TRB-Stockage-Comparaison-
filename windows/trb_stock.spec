# -*- mode: python ; coding: utf-8 -*-
"""
Configuration PyInstaller pour l'exécutable Windows autonome.

Produit un unique fichier `TRB-Comparaison-Stock.exe` qui embarque :
  - l'interpréteur Python et toutes les librairies (FastAPI, uvicorn, pandas,
    openpyxl, pydantic…) ;
  - le code backend (backend/main.py) ;
  - l'interface web (frontend/).

Build :  pyinstaller windows/trb_stock.spec --noconfirm
Le .exe est généré dans  dist/TRB-Comparaison-Stock.exe
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

# SPECPATH = dossier contenant ce .spec (windows/). ROOT = racine du dépôt.
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
LAUNCHER = os.path.join(SPECPATH, "launcher.py")

# ── Ressources à embarquer (fichiers de données) ──
datas = [
    (os.path.join(ROOT, "frontend"), "frontend"),  # interface web -> _MEIPASS/frontend
]
binaries = []
hiddenimports = []

# ── Collecte complète des paquets délicats à empaqueter ──
# (imports dynamiques, modules compilés, métadonnées) : on ratisse large pour
# éviter les "ModuleNotFoundError" au lancement du .exe.
for pkg in (
    "uvicorn",
    "fastapi",
    "starlette",
    "pydantic",
    "pydantic_core",
    "anyio",
    "multipart",      # python-multipart : gestion des uploads de fichiers
    "openpyxl",
    "pandas",
    "numpy",
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# uvicorn charge ces modules dynamiquement -> on les force explicitement.
hiddenimports += collect_submodules("uvicorn")
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "main",       # backend/main.py, importé par launcher.py
    "templates",  # backend/templates.py, importé par main.py
    "comments",   # backend/comments.py, importé par main.py
]

# backend/ sur le chemin d'analyse pour retrouver main.py
pathex = [os.path.join(ROOT, "backend")]


a = Analysis(
    [LAUNCHER],
    pathex=pathex,
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Allègements : librairies lourdes jamais utilisées par l'outil.
        "tkinter",
        "matplotlib",
        "PIL",
        "PyQt5",
        "PySide2",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TRB-Comparaison-Stock",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,           # fenêtre console : affiche l'état, se ferme pour tout arrêter
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
