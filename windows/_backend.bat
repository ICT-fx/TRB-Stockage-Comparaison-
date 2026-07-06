@echo off
title TRB Backend (API) - port 8000
cd /d "%~dp0..\backend"

REM --- Premiere utilisation : cree l'environnement et installe les dependances ---
if not exist "venv\" (
    echo Premiere utilisation : creation de l'environnement Python...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Installation des dependances ^(peut prendre 1-2 minutes^)...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo.
echo API demarree sur http://localhost:8000
echo (Ne ferme pas cette fenetre tant que tu utilises l'outil.)
echo.
uvicorn main:app --port 8000

echo.
echo Le serveur backend s'est arrete.
pause
