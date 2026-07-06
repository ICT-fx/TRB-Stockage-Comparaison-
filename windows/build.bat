@echo off
REM ============================================================
REM   Compilation de l'executable Windows autonome (.exe)
REM ------------------------------------------------------------
REM   A lancer sur un PC WINDOWS avec Python installe.
REM   (Necessaire UNIQUEMENT pour compiler ; le .exe final, lui,
REM    n'a besoin d'aucune dependance.)
REM
REM   Resultat :  ..\dist\TRB-Comparaison-Stock.exe
REM ============================================================

title Compilation TRB - Comparaison de Stock
cd /d "%~dp0.."

echo ================================================
echo   Compilation de l'executable Windows
echo ================================================
echo.

REM --- Verifie Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH.
    echo   Installe Python : https://www.python.org/downloads/
    echo   (coche "Add Python to PATH" pendant l'installation).
    pause
    exit /b 1
)

echo [1/4] Creation de l'environnement Python...
python -m venv build-venv
call build-venv\Scripts\activate.bat

echo [2/4] Installation des dependances...
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
pip install pyinstaller==6.11.1

echo [3/4] Compilation avec PyInstaller...
pyinstaller windows\trb_stock.spec --noconfirm --clean

echo [4/4] Verification...
if not exist "dist\TRB-Comparaison-Stock.exe" (
    echo [ERREUR] La compilation a echoue : le .exe est introuvable.
    pause
    exit /b 1
)

echo.
echo ================================================
echo   OK ! Executable genere :
echo     dist\TRB-Comparaison-Stock.exe
echo ================================================
echo.
pause
