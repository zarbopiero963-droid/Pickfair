@echo off
echo ================================================
echo   BETFAIR DUTCHING - Risultati Esatti
echo ================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato!
    echo Installa Python da https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Install dependencies if needed
pip show betfairlightweight >nul 2>&1
if errorlevel 1 (
    echo Prima installazione - scarico dipendenze...
    pip install betfairlightweight --quiet
)

REM Run application
echo Avvio applicazione...
python main.py
