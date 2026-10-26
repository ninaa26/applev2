"use strict";
// Liner labelling site. One photo (one task) at a time; saves go to /api/save 300 ms after each change.
const KEYS = {
  1: {"1":"moth", "2":"other_insect", "3":"debris"},
  2: {"1":"CM","2":"OFM","3":"OBLR","4":"lookalike_RBLR","5":"lookalike_LAW","6":"other_tortricid","7":"other_moth",
      "8":"other_insect","9":"debris","0":"moth"},
};
const NAMES = {moth:"moth", other_insect:"other insect", debris:"debris"};
const SPECIES = ["CM","OFM","OBLR","lookalike_RBLR","lookalike_LAW","other_tortricid","other_moth"];
const ATTR_KEYS = {e:"cut_off", w:"decayed", u:"unsure"};  // O (overlapping) is set by the server from the boxes
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
const STATUS = {returned:"sent back", done:"in review", accepted:"accepted ✓"};
function renderQueue() {
  const items = tab === "mine" ? queue.tasks : queue.review;
  const isOpen = t => t.status === "open" || t.status === "returned";
  const open = queue.tasks.filter(isOpen).length;
  $("queueInfo").textContent = tab === "mine" ? `${open} to do · ${queue.tasks.length - open} finished` : `${items.length} waiting for review`;
  const row = t => {
    const short = t.photo.replace(/\.RAW-01\.COVER/, "").replace(/__/, " · ");
    // the status and kind go on their own line, so a long photo name can't hide them
    const tags = tab === "review" ? [t.user] : [t.kind !== "label" ? t.kind : "", STATUS[t.status] || ""].filter(Boolean);
    const okTag = x => x === STATUS.accepted || x === STATUS.done;  // finished: shown in the green accent
    const count = tab === "mine" ? `${t.n - t.unchecked}/${t.n}` : "";
    const notes = tab === "mine" && (t.issues || t.note) ? `${t.issues ? t.issues + " comment(s)" : ""} ${esc(t.note || "")}` : "";
    const sub = tags.length || notes ? `<span class="sub">${tags.map(x => `<span class="badge${okTag(x) ? " ok" : ""}">${esc(x)}</span>`).join("")} ${notes}</span>` : "";
    return `<div class="item ${task && t.id === task.id ? "on" : ""}" data-id="${t.id}" title="${esc(t.photo)}"><span class="name">${esc(short)}</span><span class="count${tab === "mine" && t.n && !t.unchecked ? " full" : ""}">${count}</span>${sub}</div>`;
  };
  if (tab === "mine") {
    const todo = items.filter(isOpen), done = items.filter(t => !isOpen(t));
    $("queue").innerHTML = (todo.length ? `<h2>To do (${todo.length})</h2>` + todo.map(row).join("") : "")
      + (done.length ? `<h2>Finished (${done.length})</h2>` + done.map(row).join("") : "")
      || `<p class="mute">Nothing here.</p>`;
  } else {
    $("queue").innerHTML = items.map(row).join("") || `<p class="mute">Nothing here.</p>`;
  }
  document.querySelectorAll(".item").forEach(el => el.onclick = () => openTask(Number(el.dataset.id)));
}
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
  tab = b.dataset.tab; document.querySelectorAll(".tabs button").forEach(x => x.classList.toggle("on", x === b)); renderQueue(); });

