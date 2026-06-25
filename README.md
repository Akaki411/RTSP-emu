 # RTSP IP Camera Emulator

A lightweight desktop tool that turns your computer's webcam into an RTSP IP
camera. It captures frames with OpenCV, serves them over a minimal built-in
RTSP/RTP server (Motion-JPEG), and shows a live preview with on-screen
diagnostics in a Tkinter window.

## Requirements

- Windows or Linux
- Python 3.10+
- A webcam

On Linux, camera access uses **V4L2**, so the kernel `v4l2` driver must be
present (it normally is). Tkinter must also be available — on Debian/Ubuntu
install it with `sudo apt install python3-tk`.

## Installation

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


## Usage

```bash
python emulator.py
```

The app window opens with a live preview. Pick a camera from the dropdown in the
top-right corner. Connect any RTSP client to the stream, for example with VLC or
ffplay

## Building a standalone executable

The project ships build scripts that compile `emulator.py` into a single
self-contained binary with [Nuitka](https://nuitka.net/):

```bash
# Windows
scripts/build-windows.bat

# Linux
chmod +x build.sh
./scripts/build.sh
```

The first run downloads the required Nuitka toolchain. A C compiler is needed
(MSVC or MinGW on Windows; `gcc` on Linux).

## Configuration

Settings live in [config.json](config.json) (created automatically on first run
if missing):

| Key                    | Description                          | Default |
| ---------------------- | ------------------------------------ | ------- |
| `rtsp_port`            | TCP port the RTSP server listens on  | `8554`  |
| `rtsp_path`            | Stream path appended to the URL      | `/`     |
| `default_camera_index` | Camera index selected at startup     | `0`     |
| `frame_width`          | Requested capture width              | `640`   |
| `frame_height`         | Requested capture height             | `480`   |
| `fps`                  | Capture / streaming frame rate       | `30`    |


## License

This project is licensed under the **GNU GPL V2.0**. See the [LICENSE](LICENSE)
