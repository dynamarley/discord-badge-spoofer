@echo off
title Discord Badge Spoofer Launcher
cd /d "%~dp0"

echo ========================================================
echo   Discord Badge Spoofer Launcher
echo ========================================================
echo.

echo [1/2] Checking requirements...
python -m pip install -r requirements.txt
if errorlevel 1 (
    py -m pip install -r requirements.txt
)

echo.
echo [2/2] Starting GUI Application...
python main.py
if errorlevel 1 (
    py main.py
)

if errorlevel 1 (
    echo.
    echo [ERROR] Could not start application. Please ensure Python 3.10+ is installed.
    pause
)