// ---------- one photo
// Waits for any save in flight and tries once more; false if the photo still has unsaved changes. Nothing may
// leave a photo (finish it, open another) while that's false, or the unsaved changes would be thrown away.
async function ensureSaved() {
  for (let i = 0; saving && i < 100; i++) await new Promise(r => setTimeout(r, 100));
  if (dirty) { clearTimeout(saveTimer); await flush(); }
  for (let i = 0; saving && i < 100; i++) await new Promise(r => setTimeout(r, 100));
  return !dirty;
}
function blockedUnsaved(what) {
  setSave("error", `Can't ${what} until this photo's changes are saved. Press Retry now; if it keeps failing, tell nina.`);
}
async function openTask(id) {
  if (task && !(await ensureSaved())) { blockedUnsaved("open another photo"); return; }
  const d = await (await api(`/api/photo?task=${id}`)).json();
  task = d.task; photo = d.photo; boxes = d.boxes; version = d.version; issues = d.issues; tags = d.tags;
  warnUnchecked = false; $("finishAsk").hidden = true;
  sel = -1; undoStack = []; redoStack = []; trail = []; trailPos = -1;
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
let warnUnchecked = false;  // Done was pressed with dashed boxes left: they're outlined in red until answered
function hideFinishAsk() { warnUnchecked = false; $("finishAsk").hidden = true; draw(); }
async function finish(e, sure = false) {
  if (!(await ensureSaved())) { $("finishAsk").hidden = true; blockedUnsaved("finish"); return; }
  const left = boxes.filter(unchecked).length;
  if (left && !sure) {
    warnUnchecked = true; fit(); draw();
    $("finishAskText").textContent = `${left} box${left === 1 ? " is" : "es are"} still not checked (outlined in red). Are you sure you're done?`;
    $("finishAsk").hidden = false;
    return;
  }
  hideFinishAsk();
  const r = await api("/api/done", {task: task.id});
  setStatus((await r.json()).message || "done");
  await loadQueue(); next();
}
$("finishYes").onclick = () => finish(null, true);
$("finishShow").onclick = () => { $("finishAsk").hidden = true; sel = -1; jump(1); };  // red outlines stay while they work
$("finishCancel").onclick = hideFinishAsk;
async function reviewTask(accept) {
  if (!(await ensureSaved())) { blockedUnsaved(accept ? "accept" : "send back"); return; }
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
  if (warnUnchecked && !boxes.some(unchecked)) { hideFinishAsk(); setStatus("all boxes checked: press Done"); }
  else if (warnUnchecked) $("finishAskText").textContent = `${boxes.filter(unchecked).length} still not checked (outlined in red). Are you sure you're done?`;
  undoButtons(); draw(); showSel(); renderKey();
  dirty = true; setSave("saving");
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
      const text = await r.text();
      let cur = null; try { cur = JSON.parse(text); } catch (e) {}
      if (cur && cur.boxes) { if (t === task) { boxes = cur.boxes; version = cur.version; sel = -1; undoStack = []; redoStack = []; draw(); }
        setSave("saved", "someone else changed this photo just now: their version is shown; redo your last change"); }
      else throw new Error(text);
    } else if (!r.ok) { throw new Error(await r.text()); }
    else {
      const res = await r.json();
      if (t === task) {
        version = res.version;
        if (boxes === sent && !dirty && sent.length === res.boxes.length) { boxes = res.boxes; if (sel >= boxes.length) sel = -1; }
        else sent.forEach(b => { delete b.confirm; delete b.unlock; });
      }
      setSave(dirty ? "saving" : "saved");
    }
  } catch (e) { dirty = true; setSave("error", e.message); }
  saving = false;
  if (dirty) { clearTimeout(saveTimer); saveTimer = setTimeout(flush, 300); }
  draw(); showSel(); renderKey(); updateCount();
}
function updateCount() {
  const q = queue.tasks.find(t => task && t.id === task.id);
  if (q) { q.n = boxes.filter(b => b.label !== "skip").length; q.unchecked = boxes.filter(unchecked).length; renderQueue(); }
}
window.addEventListener("beforeunload", e => { if (dirty) { flush(); e.preventDefault(); } });
function setStatus(t) {
  if ($("status").className === "save-error" && dirty) return;  // never cover up unsaved work
  $("status").className = ""; $("status").textContent = t;
}
// The save state, hard to miss: amber while saving, green when saved, big pulsing red (and the tab title) when not.
let savedFade = null;
function setSave(state, msg = "") {
  const el = $("status");
  clearTimeout(savedFade);
  el.className = "save-" + state;
  document.title = state === "error" ? "⚠ Not saved · Liner labels" : "Liner labels";
  if (state === "saving") el.textContent = "Saving…";
  else if (state === "saved") { el.textContent = msg || "✓ Saved"; if (!msg) savedFade = setTimeout(() => el.classList.add("faded"), 2500); }
  else {
    el.innerHTML = `<b>⚠ NOT SAVED</b><span>${esc(msg).slice(0, 200)}</span><span>Don't reload or close this tab.</span>` +
      `<button id="retrySave">Retry now</button>`;
    $("retrySave").onclick = () => { dirty = true; flush(); };
  }
}

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
// One bold colour per label, from the site's palette (pink, orange, mauve, navy, sage family); red is kept for warnings.
const LABEL_COLOURS = {
  "": "#111111", moth: "#E0A100", CM: "#EE4A7F", OFM: "#FF6A13", OBLR: "#1E9A8A", lookalike_RBLR: "#A3284F",
  lookalike_LAW: "#8DAA1E", other_tortricid: "#7A5AE0", other_moth: "#D46FA6", other_insect: "#2F5BB0", debris: "#8C7A68",
};
const LIGHT_LABELS = new Set(["moth", "OFM", "lookalike_LAW"]);  // dark text on these, white on the rest
function colorOf(b) {
  if (b.label === "skip") return "#ffffff55";
  return LABEL_COLOURS[b.label || ""] || "#EE4A7F";
}
// Little drawings for the label cards, monochrome in the label's colour: every mark is the colour itself (currentColor),
// a darker shade of it (DARK) or a paler one (PALE), never another hue. A moth with spread wings for "moth" and
// "other moth", a beetle for "other insect", scattered bits for debris.
const DARK = 'style="fill:color-mix(in srgb, currentColor 52%, #000)"', PALE = 'style="fill:color-mix(in srgb, currentColor 38%, #fff)"';
const DARK_LINE = 'style="stroke:color-mix(in srgb, currentColor 52%, #000)" fill="none"', PALE_LINE = 'style="stroke:color-mix(in srgb, currentColor 38%, #fff)" fill="none"';
const ICONS = {
  moth: `<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 9.8C12.2 7 5.4 6.4 3.2 9c.4 4.3 6 9.6 12.8 10.3Z"/>
    <path d="M16 9.8c3.8-2.8 10.6-3.4 12.8-.8-.4 4.3-6 9.6-12.8 10.3Z"/><path d="M16 17.4c-2.9.9-5.6 2.7-5 4.6.7 1.6 3.2.9 5-2Z" ${PALE}/>
    <path d="M16 17.4c2.9.9 5.6 2.7 5 4.6-.7 1.6-3.2.9-5-2Z" ${PALE}/>
    <path d="M15 11.5C12 10 8 9.4 5 9.8M15 13.5c-3 .2-6 1.4-8.2 3.4M17 11.5c3-1.5 7-2.1 10-1.7M17 13.5c3 .2 6 1.4 8.2 3.4" ${PALE_LINE} stroke-width=".8" stroke-linecap="round"/>
    <circle cx="10" cy="12" r="1.2" ${DARK}/><circle cx="22" cy="12" r="1.2" ${DARK}/><ellipse cx="16" cy="15.6" rx="1.7" ry="7" ${DARK}/>
    <path d="M15.2 9.3c-1.2-2.4-3-4-5.2-4.6M16.8 9.3c1.2-2.4 3-4 5.2-4.6" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  insect: `<svg viewBox="0 0 32 32" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
    <path d="M11.5 13 7 10.5M11 17H6M11.5 21 7 24M20.5 13l4.5-2.5M21 17h5M20.5 21l4.5 3M14.5 8.5 12.5 4.5M17.5 8.5l2-4"/></g>
    <circle cx="16" cy="10" r="2.8" ${DARK}/><ellipse cx="16" cy="19" rx="5.6" ry="7.6"/>
    <path d="M16 12.2v14.2" style="stroke:var(--field)" stroke-width="1.1"/><circle cx="13.6" cy="17" r=".9" ${PALE}/><circle cx="18.4" cy="17" r=".9" ${PALE}/></svg>`,
  debris: `<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M6 9.5 10.5 7l2 3.6-3.4 2.6Z"/><path d="M19.5 6.5l4.2.8-.9 3.9-3.8-.6Z" ${DARK}/>
    <path d="M13 19.5l3.6-1.6 1.6 3.4-4.2 1.4Z"/><circle cx="24.5" cy="19" r="1.8" ${DARK}/><circle cx="8" cy="22.5" r="1.3"/><circle cx="20" cy="26" r="1.1"/>
    <path d="M17 12.5c2.2 1 4.2 1.3 6.4 1" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>`,
};
// Pass 2: each species drawn as it rests on the glue, seen from above: a tortricid "bell" of folded wings, the wing
// tips at the rear, with the species' own size, shape and field marks.
//   CM: grey bell with fine wavy cross-lines and the shiny eyespot at each wing tip.
//   OFM: small and narrow, dark chevrons, a row of short pale dashes down each outer edge.
//   OBLR: broad square shoulders, dark basal patch, the oblique band meeting in a V, a spot near each tip.
//   RBLR: pale base, one narrow bold band running obliquely back, dark tips.
//   LAW: smallest, dark, a pale band across the middle and pale spots near the tips.
//   tortricid: plain bell, wing seam and faint mottling.
const ANT = `<path d="M15 6.4c-1.6-1.7-3.3-2.4-5-2.4M17 6.4c1.6-1.7 3.3-2.4 5-2.4" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>`;
const bell = (w, top, bot, sh = 0) =>  // a resting tortricid seen from above: narrow at the head, widest near the rear, rounded
  // tail; half-width w, from y=top to y=bot; sh pushes the width forward (square shoulders, like OBLR)
  `M16 ${top}c-1.5 0-2.4 1-2.7 2.3C${16 - w * (0.45 + sh)} ${top + 6} ${16 - w} ${top + 11 - sh * 6} ${16 - w} ${bot - 5}c0 3 2.8 5 ${w} 5s${w}-2 ${w}-5C${16 + w} ${top + 11 - sh * 6} ${16 + w * (0.45 + sh)} ${top + 6} 18.7 ${top + 2.3}C18.4 ${top + 1} 17.5 ${top} 16 ${top}Z`;
const svg = body => `<svg viewBox="0 0 32 32" aria-hidden="true">${body}</svg>`;
// A bell with its markings clipped to the wings, so marks can run off the edges.
let clipN = 0;
const wings = (outline, marks) => { const id = `lw${++clipN}`;
  return `<defs><clipPath id="${id}"><path d="${outline}"/></clipPath></defs><path d="${outline}"/><g clip-path="url(#${id})">${marks}</g>`
    + `<path d="M16 ${outline.match(/M16 ([\d.]+)/)[1] * 1 + 3}V27.6" ${DARK_LINE} stroke-width=".55" opacity=".7"/>`; };
Object.assign(ICONS, {
  CM: svg(`${ANT}${wings(bell(8.2, 5, 28), `
     <path d="M8 11.6q2 -1 4 0t4 0 4 0 4 0M7.6 14.6q2.1 -1 4.2 0t4.2 0 4.2 0 4.2 0M7.4 17.6q2.15 -1 4.3 0t4.3 0 4.3 0 4.3 0" ${DARK_LINE} stroke-width=".7" opacity=".75"/>
     <path d="M7 20.2c3 1 6 1.4 9 1.4s6-.4 9-1.4v2.2c-3 1-6 1.4-9 1.4s-6-.4-9-1.4Z" ${DARK} opacity=".55"/>
     <ellipse cx="11.6" cy="25.2" rx="3" ry="2" transform="rotate(-18 11.6 25.2)" ${DARK}/><ellipse cx="20.4" cy="25.2" rx="3" ry="2" transform="rotate(18 20.4 25.2)" ${DARK}/>
     <path d="M9.6 25.6l3.6-1.1M18.8 24.5l3.6 1.1M10.2 26.6l3-.9M18.8 25.7l3 .9" ${PALE_LINE} stroke-width=".7" stroke-linecap="round"/>`)}`),
  OFM: svg(`${ANT}${wings(bell(5.8, 6, 27.5), `
     <path d="M12.4 13l3.6 1.8 3.6-1.8M11.3 17l4.7 2.2 4.7-2.2M10.8 21l5.2 2.2 5.2-2.2" ${DARK_LINE} stroke-width="1"/>
     <path d="M10.6 11.6l1.6.8M10.2 14.6l1.7.6M10 17.6l1.8.5M10 20.6l1.8.4M10.2 23.4l1.7.3M21.4 11.6l-1.6.8M21.8 14.6l-1.7.6M22 17.6l-1.8.5M22 20.6l-1.8.4M21.8 23.4l-1.7.3" ${PALE_LINE} stroke-width=".9" stroke-linecap="round"/>
     <circle cx="13.4" cy="25.4" r=".8" ${DARK}/><circle cx="18.6" cy="25.4" r=".8" ${DARK}/>`)}`),
  OBLR: svg(`${ANT}${wings(bell(9, 5, 28, 0.2), `
     <path d="M6 7h20v4.6c-3.3 1-6.7 1.5-10 1.5S9.3 12.6 6 11.6Z" ${DARK} opacity=".75"/>
     <path d="M6 14.6l3.2-1.4L16 18.4l6.8-5.2 3.2 1.4L16 22.6Z" ${DARK}/>
     <path d="M6.8 22.4l3.4-1.2 1.4 3.6-3.4 1.1ZM25.2 22.4l-3.4-1.2-1.4 3.6 3.4 1.1Z" ${DARK}/>
     <path d="M9.8 16.8l1.6 1.2M22.2 16.8l-1.6 1.2" ${PALE_LINE} stroke-width=".6"/>`)}`),
  lookalike_RBLR: svg(`${ANT}${wings(bell(8, 5.5, 28), `
     <path d="M6 6h20v8.6H6Z" ${PALE} opacity=".8"/>
     <path d="M7 14.4l2-1.6L16 19.8l7-7 2 1.6L16 23.2Z" ${DARK}/>
     <path d="M7 25.4c2-1 3.6-.8 5 .4l-1 3H7ZM25 25.4c-2-1-3.6-.8-5 .4l1 3h4Z" ${DARK} opacity=".7"/>`)}`),
  lookalike_LAW: svg(`${ANT}${wings(bell(5.6, 8, 27), `
     <path d="M8 8h16v20H8Z" ${DARK} opacity=".55"/>
     <path d="M10.4 15.6c3.7.9 7.5.9 11.2 0v2.6c-3.7.9-7.5.9-11.2 0Z" ${PALE}/>
     <circle cx="13.6" cy="23.2" r="1.3" ${PALE}/><circle cx="18.4" cy="23.2" r="1.3" ${PALE}/>`)}`),
  other_tortricid: svg(`${ANT}${wings(bell(7.4, 5.5, 28), `
     <circle cx="12" cy="13" r="1" ${DARK} opacity=".6"/><circle cx="20" cy="13" r="1" ${DARK} opacity=".6"/>
     <circle cx="11" cy="19" r="1.2" ${DARK} opacity=".5"/><circle cx="21" cy="19" r="1.2" ${DARK} opacity=".5"/>
     <circle cx="13.6" cy="23.8" r=".9" ${PALE}/><circle cx="18.4" cy="23.8" r=".9" ${PALE}/>`)}`),
  unsure: svg(`${ANT}<path d="${bell(7.4, 5.5, 28)}" fill="none" stroke="currentColor" stroke-width="1.4"/>
     <text x="16" y="21.5" text-anchor="middle" font-size="11" font-weight="700" font-family="-apple-system, system-ui, sans-serif" fill="currentColor">?</text>`),
});
const iconFor = (l, unsure = false) => l === "debris" ? ICONS.debris : l === "other_insect" ? ICONS.insect
  : unsure ? ICONS.unsure : ICONS[l] || ICONS.moth;
const SHORT = {lookalike_RBLR: "RBLR", lookalike_LAW: "LAW", other_tortricid: "tortricid", other_moth: "other moth",
               other_insect: "other insect", debris: "debris"};
function confirmSel() {  // Enter, or the ⏎ row: the guess is right, on to the next
  if (sel < 0) { setStatus("select a box first"); return; }
  const b = boxes[sel];
  if (!b.label || b.label === "skip") { setStatus("give it a label first"); return; }
  if (unchecked(b)) { record(); b.confirm = true; touch(b); changed(); }
  jump(1);
}
function deleteSel() {  // Delete, or the ⌫ row
  if (sel < 0) { setStatus("select a box first"); return; }
  record();
  const b = boxes[sel];
  if (b.source === "manual" && b.id === null) boxes.splice(sel, 1); else { b.label = "skip"; touch(b); }
  sel = -1; changed();
}
function renderKey() {  // the key doubles as buttons: a row does what its key does to the selected box
  const counts = {}; boxes.forEach(b => counts[b.label] = (counts[b.label] || 0) + 1);
  const keys = Object.entries(KEYS[pass]).sort((a, b) => (a[0] === "0") - (b[0] === "0") || a[0] - b[0]);
  const cur = sel >= 0 && boxes[sel] ? boxes[sel].label : null;
  const row = (k, text, n, act, on = false) =>
    `<button class="krow${on ? " on" : ""}" data-act="${esc(act)}" ${sel < 0 ? "disabled" : ""}><kbd>${k}</kbd><span>${text}</span><span class="n">${n}</span></button>`;
  const info = (k, text) => `<div class="krow info"><kbd>${k}</kbd><span>${text}</span><span></span></div>`;
  $("labelKeys").className = "lcards" + (pass === 2 ? " many" : "");
  $("labelKeys").innerHTML = keys.map(([k, l]) => {
    const name = pass === 1 ? NAMES[l] : (k === "0" ? "moth?" : SHORT[l] || l);
    const full = pass === 1 ? NAMES[l] : (k === "0" ? "moth, species unsure" : l);
    return `<button class="lcard${cur === l ? " on" : ""}" data-act="label:${esc(l)}" title="${esc(full)} (${k})" ${sel < 0 ? "disabled" : ""}
      style="--c:${colorOf({label:l})}"><kbd>${k}</kbd>${iconFor(l, pass === 2 && k === "0")}<span class="lname">${esc(name)}</span><span class="n">${counts[l] || 0}</span></button>`;
  }).join("");
  $("key").innerHTML = row("⏎", "the guess is right, next", `${boxes.filter(unchecked).length} left`, "confirm")
    + row("⌫", "delete (not on the card)", counts.skip || 0, "delete")
    + info("B", "draw (click an insect, or drag)") + info("Tab", "next to check · [ ] photos")
    + info(", .", "previous / next box you were on") + info("?", "guide · right-click: comment");
  document.querySelectorAll("#key button.krow, #labelKeys button.lcard").forEach(x => x.onclick = () => {
    const a = x.dataset.act;
    if (a === "confirm") confirmSel(); else if (a === "delete") deleteSel(); else if (sel >= 0) setLabel(a.slice(6));
  });
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
  ctx.setTransform(1,0,0,1,0,0); ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--stage").trim() || "#111111";
  ctx.fillRect(0, 0, cv.width, cv.height);
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
    ctx.font = `600 ${12*lw}px -apple-system, system-ui, sans-serif`; const w = ctx.measureText(t).width + 6*lw;
    ctx.fillStyle = colorOf(b); ctx.fillRect(b.x1, b.y1 - 16*lw, w, 16*lw);
    ctx.fillStyle = LIGHT_LABELS.has(b.label) ? "#1A1A1A" : "#fff"; ctx.fillText(t, b.x1 + 3*lw, b.y1 - 4*lw);
    ctx.globalAlpha = 1;
  });
  if (warnUnchecked) {  // after Done with dashed boxes left: a red ring around each, drawn in screen-sized pixels
    ctx.strokeStyle = "#D40000"; ctx.lineWidth = 4 * lw; ctx.setLineDash([]);
    boxes.forEach(b => { if (unchecked(b)) { const m = 6 * lw; ctx.strokeRect(b.x1 - m, b.y1 - m, b.x2 - b.x1 + 2 * m, b.y2 - b.y1 + 2 * m); } });
  }
  issues.forEach((it, k) => {  // pinned comments
    ctx.beginPath(); ctx.arc(it.x, it.y, 10*lw, 0, 7);
    ctx.fillStyle = it.resolved_at ? "#C9BCCB" : "#FF9E1B"; ctx.fill(); ctx.strokeStyle = "#1A1A1A"; ctx.lineWidth = 1.5*lw; ctx.stroke();
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
// The boxes visited on this photo, in order, for ◀ Previous / Next ▶. Kept by box id (or position, for a box not
// saved yet), since a save replaces the box objects.
let trail = [], trailPos = -1, walking = false;
const keyOf = b => b.id != null ? "id" + b.id : `${Math.round(b.x1)},${Math.round(b.y1)}`;
const indexOf = k => boxes.findIndex(b => keyOf(b) === k);
function remember() {
  if (walking || sel < 0 || !boxes[sel]) return;
  const k = keyOf(boxes[sel]);
  if (trail[trailPos] === k) return;
  trail = trail.slice(0, trailPos + 1); trail.push(k); trailPos = trail.length - 1;
  if (trail.length > 500) { trail.shift(); trailPos--; }
}
function walk(step) {
  for (let p = trailPos + step; p >= 0 && p < trail.length; p += step) {
    const i = indexOf(trail[p]);
    if (i < 0) continue;  // deleted since
    trailPos = p; walking = true; sel = i; zoomTo(boxes[i]); draw(); showSel(); walking = false;
    return true;
  }
  return false;
}
function prevBox() { if (!walk(-1)) setStatus("this is the first box you looked at on this photo"); }
function nextBox() { if (!walk(1)) jump(1); }
$("prevBox").onclick = prevBox; $("nextBox").onclick = nextBox;
function showSel() {
  remember(); renderKey();
  $("prevBox").disabled = trailPos <= 0;
  zc.fillStyle = "#111111"; zc.fillRect(0, 0, 256, 256);
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
function clampBox(b) {  // keep a box on the photo: a corner dragged past the edge stops at the edge
  const W = img.width, H = img.height;
  b.x1 = Math.max(0, Math.min(b.x1, W - 1)); b.x2 = Math.max(b.x1 + 1, Math.min(b.x2, W));
  b.y1 = Math.max(0, Math.min(b.y1, H - 1)); b.y2 = Math.max(b.y1 + 1, Math.min(b.y2, H));
}
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
      const nb = {id:null, label: pass === 1 ? "" : "moth", source:"manual", x1, y1, x2, y2, by:me.user, attrs:"", locked:false};
      clampBox(nb); boxes.push(nb);
      sel = boxes.length - 1; changed();
    } else { drag = null; grabAtPoint(a[0], a[1]); return; }  // a click: box the insect under it
  } else if (drag.mode === "edit") {
    const b = boxes[sel];
    [b.x1, b.x2] = [Math.min(b.x1, b.x2), Math.max(b.x1, b.x2)]; [b.y1, b.y2] = [Math.min(b.y1, b.y2), Math.max(b.y1, b.y2)];
    clampBox(b);
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
  if (e.key === ",") { prevBox(); return; }
  if (e.key === ".") { nextBox(); return; }
  if (sel < 0) return;
  if (ATTR_KEYS[k]) { toggleAttr(ATTR_KEYS[k]); return; }
  if (k === "l") { toggleLock(); return; }
  const l = KEYS[pass][e.key];
  if (l) { setLabel(l); return; }
  if (e.key === "Enter") { confirmSel(); return; }
  if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); deleteSel(); }
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

// ---------- resizable side panels (widths kept in this browser only)
const PANEL = {l: 250, r: 280, min: 170, max: 640};
function setPanels(l, r) {
  const room = innerWidth - 320;  // always leave the photo at least this much
  l = Math.max(PANEL.min, Math.min(l, PANEL.max, room - PANEL.min));
  r = Math.max(PANEL.min, Math.min(r, PANEL.max, room - l));
  document.body.style.setProperty("--lw", l + "px"); document.body.style.setProperty("--rw", r + "px");
  $("gripL").style.left = l + "px"; $("gripR").style.left = (innerWidth - r) + "px";
  if (ownPanels) try { localStorage.setItem("panels", JSON.stringify([l, r])); } catch (e) {}
  if (img.complete && img.width) { fit(); draw(); }
  fitName();
}
// The name is as big as the panel allows (18 px at most, 12 px at least), never cut short when there is room.
function fitName() {
  const b = document.querySelector(".who b");
  if (!b) return;
  b.style.fontSize = "";
  for (let px = 18; px > 12 && b.scrollWidth > b.clientWidth; px--) b.style.fontSize = px - 1 + "px";
}
let panels = [PANEL.l, PANEL.r], ownPanels = false;  // ownPanels: this browser was resized by hand
try { const p = JSON.parse(localStorage.getItem("panels")); if (p) { panels = p; ownPanels = true; } } catch (e) {}
["gripL", "gripR"].forEach(id => {
  const g = $(id), left = id === "gripL";
  g.addEventListener("mousedown", e => {
    e.preventDefault(); g.classList.add("dragging"); document.body.classList.add("resizing");
    ownPanels = true;
    const move = ev => { panels = left ? [ev.clientX, panels[1]] : [panels[0], innerWidth - ev.clientX]; setPanels(...panels); };
    const up = () => { g.classList.remove("dragging"); document.body.classList.remove("resizing");
      removeEventListener("mousemove", move); removeEventListener("mouseup", up); };
    addEventListener("mousemove", move); addEventListener("mouseup", up);
  });
  g.addEventListener("dblclick", () => { panels = left ? [PANEL.l, panels[1]] : [panels[0], PANEL.r]; setPanels(...panels); });  // PANEL = the site default
});
addEventListener("resize", () => setPanels(...panels));
setPanels(...panels);

// ---------- account card and settings menu (top of the left panel)
const MENU_ICON = {
  dashboard: `<svg viewBox="0 0 20 20"><path fill="currentColor" d="M3 3h6v8H3zM11 3h6v5h-6zM11 10h6v7h-6zM3 13h6v4H3z"/></svg>`,
  guide: `<svg viewBox="0 0 20 20"><path fill="currentColor" d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm.9 12.6H9.1v-1.8h1.8Zm1.6-5.4c-.3.5-.8.9-1.2 1.2-.4.3-.5.5-.5 1v.4H9.1V11c0-.8.3-1.3.9-1.8.5-.4 1-.7 1-1.3 0-.6-.4-1-1-1s-1.1.4-1.2 1.1L7 7.6C7.3 6.2 8.4 5.3 10 5.3c1.7 0 2.9 1 2.9 2.5 0 .5-.1 1-.4 1.4Z"/></svg>`,
  widths: `<svg viewBox="0 0 20 20"><path fill="currentColor" d="M2 4h16v12H2zm2 2v8h3V6zm5 0v8h2V6zm4 0v8h3V6z"/></svg>`,
  share: `<svg viewBox="0 0 20 20"><path fill="currentColor" d="M10 2 5.5 6.5l1.4 1.4L9 5.8V13h2V5.8l2.1 2.1 1.4-1.4ZM4 12v4h12v-4h2v6H2v-6z"/></svg>`,
  logout: `<svg viewBox="0 0 20 20"><path fill="currentColor" d="M4 3h7v2H6v10h5v2H4zm9.6 3.4L17.2 10l-3.6 3.6-1.4-1.4 1.2-1.2H8V9h5.4l-1.2-1.2Z"/></svg>`,
};
// A small resting moth, a triangle of swept-back wings, for either side of the name.
const MOTH_MARK = `<svg class="mmark" viewBox="0 0 24 24" aria-hidden="true"><path d="M11.6 5.5C9.4 8.6 5.6 14 2.5 18.6c3 1 6.3.4 9.1-1.1Z"/>
  <path d="M12.4 5.5c2.2 3.1 6 8.5 9.1 13.1-3 1-6.3.4-9.1-1.1Z"/><path d="M12 4.2c1 0 1.4.9 1.4 2v10.6c0 1-.6 1.8-1.4 1.8s-1.4-.8-1.4-1.8V6.2c0-1.1.4-2 1.4-2Z" style="fill:color-mix(in srgb, currentColor 55%, #000)"/>
  <path d="M11.4 4.4C10.8 3 9.8 2.1 8.4 1.7M12.6 4.4c.6-1.4 1.6-2.3 3-2.7" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>`;
