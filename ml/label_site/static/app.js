"use strict";
// Liner labelling site. One photo (one task) at a time; saves go to /api/save 300 ms after each change.
const KEYS = {
  1: {"1":"moth", "2":"other_insect", "3":"debris"},
  2: {"1":"CM","2":"OFM","3":"OBLR","4":"lookalike_RBLR","5":"lookalike_LAW","6":"other_tortricid","7":"other_moth",
      "8":"other_insect","9":"debris","0":"moth"},
};
const NAMES = {moth:"moth", other_insect:"other insect", debris:"debris"};
const SPECIES = ["CM","OFM","OBLR","lookalike_RBLR","lookalike_LAW","other_tortricid","other_moth"];
const ATTR_KEYS = {o:"overlapping", e:"cut_off", w:"decayed", u:"unsure"};
const DETECTOR_SOURCES = new Set(["yolo","baseline","flatbug"]);
const $ = id => document.getElementById(id);
const esc = t => String(t ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const isMoth = l => l === "moth" || SPECIES.includes(l);
const attrsOf = b => (b.attrs || "").split(",").filter(Boolean);
const unchecked = b => b.label !== "skip" && (!b.by || !b.label);  // a box nobody has given a label counts as to do

let me = {}, queue = {tasks:[], review:[]}, tab = "mine";
let task = null, photo = null, boxes = [], version = null, issues = [], tags = [];
let pass = 1, img = new Image(), sel = -1, view = {s:1, x:0, y:0}, fitScale = 1;
let drag = null, space = false, drawMode = false, pendingIssue = null;
let undoStack = [], redoStack = [], saveTimer = null, dirty = false, saving = false;
try { pass = Number(localStorage.getItem("pass")) || 1; } catch (e) {}
const cv = $("cv"), ctx = cv.getContext("2d"), main = $("main"), zc = $("zoom").getContext("2d");

async function api(path, body) {
  const opt = body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json", "X-CSRF": me.csrf}, body: JSON.stringify(body)};
  const r = await fetch(path, opt);
  if (r.status === 401) { location.href = "/login"; throw new Error("logged out"); }
  return r;
}

// ---------- queue
async function loadQueue() {
  queue = await (await api("/api/queue")).json();
  renderQueue();
}
function renderQueue() {
  const items = tab === "mine" ? queue.tasks : queue.review;
  const open = queue.tasks.filter(t => t.status === "open" || t.status === "returned").length;
  $("queueInfo").textContent = tab === "mine" ? `${open} to do · ${queue.tasks.length - open} finished` : `${items.length} waiting for review`;
  $("queue").innerHTML = items.map(t => {
    const short = t.photo.replace(/\.RAW-01\.COVER/, "").replace(/__/, " · ");
    const badge = tab === "review" ? `<span class="badge">${esc(t.user)}</span>`
      : (t.kind !== "label" ? `<span class="badge">${esc(t.kind)}</span>` : "")
        + (t.status === "returned" ? `<span class="badge">sent back</span>` : t.status === "done" ? `<span class="badge">in review</span>`
           : t.status === "accepted" ? `<span class="badge">accepted ✓</span>` : "");
    const count = tab === "mine" ? `${t.n - t.unchecked}/${t.n}` : "";
    const sub = tab === "mine" && (t.issues || t.note) ? `<span class="sub">${t.issues ? t.issues + " comment(s)" : ""} ${esc(t.note || "")}</span>` : "";
    return `<div class="item ${task && t.id === task.id ? "on" : ""}" data-id="${t.id}"><span class="name">${esc(short)}${badge}</span><span class="count">${count}</span>${sub}</div>`;
  }).join("") || `<p class="mute">Nothing here.</p>`;
  document.querySelectorAll(".item").forEach(el => el.onclick = () => openTask(Number(el.dataset.id)));
}
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
  tab = b.dataset.tab; document.querySelectorAll(".tabs button").forEach(x => x.classList.toggle("on", x === b)); renderQueue(); });

