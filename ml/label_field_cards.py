"""Label the insects crop_field_cards.py found, and box the ones it missed, in the browser.

    python label_field_cards.py                 # then open http://localhost:8765
    python label_field_cards.py --port 9000

Reads and writes data/field/labels.csv (saved after every change). Standard library + Pillow only.

In the page there are two passes (buttons on the right; the page remembers which):
  pass 1, anyone:   click a box, then 1 moth  2 other_insect (not a moth)  3 debris (on the card, not an insect)
  pass 2, an expert: 1 CM  2 OFM  3 OBLR  4 lookalike_RBLR  5 lookalike_LAW  6 other_tortricid  7 other_moth
                     8 other_insect  9 debris  0 moth (unsure); Tab visits the boxes still marked plain `moth`
  Delete / Backspace  not a bug or off the card: a box you drew is removed, flatbug's becomes `skip`
                      (drawn faintly; select it and press a number to bring it back)
  drag on empty space box an insect flatbug missed (source=manual)
  selected box        drag a corner or edge to resize, inside to move; flatbug's become source=flatbug-edited
  Cmd/Ctrl+Z          undo (Shift+Cmd+Z or Ctrl+Y redo), also the Undo / Redo buttons
  Tab / Shift+Tab     next / previous box to do;  ] / [  next / previous photo;  F  fit the photo
  scroll              zoom at the cursor; right-drag or Space+drag pans
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median
from urllib.parse import unquote

from PIL import Image, ImageOps

from crop_field_cards import FIELDS, server_crop

# Pass 1 (anyone): moth / other_insect / debris, Delete = skip. Pass 2 (a trained eye): the species.
SPECIES = ["CM", "OFM", "OBLR", "lookalike_RBLR", "lookalike_LAW", "other_tortricid", "other_moth"]


class Store:
    def __init__(self, data: Path):
        self.data = data
        self.path = data / "labels.csv"
        self.lock = threading.Lock()
        with open(self.path, newline="") as f:
            self.rows = list(csv.DictReader(f))
        for r in self.rows:  # labels.csv from before the source column
            r["source"] = r.get("source") or "flatbug"

    def photos(self) -> list[str]:
        return sorted(p.name for p in (self.data / "inbox").iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))

    def save(self, photo: str, boxes: list[dict]) -> list[dict]:
        """Replace one photo's rows. New boxes, and boxes moved or resized, get a fresh crop and length."""
        with self.lock:
            old = {r["n"]: r for r in self.rows if r["photo"] == photo}
            ppms = [float(r["ppm"]) for r in old.values() if r.get("ppm")]
            ppm = median(ppms) if ppms else None
            img = None
            stem = Path(photo).stem
            next_n = max([int(n) for n in old] + [0]) + 1
            rows = []
            for b in boxes:
                box = [int(round(float(b[k]))) for k in ("x1", "y1", "x2", "y2")]
                r = dict(old.get(str(b.get("n")), {}))
                if not r:  # drawn by hand
                    r = {"photo": photo, "n": str(next_n), "source": "manual", "conf": ""}
                    next_n += 1
                    moved = True
                else:
                    moved = box != [int(r[k]) for k in ("x1", "y1", "x2", "y2")]
                if moved:
                    if r["source"] == "flatbug":
                        r["source"] = "flatbug-edited"  # flatbug found it, but its box was off
                    if r["source"] != "manual":
                        r["crop"] = str(self.data / "crops" / stem / f"{stem}_{int(r['n']):02d}e.jpg")
                    else:
                        r["crop"] = str(self.data / "crops" / stem / f"{stem}_m{r['n']}.jpg")
                    r["cutout"] = ""  # flatbug's outline no longer matches the box; re-segment later
                    if img is None:
                        with Image.open(self.data / "inbox" / photo) as im:
                            img = ImageOps.exif_transpose(im).convert("RGB")
                    Path(r["crop"]).parent.mkdir(parents=True, exist_ok=True)
                    server_crop(img, box).save(r["crop"], quality=92)
                    long_px = max(box[2] - box[0], box[3] - box[1])
                    r.update({"x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3],
                              "ppm": r.get("ppm") or (f"{ppm:.2f}" if ppm else ""),
                              "length_mm": f"{long_px / ppm:.1f}" if ppm else ""})
                r["label"] = b.get("label", "")
                rows.append(r)
            self.rows = [r for r in self.rows if r["photo"] != photo] + rows
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
                w.writeheader()
                w.writerows(self.rows)
            tmp.replace(self.path)
            return [self.view(r) for r in rows]

    @staticmethod
    def view(r: dict) -> dict:
        return {"n": r["n"], "label": r.get("label", ""), "source": r.get("source") or "flatbug",
                "x1": float(r["x1"]), "y1": float(r["y1"]), "x2": float(r["x2"]), "y2": float(r["y2"]),
                "conf": r.get("conf", ""), "length_mm": r.get("length_mm", "")}


