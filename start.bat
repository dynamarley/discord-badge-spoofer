@echo off
title Discord Badge Spoofer
cd /d "%~dp0"

start "" pythonw main.py
if errorlevel 1 (
    start "" pyw main.py
)
if errorlevel 1 (
    start "" python main.py
)
if errorlevel 1 (
    echo [ERROR] Could not start application. Please ensure Python 3.10+ is installed.
    pause
)
exit /b