// ---------- one photo
async function openTask(id) {
  if (dirty) await flush();
  const d = await (await api(`/api/photo?task=${id}`)).json();
  task = d.task; photo = d.photo; boxes = d.boxes; version = d.version; issues = d.issues; tags = d.tags;
  sel = -1; undoStack = []; redoStack = [];
  img = new Image(); img.onload = () => { fit(); draw(); }; img.src = "/img/" + encodeURIComponent(photo.name);
  if (task.kind === "species") setPass(2);
  document.querySelectorAll("[data-tag]").forEach(c => c.checked = tags.includes(c.dataset.tag));
  const banner = $("banner");
  const msg = task.status === "returned" ? `Sent back by the reviewer: ${task.note || "see the comments"}` :
    task.kind === "tiebreak" ? "Two people disagreed on the boxes marked with comments: decide each one, then resolve the comment." :
    task.kind === "reference" ? "Reference photo: label it as carefully as you can. Others are scored against it." :
    task.kind === "species" ? "Pass 2: name the species of each moth (0 = moth, unsure)." : "";
  banner.hidden = !msg; banner.textContent = msg;
  renderQueue(); renderIssues(); renderActions(); showSel(); undoButtons();
}
function renderActions() {
  const el = $("taskActions"); el.innerHTML = "";
  if (!task) return;
  const mine = task.user === me.user;
  if (mine && task.status !== "accepted") {
    const b = document.createElement("button"); b.className = "wide primary"; b.textContent = "Done with this photo ✓";
    b.onclick = finish; el.appendChild(b);
  }
  if (me.admin && task.status === "done" && (!mine || tab === "review")) {
    el.insertAdjacentHTML("beforeend", `<textarea id="note" rows="2" placeholder="Note for the labeller (if sending back)"></textarea>
      <div class="row"><button id="accept" class="primary">Accept</button><button id="sendBack">Send back</button></div>`);
    $("accept").onclick = () => reviewTask(true); $("sendBack").onclick = () => reviewTask(false);
  }
  el.insertAdjacentHTML("beforeend", `<span class="mute">${esc(photo.name)} · ${photo.px_per_mm ? photo.px_per_mm.toFixed(1) + " px/mm" : "no scale"}${photo.why ? " · " + esc(photo.why) : ""}${photo.other_shots.length ? ` · ${photo.other_shots.length} other shot(s) of this card` : ""}</span>`);
}
let finishArmed = 0;
async function finish(e) {
  if (dirty) await flush();
  const left = boxes.filter(unchecked).length, btn = e && e.currentTarget;
  if (left && Date.now() - finishArmed > 5000) {  // a second press within 5 s finishes anyway
    finishArmed = Date.now();
    setStatus(`${left} box(es) not checked yet (Tab shows them). Press Done again to finish anyway.`);
    if (btn) btn.textContent = `Finish with ${left} unchecked?`;
    return;
  }
  finishArmed = 0;
  const r = await api("/api/done", {task: task.id});
  setStatus((await r.json()).message || "done");
  await loadQueue(); next();
}
async function reviewTask(accept) {
  const note = $("note") ? $("note").value : "";
  if (!accept && !note && !issues.some(i => !i.resolved_at)) { setStatus("say what to fix: a note or a pinned comment"); return; }
  await api("/api/review", {task: task.id, accept, note});
  setStatus(accept ? "accepted" : "sent back");
  await loadQueue(); next();
}
function next() {
  const items = tab === "mine" ? queue.tasks.filter(t => t.status === "open" || t.status === "returned") : queue.review;
  const t = items.find(t => !task || t.id !== task.id);
  if (t) openTask(t.id);
}

// ---------- saving
function changed() {
  undoButtons(); draw(); showSel(); renderKey();
  dirty = true; setStatus("saving…");
  clearTimeout(saveTimer); saveTimer = setTimeout(flush, 300);
}
async function flush() {
  if (saving || !dirty) return;
  saving = true; dirty = false;
  const sent = boxes, t = task;
  try {
    const r = await api("/api/save", {task: t.id, base: version,
      boxes: sent.map(b => ({id:b.id, x1:b.x1, y1:b.y1, x2:b.x2, y2:b.y2, label:b.label, attrs:b.attrs || "", locked:b.locked, confirm:!!b.confirm, unlock:!!b.unlock}))});
    if (r.status === 409) {
      const cur = await r.json();
      if (cur.boxes) { if (t === task) { boxes = cur.boxes; version = cur.version; sel = -1; undoStack = []; redoStack = []; draw(); }
        setStatus("someone else changed this photo just now: their version is shown; redo your last change"); }
      else setStatus(await r.text());
    } else if (!r.ok) { throw new Error(await r.text()); }
    else {
      const res = await r.json();
      if (t === task) {
        version = res.version;
        if (boxes === sent && !dirty && sent.length === res.boxes.length) { boxes = res.boxes; if (sel >= boxes.length) sel = -1; }
        else sent.forEach(b => { delete b.confirm; delete b.unlock; });
      }
      setStatus("saved");
    }
  } catch (e) { dirty = true; setStatus("NOT SAVED: " + e.message); }
  saving = false;
  if (dirty) { clearTimeout(saveTimer); saveTimer = setTimeout(flush, 300); }
  draw(); showSel(); renderKey(); updateCount();
}
function updateCount() {
  const q = queue.tasks.find(t => task && t.id === task.id);
  if (q) { q.n = boxes.filter(b => b.label !== "skip").length; q.unchecked = boxes.filter(unchecked).length; renderQueue(); }
}
window.addEventListener("beforeunload", e => { if (dirty) { flush(); e.preventDefault(); } });
function setStatus(t) { $("status").textContent = t; }

