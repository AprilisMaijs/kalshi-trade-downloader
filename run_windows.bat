@echo off
rem Double-click launcher for Windows. First run sets everything up automatically.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed or was not added to PATH.
  echo Install it from https://www.python.org/downloads/ and make sure to tick
  echo "Add python.exe to PATH" during installation, then run this again.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo First-time setup: creating a private Python environment...
  python -m venv .venv
)

".venv\Scripts\python.exe" -c "import streamlit" >nul 2>nul
if errorlevel 1 (
  echo First-time setup: installing the app's components ^(takes a minute^)...
  ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
)

echo Starting the app... your browser will open in a moment.
echo (Keep this window open while you use the app. Close it to quit.)
".venv\Scripts\python.exe" -m streamlit run app.py
pause
