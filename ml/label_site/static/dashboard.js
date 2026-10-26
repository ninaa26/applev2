"use strict";
const esc = t => String(t ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pct = (a, b) => b ? `${Math.round(100 * a / b)}%` : "–";
(async function () {
  const r = await fetch("/api/dashboard");
  if (r.status === 401) { location.href = "/login"; return; }
  const d = await r.json();
  const tile = (v, l) => `<div class="tile"><b>${esc(v)}</b><span>${esc(l)}</span></div>`;
  document.getElementById("totals").innerHTML =
    tile(d.photos.n, "photos on the site") + tile(d.photos.gold || 0, "hidden test photos") +
    tile(pct(d.boxes.checked || 0, d.boxes.n), `of ${d.boxes.n} boxes checked`) +
    tile(d.mean_agreement == null ? "–" : pct(d.mean_agreement, 1), "two-person agreement") +
    tile(d.issues_open, "open comments");
  document.getElementById("people").innerHTML =
    "<tr><th>Person</th><th>To do</th><th>Sent back</th><th>In review</th><th>Accepted</th><th>Box changes</th><th>s / box</th>" +
    "<th>Test photos</th><th>Found</th><th>Right</th><th>Kept wrong guess</th><th>Extra boxes</th></tr>" +
    d.people.map(p => `<tr><td>${esc(p.user)}</td><td>${p.open}</td><td>${p.returned}</td><td>${p.done}</td><td>${p.accepted}</td>` +
      `<td>${p.box_changes}</td><td>${p.sec_per_box == null ? "–" : p.sec_per_box.toFixed(1)}</td><td>${p.gold_photos}</td>` +
      `<td>${pct(p.gold_found, p.gold_gold)}</td><td>${pct(p.gold_label_right, p.gold_found)}</td>` +
      `<td>${pct(p.gold_took_wrong, p.gold_model_wrong)}${p.gold_model_wrong ? ` (${p.gold_took_wrong}/${p.gold_model_wrong})` : ""}</td><td>${p.gold_extra ?? 0}</td></tr>`).join("");
  document.getElementById("merges").innerHTML = "<tr><th>Photo</th><th>People</th><th>Agreement</th><th>Disputed boxes</th></tr>" +
    (d.merges.map(m => `<tr><td>${esc(m.photo)}</td><td>${esc(m.a)} + ${esc(m.b)}</td><td>${pct(m.agreement, 1)}</td><td>${m.disputes}</td></tr>`).join("")
     || `<tr><td colspan="4">None finished yet.</td></tr>`);
})();