// ---------- undo
const snap = () => ({task: task && task.id, boxes: JSON.parse(JSON.stringify(boxes)), sel});
function record(s = snap()) { undoStack.push(s); if (undoStack.length > 200) undoStack.shift(); redoStack = []; undoButtons(); }
function restore(from, to) {
  const s = from.pop(); if (!s || !task || s.task !== task.id) return;
  to.push(snap()); boxes = s.boxes; sel = s.sel < boxes.length ? s.sel : -1;
  boxes.forEach(b => { if (b.locked) b.unlock = true; });
  changed();
}
function undoButtons() { $("undo").disabled = !undoStack.length; $("redo").disabled = !redoStack.length; }
$("undo").onclick = () => restore(undoStack, redoStack); $("redo").onclick = () => restore(redoStack, undoStack);

// ---------- what to show
function setPass(m) {
  pass = m; try { localStorage.setItem("pass", m); } catch (e) {}
  document.querySelectorAll(".modes button").forEach(b => b.classList.toggle("on", Number(b.dataset.m) === m));
  renderKey(); draw();
}
document.querySelectorAll(".modes button").forEach(b => b.onclick = () => setPass(Number(b.dataset.m)));
const thr = () => Number($("thr").value);
function hidden(b) {  // view only: never changes the data
  if ($("hideAll").checked) return true;
  return DETECTOR_SOURCES.has(b.source) && unchecked(b) && b.conf !== "" && Number(b.conf) < thr();
}
function inFilter(b) {
  const f = $("filter").value;
  if (b.label === "skip") return false;
  if (f === "unchecked") return unchecked(b);
  if (f === "unsure") return unchecked(b) && b.model_conf !== "" && Number(b.model_conf) < 0.8;
  if (f === "missed") return b.source === "missed-by-detector";
  if (f === "disputed") return attrsOf(b).includes("disputed");
  return true;
}
const todo = b => !hidden(b) && inFilter(b) && (pass === 1 ? (unchecked(b) || !b.label) : b.label === "moth");
function order() {  // Tab order: the filter's, least sure first when asked
  const idx = boxes.map((b, i) => i);
  if ($("filter").value === "unsure") idx.sort((i, j) => Number(boxes[i].model_conf || 1) - Number(boxes[j].model_conf || 1));
  return idx;
}
["filter", "hideAll"].forEach(id => $(id).onchange = () => draw());
$("thr").oninput = () => { $("thrv").textContent = thr().toFixed(2); draw(); };
["bri", "con", "sat"].forEach(id => $(id).oninput = () => draw());
$("resetImg").onclick = () => { $("bri").value = 100; $("con").value = 100; $("sat").value = 100; draw(); };
function colorOf(b) {
  const l = b.label;
  if (!l) return "#d946ef";
  if (l === "other_insect") return "#16a34a";
  if (l === "debris") return "#a8a29e";
  if (l === "skip") return "#ffffff55";
  return l === "moth" ? "#f97316" : "#2563eb";
}
function renderKey() {
  const counts = {}; boxes.forEach(b => counts[b.label] = (counts[b.label] || 0) + 1);
  const keys = Object.entries(KEYS[pass]).sort((a, b) => (a[0] === "0") - (b[0] === "0") || a[0] - b[0]);
  $("key").innerHTML = keys.map(([k, l]) =>
    `<kbd>${k}</kbd><span><span class="sw" style="background:${colorOf({label:l})}"></span> ${pass === 1 ? NAMES[l] : (k === "0" ? "moth, unsure" : l)}</span><span class="n">${counts[l] || 0}</span>`).join("")
    + `<kbd>⏎</kbd><span>the guess is right, next</span><span class="n">${boxes.filter(unchecked).length} left</span>`
    + `<kbd>⌫</kbd><span>delete (not on the card)</span><span class="n">${counts.skip || 0}</span>`
    + `<kbd>B</kbd><span>draw (click an insect, or drag)</span><span></span>`
    + `<kbd>Tab</kbd><span>next to check · [ ] photos</span><span></span>`
    + `<kbd>?</kbd><span>guide · right-click: comment</span><span></span>`;
}

