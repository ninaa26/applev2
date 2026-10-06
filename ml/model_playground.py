"""Try any of our models on a photo, in the browser.

    python model_playground.py                  # then open http://localhost:8770
    python model_playground.py --port 9000

Pick a detector and (optionally) a species classifier, drop or paste a photo, and the boxes are drawn on it. Or
Capture screen: share a screen or window, drag a box over part of it, and Run (or tick Live, which re-runs as soon
as each run finishes, about once a second with YOLO alone) to detect whatever is under the box.
Detectors: every YOLO run under models/yolo11/*/weights/best.pt (train_yolo.py; its held-out mAP50 is shown),
the server's baseline, and flatbug. Classifiers: every models/*/head.npz (train_v1.py, BioCLIP 2 + linear head),
run on the server's padded crop of each box. Models load on first use and stay loaded.

YOLO runs the way it was trained: the photo is shrunk so the printed grid comes out at the run's px/mm (from the
grid, or the px/mm box on the page), cut into overlapping tiles, and the tiles' boxes merged. If no grid is found
and no px/mm is given, the photo is used as is, which only works if it's already about trap scale.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
from PIL import Image, ImageOps

HERE = Path(__file__).parent
from eval_detector_roboflow import Baseline, Flatbug, grid_px_per_mm  # noqa: E402

GRID_MM = 25.0


def yolo_runs() -> dict[str, dict]:
    runs = {}
    for best in sorted(HERE.glob("models/yolo11/*/weights/best.pt")):
        run = best.parents[1]
        s = run / "summary.json"
        info = json.loads(s.read_text()) if s.exists() else {}
        # Runs from before train_yolo.py had a test split only have "val": the photos that also picked the checkpoint.
        m, what = (info["test"], "test") if "test" in info else (info.get("val", {}), "checkpoint-selection (optimistic)")
        runs[f"yolo:{run.name}"] = {
            "name": f"YOLO {run.name}",
            "info": (f"{what} mAP50 {m['mAP50']:.2f} (moth {m['per_class_mAP50'].get('moth', 0):.2f})"
                     if m else "still training (using its best epoch so far)"),
            "path": best, "ppm": info.get("ppm", 12), "tile": info.get("tile", 640),
            "overlap": info.get("overlap", 160)}
    return runs


def detectors() -> dict[str, dict]:
    return {**yolo_runs(),
            "baseline": {"name": "Baseline (server default, OpenCV)", "info": "finds dark blobs; no classes"},
            "flatbug": {"name": "flatbug", "info": "pretrained arthropod detector; no classes"}}


def classifiers() -> dict[str, dict]:
    out = {"none": {"name": "None", "info": "boxes only"}}
    for head in sorted(HERE.glob("models/*/head.npz")):
        out[f"v1:{head.parent.name}"] = {"name": f"BioCLIP {head.parent.name}", "info": "species per box", "path": head}
    return out


class Models:
    def __init__(self):
        self.loaded: dict[str, object] = {}
        self.lock = threading.Lock()

    def get(self, key: str, make):
        if key not in self.loaded:
            self.loaded[key] = make()
        return self.loaded[key]

    def detect(self, key: str, img: Image.Image, ppm_hint: float | None) -> tuple[list[dict], dict]:
        bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        ppm = ppm_hint or grid_px_per_mm(bgr, GRID_MM)
        meta = {"ppm": round(ppm, 1) if ppm else None, "ppm_from": "you" if ppm_hint else ("grid" if ppm else None)}
        if key == "baseline":
            boxes = self.get(key, lambda: Baseline(GRID_MM))(bgr, Path("upload.jpg"))
            return [{"x1": b[0], "y1": b[1], "x2": b[2], "y2": b[3], "conf": b[4], "cls": "insect"} for b in boxes], meta
        if key == "flatbug":
            fb = self.get(key, lambda: Flatbug(str(HERE / "flat_bug_M.pt")))
            with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
                img.save(f.name, quality=95)
                boxes = fb(bgr, Path(f.name))
            return [{"x1": b[0], "y1": b[1], "x2": b[2], "y2": b[3], "conf": b[4], "cls": "insect"} for b in boxes], meta
        run = yolo_runs()[key]
        return self.yolo(key, run, img, ppm), {**meta, "scale": round(min(1.0, run["ppm"] / ppm), 3) if ppm else 1.0}

    def yolo(self, key: str, run: dict, img: Image.Image, ppm: float | None) -> list[dict]:
        import torch
        from torchvision.ops import nms
        from ultralytics import YOLO

        model = self.get(key, lambda: YOLO(str(run["path"])))
        scale = min(1.0, run["ppm"] / ppm) if ppm else 1.0
        small = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS) if scale < 1 else img
        tile, step = run["tile"], run["tile"] - run["overlap"]
        xs = list(range(0, max(small.width - tile, 0) + 1, step)) or [0]
        ys = list(range(0, max(small.height - tile, 0) + 1, step)) or [0]
        if xs[-1] + tile < small.width:
            xs.append(small.width - tile)
        if ys[-1] + tile < small.height:
            ys.append(small.height - tile)
        origins = [(x, y) for y in ys for x in xs]
        tiles = [small.crop((x, y, x + tile, y + tile)) for x, y in origins]
        boxes, confs, cls = [], [], []
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        for i in range(0, len(tiles), 16):
            for (ox, oy), r in zip(origins[i:i + 16], model.predict(tiles[i:i + 16], imgsz=tile, conf=0.05,
                                                                     device=device, verbose=False)):
                b = r.boxes
                if len(b):
                    boxes.append(b.xyxy.cpu() + torch.tensor([ox, oy, ox, oy]))
                    confs.append(b.conf.cpu())
                    cls.append(b.cls.cpu())
        if not boxes:
            return []
        boxes, confs, cls = torch.cat(boxes), torch.cat(confs), torch.cat(cls)
        keep = nms(boxes, confs, 0.5)  # one insect seen by two overlapping tiles: keep the surer box
        names = model.names
        return [{"x1": float(b[0]) / scale, "y1": float(b[1]) / scale, "x2": float(b[2]) / scale,
                 "y2": float(b[3]) / scale, "conf": float(confs[k]), "cls": names[int(cls[k])]}
                for k in keep.tolist() for b in [boxes[k]]]

    def classify(self, key: str, img: Image.Image, boxes: list[dict]) -> None:
        clf = self.get(key, lambda: Head(classifiers()[key]["path"]))
        todo = [b for b in boxes if b["conf"] >= 0.15]  # don't spend BioCLIP time on the faintest boxes
        for i in range(0, len(todo), 32):
            for b, p in zip(todo[i:i + 32], clf([crop(img, b) for b in todo[i:i + 32]])):
                b["species"] = [[c, round(float(p[k]), 3)] for k, c in sorted(enumerate(clf.classes), key=lambda kv: -p[kv[0]])[:3]]


def crop(img: Image.Image, b: dict, pad: float = 0.35) -> Image.Image:
    """The server's crop (sentinel_server/pipeline/classify.py: crop): a padded square around the box."""
    side = max(b["x2"] - b["x1"], b["y2"] - b["y1"]) * (1 + 2 * pad)
    cx, cy = (b["x1"] + b["x2"]) / 2, (b["y1"] + b["y2"]) / 2
    return img.crop((int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2)))


