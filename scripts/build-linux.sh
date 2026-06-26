#!/usr/bin/env bash

cd "$(dirname "$0")/.."

echo "Check Python installation..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python is not installed"
    exit 1
fi

echo "Python version check..."
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')
if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    echo "The old version of Python is installed. Install the version no lower than 3.10"
    exit 1
fi


echo "Checking the virtual environment..."
if [ ! -d "venv" ]; then
    echo "Creating a virtual environment..."
    python3 -m venv venv
fi

echo "Activating the virtual environment..."
source venv/bin/activate


echo "Installing dependencies..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "[ERROR] Dependency install error"
    read -r -p "Press Enter to exit..."
    exit 1
fi

clear
python -m nuitka \
    --onefile \
    --assume-yes-for-downloads \
    --enable-plugin=tk-inter \
    --output-dir=build \
    --output-filename=rtsp-emulator \
    --jobs=4 \
    --lto=yes \
    --show-progress \
    --show-memory \
    emulator.py

if [ $? -ne 0 ]; then
    echo "[ERROR] Compilation error"
    read -r -p "Press Enter to exit..."
    exit 1
fi
