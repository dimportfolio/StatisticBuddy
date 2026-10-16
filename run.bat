@echo off
rem Creates the Python environment on first run, then starts Maple Tracker.
cd /d "%~dp0"
set VENV=%LOCALAPPDATA%\MapleTracker\venv
if not exist "%VENV%\Scripts\python.exe" (
    echo Setting up Python environment...
    python -m venv "%VENV%" || (echo Python 3.12 is required: https://www.python.org/downloads/ & pause & exit /b 1)
)
if not exist "%VENV%\installed.txt" (
    "%VENV%\Scripts\python" -m pip install --upgrade pip
    "%VENV%\Scripts\python" -m pip install -r requirements.txt || (pause & exit /b 1)
    echo ok> "%VENV%\installed.txt"
)
start "" "%VENV%\Scripts\pythonw" -m mapletracker
