 # RTSP IP Camera Emulator

![Python](https://img.shields.io/badge/Python-3.13-blue)
![License](https://img.shields.io/badge/License-GPL_2.0-lightgrey)

A lightweight desktop tool that turns your computer's webcam into an RTSP IP
camera.

## Features

- **Webcam → RTSP** — re-streams any local camera as `rtsp://localhost:8554/`.
- **Video file → RTSP** — pick a video file from the source dropdown and it is
  streamed in an endless **loop**.
- **Windows and Linux** support

## Requirements

- Windows or Linux
- Python 3.10+
- A webcam

On Linux, camera access uses **V4L2**, so the kernel `v4l2` driver must be
present (it normally is). Tkinter must also be available — on Debian/Ubuntu
install it with `sudo apt install python3-tk`.

## Installation

Download latest version from [release page](https://github.com/Akaki411/RTSP-emu/releases)

## Dev installation

Windows (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Linux (bash):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Or use ready-made scripts from the **`scripts/`** folder.

## Usage

```bash
python emulator.py
```

Connect any RTSP client to the stream, for example with VLC or `ffplay`:

```bash
ffplay rtsp://localhost:8554/
```

## Building a standalone executable

The project ships build scripts (in `scripts/`) that set up a virtual
environment, install dependencies and compile `emulator.py` into a single
portable binary with [Nuitka](https://nuitka.net/):

```bash
# Windows
scripts\build-windows.bat

# Linux
chmod +x scripts/build-linux.sh
./scripts/build-linux.sh
```

The first run downloads the required Nuitka toolchain. A C compiler is needed
(MSVC on Windows; `gcc` on Linux).

## Configuration

All parameters are edited from the **Settings** tab inside the app. Nothing is
written to disk: the app always starts with the built-in defaults below, and any
changes you make apply **for the current session only** and reset on restart.

| Key                    | Description                          | Default |
| ---------------------- | ------------------------------------ | ------- |
| `rtsp_port`            | TCP port the RTSP server listens on  | `8554`  |
| `rtsp_path`            | Stream path appended to the URL      | `/`     |
| `frame_width`          | Requested capture width              | `640`   |
| `frame_height`         | Requested capture height             | `480`   |
| `fps`                  | Capture / streaming frame rate       | `30`    |

Clicking **Apply** applies changes live: the RTSP server restarts to pick up a
new port/path, and the resolution is re-applied to camera sources.


## License

This project is licensed under the **GNU GPL V2.0**. See the [LICENSE](LICENSE)