// ---------- canvas
function fit() {
  cv.width = main.clientWidth; cv.height = main.clientHeight;
  if (!img.width) return;
  const s = Math.min(cv.width / img.width, cv.height / img.height);
  view = {s, x:(cv.width - img.width * s) / 2, y:(cv.height - img.height * s) / 2}; fitScale = s;
}
function zoomAt(mx, my, k) {
  const [ix, iy] = toImg(mx, my);
  view.s = Math.min(Math.max(view.s * k, fitScale * 0.5), 12);
  view.x = mx - ix * view.s; view.y = my - iy * view.s; draw();
}
const toImg = (mx, my) => [(mx - view.x) / view.s, (my - view.y) / view.s];
const toScr = (x, y) => [x * view.s + view.x, y * view.s + view.y];
function handles(b) {
  const [x1, y1] = toScr(b.x1, b.y1), [x2, y2] = toScr(b.x2, b.y2), xm = (x1 + x2) / 2, ym = (y1 + y2) / 2;
  return {nw:[x1,y1], n:[xm,y1], ne:[x2,y1], e:[x2,ym], se:[x2,y2], s:[xm,y2], sw:[x1,y2], w:[x1,ym]};
}
const draggable = b => !b.locked && !($("lockChecked").checked && b.by && b.by !== me.user && !me.admin) ;
function grabAt(mx, my) {
  if (sel < 0) return null;
  const b = boxes[sel]; if (!draggable(b)) return null;
  for (const [k, [hx, hy]] of Object.entries(handles(b))) if (Math.abs(mx - hx) <= 8 && Math.abs(my - hy) <= 8) return k;
  const [x, y] = toImg(mx, my);
  return (x >= b.x1 && x <= b.x2 && y >= b.y1 && y <= b.y2) ? "move" : null;
}
function hit(x, y) {
  let best = -1, key = Infinity;
  boxes.forEach((b, i) => { if (hidden(b)) return;
    const k = (b.x2 - b.x1) * (b.y2 - b.y1) * (b.label === "skip" ? 1e6 : 1);
    if (x >= b.x1 && x <= b.x2 && y >= b.y1 && y <= b.y2 && k < key) { best = i; key = k; } });
  return best;
}
function draw() {
  ctx.setTransform(1,0,0,1,0,0); ctx.fillStyle = "#2a2a28"; ctx.fillRect(0, 0, cv.width, cv.height);
  if (!img.complete || !img.width || !photo) return;
  ctx.setTransform(view.s, 0, 0, view.s, view.x, view.y);
  ctx.filter = `brightness(${$("bri").value}%) contrast(${$("con").value}%) saturate(${$("sat").value}%)`;
  ctx.drawImage(img, 0, 0); ctx.filter = "none";
  const lw = 1 / view.s, f = $("filter").value;
  boxes.forEach((b, i) => {
    if (hidden(b) && i !== sel) return;
    if (b.label === "skip" && i !== sel) {
      ctx.strokeStyle = "#ffffff40"; ctx.lineWidth = lw; ctx.setLineDash([3*lw, 5*lw]);
      ctx.strokeRect(b.x1, b.y1, b.x2 - b.x1, b.y2 - b.y1); ctx.setLineDash([]); return;
    }
    const dim = f !== "all" && !inFilter(b) && i !== sel;
    ctx.globalAlpha = dim ? 0.3 : 1;
    ctx.strokeStyle = colorOf(b); ctx.lineWidth = (i === sel ? 3 : 2) * lw;
    ctx.setLineDash(unchecked(b) ? [6*lw, 4*lw] : []);
    ctx.strokeRect(b.x1, b.y1, b.x2 - b.x1, b.y2 - b.y1); ctx.setLineDash([]);
    const a = attrsOf(b).map(x => ({overlapping:"O", cut_off:"E", decayed:"W", unsure:"U", disputed:"!"}[x])).join("");
    const t = (b.label ? (b.label === "other_insect" ? "insect" : b.label) : "?") + (unchecked(b) ? "?" : "")
      + (b.source === "manual" ? " ✎" : "") + (a ? " " + a : "") + (b.locked ? " 🔒" : "");
    ctx.font = `${12*lw}px system-ui`; const w = ctx.measureText(t).width + 6*lw;
    ctx.fillStyle = colorOf(b); ctx.fillRect(b.x1, b.y1 - 16*lw, w, 16*lw);
    ctx.fillStyle = b.label === "debris" ? "#1d1d1b" : "#fff"; ctx.fillText(t, b.x1 + 3*lw, b.y1 - 4*lw);
    ctx.globalAlpha = 1;
  });
  issues.forEach((it, k) => {  // pinned comments
    ctx.beginPath(); ctx.arc(it.x, it.y, 10*lw, 0, 7);
    ctx.fillStyle = it.resolved_at ? "#9ca3af" : "#facc15"; ctx.fill(); ctx.strokeStyle = "#1d1d1b"; ctx.lineWidth = 1.5*lw; ctx.stroke();
    ctx.fillStyle = "#1d1d1b"; ctx.font = `bold ${11*lw}px system-ui`; ctx.fillText(String(k + 1), it.x - 3.5*lw, it.y + 4*lw);
  });
  ctx.setTransform(1,0,0,1,0,0);
  if (sel >= 0 && boxes[sel] && draggable(boxes[sel])) {
    ctx.fillStyle = "#fff"; ctx.strokeStyle = "#1d1d1b"; ctx.lineWidth = 1;
    Object.values(handles(boxes[sel])).forEach(([x, y]) => { ctx.fillRect(x-4, y-4, 8, 8); ctx.strokeRect(x-4, y-4, 8, 8); });
  }
  if (drag && drag.mode === "box") {
    const [a, b] = [toScr(...drag.start), toScr(...drag.end)];
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.setLineDash([4, 4]); ctx.strokeRect(a[0], a[1], b[0]-a[0], b[1]-a[1]); ctx.setLineDash([]);
  }
}
function showSel() {
  zc.fillStyle = "#eee"; zc.fillRect(0, 0, 256, 256);
  document.querySelectorAll("#attrs button").forEach(x => x.classList.remove("on"));
  if (sel < 0 || !boxes[sel]) { $("info").textContent = "Nothing selected"; $("lock").textContent = "🔒 Lock box (L)"; return; }
  const b = boxes[sel], side = Math.max(b.x2 - b.x1, b.y2 - b.y1) * 1.7, cx = (b.x1 + b.x2) / 2, cy = (b.y1 + b.y2) / 2;
  if (img.complete && img.width) {
    zc.filter = `brightness(${$("bri").value}%) contrast(${$("con").value}%) saturate(${$("sat").value}%)`;
    zc.drawImage(img, cx - side/2, cy - side/2, side, side, 0, 0, 256, 256); zc.filter = "none";
  }
  const lab = b.label === "skip" ? "deleted (press a number to bring back)" : (b.label || "unlabelled");
  $("info").innerHTML = `<b>${esc(lab)}</b>${unchecked(b) ? " · not checked yet" : ` · checked by ${esc(b.by)}`}<br>`
    + `${esc(b.source)}${b.conf ? " · detector " + esc(b.conf) : ""}${b.detector_label ? " (" + esc(b.detector_label) + ")" : ""}`
    + (b.model_label ? `<br>classifier: ${esc(b.model_label)} ${esc(b.model_conf)}` : "")
    + (b.old_label ? `<br>earlier: ${esc(b.old_label)}` : "")
    + (b.length_mm ? `<br>~${esc(b.length_mm)} mm${b.body_mm ? " (body " + esc(b.body_mm) + ")" : ""}${b.length_from === "box" ? " from the box" : ""}` : "");
  attrsOf(b).forEach(a => { const x = document.querySelector(`#attrs [data-a="${a}"]`); if (x) x.classList.add("on"); });
  $("lock").textContent = b.locked ? "🔓 Unlock box (L)" : "🔒 Lock box (L)";
}
function zoomTo(b) {
  const r = main.getBoundingClientRect();
  const want = Math.min(r.width, r.height) / (Math.max(b.x2 - b.x1, b.y2 - b.y1) * 4);
  if (view.s < want * 0.5) view.s = want;
  view.x = r.width / 2 - (b.x1 + b.x2) / 2 * view.s; view.y = r.height / 2 - (b.y1 + b.y2) / 2 * view.s;
}
function jump(step) {
  const idx = order(), pos = sel < 0 ? -1 : idx.indexOf(sel);
  for (let k = 1; k <= idx.length; k++) {
    const i = idx[((pos < 0 ? (step > 0 ? -1 : 0) : pos) + step * k + idx.length * 2) % idx.length];
    if (todo(boxes[i])) { sel = i; zoomTo(boxes[i]); draw(); showSel(); return true; }
  }
  setStatus(pass === 1 ? "every box shown here is checked" : "no plain 'moth' boxes left"); return false;
}

