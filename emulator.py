import os
import sys
import socket
import struct
import time
import threading
from collections import deque
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
from PIL import Image, ImageTk, ImageDraw, ImageFont

IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")

OPEN_FILE_LABEL = "Open video file..."
DEFAULT_SETTINGS = {
    "rtsp_port": 8554,
    "rtsp_path": "/",
    "default_camera_index": 0,
    "frame_width": 640,
    "frame_height": 480,
    "fps": 30,
}


def camera_backend():
    if IS_WINDOWS:
        return cv2.CAP_DSHOW
    if IS_LINUX:
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


class LogCapture:
    def __init__(self, stream, maxlines=12):
        self.stream = stream
        self.lines = deque(maxlen=maxlines)
        self.lock = threading.Lock()
        self._buffer = ""

    def write(self, text):
        if self.stream is not None:
            self.stream.write(text)
        with self.lock:
            self._buffer += text
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                if line.strip():
                    self.lines.append(line)

    def flush(self):
        if self.stream is not None:
            self.stream.flush()

    def get_lines(self):
        with self.lock:
            return list(self.lines)

class RTSPServer:
    def __init__(self, app):
        self.app = app
        self.port = app.config.get("rtsp_port", 8554)
        self.path = app.config.get("rtsp_path", "/")
        self.sock = None
        self.running = True

    def start(self):
        self.server_thread = threading.Thread(target=self.run_server, daemon=True)
        self.server_thread.start()

    def run_server(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(('0.0.0.0', self.port))
            self.sock.listen(5)
            print(f"[RTSP] Server started on rtsp://localhost:{self.port}{self.path}")
        except Exception as e:
            print(f"[RTSP] Listen port error {self.port}: {e}")
            return

        while self.running:
            try:
                self.sock.settimeout(1.0)
                client_sock, client_addr = self.sock.accept()
                print(f"[RTSP] Client connected: {client_addr}")
                threading.Thread(target=self.handle_client, args=(client_sock, client_addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def handle_client(self, client_sock, client_addr):
        session_id = "987654321"
        client_rtp_port = None
        streaming = False
        stop_stream_event = threading.Event()
        stream_thread = None

        with self.app.client_lock:
            self.app.client_count += 1

        try:
            client_sock.settimeout(1.0)
            while self.running and not stop_stream_event.is_set():
                try:
                    data = client_sock.recv(2048)
                    if not data:
                        break
                except socket.timeout:
                    continue

                request = data.decode('utf-8', errors='ignore')
                lines = request.split('\r\n')
                if not lines or not lines[0]:
                    continue

                req_line = lines[0].split()
                if len(req_line) < 3:
                    continue
                method, url, _ = req_line[0], req_line[1], req_line[2]

                cseq = "1"
                for line in lines:
                    if line.lower().startswith("cseq:"):
                        cseq = line.split(":")[1].strip()
                        break

                match method:
                    case "SETUP":
                        for line in lines:
                            if line.lower().startswith("transport:"):
                                if "client_port=" in line:
                                    ports = line.split("client_port=")[1].split(";")[0].split("-")
                                    client_rtp_port = int(ports[0])
                                break
                        response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\nTransport: RTP/AVP;unicast;client_port={client_rtp_port}-{client_rtp_port + 1};server_port=6004-6005\r\nSession: {session_id}\r\n\r\n"
                    case "OPTIONS":
                        response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\nPublic: OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN\r\n\r\n"
                    case "DESCRIBE":
                        sdp = (
                            f"v=0\r\n"
                            f"o=- 0 0 IN IP4 127.0.0.1\r\n"
                            f"s=Python RTSP Emulator\r\n"
                            f"c=IN IP4 127.0.0.1\r\n"
                            f"t=0 0\r\n"
                            f"m=video 0 RTP/AVP 26\r\n"
                            f"a=rtpmap:26 JPEG/90000\r\n"
                        )
                        response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\nContent-Type: application/sdp\r\nContent-Length: {len(sdp)}\r\n\r\n{sdp}"
                    case "PLAY":
                        response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\nSession: {session_id}\r\nRTP-Info: url={url};seq=1;rtptime=0\r\n\r\n"
                        client_sock.sendall(response.encode('utf-8'))

                        if client_rtp_port and not streaming:
                            streaming = True
                            stop_stream_event.clear()
                            stream_thread = threading.Thread(
                                target=self.stream_rtp,
                                args=(client_addr[0], client_rtp_port, stop_stream_event),
                                daemon=True
                            )
                            stream_thread.start()
                        continue
                    case "TEARDOWN":
                        response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\nSession: {session_id}\r\n\r\n"
                        client_sock.sendall(response.encode('utf-8'))
                        break
                    case _:
                        response = f"RTSP/1.0 404 Not Found\r\nCSeq: {cseq}\r\n\r\n"

                client_sock.sendall(response.encode('utf-8'))

        except Exception as e:
            print(f"[RTSP] Client session error: {e}")
        finally:
            stop_stream_event.set()
            if stream_thread:
                stream_thread.join(timeout=1.0)
            client_sock.close()
            with self.app.client_lock:
                self.app.client_count -= 1
            print(f"[RTSP] Client disconnected: {client_addr}")

    def stream_rtp(self, client_ip, rtp_port, stop_event):
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        seq_num = 0
        timestamp = 0
        ssrc = 123456
        fps = self.app.fps
        sleep_time = 1.0 / fps

        print(f"[RTP] Thread started on {client_ip}:{rtp_port}")

        while not stop_event.is_set() and self.app.running:
            start_time = time.time()
            frame = None
            
            with self.app.frame_lock:
                if self.app.latest_frame is not None:
                    frame = self.app.latest_frame.copy()

            if frame is not None:
                ret, encoded_img = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if ret:
                    payload = encoded_img.tobytes()

                    byte0 = (2 << 6)
                    byte1 = (1 << 7) | 26
                    timestamp += int(90000 / fps)
                    if timestamp >= 0xFFFFFFFF: timestamp = 0
                    rtp_header = struct.pack('!BBHII', byte0, byte1, seq_num, timestamp, ssrc)

                    h, w = frame.shape[:2]
                    width_b = min(255, w // 8)
                    height_b = min(255, h // 8)
                    jpeg_header = struct.pack('!BBBBBBBB', 0, 0, 0, 0, 1, 70, width_b, height_b)

                    packet = rtp_header + jpeg_header + payload

                    try:
                        if len(packet) <= 65507:
                            udp_sock.sendto(packet, (client_ip, rtp_port))
                            with self.app.bytes_lock:
                                self.app.bytes_sent += len(packet)
                        seq_num = (seq_num + 1) % 65536
                    except Exception:
                        break

            elapsed = time.time() - start_time
            if elapsed < sleep_time:
                time.sleep(sleep_time - elapsed)

        udp_sock.close()
        print(f"[RTP] Thread {client_ip}:{rtp_port} is stopped")


class App:
    def __init__(self, root, config, log_capture=None):
        self.root = root
        self.root.title("RTSP IP Camera Emulator")
        self.config = config
        self.log_capture = log_capture

        self.current_camera_index = config.get("default_camera_index", 0)
        self.width = config.get("frame_width", 640)
        self.height = config.get("frame_height", 480)
        self.fps = config.get("fps", 30)

        self.cap = None
        self.latest_frame = None
        self.running = True
        self.rtsp_server = None

        self.source_map = {}
        self.video_files = []
        self.source_kind = "camera"
        self.source_fps = self.fps
        self.current_source_name = ""

        self.client_count = 0
        self.client_lock = threading.Lock()
        self.bytes_sent = 0
        self.bytes_lock = threading.Lock()
        self.bitrate_kbps = 0
        self._last_bitrate_time = time.time()
        self._last_bytes = 0

        self.frame_lock = threading.Lock()
        self.cap_lock = threading.Lock()

        self.overlay_font = self.load_overlay_font(12)

        self.setup_combobox_style()

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.preview_tab = tk.Frame(self.notebook, bg="black")
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.preview_tab, text="Preview")
        self.notebook.add(self.settings_tab, text="Settings")

        self.video_label = tk.Label(self.preview_tab, bg="black")
        self.video_label.pack(fill=tk.BOTH, expand=True)

        self.source_selector = ttk.Combobox(self.preview_tab, state="readonly", width=30, style="Dark.TCombobox")
        self.source_selector.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)
        self.source_selector.bind("<<ComboboxSelected>>", self.on_source_changed)

        self.build_settings_tab()

        self.populate_sources()
        self.activate_source(self.source_selector.get())

        self.capture_thread = threading.Thread(target=self.update_camera_feed, daemon=True)
        self.capture_thread.start()

        self.rtsp_server = RTSPServer(self)
        self.rtsp_server.start()

        self.update_gui_frame()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_combobox_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        dark_bg = "#2b2b2b"
        fg =      "#ffffff"
        sel_bg =  "#0078d7"

        style.configure(
            "Dark.TCombobox",
            fieldbackground=dark_bg,
            background=dark_bg,
            foreground=fg,
            arrowcolor=fg,
            bordercolor="#444444",
            lightcolor=dark_bg,
            darkcolor=dark_bg,
            relief="flat",
            padding=4,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", dark_bg)],
            background=[("readonly", dark_bg)],
            foreground=[("readonly", fg)],
            selectbackground=[("readonly", dark_bg)],
            selectforeground=[("readonly", fg)],
            arrowcolor=[("active", fg)],
        )

        self.root.option_add("*TCombobox*Listbox.background", dark_bg)
        self.root.option_add("*TCombobox*Listbox.foreground", fg)
        self.root.option_add("*TCombobox*Listbox.selectBackground", sel_bg)
        self.root.option_add("*TCombobox*Listbox.selectForeground", fg)
        self.root.option_add("*TCombobox*Listbox.borderWidth", 0)

    def load_overlay_font(self, size):
        for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def set_source(self, kind, value):
        with self.cap_lock:
            if self.cap is not None:
                self.cap.release()
                self.cap = None

            if kind == "camera":
                self.cap = cv2.VideoCapture(value, camera_backend())
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self.source_fps = self.fps
                self.current_camera_index = value
            else:
                self.cap = cv2.VideoCapture(value)
                file_fps = self.cap.get(cv2.CAP_PROP_FPS)
                self.source_fps = file_fps if file_fps and file_fps > 0 else self.fps

            self.source_kind = kind

    def get_camera_devices(self):
        if IS_WINDOWS:
            try:
                from pygrabber.dshow_graph import FilterGraph
                names = FilterGraph().get_input_devices()
                if names:
                    return [(i, name) for i, name in enumerate(names)]
            except Exception as e:
                print(f"[CAM] Could not read device names: {e}")
        elif IS_LINUX:
            import glob
            import re
            devices = []
            for path in sorted(glob.glob("/dev/video*")):
                m = re.search(r"(\d+)$", path)
                if not m:
                    continue
                idx = int(m.group(1))
                cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
                ok = cap.isOpened()
                cap.release()
                if not ok:
                    continue
                name = f"Camera {idx}"
                try:
                    with open(f"/sys/class/video4linux/video{idx}/name") as f:
                        name = f.read().strip() or name
                except OSError:
                    pass
                devices.append((idx, name))
            return devices
        return []

    def populate_sources(self):
        available = self.get_camera_devices()

        if not available:
            for i in range(4):
                c = cv2.VideoCapture(i, camera_backend())
                if c.isOpened():
                    available.append((i, f"Camera {i}"))
                    c.release()

        if not available:
            available = [(self.current_camera_index, f"Camera {self.current_camera_index}")]

        self.source_map = {}
        for idx, name in available:
            self.source_map[name] = ("camera", idx)
        for label, path in self.video_files:
            self.source_map[label] = ("file", path)

        self._refresh_source_values()

        default_name = next(
            (n for n, (k, v) in self.source_map.items() if k == "camera" and v == self.current_camera_index),
            None,
        )
        if default_name is None:
            default_name = next(iter(self.source_map))
        self.source_selector.set(default_name)
        print(f"[CAM] Detected cameras: {[n for n, (k, _) in self.source_map.items() if k == 'camera']}")

    def _refresh_source_values(self):
        self.source_selector["values"] = list(self.source_map.keys()) + [OPEN_FILE_LABEL]

    def activate_source(self, name):
        entry = self.source_map.get(name)
        if not entry:
            return
        kind, value = entry
        self.set_source(kind, value)
        self.current_source_name = name
        if kind == "camera":
            print(f"[SRC] Camera: {name}")
        else:
            print(f"[SRC] Looping video file: {name}")

    def on_source_changed(self, event=None):
        selected = self.source_selector.get()
        if selected == OPEN_FILE_LABEL:
            self.browse_video_file()
            return
        self.activate_source(selected)

    def browse_video_file(self):
        path = filedialog.askopenfilename(
            title="Select video file",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mkv *.mov *.webm *.flv *.wmv *.m4v *.mpg *.mpeg"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            self.source_selector.set(self.current_source_name)
            return

        label = os.path.basename(path)
        if label in self.source_map and self.source_map[label] != ("file", path):
            label = f"{label}  [{path}]"
        if not any(p == path for _, p in self.video_files):
            self.video_files.append((label, path))
        self.source_map[label] = ("file", path)

        self._refresh_source_values()
        self.source_selector.set(label)
        self.activate_source(label)

    def update_camera_feed(self):
        while self.running:
            frame = None
            with self.cap_lock:
                if self.cap and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if not ret:
                        # End of a video file -> rewind to loop it seamlessly.
                        if self.source_kind == "file":
                            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        frame = None

            if frame is not None:
                with self.frame_lock:
                    self.latest_frame = frame.copy()

            time.sleep(1.0 / max(1.0, self.source_fps))

    def build_settings_tab(self):
        fields = [
            ("RTSP port", "rtsp_port"),
            ("RTSP path", "rtsp_path"),
            ("Default camera index", "default_camera_index"),
            ("Frame width", "frame_width"),
            ("Frame height", "frame_height"),
            ("FPS", "fps"),
        ]
        self.settings_vars = {}

        container = ttk.Frame(self.settings_tab, padding=16)
        container.pack(anchor="nw", fill=tk.X)

        for row, (label, key) in enumerate(fields):
            ttk.Label(container, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 12))
            var = tk.StringVar(value=str(self.config.get(key, DEFAULT_SETTINGS.get(key, ""))))
            ttk.Entry(container, textvariable=var, width=24).grid(row=row, column=1, sticky="w", pady=4)
            self.settings_vars[key] = var

        ttk.Button(container, text="Apply", command=self.apply_settings).grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(16, 0))
        ttk.Label(
            container,
            text="Settings apply for the current session only and reset to defaults\n"
                 "on restart. Port/path changes restart the RTSP server; resolution\n"
                 "applies to camera sources.",
            foreground="#666666",
        ).grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def apply_settings(self):
        new = {}
        try:
            new["rtsp_port"] = int(self.settings_vars["rtsp_port"].get())
            new["default_camera_index"] = int(self.settings_vars["default_camera_index"].get())
            new["frame_width"] = int(self.settings_vars["frame_width"].get())
            new["frame_height"] = int(self.settings_vars["frame_height"].get())
            new["fps"] = max(1, int(self.settings_vars["fps"].get()))
        except ValueError:
            messagebox.showerror("Invalid settings", "Port, indices and sizes must be integers.")
            return

        path = self.settings_vars["rtsp_path"].get().strip() or "/"
        if not path.startswith("/"):
            path = "/" + path
        new["rtsp_path"] = path

        self.config.update(new)
        self.width = new["frame_width"]
        self.height = new["frame_height"]
        self.fps = new["fps"]

        self.restart_rtsp_server()
        if self.source_kind == "camera":
            self.set_source("camera", self.current_camera_index)
        print("[CFG] Settings applied")

    def restart_rtsp_server(self):
        if self.rtsp_server:
            self.rtsp_server.running = False
            if self.rtsp_server.sock:
                try:
                    self.rtsp_server.sock.close()
                except Exception:
                    pass
        self.rtsp_server = RTSPServer(self)
        self.rtsp_server.start()

    def update_gui_frame(self):
        if not self.running:
            return

        frame = None
        with self.frame_lock:
            if self.latest_frame is not None:
                frame = self.latest_frame.copy()

        self.update_bitrate()

        if frame is not None:
            cv2_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(cv2_image)
            # Fit the preview into a fixed-size canvas so switching to a video of
            # a different resolution never resizes the window or rescales the UI.
            pil_image = self.fit_to_canvas(pil_image, self.width, self.height)
            self.draw_overlay(pil_image, frame)
            imgtk = ImageTk.PhotoImage(image=pil_image)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)

        self.root.after(30, self.update_gui_frame)

    def fit_to_canvas(self, img, target_w, target_h):
        if img.width == 0 or img.height == 0:
            return img
        scale = min(target_w / img.width, target_h / img.height)
        new_w = max(1, round(img.width * scale))
        new_h = max(1, round(img.height * scale))
        resized = img.resize((new_w, new_h), Image.BILINEAR)
        canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
        canvas.paste(resized, ((target_w - new_w) // 2, (target_h - new_h) // 2))
        return canvas

    def update_bitrate(self):
        now = time.time()
        elapsed = now - self._last_bitrate_time
        if elapsed >= 1.0:
            with self.bytes_lock:
                sent = self.bytes_sent
            self.bitrate_kbps = int((sent - self._last_bytes) * 8 / elapsed / 1000)
            self._last_bytes = sent
            self._last_bitrate_time = now

    def draw_overlay(self, pil_image, frame):
        draw = ImageDraw.Draw(pil_image)
        img_w, img_h = pil_image.size
        font = self.overlay_font

        def text(x, y, s):
            draw.text((x, y), s, fill="white", font=font, stroke_width=2, stroke_fill="black")

        port = self.rtsp_server.port if self.rtsp_server else self.config.get("rtsp_port", 8554)
        path = self.rtsp_server.path if self.rtsp_server else self.config.get("rtsp_path", "/")
        h, w = frame.shape[:2]
        with self.client_lock:
            clients = self.client_count

        top_lines = [
            f"rtsp://localhost:{port}{path}",
            f"{self.fps} FPS | {w}x{h} | {self.bitrate_kbps} kbps",
            f"Clients: {clients}",
        ]
        y = 8
        for line in top_lines:
            text(8, y, line)
            y += 20

        logs = self.log_capture.get_lines()[-8:] if self.log_capture else []
        line_h = 18
        ly = img_h - 8 - line_h * len(logs)
        for line in logs:
            text(8, ly, line)
            ly += line_h

    def on_close(self):
        self.running = False
        if self.rtsp_server:
            self.rtsp_server.running = False
            if self.rtsp_server.sock:
                self.rtsp_server.sock.close()
        with self.cap_lock:
            if self.cap:
                self.cap.release()
        self.root.destroy()


if __name__ == "__main__":
    config_data = dict(DEFAULT_SETTINGS)

    log_capture = LogCapture(sys.stdout)
    sys.stdout = log_capture

    root = tk.Tk()
    app = App(root, config_data, log_capture)
    root.mainloop()