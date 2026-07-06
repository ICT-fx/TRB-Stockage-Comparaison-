@echo off
title TRB Frontend (Interface) - port 3000
cd /d "%~dp0..\frontend"

echo.
echo Interface disponible sur http://localhost:3000
echo (Ne ferme pas cette fenetre tant que tu utilises l'outil.)
echo.
python -m http.server 3000

echo.
echo Le serveur frontend s'est arrete.
pause
