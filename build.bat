@echo off
REM Build script for Pickfair - Windows Executable
REM Requires Python 3.10+ and PyInstaller

echo ============================================
echo   Pickfair Build Script v3.16.0
echo ============================================

REM Check Python
python --version
if %errorlevel% neq 0 (
    echo [ERROR] Python non trovato. Installa Python 3.10+
    pause
    exit /b 1
)

REM Install/Update dependencies
echo.
echo [1/4] Installazione dipendenze...
pip install --upgrade pyinstaller
pip install customtkinter numpy betfairlightweight telethon

REM Plugin libraries (pre-installed for plugins to use)
pip install pandas matplotlib

echo.
echo [2/4] Pulizia cartelle precedenti...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist __pycache__ rmdir /s /q __pycache__

echo.
echo [3/4] Compilazione eseguibile...
pyinstaller --onefile --windowed ^
    --name "Pickfair" ^
    --add-data "plugins;plugins" ^
    --hidden-import customtkinter ^
    --hidden-import numpy ^
    --hidden-import pandas ^
    --hidden-import matplotlib ^
    --hidden-import betfairlightweight ^
    --hidden-import telethon ^
    --hidden-import plugin_manager ^
    main.py

if %errorlevel% neq 0 (
    echo [ERROR] Build fallita!
    pause
    exit /b 1
)

echo.
echo [4/4] Copia file aggiuntivi...
if not exist "dist\plugins" mkdir "dist\plugins"
copy "plugins\plugin_template.py" "dist\plugins\"
copy "plugins\example_odds_alert.py" "dist\plugins\"

echo.
echo ============================================
echo   Build completata!
echo   Eseguibile: dist\Pickfair.exe
echo ============================================
pause
