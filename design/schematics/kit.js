// Orchard Sentinel schematics: drawings shared by the ten directions, all in SVG from data.js.
// Colours come from each page's CSS variables (--cm, --ofm, --oblr, --other, --ink, --muted, --grid,
// --track, --liner, --liner-grid), so one drawing takes each direction's look.
(() => {
  const { daily, PESTS, traps, pheno, day, dayLabel, DAYS } = window.OS;
  const SP = [...PESTS, 'other_moth'];
  const VAR = { CM: '--cm', OFM: '--ofm', OBLR: '--oblr', other_moth: '--other' };
  const col = (sp) => `var(${VAR[sp] || '--other'})`;

  // Per-trap new catches for the last 7 days (Jun 9 … Jun 15); null = no photo that day (T5 offline).
  const trap7 = {
    T1: [1,1,2,1,1,2,1], T2: [2,2,1,3,2,2,2], T3: [0,1,1,0,1,1,0],
    T4: [0,1,1,0,2,1,1], T5: [0,0,0,0,0,null,null], T6: [0,1,0,1,0,1,0],
  };
  for (const sp of PESTS) {
    const ts = traps.filter((t) => t.lure === sp);
    for (let i = 0; i < 7; i++) console.assert(ts.reduce((s, t) => s + (trap7[t.id][i] || 0), 0) === daily[sp][DAYS - 7 + i], `trap7 ${sp} day ${i}`);
  }

  // Stacked new catches per day, whole orchard. opts: height, ticks (bool), labels: 'ends' | 'weeks'
  function stack(el, { height = 160, days = DAYS, barGap = 0.28, labels = 'ends' } = {}) {
    const start = DAYS - days, W = 600, H = height, padL = 22, padB = 20, padT = 6;
    const totals = Array.from({ length: days }, (_, i) => SP.reduce((s, sp) => s + daily[sp][start + i], 0));
    const top = Math.max(4, Math.ceil(Math.max(...totals) / 2) * 2 + 2);
    const bw = (W - padL) / days, y = (v) => padT + (H - padT - padB) * (1 - v / top);
    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="none" role="img" aria-label="New catches per day, whole orchard, last ${days} days, peak ${Math.max(...totals)}">`;
    for (const t of [0, top / 2, top]) s += `<line x1="${padL}" x2="${W}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)" stroke-width="1" vector-effect="non-scaling-stroke"/>`;
    for (let i = 0; i < days; i++) {
      let acc = 0; const x = padL + i * bw + bw * barGap / 2, w = bw * (1 - barGap);
      for (const sp of SP) { const v = daily[sp][start + i]; if (!v) continue; s += `<rect x="${x}" y="${y(acc + v)}" width="${w}" height="${y(acc) - y(acc + v) - 1}" fill="${col(sp)}"><title>${dayLabel(day(start + i))}: ${v} ${window.OS.LABEL[sp]}</title></rect>`; acc += v; }
    }
    s += '</svg>';
    const lab = labels === 'weeks'
      ? [0, 7, 14, 21].filter((i) => i < days - 4).map((i) => `<span style="left:${(padL + (i + 0.5) * bw) / W * 100}%${i ? '' : ';transform:none'}">${dayLabel(day(start + i))}</span>`).join('') + `<span style="left:auto;right:0;transform:none">${dayLabel(day(DAYS - 1))}</span>`
      : `<span style="left:${padL / W * 100}%;transform:none">${dayLabel(day(start))}</span><span style="left:auto;right:0;transform:none">${dayLabel(day(DAYS - 1))}</span>`;
    el.innerHTML = `<div class="k-stack" style="position:relative">${s}<div class="k-y" aria-hidden="true"><span style="top:${y(top)}px">${top}</span><span style="top:${y(top / 2)}px">${top / 2}</span><span style="top:${y(0)}px">0</span></div><div class="k-x" aria-hidden="true">${lab}</div></div>`;
  }

  // Degree-day ruler from biofix to the last milestone, with the next milestone marked.
  function dd(sp, { compact = false } = {}) {
    const p = pheno[sp], pct = (v) => Math.min(100, v / p.top * 100);
    const next = p.milestones.find((m) => m.dd > p.dd);
    const ticks = p.milestones.map((m) => `<i class="k-tick${p.dd >= m.dd ? ' on' : ''}${m === next ? ' next' : ''}" style="left:${pct(m.dd)}%" title="${m.dd} DD: ${m.short}"></i>`).join('');
    const nextLab = next && !compact ? `<span class="k-next" style="left:${pct(next.dd)}%">${next.short} · ${next.dd}</span>` : '';
    return `<div class="k-dd" role="img" aria-label="${p.dd} of ${p.top} degree days since biofix ${dayLabel(p.biofix)}">${nextLab}<div class="k-track"><span class="k-fill" style="width:${pct(p.dd)}%;background:${col(sp)}"></span>${ticks}</div><div class="k-ddlab"><span><b>${p.dd} DD</b> since biofix ${dayLabel(p.biofix)}</span><span>${p.top}</span></div></div>`;
  }

  // A moth on the glue, top-down, as the camera sees it. Small seeded variation so no two crops match.
  const rnd = (seed) => { let x = Math.sin(seed * 9301 + 49297) * 233280; return x - Math.floor(x); };
  const MOTH = {
    CM:   { wing: '#77736b', patch: '#8b5a2b', hind: '#a8a39a', len: 30, spread: 0.42 },
    OFM:  { wing: '#58534c', patch: '#3f3a34', hind: '#8f8a82', len: 24, spread: 0.36 },
    OBLR: { wing: '#a07b47', patch: '#6c4f2a', hind: '#c8b48e', len: 30, spread: 0.5 },
    other_moth: { wing: '#b8a888', patch: '#9a8a6c', hind: '#d8ccb0', len: 26, spread: 0.6 },
  };
  function mothShape(sp, seed, cx, cy, scale = 1) {
    const m = MOTH[sp] || MOTH.other_moth, r = rnd(seed), rot = Math.round(r * 360), L = m.len * scale * (0.9 + rnd(seed + 1) * 0.2), a = m.spread;
    const wing = (side) => {
      const s = side;
      // forewing: a long triangle from the shoulder, outer edge nearly straight, tip squared off
      const tipX = s * L * (0.2 + a * 0.5), tipY = L * 0.5, inX = s * L * (0.05 + a * 0.12), inY = L * 0.6;
      return `<path d="M${s * L * 0.03} ${-L * 0.3} L ${s * L * 0.12} ${-L * 0.28} L ${tipX} ${tipY} L ${inX} ${inY} L ${s * L * 0.02} ${L * 0.3} Z" fill="${m.wing}" stroke="${m.patch}" stroke-width="${L * 0.015}" stroke-linejoin="round"/>`
        + `<path d="M${tipX * 0.72} ${tipY * 0.68} L ${tipX} ${tipY} L ${inX + (tipX - inX) * 0.35} ${inY - (inY - tipY) * 0.35} Z" fill="${m.patch}"/>`;
    };
    const hind = (s) => `<ellipse cx="${s * L * 0.16}" cy="${L * 0.16}" rx="${L * 0.2}" ry="${L * 0.3}" fill="${m.hind}" opacity=".7" transform="rotate(${s * 20} ${s * L * 0.16} ${L * 0.16})"/>`;
    return `<g transform="translate(${cx} ${cy}) rotate(${rot})">${hind(-1)}${hind(1)}${wing(-1)}${wing(1)}<ellipse cx="0" cy="${L * 0.05}" rx="${L * 0.07}" ry="${L * 0.38}" fill="#3b352d"/><path d="M${-L * 0.03} ${-L * 0.32} q ${-L * 0.1} ${-L * 0.2} ${-L * 0.22} ${-L * 0.24} M${L * 0.03} ${-L * 0.32} q ${L * 0.1} ${-L * 0.2} ${L * 0.22} ${-L * 0.24}" stroke="#3b352d" stroke-width="${Math.max(0.6, L * 0.02)}" fill="none"/></g>`;
  }
  function moth(sp, seed, size = 72) {
    const off = rnd(seed + 5) * 20;
    return `<svg class="k-crop" viewBox="0 0 72 72" width="${size}" height="${size}" role="img" aria-label="${window.OS.LABEL[sp] || 'Insect'} on the liner, photo crop"><rect width="72" height="72" fill="var(--liner, #f4f2e8)"/><path d="M${off} 0V72M${off + 48} 0V72M0 ${off + 6}H72M0 ${off + 54}H72" stroke="var(--liner-grid, #c9c6b6)" stroke-width="1"/>${mothShape(sp, seed, 36, 38, 1.35)}</svg>`;
  }

  // The whole liner in one trap: 7 × 7.75 in sticky area on a 1-in grid, every insect boxed by species.
  function liner(trapId = 'T2', { boxes = true, w = 420 } = {}) {
    const W = 700, H = 775, t = traps.find((x) => x.id === trapId);
    const n = { T1: [['CM', 9], ['other_moth', 2]], T2: [['OFM', 14], ['other_moth', 1]], T3: [['CM', 4]], T4: [['OBLR', 6]], T5: [], T6: [['OFM', 3]] }[trapId];
    let s = `<svg class="k-liner" viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${w}px" role="img" aria-label="Sticky liner in ${t.name} (${t.id}), ${n.reduce((a, b) => a + b[1], 0)} insects this week"><rect width="${W}" height="${H}" fill="var(--liner, #f4f2e8)"/>`;
    for (let i = 1; i < 7; i++) s += `<line x1="${i * 100}" x2="${i * 100}" y1="0" y2="${H}" stroke="var(--liner-grid, #c9c6b6)" stroke-width="2"/>`;
    for (let j = 1; j < 8; j++) s += `<line y1="${j * 100}" y2="${j * 100}" x1="0" x2="${W}" stroke="var(--liner-grid, #c9c6b6)" stroke-width="2"/>`;
    let k = 0;
    for (const [sp, count] of n) for (let i = 0; i < count; i++, k++) {
      const seed = trapId.charCodeAt(1) * 31 + k * 7, x = 60 + rnd(seed) * (W - 120), y = 60 + rnd(seed + 2) * (H - 120), L = (MOTH[sp] || MOTH.other_moth).len * 1.5;
      s += mothShape(sp, seed, x, y, 1.5);
      if (boxes) s += `<rect x="${x - L * 0.7}" y="${y - L * 0.7}" width="${L * 1.4}" height="${L * 1.4}" fill="none" stroke="${col(sp)}" stroke-width="4"/>`;
    }
    return s + '</svg>';
  }

  // Orchard plan: three blocks of tree rows, the barn with its hub, one pin per trap with its week's count.
  function map({ w = 600, h = 360 } = {}) {
    const blocks = [{ name: 'Block A · Gala', x: 0.06, y: 0.08, w: 0.42, h: 0.38 }, { name: 'Block B · Honeycrisp', x: 0.52, y: 0.06, w: 0.42, h: 0.44 }, { name: 'Block C · Empire', x: 0.1, y: 0.56, w: 0.62, h: 0.36 }];
    let s = `<svg class="k-map" viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="Orchard plan with ${traps.length} traps in 3 blocks">`;
    for (const b of blocks) {
      s += `<rect x="${b.x * w}" y="${b.y * h}" width="${b.w * w}" height="${b.h * h}" fill="var(--block)" rx="4"/>`;
      for (let r = b.y * h + 14; r < (b.y + b.h) * h - 6; r += 11) s += `<line x1="${b.x * w + 10}" x2="${(b.x + b.w) * w - 10}" y1="${r}" y2="${r}" stroke="var(--rows)" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 6"/>`;
      s += `<text x="${b.x * w + 10}" y="${(b.y + b.h) * h - 8}" class="k-maplab">${b.name}</text>`;
    }
    s += `<rect x="${0.8 * w}" y="${0.66 * h}" width="${0.12 * w}" height="${0.16 * h}" fill="var(--barn)" rx="3"/><text x="${0.86 * w}" y="${0.88 * h + 6}" text-anchor="middle" class="k-maplab">Barn · hub</text>`;
    for (const t of traps) {
      const n = t.week[t.lure] || 0, cx = t.x * w, cy = t.y * h, off = t.state === 'offline';
      s += `<g class="k-pin${off ? ' off' : ''}"><circle cx="${cx}" cy="${cy}" r="15" fill="${off ? 'var(--surface)' : col(t.lure)}" stroke="${off ? 'var(--negative, #b3261e)' : 'var(--surface)'}" stroke-width="${off ? 2.5 : 2}" ${off ? 'stroke-dasharray="4 3"' : ''}/><text x="${cx}" y="${cy + 4.5}" text-anchor="middle" class="k-pinn" fill="${off ? 'var(--negative, #b3261e)' : '#fff'}">${off ? '!' : n}</text><text x="${cx}" y="${cy + 30}" text-anchor="middle" class="k-maplab">${t.id}</text><title>${t.name} ${t.id}, ${t.lure} lure: ${off ? 'offline' : n + ' this week'}</title></g>`;
    }
    return s + '</svg>';
  }

  window.Kit = { stack, dd, moth, liner, map, trap7, col, SP };
})();
