#!/bin/bash
# Double-click launcher for macOS. First run sets everything up automatically.
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed."
  echo "Please install it from https://www.python.org/downloads/ and run this again."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "First-time setup: creating a private Python environment..."
  python3 -m venv .venv
fi

if ! .venv/bin/python -c "import streamlit" >/dev/null 2>&1; then
  echo "First-time setup: installing the app's components (takes a minute)..."
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi

echo "Starting the app... your browser will open in a moment."
echo "(Keep this window open while you use the app. Close it to quit.)"
exec .venv/bin/python -m streamlit run app.py