def handler(store: Store):
    page = PAGE.replace("__SPECIES__", json.dumps(SPECIES))

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, body: bytes, ctype: str, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                return self.send(page.encode(), "text/html; charset=utf-8")
            if self.path == "/api/data":
                by = {p: [] for p in store.photos()}
                for r in store.rows:
                    by.setdefault(r["photo"], []).append(store.view(r))
                return self.send(json.dumps(by).encode(), "application/json")
            if self.path.startswith("/img/"):
                name = Path(unquote(self.path[5:])).name  # no path tricks: inbox files only
                p = store.data / "inbox" / name
                if p.is_file():
                    return self.send(p.read_bytes(), "image/jpeg")
            self.send(b"not found", "text/plain", 404)

        def do_POST(self):
            if self.path != "/api/save":
                return self.send(b"not found", "text/plain", 404)
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if body["photo"] not in store.photos():
                return self.send(b"unknown photo", "text/plain", 400)
            rows = store.save(body["photo"], body["boxes"])
            self.send(json.dumps(rows).encode(), "application/json")

    return H


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Field card labels</title>
<style>
  :root { --bg:#f6f6f4; --panel:#fff; --ink:#1d1d1b; --mute:#6b6b66; --line:#dddcd6; }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.4 -apple-system, system-ui, sans-serif; color:var(--ink); background:var(--bg);
         display:grid; grid-template-columns:240px 1fr 260px; height:100vh; overflow:hidden; }
  aside { background:var(--panel); border-right:1px solid var(--line); overflow:auto; padding:12px; }
  aside.right { border-right:0; border-left:1px solid var(--line); }
  h2 { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--mute); margin:14px 0 6px; }
  .photo { padding:6px 8px; border-radius:6px; cursor:pointer; display:flex; justify-content:space-between; gap:8px; }
  .photo:hover { background:#f0f0ec; } .photo.on { background:#1d1d1b; color:#fff; }
  .photo .name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .photo .count { font-variant-numeric:tabular-nums; opacity:.7; }
  .photo.done .count::after { content:" ✓"; }
  main { position:relative; overflow:hidden; background:#2a2a28; }
  canvas { display:block; }
  .modes { display:flex; gap:4px; }
  .modes button { flex:1; font:inherit; font-size:12px; padding:6px; border:1px solid var(--line); background:#fff; border-radius:6px; cursor:pointer; }
  .modes button.on { background:#1d1d1b; color:#fff; border-color:#1d1d1b; }
  .modes button:disabled { opacity:.4; cursor:default; }
  .key { display:grid; grid-template-columns:22px 1fr auto; gap:4px 8px; align-items:center; }
  .key kbd { font:12px ui-monospace, monospace; border:1px solid var(--line); border-radius:4px; text-align:center; padding:1px 0; }
  .sw { width:12px; height:12px; border-radius:3px; display:inline-block; vertical-align:-1px; }
  .key .n { color:var(--mute); font-variant-numeric:tabular-nums; }
  #zoom { width:100%; aspect-ratio:1; background:#eee; border-radius:6px; }
  #info { color:var(--mute); margin-top:6px; min-height:3em; }
  #status { position:absolute; left:12px; bottom:12px; color:#fff; background:#0008; padding:4px 8px; border-radius:6px; font-size:12px; }
  .help { color:var(--mute); font-size:12px; }
  .help b { color:var(--ink); font-weight:600; }
</style></head><body>
<aside><h2>Photos</h2><div id="photos"></div>
  <h2>How</h2><div class="help" id="help"></div></aside>
<main id="main"><canvas id="cv"></canvas><div id="status"></div></main>
<aside class="right">
  <div class="modes"><button id="undo" title="⌘Z">↶ Undo</button><button id="redo" title="⇧⌘Z">↷ Redo</button></div>
  <h2>Pass</h2><div class="modes"><button data-m="1">1 · moth / insect / debris</button><button data-m="2">2 · species</button></div>
  <h2>Selected</h2><canvas id="zoom" width="256" height="256"></canvas><div id="info">Nothing selected</div>
  <h2>Keys</h2><div class="key" id="key"></div></aside>
<script>
const SPECIES = __SPECIES__;
const KEYS = {  // key -> label, per pass
  1: {"1":"moth", "2":"other_insect", "3":"debris"},
  2: {"1":"CM","2":"OFM","3":"OBLR","4":"lookalike_RBLR","5":"lookalike_LAW","6":"other_tortricid","7":"other_moth",
      "8":"other_insect","9":"debris","0":"moth"},
};
const NAMES = {moth:"moth (species later)", other_insect:"other insect (not a moth)", debris:"debris (not an insect)"};
const isMoth = l => l === "moth" || SPECIES.includes(l);
function colorOf(l) {
  if (!l) return "#d946ef";
  if (l === "other_insect") return "#16a34a";
  if (l === "debris") return "#a8a29e";
  if (l === "skip") return "#ffffff55";
  return l === "moth" ? "#f97316" : "#2563eb";  // species named: blue
}
const HELP = {
  1: `<b>Click</b> a box, then <b>1</b> moth · <b>2</b> other insect · <b>3</b> debris.<br>
      <b>Delete</b>: not a bug, or off the card: the box disappears.<br>
      <b>Drag</b> on empty space: box a missed insect.<br>
      <b>Selected box</b>: drag a corner or edge to resize, drag inside to move.<br>
      <b>⌘Z</b> undo · <b>⇧⌘Z</b> redo<br>
      <b>Tab</b> next unlabelled · <b>[ ]</b> photos<br><b>Scroll</b> zoom · <b>right-drag</b> pan · <b>F</b> fit<br><br>
      <b>debris</b>: on the card, not an insect (leaf bits, loose legs, scales, glue blobs). Keep these: the trap sees them too.<br>
      One box over two insects: resize it to one and draw the other.`,
  2: `Species, by a trained eye. <b>Tab</b> jumps to the next box still marked plain <b>moth</b>.<br>
      <b>0</b> = moth, species unsure. <b>8 / 9</b> fix a pass-1 label.<br>
      Boxes, resizing and Delete work as in pass 1.`,
};
let pass = 1; try { pass = Number(localStorage.getItem("pass")) || 1; } catch (e) {}
let data = {}, photo = null, img = new Image(), sel = -1;
let view = {s:1, x:0, y:0}, drag = null, space = false;
const cv = document.getElementById("cv"), ctx = cv.getContext("2d"), main = document.getElementById("main");
const zc = document.getElementById("zoom").getContext("2d");

async function load() {
  data = await (await fetch("/api/data")).json();
  const first = Object.keys(data).find(p => data[p].some(todo)) || Object.keys(data)[0];
  setPass(pass); open(first); undoButtons();
}
const todo = b => pass === 1 ? !b.label : b.label === "moth";
function boxes() { return data[photo]; }
function setPass(m) {
  pass = m; try { localStorage.setItem("pass", m); } catch (e) {}
  document.querySelectorAll(".modes button").forEach(b => b.classList.toggle("on", Number(b.dataset.m) === m));
  document.getElementById("help").innerHTML = HELP[m];
  if (photo) { renderList(); draw(); }
}
document.querySelectorAll(".modes button").forEach(b => b.onclick = () => setPass(Number(b.dataset.m)));
function renderList() {
  document.getElementById("photos").innerHTML = Object.keys(data).map(p => {
    const bs = data[p].filter(b => b.label !== "skip");
    const [done, all] = pass === 1 ? [bs.filter(b => b.label).length, bs.length]
                                   : [bs.filter(b => SPECIES.includes(b.label)).length, bs.filter(b => isMoth(b.label)).length];
    return `<div class="photo ${p===photo?"on":""} ${all && done===all?"done":""}" data-p="${encodeURIComponent(p)}"><span class="name">${p.replace(/\.RAW-01\.COVER/,"")}</span><span class="count">${done}/${all}</span></div>`;
  }).join("");
  document.querySelectorAll(".photo").forEach(el => el.onclick = () => open(decodeURIComponent(el.dataset.p)));
  const counts = {}; Object.values(data).flat().forEach(b => counts[b.label] = (counts[b.label]||0) + 1);
  const keys = Object.entries(KEYS[pass]).sort((a,b) => (a[0]==="0") - (b[0]==="0") || a[0]-b[0]);
  document.getElementById("key").innerHTML = keys.map(([k,l]) =>
    `<kbd>${k}</kbd><span><span class="sw" style="background:${colorOf(l)}"></span> ${pass===1 ? NAMES[l] : (k==="0" ? "moth, unsure" : l)}</span><span class="n">${counts[l]||0}</span>`).join("")
    + `<kbd>⌫</kbd><span>delete (not a bug)</span><span class="n">${counts.skip||0}</span>`
    + `<kbd></kbd><span><span class="sw" style="background:${colorOf("")}"></span> unlabelled</span><span class="n">${counts[""]||0}</span>`;
}
function open(p) {
  photo = p; sel = -1; img = new Image();
  img.onload = () => { fit(); draw(); };
  img.src = "/img/" + encodeURIComponent(p);
  renderList(); showSel();
}
function fit() {
  cv.width = main.clientWidth; cv.height = main.clientHeight;
  const s = Math.min(cv.width / img.width, cv.height / img.height);
  view = {s, x:(cv.width - img.width*s)/2, y:(cv.height - img.height*s)/2};
}
const toImg = (mx,my) => [(mx - view.x)/view.s, (my - view.y)/view.s];
const toScr = (x,y) => [x*view.s + view.x, y*view.s + view.y];
function handles(b) {  // 8 resize handles in screen px
  const [x1,y1] = toScr(b.x1,b.y1), [x2,y2] = toScr(b.x2,b.y2), xm = (x1+x2)/2, ym = (y1+y2)/2;
  return {nw:[x1,y1], n:[xm,y1], ne:[x2,y1], e:[x2,ym], se:[x2,y2], s:[xm,y2], sw:[x1,y2], w:[x1,ym]};
}
function grabAt(mx, my) {  // what dragging at this screen point would do to the selected box
  if (sel < 0) return null;
  const b = boxes()[sel];
  for (const [k,[hx,hy]] of Object.entries(handles(b))) if (Math.abs(mx-hx) <= 8 && Math.abs(my-hy) <= 8) return k;
  const [x,y] = toImg(mx,my);
  return (x>=b.x1 && x<=b.x2 && y>=b.y1 && y<=b.y2) ? "move" : null;
}
function draw() {
  ctx.setTransform(1,0,0,1,0,0); ctx.fillStyle = "#2a2a28"; ctx.fillRect(0,0,cv.width,cv.height);
  if (!img.complete || !photo) return;
  ctx.setTransform(view.s,0,0,view.s,view.x,view.y);
  ctx.drawImage(img,0,0);
  const lw = 1/view.s;
  boxes().forEach((b,i) => {
    if (b.label === "skip" && i !== sel) {  // deleted: barely there, so you can still undo it
      ctx.strokeStyle = "#ffffff40"; ctx.lineWidth = lw; ctx.setLineDash([3*lw,5*lw]);
      ctx.strokeRect(b.x1, b.y1, b.x2-b.x1, b.y2-b.y1); ctx.setLineDash([]); return;
    }
    ctx.strokeStyle = colorOf(b.label); ctx.lineWidth = (i===sel?3:2)*lw;
    ctx.setLineDash(b.label ? [] : [6*lw,4*lw]);
    ctx.strokeRect(b.x1, b.y1, b.x2-b.x1, b.y2-b.y1);
    ctx.setLineDash([]);
    const t = (b.label ? (b.label==="other_insect" ? "insect" : b.label) : "?") + (b.source==="manual" ? " ✎" : "");
    ctx.font = `${12*lw}px system-ui`; const w = ctx.measureText(t).width + 6*lw;
    ctx.fillStyle = colorOf(b.label); ctx.fillRect(b.x1, b.y1 - 16*lw, w, 16*lw);
    ctx.fillStyle = b.label === "debris" ? "#1d1d1b" : "#fff"; ctx.fillText(t, b.x1 + 3*lw, b.y1 - 4*lw);
  });
  ctx.setTransform(1,0,0,1,0,0);
  if (sel >= 0 && boxes()[sel]) {
    ctx.fillStyle = "#fff"; ctx.strokeStyle = "#1d1d1b"; ctx.lineWidth = 1;
    Object.values(handles(boxes()[sel])).forEach(([x,y]) => { ctx.fillRect(x-4,y-4,8,8); ctx.strokeRect(x-4,y-4,8,8); });
  }
  if (drag && drag.mode === "box") {
    const [a,b] = [toScr(...drag.start), toScr(...drag.end)];
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.setLineDash([4,4]); ctx.strokeRect(a[0],a[1],b[0]-a[0],b[1]-a[1]); ctx.setLineDash([]);
  }
}
function showSel() {
  const info = document.getElementById("info");
  zc.fillStyle = "#eee"; zc.fillRect(0,0,256,256);
  if (sel < 0 || !boxes()[sel]) { info.textContent = "Nothing selected"; return; }
  const b = boxes()[sel], side = Math.max(b.x2-b.x1, b.y2-b.y1) * 1.7, cx = (b.x1+b.x2)/2, cy = (b.y1+b.y2)/2;
  if (img.complete) zc.drawImage(img, cx-side/2, cy-side/2, side, side, 0, 0, 256, 256);
  const lab = b.label === "skip" ? "deleted (press a number to bring back)" : (b.label || "unlabelled");
  info.innerHTML = `#${b.n ?? "new"} · <b>${lab}</b><br>${b.source}${b.conf?" · conf "+b.conf:""}${b.length_mm?" · ~"+b.length_mm+" mm":""}`;
}
// Undo history: a copy of a photo's boxes taken just before each change.
let undoStack = [], redoStack = [];
const snap = () => ({photo, boxes: JSON.parse(JSON.stringify(boxes())), sel});
function record(s = snap()) { undoStack.push(s); if (undoStack.length > 200) undoStack.shift(); redoStack = []; undoButtons(); }
function restore(from, to) {
  const s = from.pop(); if (!s) return;
  if (s.photo !== photo) open(s.photo);
  to.push(snap());
  data[s.photo] = s.boxes; sel = s.sel < s.boxes.length ? s.sel : -1;
  changed();
}
function undoButtons() {
  document.getElementById("undo").disabled = !undoStack.length;
  document.getElementById("redo").disabled = !redoStack.length;
}
document.getElementById("undo").onclick = () => restore(undoStack, redoStack);
document.getElementById("redo").onclick = () => restore(redoStack, undoStack);

let saveTimer = null, dirty = new Set();
function changed() {
  undoButtons();
  draw(); renderList(); showSel();
  dirty.add(photo); setStatus("saving…");
  clearTimeout(saveTimer); saveTimer = setTimeout(flush, 300);
}
async function flush() {
  for (const p of [...dirty]) {
    dirty.delete(p);
    try {
      const sent = data[p];
      const r = await fetch("/api/save", {method:"POST", headers:{"Content-Type":"application/json"},
                            body: JSON.stringify({photo:p, boxes:sent})});
      if (!r.ok) throw new Error(await r.text());
      const rows = await r.json();
      // keep anything changed while the save was in flight; just learn the new ids
      if (data[p] === sent && sent.length === rows.length)
        sent.forEach((b,i) => { b.n = rows[i].n; b.source = rows[i].source; b.length_mm = rows[i].length_mm; });
      setStatus("saved");
    } catch (e) { dirty.add(p); setStatus("NOT SAVED: " + e.message); }
  }
  if (photo) { renderList(); showSel(); }
}
window.addEventListener("beforeunload", e => { if (dirty.size) { flush(); e.preventDefault(); } });
function setStatus(t) { document.getElementById("status").textContent = t; }
function hit(x,y) {  // smallest box under the point; deleted boxes only if nothing else is there
  let best = -1, key = Infinity;
  boxes().forEach((b,i) => { const k = (b.x2-b.x1)*(b.y2-b.y1) * (b.label === "skip" ? 1e6 : 1);
    if (x>=b.x1 && x<=b.x2 && y>=b.y1 && y<=b.y2 && k < key) { best = i; key = k; } });
  return best;
}
const CURSORS = {nw:"nwse-resize", se:"nwse-resize", ne:"nesw-resize", sw:"nesw-resize", n:"ns-resize", s:"ns-resize", e:"ew-resize", w:"ew-resize", move:"move"};
cv.addEventListener("contextmenu", e => e.preventDefault());
cv.addEventListener("mousedown", e => {
  const p = toImg(e.offsetX, e.offsetY);
  if (e.button === 2 || space) { drag = {mode:"pan", mx:e.offsetX, my:e.offsetY, vx:view.x, vy:view.y}; return; }
  const g = grabAt(e.offsetX, e.offsetY);
  if (g && (g !== "move" || hit(...p) === sel)) {
    const b = boxes()[sel]; drag = {mode:"edit", edges:g, start:p, orig:{...b}, before:snap(), moved:false}; return;
  }
  const h = hit(...p);
  if (h >= 0) { sel = h; draw(); showSel(); return; }
  sel = -1; drag = {mode:"box", start:p, end:p}; draw(); showSel();
});
window.addEventListener("mousemove", e => {
  const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  if (!drag) { if (e.target === cv) { const g = grabAt(mx, my); cv.style.cursor = g ? CURSORS[g] : "crosshair"; } return; }
  if (drag.mode === "pan") { view.x = drag.vx + mx - drag.mx; view.y = drag.vy + my - drag.my; }
  else if (drag.mode === "box") drag.end = toImg(mx, my);
  else {
    const [x,y] = toImg(mx, my), dx = x - drag.start[0], dy = y - drag.start[1], o = drag.orig, b = boxes()[sel], k = drag.edges;
    if (k === "move") { b.x1 = o.x1+dx; b.x2 = o.x2+dx; b.y1 = o.y1+dy; b.y2 = o.y2+dy; }
    else {
      if (k.includes("w")) b.x1 = o.x1 + dx; if (k.includes("e")) b.x2 = o.x2 + dx;
      if (k.includes("n")) b.y1 = o.y1 + dy; if (k.includes("s")) b.y2 = o.y2 + dy;
    }
    drag.moved = Math.abs(dx)*view.s > 1 || Math.abs(dy)*view.s > 1;
    showSel();
  }
  draw();
});
window.addEventListener("mouseup", () => {
  if (drag && drag.mode === "box") {
    const [a,b] = [drag.start, drag.end];
    const x1 = Math.min(a[0],b[0]), x2 = Math.max(a[0],b[0]), y1 = Math.min(a[1],b[1]), y2 = Math.max(a[1],b[1]);
    if ((x2-x1)*view.s > 6 && (y2-y1)*view.s > 6) {
      record();
      boxes().push({n:null, label: pass === 1 ? "" : "moth", source:"manual", x1, y1, x2, y2, conf:"", length_mm:""});
      sel = boxes().length - 1; changed();
    }
  } else if (drag && drag.mode === "edit") {
    const b = boxes()[sel];
    [b.x1, b.x2] = [Math.min(b.x1,b.x2), Math.max(b.x1,b.x2)]; [b.y1, b.y2] = [Math.min(b.y1,b.y2), Math.max(b.y1,b.y2)];
    if (drag.moved) { record(drag.before); changed(); }
  }
  drag = null; draw();
});
cv.addEventListener("wheel", e => {
  e.preventDefault();
  const k = Math.exp(-e.deltaY * 0.0015), [ix,iy] = toImg(e.offsetX, e.offsetY);
  view.s *= k; view.x = e.offsetX - ix*view.s; view.y = e.offsetY - iy*view.s; draw();
}, {passive:false});
window.addEventListener("keyup", e => { if (e.key === " ") space = false; });
window.addEventListener("keydown", e => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
    e.preventDefault();
    if (e.shiftKey) restore(redoStack, undoStack); else restore(undoStack, redoStack);
    return;
  }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "y") { e.preventDefault(); restore(redoStack, undoStack); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;  // leave browser shortcuts alone
  if (e.key === " ") { space = true; e.preventDefault(); return; }
  const names = Object.keys(data), pi = names.indexOf(photo);
  if (e.key === "]") return open(names[(pi+1) % names.length]);
  if (e.key === "[") return open(names[(pi-1+names.length) % names.length]);
  if (e.key === "f" || e.key === "F") { fit(); draw(); return; }
  if (e.key === "Tab") {
    e.preventDefault();
    const bs = boxes(), step = e.shiftKey ? -1 : 1;
    for (let k = 1; k <= bs.length; k++) {
      const i = ((sel < 0 ? (step>0?-1:0) : sel) + step*k + bs.length*2) % bs.length;
      if (todo(bs[i])) { sel = i; zoomTo(bs[i]); draw(); showSel(); return; }
    }
    setStatus(pass === 1 ? "every box on this photo is labelled" : "no plain 'moth' boxes left on this photo"); return;
  }
  if (e.key === "Escape") { sel = -1; draw(); showSel(); return; }
  if (sel < 0) return;
  const l = KEYS[pass][e.key];
  if (l) { if (boxes()[sel].label !== l) { record(); boxes()[sel].label = l; changed(); } return; }
  if (e.key === "Delete" || e.key === "Backspace") {
    e.preventDefault();
    record();
    const b = boxes()[sel];
    if (b.source === "manual") boxes().splice(sel, 1); else b.label = "skip";  // flatbug's: kept as a false hit
    sel = -1; changed();
  }
});
function zoomTo(b) {
  const r = main.getBoundingClientRect();
  const want = Math.min(r.width, r.height) / (Math.max(b.x2-b.x1, b.y2-b.y1) * 4);
  if (view.s < want * 0.5) view.s = want;
  view.x = r.width/2 - (b.x1+b.x2)/2*view.s; view.y = r.height/2 - (b.y1+b.y2)/2*view.s;
}
window.addEventListener("resize", () => { if (img.complete) { fit(); draw(); } });
load();
</script></body></html>
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/field"))
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    if not (args.data / "labels.csv").exists():
        raise SystemExit(f"no {args.data / 'labels.csv'}: run crop_field_cards.py first")
    store = Store(args.data)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), handler(store))
    print(f"Labelling {len(store.rows)} boxes on {len(store.photos())} photos: http://localhost:{args.port}  (Ctrl+C to stop)")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