// ---------- editing
function touch(b) { b.by = me.user; }
function setLabel(l) {
  const b = boxes[sel];
  if (b.label !== l || unchecked(b)) { record(); b.label = l; b.confirm = true; touch(b); changed(); }
}
function toggleAttr(a) {
  if (sel < 0) return;
  const b = boxes[sel], s = new Set(attrsOf(b));
  record(); s.has(a) ? s.delete(a) : s.add(a); b.attrs = [...s].sort().join(","); touch(b); changed();
}
document.querySelectorAll("#attrs button").forEach(x => x.onclick = () => toggleAttr(x.dataset.a));
function toggleLock() {
  if (sel < 0) return;
  const b = boxes[sel]; record();
  if (b.locked) { b.locked = false; b.unlock = true; } else b.locked = true;
  changed();
}
$("lock").onclick = toggleLock;
function setDraw(on) {
  drawMode = on; const b = $("draw");
  b.classList.toggle("on", on); b.textContent = on ? "▭ Draw box: ON (B) · click or drag" : "▭ Draw box: off (B)";
  cv.style.cursor = on ? "crosshair" : "grab";
}
$("draw").onclick = () => setDraw(!drawMode);
async function grabAtPoint(x, y) {
  setStatus("finding the insect…");
  const r = await api("/api/grab", {task: task.id, x, y});
  const box = (await r.json()).box;
  if (!box) { setStatus("nothing found there: drag a box instead"); return; }
  record();
  boxes.push({id:null, label: pass === 1 ? "" : "moth", source:"manual", by:me.user, attrs:"", locked:false, ...box});
  sel = boxes.length - 1; changed();
}

