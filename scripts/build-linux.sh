#!/usr/bin/env bash
# Compile the RTSP emulator into a standalone Linux executable with Nuitka.
set -e

python3 -m nuitka \
    --standalone \
    --onefile \
    --assume-yes-for-downloads \
    --enable-plugin=tk-inter \
    --output-dir=build \
    --output-filename=rtsp-emulator \
    emulator.py