class Head:
    """BioCLIP 2 features + a train_v1.py linear head (the server's bioclip-v1)."""

    def __init__(self, path: Path):
        from train_v1 import Embedder

        z = np.load(path)
        self.W, self.b, self.classes = z["W"], z["b"], [str(c) for c in z["classes"]]
        self.emb = Embedder(str(z["model"]))

    def __call__(self, crops: list[Image.Image]) -> np.ndarray:
        torch = self.emb.torch
        with torch.no_grad():
            f = self.emb.model.encode_image(torch.stack([self.emb.preprocess(c) for c in crops]).to(self.emb.device))
        logits = torch.nn.functional.normalize(f, dim=-1).float().cpu().numpy() @ self.W.T + self.b
        p = np.exp(logits - logits.max(axis=1, keepdims=True))
        return p / p.sum(axis=1, keepdims=True)


MODELS = Models()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, code: int = 200):
        self.send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self.send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif path == "/api/models":
            strip = lambda d: {k: {"name": v["name"], "info": v["info"]} for k, v in d.items()}  # noqa: E731
            self.send_json({"detectors": strip(detectors()), "classifiers": strip(classifiers())})
        else:
            self.send(404, b"not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/run":
            return self.send(404, b"not found", "text/plain")
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            with Image.open(io.BytesIO(data)) as im:
                img = ImageOps.exif_transpose(im).convert("RGB")
            det, clf = q.get("detector", "baseline"), q.get("classifier", "none")
            if det not in detectors() or clf not in classifiers():
                return self.send_json({"error": "unknown model (reload the page)"}, 400)
            ppm = float(q["ppm"]) if q.get("ppm") else None
            t0 = time.time()
            with MODELS.lock:  # one model run at a time: they share the GPU
                boxes, meta = MODELS.detect(det, img, ppm)
                t1 = time.time()
                if clf != "none":
                    MODELS.classify(clf, img, boxes)
            self.send_json({"w": img.width, "h": img.height, "boxes": boxes, **meta,
                            "detect_s": round(t1 - t0, 2), "classify_s": round(time.time() - t1, 2)})
        except Exception as e:  # show it on the page rather than a dead request
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Model Playground</title>
<style>
:root { --bg:#f6f6f4; --panel:#fff; --ink:#1d1d1f; --muted:#6b6b70; --line:#dedede; --accent:#2563eb;
        --moth:#e5484d; --other_insect:#12a5c4; --debris:#d9a400; --insect:#c026d3; }
@media (prefers-color-scheme: dark) { :root { --bg:#161617; --panel:#202022; --ink:#ececec; --muted:#9a9aa0; --line:#333; } }
* { box-sizing:border-box } body { margin:0; font:14px/1.4 -apple-system, system-ui, sans-serif; background:var(--bg); color:var(--ink) }
.app { display:grid; grid-template-columns:300px 1fr; height:100vh }
aside { background:var(--panel); border-right:1px solid var(--line); padding:16px; overflow:auto }
h1 { font-size:16px; margin:0 0 12px } label { display:block; font-weight:600; margin:14px 0 4px }
select, input[type=number], button { width:100%; font:inherit; padding:7px 8px; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--ink) }
button.primary { background:var(--accent); color:#fff; border:0; font-weight:600; margin-top:14px; cursor:pointer }
button:disabled { opacity:.5 } .hint { color:var(--muted); font-size:12px; margin-top:3px }
#drop { border:2px dashed var(--line); border-radius:8px; padding:18px 10px; text-align:center; color:var(--muted); cursor:pointer; margin-top:14px }
#drop.over { border-color:var(--accent); color:var(--accent) }
main { position:relative; overflow:hidden } canvas { display:block; width:100%; height:100%; cursor:grab }
#empty { position:absolute; inset:0; display:grid; place-items:center; color:var(--muted); pointer-events:none } #empty[hidden] { display:none }
.counts div { display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px solid var(--line) }
.sw { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px }
#status { margin-top:10px; color:var(--muted); font-size:12px; white-space:pre-wrap } #status.err { color:var(--moth) }
#detail { margin-top:12px; font-size:12px } .row { display:flex; gap:8px; align-items:center } .row input[type=range] { flex:1 }
@media (max-width:700px) { .app { grid-template-columns:1fr; grid-template-rows:auto 70vh; height:auto } aside { border-right:0 } }
</style></head><body><div class="app">
<aside>
  <h1>Model playground</h1>
  <label for="det">Detector</label><select id="det"></select><div class="hint" id="detInfo"></div>
  <label for="clf">Species classifier</label><select id="clf"></select><div class="hint" id="clfInfo"></div>
  <label for="ppm">px/mm</label><input id="ppm" type="number" min="1" step="0.1" placeholder="auto (from the 25 mm grid)">
  <div class="hint">Leave empty unless the grid isn't found.</div>
  <div id="drop">Drop a photo here, paste one, or click to choose<input id="file" type="file" accept="image/*" hidden></div>
  <button id="capBtn" style="margin-top:8px">Capture screen instead…</button>
  <div id="capCtl" hidden>
    <div class="hint">Drag the box to move it, its corner to resize, or drag outside it for a new one.</div>
    <label class="row" style="font-weight:400"><input id="live" type="checkbox" style="width:auto"> Live: run again as soon as each run finishes</label>
  </div>
  <button class="primary" id="run" disabled>Run</button>
  <label>Min confidence <span id="confV">0.25</span></label>
  <div class="row"><input id="conf" type="range" min="0.05" max="0.95" step="0.05" value="0.25"></div>
  <label>Found</label><div class="counts" id="counts"><div class="hint">Nothing yet</div></div>
  <div id="detail"></div><div id="status"></div>
</aside>
<main><canvas id="cv"></canvas><div id="empty">Upload a photo to start</div></main>
</div>
<script>
const $ = id => document.getElementById(id);
let models, file, img, result, view = {s:1, x:0, y:0}, sel = null;
// Screen capture: the shared screen plays in a <video>; `box` (video px) is the part the model sees, `off` where the
// last result's box was, so its detections are drawn back over the right spot.
let cap = null, box = null, off = {x: 0, y: 0};
const src = () => cap ? cap.video : img;
const srcW = () => cap ? cap.video.videoWidth : img.width, srcH = () => cap ? cap.video.videoHeight : img.height;
const color = c => getComputedStyle(document.documentElement).getPropertyValue('--' + c).trim() || '#c026d3';
function remember(k, v) { try { localStorage.setItem('pg.' + k, v) } catch (e) {} }
function recall(k) { try { return localStorage.getItem('pg.' + k) } catch (e) { return null } }

async function loadModels() {
  models = await (await fetch('/api/models')).json();
  for (const [sel, kind] of [[$('det'), 'detectors'], [$('clf'), 'classifiers']]) {
    sel.innerHTML = '';
    for (const [k, m] of Object.entries(models[kind])) sel.add(new Option(m.name, k));
    const prev = recall(kind); if (prev && models[kind][prev]) sel.value = prev;
  }
  info();
}
function info() {
  $('detInfo').textContent = models.detectors[$('det').value]?.info || '';
  $('clfInfo').textContent = models.classifiers[$('clf').value]?.info || '';
}
$('det').onchange = () => { remember('detectors', $('det').value); info(); if (file) run(); };
$('clf').onchange = () => { remember('classifiers', $('clf').value); info(); if (file) run(); };
$('conf').oninput = () => { $('confV').textContent = $('conf').value; draw(); counts(); };

function setFile(f) {
  if (!f || !f.type.startsWith('image/')) return;
  stopCapture(); file = f; result = null; sel = null; off = {x: 0, y: 0}; $('run').disabled = false; $('empty').hidden = true;
  img = new Image(); img.onload = () => { fit(); draw(); run(); }; img.src = URL.createObjectURL(f);
}
$('drop').onclick = () => $('file').click();
$('file').onchange = e => setFile(e.target.files[0]);
for (const t of [$('drop'), document.querySelector('main')]) {
  t.addEventListener('dragover', e => { e.preventDefault(); $('drop').classList.add('over'); });
  t.addEventListener('dragleave', () => $('drop').classList.remove('over'));
  t.addEventListener('drop', e => { e.preventDefault(); $('drop').classList.remove('over'); setFile(e.dataTransfer.files[0]); });
}
document.addEventListener('paste', e => { const f = [...e.clipboardData.files][0]; if (f) setFile(f); });
$('run').onclick = run;

$('capBtn').onclick = () => cap ? stopCapture() : startCapture();
$('live').onchange = () => { if ($('live').checked && !busy) run(); };
async function startCapture() {
  let stream;
  try { stream = await navigator.mediaDevices.getDisplayMedia({video: {frameRate: 10}, audio: false}); }
  catch (e) { $('status').className = 'err'; $('status').textContent = 'Screen capture: ' + e.message; return; }
  const video = document.createElement('video'); video.muted = true; video.srcObject = stream; await video.play();
  cap = {video, stream}; result = null; sel = null; img = null; file = null;
  const w = video.videoWidth, h = video.videoHeight;
  box = {x: w * 0.3, y: h * 0.3, w: w * 0.4, h: h * 0.4};
  stream.getVideoTracks()[0].onended = stopCapture;
  $('capCtl').hidden = false; $('capBtn').textContent = 'Stop capturing'; $('run').disabled = false; $('empty').hidden = true;
  fit(); (function loop() { if (!cap) return; draw(); requestAnimationFrame(loop); })();
}
function stopCapture() {
  if (!cap) return;
  cap.stream.getTracks().forEach(t => t.stop()); cap = null; box = null; result = null; $('live').checked = false;
  $('capCtl').hidden = true; $('capBtn').textContent = 'Capture screen instead…'; $('run').disabled = true;
  $('empty').hidden = false; draw(); counts(); detail();
}
function grab() {  // the box's pixels, at the screen's full resolution
  const c = document.createElement('canvas'), b = {x: Math.round(box.x), y: Math.round(box.y), w: Math.round(box.w), h: Math.round(box.h)};
  c.width = b.w; c.height = b.h; c.getContext('2d').drawImage(cap.video, b.x, b.y, b.w, b.h, 0, 0, b.w, b.h);
  return new Promise(res => c.toBlob(blob => res([blob, b]), 'image/png'));
}
let busy = false;
async function run() {
  if (busy || !(file || cap)) return;
  busy = true;
  let body = file, at = {x: 0, y: 0};
  if (cap) [body, at] = await grab();
  $('run').disabled = true; $('status').className = '';
  if (!(cap && $('live').checked && result))  // live: keep the last result's line instead of flashing this
    $('status').textContent = 'Running ' + models.detectors[$('det').value].name + '… (the first run of a model loads it)';
  const q = new URLSearchParams({detector: $('det').value, classifier: $('clf').value});
  if ($('ppm').value) q.set('ppm', $('ppm').value);
  try {
    const r = await (await fetch('/api/run?' + q, {method: 'POST', body})).json();
    if (r.error) throw new Error(r.error);
    result = r; sel = null; off = at;
    $('status').textContent = `${r.boxes.length} boxes before the confidence cut · detect ${r.detect_s}s` +
      ($('clf').value !== 'none' ? ` · classify ${r.classify_s}s` : '') +
      `\npx/mm: ${r.ppm ?? 'grid not found'}${r.ppm_from ? ' (' + r.ppm_from + ')' : ''}` +
      (r.scale && r.scale < 1 ? ` · shrunk ×${r.scale} for YOLO` : '');
  } catch (e) { $('status').className = 'err'; $('status').textContent = e.message; }
  $('run').disabled = false; busy = false; draw(); counts(); detail();
  if (cap && $('live').checked) setTimeout(run, 300);
}
const shown = () => result ? result.boxes.filter(b => b.conf >= +$('conf').value) : [];
function counts() {
  const c = {}; for (const b of shown()) c[b.cls] = (c[b.cls] || 0) + 1;
  const sp = {}; for (const b of shown()) if (b.species) sp[b.species[0][0]] = (sp[b.species[0][0]] || 0) + 1;
  const row = (k, n, sw) => `<div><span>${sw ? `<span class="sw" style="background:${color(k)}"></span>` : ''}${k}</span><b>${n}</b></div>`;
  $('counts').innerHTML = Object.keys(c).length ? Object.entries(c).map(([k, n]) => row(k, n, 1)).join('') +
    (Object.keys(sp).length ? '<div class="hint" style="border:0;margin-top:8px">Top species</div>' +
     Object.entries(sp).sort((a, b) => b[1] - a[1]).map(([k, n]) => row(k, n)).join('') : '') : '<div class="hint">None above this confidence</div>';
}
function detail() {
  if (!sel) { $('detail').innerHTML = result ? `<span class="hint">Click a box for details. ${cap ? '' : 'Drag to pan, '}scroll or pinch to zoom, F to fit.</span>` : ''; return; }
  const w = sel.x2 - sel.x1, h = sel.y2 - sel.y1, mm = result.ppm ? ` · ${(Math.max(w, h) / result.ppm).toFixed(1)} mm long` : '';
  $('detail').innerHTML = `<b style="color:${color(sel.cls)}">${sel.cls}</b> · conf ${sel.conf.toFixed(2)}${mm}` +
    (sel.species ? '<br>' + sel.species.map(([s, p]) => `${s} ${(p * 100).toFixed(0)}%`).join(' · ') : '');
}

const cv = $('cv'), ctx = cv.getContext('2d');
function fit() {
  const r = cv.getBoundingClientRect(); if (!src()) return;
  view.s = Math.min(r.width / srcW(), r.height / srcH()) * 0.97;
  view.x = (r.width - srcW() * view.s) / 2; view.y = (r.height - srcH() * view.s) / 2;
}
function draw() {
  const r = cv.getBoundingClientRect(), d = devicePixelRatio;
  cv.width = r.width * d; cv.height = r.height * d; ctx.setTransform(d, 0, 0, d, 0, 0); ctx.clearRect(0, 0, r.width, r.height);
  if (!src()) return;
  const X = x => view.x + x * view.s, Y = y => view.y + y * view.s;
  ctx.drawImage(src(), view.x, view.y, srcW() * view.s, srcH() * view.s);
  if (cap) {  // dim everything outside the box
    ctx.fillStyle = 'rgba(0,0,0,.45)'; ctx.beginPath(); ctx.rect(view.x, view.y, srcW() * view.s, srcH() * view.s);
    ctx.rect(X(box.x), Y(box.y + box.h), box.w * view.s, -box.h * view.s); ctx.fill('evenodd');
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.setLineDash([6, 4]); ctx.strokeRect(X(box.x), Y(box.y), box.w * view.s, box.h * view.s);
    ctx.setLineDash([]); ctx.fillStyle = '#fff'; ctx.fillRect(X(box.x + box.w) - 7, Y(box.y + box.h) - 7, 14, 14);
  }
  for (const b of shown()) {
    ctx.strokeStyle = color(b.cls); ctx.lineWidth = b === sel ? 3 : 1.5;
    ctx.strokeRect(X(off.x + b.x1), Y(off.y + b.y1), (b.x2 - b.x1) * view.s, (b.y2 - b.y1) * view.s);
  }
}
addEventListener('resize', () => { fit(); draw(); });
addEventListener('keydown', e => { if (e.key === 'f' && e.target.tagName !== 'INPUT') { fit(); draw(); } });
let drag = null;
const toSrc = e => { const r = cv.getBoundingClientRect(); return {x: (e.clientX - r.left - view.x) / view.s, y: (e.clientY - r.top - view.y) / view.s}; };
cv.onpointerdown = e => {
  drag = {x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false}; cv.setPointerCapture(e.pointerId);
  if (cap) {  // resize from the corner handle, move from inside, or draw a new box from outside
    const p = toSrc(e), h = 12 / view.s, b = {...box};
    drag.box = b; drag.p = p;
    drag.mode = Math.abs(p.x - (b.x + b.w)) < h && Math.abs(p.y - (b.y + b.h)) < h ? 'resize'
      : p.x > b.x && p.x < b.x + b.w && p.y > b.y && p.y < b.y + b.h ? 'move' : 'new';
  }
};
cv.onpointermove = e => {
  if (cap && !drag) { const p = toSrc(e), h = 12 / view.s;
    cv.style.cursor = Math.abs(p.x - (box.x + box.w)) < h && Math.abs(p.y - (box.y + box.h)) < h ? 'nwse-resize'
      : p.x > box.x && p.x < box.x + box.w && p.y > box.y && p.y < box.y + box.h ? 'move' : 'crosshair'; return; }
  if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
  if (!cap) { view.x = drag.vx + dx; view.y = drag.vy + dy; draw(); return; }
  if (!drag.moved) return;
  const p = toSrc(e), b = drag.box, W = srcW(), H = srcH(), clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  if (drag.mode === 'move') box = {...b, x: clamp(b.x + p.x - drag.p.x, 0, W - b.w), y: clamp(b.y + p.y - drag.p.y, 0, H - b.h)};
  else if (drag.mode === 'resize') box = {...b, w: clamp(p.x - b.x, 32, W - b.x), h: clamp(p.y - b.y, 32, H - b.y)};
  else { const x1 = clamp(Math.min(p.x, drag.p.x), 0, W), y1 = clamp(Math.min(p.y, drag.p.y), 0, H);
    box = {x: x1, y: y1, w: Math.max(32, clamp(Math.max(p.x, drag.p.x), 0, W) - x1), h: Math.max(32, clamp(Math.max(p.y, drag.p.y), 0, H) - y1)}; }
  result = null; counts();  // old boxes no longer line up
};
cv.onpointerup = e => {
  if (drag && !drag.moved && result) {
    const p = toSrc(e), x = p.x - off.x, y = p.y - off.y;
    const hits = shown().filter(b => x >= b.x1 && x <= b.x2 && y >= b.y1 && y <= b.y2);
    sel = hits.sort((a, b) => (a.x2 - a.x1) * (a.y2 - a.y1) - (b.x2 - b.x1) * (b.y2 - b.y1))[0] || null; detail(); draw();
  }
  drag = null;
};
cv.addEventListener('wheel', e => {
  e.preventDefault(); const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  if (e.ctrlKey || !e.deltaX && Math.abs(e.deltaY) > 40) {  // pinch or mouse wheel: zoom at the cursor
    const f = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.002));
    view.x = mx - (mx - view.x) * f; view.y = my - (my - view.y) * f; view.s *= f;
  } else { view.x -= e.deltaX; view.y -= e.deltaY; }
  draw();
}, {passive: false});
loadModels(); draw();
</script></body></html>
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args(argv)
    print(f"Model playground: http://localhost:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