function renderAccount() {
  const tones = ["#EE4A7F", "#2F5BB0", "#1E9A8A", "#7A5AE0", "#D46FA6", "#FF6A13", "#8DAA1E"];
  const tone = tones[[...me.user].reduce((a, c) => a + c.charCodeAt(0), 0) % tones.length];
  const item = (id, icon, text, extra = "") => `<button class="mitem${extra}" id="${id}" role="menuitem">${MENU_ICON[icon]}<span>${text}</span></button>`;
  // The whole card is the settings button.
  $("me").innerHTML = `<button id="cog" class="account" style="--tone:${tone}" aria-haspopup="menu" aria-expanded="false"
      title="Settings" aria-label="${esc(me.user)}: settings">
      <span class="who">${MOTH_MARK}<b>${esc(me.user)}</b>${MOTH_MARK}</span>
    </button>
    <div class="menu" id="cogMenu" role="menu" hidden>
      <div class="mrole">Signed in as <b>${me.admin ? "Admin" : "Labeller"}</b></div>
      <div class="msep"></div>
      ${me.admin ? item("mDash", "dashboard", "Dashboard") : ""}
      ${item("mGuide", "guide", "Labelling guide")}
      ${item("mWidths", "widths", "Reset panel widths")}
      ${me.admin ? item("mShare", "share", "Set my widths as default") : ""}
      <div class="msep"></div>
      ${item("mLogout", "logout", "Log out", " danger")}
    </div>`;
  fitName();
  document.fonts.ready.then(fitName);  // again once the name's font has loaded
  const menu = $("cogMenu"), cog = $("cog");
  const show = on => { menu.hidden = !on; cog.setAttribute("aria-expanded", String(on)); cog.classList.toggle("open", on); };
  cog.onclick = e => { e.stopPropagation(); show(menu.hidden); };
  document.addEventListener("click", e => { if (!menu.hidden && !menu.contains(e.target)) show(false); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !menu.hidden) show(false); });
  if (me.admin) $("mDash").onclick = () => { location.href = "/dashboard"; };
  $("mGuide").onclick = () => { show(false); toggleGuide(); };
  $("mWidths").onclick = () => { show(false); ownPanels = false; try { localStorage.removeItem("panels"); } catch (e) {}
    panels = [PANEL.l, PANEL.r]; setPanels(...panels); setStatus("panel widths reset"); };
  if (me.admin) $("mShare").onclick = async () => {
    show(false);
    const r = await api("/api/admin/panels", {left: Math.round(panels[0]), right: Math.round(panels[1])});
    setStatus(r.ok ? (await r.json()).message : await r.text());
    if (r.ok) [PANEL.l, PANEL.r] = panels;
  };
  $("mLogout").onclick = async () => {
    if (!(await ensureSaved())) { show(false); blockedUnsaved("log out"); return; }
    await api("/logout", {}); location.href = "/login";
  };
}

// ---------- start
(async function start() {
  me = await (await api("/api/me")).json();
  renderAccount();
  $("reviewTab").hidden = !me.admin;
  if (me.panels) { [PANEL.l, PANEL.r] = me.panels; if (!ownPanels) { panels = [...me.panels]; setPanels(...panels); } }

  setPass(pass); setDraw(false); renderKey();
  await loadQueue();
  const first = queue.tasks.find(t => t.status === "returned") || queue.tasks.find(t => t.status === "open") || queue.tasks[0];
  if (first) openTask(first.id); else setStatus("No photos assigned to you yet.");
})();
