@echo off
REM ============================================================
REM  LogWatch - Windows-Build-Skript
REM  Erzeugt eine einzelne EXE in dist\LogWatch.exe
REM  Voraussetzung: Python 3.10+ ist installiert und im PATH.
REM ============================================================

echo [1/4] Virtuelle Umgebung anlegen (falls nicht vorhanden)...
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/4] Abhaengigkeiten installieren...
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo [3/4] (Optional) Unit-Tests ausfuehren...
pip install pytest
python -m pytest -q
if errorlevel 1 (
    echo WARNUNG: Tests fehlgeschlagen. Build wird dennoch fortgesetzt.
)

echo [4/4] EXE bauen mit PyInstaller...
pyinstaller logwatch.spec --noconfirm

echo.
echo Fertig. Die EXE liegt unter: dist\LogWatch.exe
pause
