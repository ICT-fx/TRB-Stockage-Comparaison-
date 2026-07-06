@echo off
title TRB Chemedica - Lancement
cd /d "%~dp0"

echo ================================================
echo   TRB Chemedica - Comparaison de Stock
echo ================================================
echo.

REM --- Verifie que Python est installe ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe, ou pas dans le PATH.
    echo.
    echo   1. Telecharge Python : https://www.python.org/downloads/
    echo   2. Pendant l'installation, COCHE "Add Python to PATH".
    echo   3. Relance ce fichier.
    echo.
    pause
    exit /b 1
)

echo Lancement du backend (API)...
start "TRB Backend (API)" "%~dp0_backend.bat"

echo Lancement du frontend (Interface)...
start "TRB Frontend (Interface)" "%~dp0_frontend.bat"

echo.
echo Attente du demarrage puis ouverture du navigateur...
echo (La premiere fois, l'installation peut prendre 1-2 minutes :
echo  si la page est vide, attends puis rafraichis avec F5.)
timeout /t 6 /nobreak >nul
start "" http://localhost:3000

echo.
echo ================================================
echo   C'est lance !
echo     - Interface : http://localhost:3000
echo     - API       : http://localhost:8000
echo.
echo   Deux fenetres se sont ouvertes (Backend et
echo   Frontend). Pour TOUT ARRETER : ferme ces deux
echo   fenetres.
echo ================================================
echo.
echo Tu peux fermer cette fenetre.
timeout /t 10 /nobreak >nul
exit