cv.addEventListener("contextmenu", e => {
  e.preventDefault();
  const [x, y] = toImg(e.offsetX, e.offsetY), i = hit(x, y);
  pendingIssue = {x, y, box_id: i >= 0 ? boxes[i].id : null};
  const m = $("issueMenu"); m.hidden = false;
  m.style.left = Math.min(e.offsetX, main.clientWidth - 250) + "px"; m.style.top = Math.min(e.offsetY, main.clientHeight - 180) + "px";
  $("issueText").value = ""; $("issueText").focus();
});
$("issueCancel").onclick = () => { $("issueMenu").hidden = true; pendingIssue = null; };
$("issueSave").onclick = async () => {
  if (!pendingIssue) return;
  await api("/api/issue", {task: task.id, ...pendingIssue, kind: $("issueKind").value, text: $("issueText").value});
  $("issueMenu").hidden = true; pendingIssue = null;
  const d = await (await api(`/api/photo?task=${task.id}`)).json(); issues = d.issues; renderIssues(); draw();
};
function renderIssues() {
  const open = issues.filter(i => !i.resolved_at);
  $("issues").innerHTML = issues.length ? `<h2>Comments (${open.length} open)</h2>` + issues.map((it, k) =>
    `<div class="issue ${it.resolved_at ? "done" : ""}"><b>${k + 1}. ${esc(it.kind.replace("_", " "))}</b> · ${esc(it.by)}<br>${esc(it.text)}
     <div class="row"><button data-go="${k}" class="small">show</button>${it.resolved_at ? `<span class="mute">resolved by ${esc(it.resolved_by)}</span>` : `<button data-res="${it.id}" class="small">resolve</button>`}</div></div>`).join("") : "";
  document.querySelectorAll("[data-go]").forEach(x => x.onclick = () => { const it = issues[Number(x.dataset.go)];
    view.s = Math.max(view.s, fitScale * 3); view.x = main.clientWidth/2 - it.x*view.s; view.y = main.clientHeight/2 - it.y*view.s; draw(); });
  document.querySelectorAll("[data-res]").forEach(x => x.onclick = async () => {
    await api("/api/issue/resolve", {task: task.id, id: Number(x.dataset.res)});
    issues.find(i => i.id === Number(x.dataset.res)).resolved_at = Date.now() / 1000; issues.find(i => i.id === Number(x.dataset.res)).resolved_by = me.user;
    renderIssues(); draw(); });
}
document.querySelectorAll("[data-tag]").forEach(c => c.onchange = () => api("/api/tag", {task: task.id, tag: c.dataset.tag, on: c.checked}));

