@echo off
rem Double-click to run: creates .venv on first start, installs the dependencies, launches the app.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv 2>nul || python -m venv .venv 2>nul
)
if not exist ".venv\Scripts\python.exe" (
    echo Could not create the virtual environment. Install Python 3.10+ from python.org, tick "Add python.exe to PATH".
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo Installing the dependencies failed.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" boost.py %*
pause
