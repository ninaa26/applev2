"""Live view of the trap's USB camera in a browser, with the same settings the trap photographs with.

    sudo -u sentinel /opt/sentinel/venv/bin/sentinel-camfeed --config /etc/sentinel/config.toml

Then open http://<pi's tailscale name>:8081 (e.g. http://sentinel-t1:8081) from any device on the
tailnet. It listens on the Tailscale address only, so it isn't visible on the campus network.
The frame shows the time and the share of saturated pixels (the trap aims for < 2 %).

Bench use only: while it runs, sentinel-cycle cannot open the camera. Stop it with Ctrl-C,
or `pkill -f sentinel-camfeed`.
"""

from __future__ import annotations

import argparse
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import config as config_mod
from ..camera import UsbCamera, clipped_fraction

PAGE = b"""<html><head><title>Trap camera</title></head>
<body style="margin:0;background:#111;display:grid;place-items:center;height:100vh">
<img src="/stream" style="max-width:100%;max-height:100vh"></body></html>"""


def tailscale_ip() -> str:
    try:
        return subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, check=True).stdout.split()[0]
    except Exception:
        return "127.0.0.1"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=config_mod.DEFAULT_CONFIG_PATH)
    ap.add_argument("--host", help="address to listen on (default: this Pi's Tailscale IP)")
    ap.add_argument("--port", type=int, default=8081)
    args = ap.parse_args(argv)

    import cv2  # type: ignore

    cam_cfg = config_mod.load(args.config)["camera"]
    if cam_cfg["backend"] != "usb":
        raise SystemExit("sentinel-camfeed only supports camera.backend = 'usb'")
    controls = dict(cam_cfg.get("usb_controls") or {})
    if cam_cfg.get("usb_wb_temperature"):
        controls.update(white_balance_automatic=0, white_balance_temperature=cam_cfg["usb_wb_temperature"])
    UsbCamera(cam_cfg)._set_controls(controls)

    cap = cv2.VideoCapture(str(cam_cfg["usb_device"]), cv2.CAP_V4L2)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {cam_cfg['usb_device']} (is sentinel-cycle or another viewer using it?)")
    w, h = cam_cfg["usb_size"]
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(w))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(h))
    latest: list[bytes | None] = [None]
    lock = threading.Lock()

    def grab():
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.1)
                continue
            label = f"{time.strftime('%H:%M:%S')}  clipped {clipped_fraction(frame):.1%}"
            cv2.putText(frame, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()
            with lock:
                latest[0] = jpg

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path != "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(PAGE)
                return
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=f")
            self.end_headers()
            try:
                while True:
                    with lock:
                        jpg = latest[0]
                    if jpg:
                        self.wfile.write(b"--f\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                    time.sleep(0.1)
            except (BrokenPipeError, ConnectionResetError):
                pass

    threading.Thread(target=grab, daemon=True).start()
    host = args.host or tailscale_ip()
    print(f"Live view: http://{host}:{args.port}  (Ctrl-C to stop)", flush=True)
    try:
        ThreadingHTTPServer((host, args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