cv.addEventListener("mousedown", e => {
  if (!photo) return;
  $("issueMenu").hidden = true;
  const mx = e.offsetX, my = e.offsetY;
  if (e.button === 1 || space) { drag = {mode:"pan", mx, my, vx:view.x, vy:view.y, click:null}; return; }
  if (e.button !== 0) return;
  if (drawMode || e.shiftKey) { drag = {mode:"box", start:toImg(mx, my), end:toImg(mx, my)}; return; }
  const edges = grabAt(mx, my);
  if (edges) { const b = boxes[sel]; drag = {mode:"edit", edges, start:toImg(mx, my), orig:{...b}, before:snap(), moved:false}; return; }
  const [x, y] = toImg(mx, my);
  drag = {mode:"pan", mx, my, vx:view.x, vy:view.y, click:hit(x, y), moved:false};
  cv.style.cursor = "grabbing";
});
window.addEventListener("mousemove", e => {
  if (!drag) return;
  const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  if (drag.mode === "pan") {
    if (Math.abs(mx - drag.mx) + Math.abs(my - drag.my) > 3) drag.moved = true;
    view.x = drag.vx + mx - drag.mx; view.y = drag.vy + my - drag.my;
  } else if (drag.mode === "box") drag.end = toImg(mx, my);
  else {
    const [x, y] = toImg(mx, my), dx = x - drag.start[0], dy = y - drag.start[1], o = drag.orig, b = boxes[sel], k = drag.edges;
    if (k === "move") { b.x1 = o.x1 + dx; b.x2 = o.x2 + dx; b.y1 = o.y1 + dy; b.y2 = o.y2 + dy; }
    else { if (k.includes("w")) b.x1 = o.x1 + dx; if (k.includes("e")) b.x2 = o.x2 + dx;
           if (k.includes("n")) b.y1 = o.y1 + dy; if (k.includes("s")) b.y2 = o.y2 + dy; }
    drag.moved = Math.abs(dx) * view.s > 1 || Math.abs(dy) * view.s > 1; showSel();
  }
  draw();
});
window.addEventListener("mouseup", () => {
  if (!drag) return;
  cv.style.cursor = drawMode ? "crosshair" : "grab";
  if (drag.mode === "pan" && !drag.moved && drag.click !== null) { sel = drag.click; showSel(); }
  if (drag.mode === "box") {
    const [a, b] = [drag.start, drag.end];
    const x1 = Math.min(a[0], b[0]), x2 = Math.max(a[0], b[0]), y1 = Math.min(a[1], b[1]), y2 = Math.max(a[1], b[1]);
    if ((x2 - x1) * view.s > 6 && (y2 - y1) * view.s > 6) {
      record();
      boxes.push({id:null, label: pass === 1 ? "" : "moth", source:"manual", x1, y1, x2, y2, by:me.user, attrs:"", locked:false});
      sel = boxes.length - 1; changed();
    } else { drag = null; grabAtPoint(a[0], a[1]); return; }  // a click: box the insect under it
  } else if (drag.mode === "edit") {
    const b = boxes[sel];
    [b.x1, b.x2] = [Math.min(b.x1, b.x2), Math.max(b.x1, b.x2)]; [b.y1, b.y2] = [Math.min(b.y1, b.y2), Math.max(b.y1, b.y2)];
    if (drag.moved) { record(drag.before); touch(b); changed(); }
  }
  drag = null; draw();
});
cv.addEventListener("wheel", e => {
  e.preventDefault();
  const wheel = e.deltaMode !== 0 || (e.deltaX === 0 && Math.abs(e.deltaY) >= 40 && Number.isInteger(e.deltaY));
  if (e.ctrlKey || wheel) zoomAt(e.offsetX, e.offsetY, Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)));
  else { view.x -= e.deltaX; view.y -= e.deltaY; draw(); }
}, {passive:false});
cv.addEventListener("dblclick", e => zoomAt(e.offsetX, e.offsetY, e.shiftKey ? 0.5 : 2));
window.addEventListener("keyup", e => { if (e.key === " ") space = false; });
window.addEventListener("keydown", e => {
  if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT" && e.target.type === "text") return;
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? restore(redoStack, undoStack) : restore(undoStack, redoStack); return; }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "y") { e.preventDefault(); restore(redoStack, undoStack); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "?") { toggleGuide(); return; }
  if (e.key === "Escape") { if (!$("guide").hidden) return toggleGuide(); $("issueMenu").hidden = true; sel = -1; draw(); showSel(); return; }
  if (!task) return;
  if (e.key === " ") { space = true; e.preventDefault(); return; }
  const items = tab === "mine" ? queue.tasks : queue.review, pi = items.findIndex(t => t.id === task.id);
  if (e.key === "]" && items.length) return openTask(items[(pi + 1) % items.length].id);
  if (e.key === "[" && items.length) return openTask(items[(pi - 1 + items.length) % items.length].id);
  const k = e.key.toLowerCase();
  if (k === "b") { setDraw(!drawMode); return; }
  if (k === "h") { $("hideAll").checked = !$("hideAll").checked; draw(); return; }
  if (k === "f" || (e.key === "0" && pass === 1)) { fit(); draw(); return; }
  if (e.key === "+" || e.key === "=" || e.key === "-" || e.key === "_") { zoomAt(cv.width/2, cv.height/2, e.key === "+" || e.key === "=" ? 1.5 : 1/1.5); return; }
  const arrows = {ArrowLeft:[1,0], ArrowRight:[-1,0], ArrowUp:[0,1], ArrowDown:[0,-1]}[e.key];
  if (arrows) { e.preventDefault(); const d = e.shiftKey ? 400 : 120; view.x += arrows[0]*d; view.y += arrows[1]*d; draw(); return; }
  if (e.key === "Tab") { e.preventDefault(); jump(e.shiftKey ? -1 : 1); return; }
  if (sel < 0) return;
  if (ATTR_KEYS[k]) { toggleAttr(ATTR_KEYS[k]); return; }
  if (k === "l") { toggleLock(); return; }
  const l = KEYS[pass][e.key];
  if (l) { setLabel(l); return; }
  if (e.key === "Enter") {
    const b = boxes[sel];
    if (!b.label || b.label === "skip") { setStatus("give it a label first"); return; }
    if (unchecked(b)) { record(); b.confirm = true; touch(b); changed(); }
    jump(1); return;
  }
  if (e.key === "Delete" || e.key === "Backspace") {
    e.preventDefault(); record();
    const b = boxes[sel];
    if (b.source === "manual" && b.id === null) boxes.splice(sel, 1); else { b.label = "skip"; touch(b); }
    sel = -1; changed();
  }
});
window.addEventListener("resize", () => { if (img.complete) { fit(); draw(); } });

