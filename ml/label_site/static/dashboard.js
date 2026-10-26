"use strict";
const esc = t => String(t ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pct = (a, b) => b ? `${Math.round(100 * a / b)}%` : "–";
const KIND = {label:"label", double:"two-person", gold_check:"hidden test", tiebreak:"tiebreak", gold_truth:"reference", species:"species"};
const STATUS = {open:"to do", returned:"sent back", done:"in review", accepted:"accepted"};
let me = {}, d = null;
async function post(path, body) {
  const r = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json", "X-CSRF": me.csrf}, body: JSON.stringify(body)});
  const text = await r.text();
  let msg = text; try { msg = JSON.parse(text).message || text; } catch (e) {}
  document.getElementById("aMsg").textContent = msg;
  await load();
}
function renderPeople() {
  const tile = (v, l) => `<div class="tile"><b>${esc(v)}</b><span>${esc(l)}</span></div>`;
  document.getElementById("totals").innerHTML =
    tile(d.photos.n, "photos on the site") + tile(d.photos.gold || 0, "hidden test photos") +
    tile(pct(d.boxes.checked || 0, d.boxes.n), `of ${d.boxes.n} boxes checked`) +
    tile(d.mean_agreement == null ? "–" : pct(d.mean_agreement, 1), "two-person agreement") +
    tile(d.issues_open, "open comments");
  document.getElementById("people").innerHTML =
    "<tr><th>Person</th><th>To do</th><th>Boxes left</th><th>Sent back</th><th>In review</th><th>Accepted</th><th>Box changes</th><th>s / box</th>" +
    "<th>Test photos</th><th>Found</th><th>Right</th><th>Kept wrong guess</th><th>Species right</th><th>Extra boxes</th><th></th></tr>" +
    d.people.map(p => `<tr><td>${esc(p.user)}${p.paused ? ` <span class="paused">paused</span>` : ""}</td><td>${p.open}</td><td>${p.unchecked_open}</td><td>${p.returned}</td><td>${p.done}</td><td>${p.accepted}</td>` +
      `<td>${p.box_changes}</td><td>${p.sec_per_box == null ? "–" : p.sec_per_box.toFixed(1)}</td><td>${p.gold_photos}</td>` +
      `<td>${pct(p.gold_found, p.gold_gold)}</td><td>${pct(p.gold_label_right, p.gold_found)}</td>` +
      `<td>${pct(p.gold_took_wrong, p.gold_model_wrong)}${p.gold_model_wrong ? ` (${p.gold_took_wrong}/${p.gold_model_wrong})` : ""}</td>` +
      `<td>${pct(p.gold_species_right, p.gold_species_named)}${p.gold_species_named ? ` (${p.gold_species_right}/${p.gold_species_named})` : ""}</td><td>${p.gold_extra ?? 0}</td>` +
      `<td class="acts">${d.admins.includes(p.user) ? "" : p.paused
        ? `<button data-resume="${esc(p.user)}" title="They can label again, with the photos they had">Resume</button>` +
          (p.open ? `<button data-release="${esc(p.user)}" title="Give their open photos to whoever has least left">Hand out their photos</button>` : "")
        : `<button data-pause="${esc(p.user)}" title="They can't open or get photos until resumed; their photos wait for them">Pause</button>`}</td></tr>`).join("");
  document.querySelectorAll("[data-pause]").forEach(b => b.onclick = () => post("/api/admin/pause", {user: b.dataset.pause, on: true}));
  document.querySelectorAll("[data-release]").forEach(b => b.onclick = () => {  // asks once more: it moves their work
    if (b.dataset.armed) post("/api/admin/pause", {user: b.dataset.release, on: true, release: true});
    else { b.dataset.armed = 1; b.textContent = `Give ${b.dataset.release}'s ${d.people.find(p => p.user === b.dataset.release).open} photos away?`; }
  });
  document.querySelectorAll("[data-resume]").forEach(b => b.onclick = () => post("/api/admin/pause", {user: b.dataset.resume, on: false}));
  document.getElementById("merges").innerHTML = "<tr><th>Photo</th><th>People</th><th>Agreement</th><th>Disputed boxes</th></tr>" +
    (d.merges.map(m => `<tr><td>${esc(m.photo)}</td><td>${esc(m.a)} + ${esc(m.b)}</td><td>${pct(m.agreement, 1)}</td><td>${m.disputes}</td></tr>`).join("")
     || `<tr><td colspan="4">None finished yet.</td></tr>`);
}
function renderTasks() {
  const fu = document.getElementById("fUser"), fs = document.getElementById("fStatus");
  if (fu.options.length === 1) d.people.forEach(p => fu.insertAdjacentHTML("beforeend", `<option>${esc(p.user)}</option>`));
  const others = d.people.filter(p => !p.paused).map(p => p.user);
  const rows = d.tasks.filter(t => (!fu.value || t.user === fu.value) &&
    (!fs.value || (fs.value === "open" ? (t.status === "open" || t.status === "returned") : t.status === fs.value)));
  document.getElementById("tasks").innerHTML = "<tr><th>Photo</th><th>Person</th><th>Kind</th><th>Status</th><th>Checked</th><th>Move to</th></tr>" +
    rows.slice(0, 500).map(t => {
      const canMove = t.status === "open" || t.status === "returned";
      const holders = new Set(d.tasks.filter(x => x.photo === t.photo).map(x => x.user));  // nobody gets a photo twice
      const pool = t.kind === "gold_truth" ? others.filter(u => d.admins.includes(u)) : others;
      const opts = pool.filter(u => !holders.has(u)).map(u => `<option>${esc(u)}</option>`).join("");
      return `<tr><td title="${esc(t.photo)}">${esc(t.photo.replace("__", " · ").slice(0, 48))}</td><td>${esc(t.user)}</td><td>${esc(KIND[t.kind] || t.kind)}</td>` +
        `<td>${esc(STATUS[t.status] || t.status)}</td><td>${t.n - t.unchecked}/${t.n}</td>` +
        `<td>${canMove ? `<select data-to="${t.id}"><option value="">–</option>${opts}</select> <button data-move="${t.id}">Move</button>` : ""}</td></tr>`;
    }).join("") + (rows.length > 500 ? `<tr><td colspan="6">${rows.length - 500} more: pick a person to see them</td></tr>` : "")
    + (rows.length ? "" : `<tr><td colspan="6">Nothing here.</td></tr>`);
  document.querySelectorAll("[data-move]").forEach(b => b.onclick = () => {
    const to = document.querySelector(`[data-to="${b.dataset.move}"]`).value;
    if (to) post("/api/admin/reassign", {task: Number(b.dataset.move), to});
  });
}
async function load() {
  const r = await fetch("/api/dashboard");
  if (r.status === 401) { location.href = "/login"; return; }
  d = await r.json();
  renderPeople(); renderTasks();
}
(async function () {
  me = await (await fetch("/api/me")).json();
  ["fUser", "fStatus"].forEach(id => document.getElementById(id).onchange = renderTasks);
  await load();
})();