// ---------- guide
async function toggleGuide() {
  const g = $("guide"); g.hidden = !g.hidden;
  if (!g.hidden && !$("examples").dataset.done) {
    $("examples").dataset.done = 1;
    try {
      const ex = await (await fetch("/guide/examples.json")).json().catch(() => ({}));
      $("examples").innerHTML = Object.entries(ex).flatMap(([label, files]) => files.map(f =>
        `<figure><img src="/guide/${encodeURIComponent(f)}" alt="${esc(label)} example"><figcaption>${esc(label)}</figcaption></figure>`)).join("");
    } catch (e) {}
  }
}
$("help").onclick = toggleGuide; $("guideClose").onclick = toggleGuide;

// ---------- start
(async function start() {
  me = await (await api("/api/me")).json();
  $("me").innerHTML = `<span>Signed in as <b>${esc(me.user)}</b></span><span>${me.admin ? `<a href="/dashboard">Dashboard</a> · ` : ""}<button id="logout" class="small">Log out</button></span>`;
  $("logout").onclick = async () => { await api("/logout", {}); location.href = "/login"; };
  $("reviewTab").hidden = !me.admin;
  setPass(pass); setDraw(false); renderKey();
  await loadQueue();
  const first = queue.tasks.find(t => t.status === "returned") || queue.tasks.find(t => t.status === "open") || queue.tasks[0];
  if (first) openTask(first.id); else setStatus("No photos assigned to you yet.");
})();
