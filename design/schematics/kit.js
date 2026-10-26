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
  // Each species is drawn with the marks that tell it apart, its colours mixed with the page's label colour
  // (--cm, --ofm, --oblr, --other) so a crop reads as the same species as its dot and its bars.
  //   CM: grey, fine wavy cross-lines, the copper eyespot at the wing tip.
  //   OFM: smaller and narrow, dark grey-brown, a row of short pale dashes along the leading edge.
  //   OBLR: broad "bell" shoulders, tan, dark basal patch, the oblique band and a spot near the tip.
  //   other_moth: plain and broad, one small dark spot mid-wing.
  const mix = (sp, pct, base) => `color-mix(in srgb, ${col(sp)} ${pct}%, ${base})`;
  const MOTH = {
    CM:   { len: 30, spread: 0.42, shoulder: 0.14, wing: [15, '#7f7c76'], hind: [10, '#b9b5ad'], mark: [55, '#b07a3a'], line: [30, '#4c4842'] },
    OFM:  { len: 23, spread: 0.32, shoulder: 0.1,  wing: [30, '#5b564f'], hind: [16, '#9b968e'], mark: [40, '#f1ead8'], line: [35, '#2f2b26'] },
    OBLR: { len: 30, spread: 0.52, shoulder: 0.26, wing: [20, '#b8915a'], hind: [12, '#d9c6a2'], mark: [55, '#6a4723'], line: [40, '#5a3d1e'] },
    other_moth: { len: 26, spread: 0.62, shoulder: 0.18, wing: [30, '#bcae90'], hind: [20, '#ddd3bd'], mark: [40, '#6f6455'], line: [30, '#8c7f68'] },
  };
  let clipN = 0;
  function mothShape(sp, seed, cx, cy, scale = 1) {
    const m = MOTH[sp] || MOTH.other_moth, k = MOTH[sp] ? sp : 'other_moth', r = rnd(seed), rot = Math.round(r * 360);
    const L = m.len * scale * (0.9 + rnd(seed + 1) * 0.2), a = m.spread, f = (v) => +v.toFixed(2);
    const paint = (spec) => mix(k, spec[0], spec[1]);
    // Right forewing, head up: shoulder S, apex A (wing tip), tornus T, root R along the body. The left is its mirror.
    const S = [L * 0.04, -L * 0.3], A = [L * (0.2 + a * 0.5), L * 0.48], T = [L * (0.08 + a * 0.2), L * 0.62], R = [L * 0.03, L * 0.3];
    const lerp = (p, q, t) => [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
    const costa = (t) => { const p = lerp(S, A, t), bow = Math.sin(Math.PI * t) * L * m.shoulder * (1 - t * 0.6); return [p[0] + bow, p[1] - bow * 0.3]; };
    const body = (t) => [0, -L * 0.3 + L * 0.95 * t];
    const pt = (p) => `${f(p[0])} ${f(p[1])}`;
    const c1 = costa(0.35), c2 = costa(0.75);
    const outline = `M${pt(S)} C ${pt(c1)} ${pt(c2)} ${pt(A)} Q ${pt(lerp(A, T, 0.5).map((v, i) => v + (i ? L * 0.02 : L * 0.03)))} ${pt(T)} Q ${pt([R[0] + L * 0.02, L * 0.5])} ${pt(R)} Z`;
    const id = `km${++clipN}`, line = paint(m.line), mark = paint(m.mark), sw = f(Math.max(0.4, L * 0.018));
    const band = (t1, t2, u1, u2) => `M${pt(lerp(costa(t1), costa(t1), 0).map((v, i) => v + (i ? -L * 0.05 : L * 0.08)))} L ${pt(costa(t2).map((v, i) => v + (i ? -L * 0.05 : L * 0.08)))} L ${pt(body(u2))} L ${pt(body(u1))} Z`;
    let marks = '';
    if (k === 'CM') {
      for (let t = 0.08; t < 0.66; t += 0.075) {
        const p = costa(t), q = body(t + 0.12), mid = lerp(p, q, 0.5);
        marks += `<path d="M${pt(p)} Q ${pt([mid[0] + L * 0.025, mid[1] - L * 0.03])} ${pt(q)}" style="stroke:${line}" stroke-width="${sw}" fill="none" opacity=".55"/>`;
      }
      const o = lerp(lerp(A, T, 0.35), S, 0.16), ang = f(Math.atan2(A[1] - S[1], A[0] - S[0]) * 180 / Math.PI);
      marks += `<ellipse cx="${f(o[0])}" cy="${f(o[1])}" rx="${f(L * 0.13)}" ry="${f(L * 0.085)}" transform="rotate(${ang} ${f(o[0])} ${f(o[1])})" style="fill:${mark};stroke:${line}" stroke-width="${sw}"/>`
        + `<path d="M${f(o[0] - L * 0.05)} ${f(o[1] - L * 0.01)} l ${f(L * 0.07)} ${f(L * 0.05)} M${f(o[0] - L * 0.02)} ${f(o[1] - L * 0.04)} l ${f(L * 0.07)} ${f(L * 0.05)}" stroke="#e6c27a" stroke-width="${sw}" opacity=".9"/>`;
    } else if (k === 'OFM') {
      for (let t = 0.32; t < 0.95; t += 0.11) {
        const p = costa(t), q = lerp(p, body(t + 0.1), 0.28);
        marks += `<path d="M${pt(p)} L ${pt(q)}" style="stroke:${mark}" stroke-width="${f(sw * 1.3)}" stroke-linecap="round" opacity=".9"/>`;
      }
      const w1 = costa(0.55), w2 = body(0.72);
      marks += `<path d="M${pt(w1)} Q ${pt(lerp(w1, w2, 0.5).map((v, i) => v + (i ? L * 0.04 : -L * 0.02)))} ${pt(w2)}" style="stroke:${mark}" stroke-width="${sw}" fill="none" opacity=".35"/>`
        + `<circle cx="${f(lerp(A, S, 0.12)[0] - L * 0.02)}" cy="${f(lerp(A, S, 0.12)[1])}" r="${f(L * 0.03)}" style="fill:${line}"/>`;
    } else if (k === 'OBLR') {
      marks += `<path d="${band(0, 0.16, 0, 0.2)}" style="fill:${mark}" opacity=".75"/>`
        + `<path d="${band(0.36, 0.52, 0.62, 0.8)}" style="fill:${mark}"/>`
        + `<path d="M${pt(costa(0.74))} L ${pt(costa(0.88))} L ${pt(lerp(costa(0.8), body(0.7), 0.3))} Z" style="fill:${mark}"/>`;
    } else {
      const d = lerp(costa(0.5), body(0.55), 0.45);
      marks += `<circle cx="${f(d[0])}" cy="${f(d[1])}" r="${f(L * 0.035)}" style="fill:${mark}" opacity=".7"/>`;
    }
    const fore = `<path d="${outline}" style="fill:${paint(m.wing)};stroke:${line}" stroke-width="${sw}" stroke-linejoin="round"/><g clip-path="url(#${id})">${marks}</g>`;
    const hindW = `<ellipse cx="${f(L * (0.12 + a * 0.12))}" cy="${f(L * 0.18)}" rx="${f(L * (0.16 + a * 0.08))}" ry="${f(L * 0.3)}" style="fill:${paint(m.hind)}" opacity=".75" transform="rotate(20 ${f(L * 0.14)} ${f(L * 0.18)})"/>`;
    const dark = mix(k, 15, '#2e2a25'), aw = f(Math.max(0.6, L * 0.022)), ant = k === 'OBLR' ? 0.18 : 0.26;
    return `<g transform="translate(${f(cx)} ${f(cy)}) rotate(${rot})"><defs><clipPath id="${id}"><path d="${outline}"/></clipPath></defs>`
      + `${hindW}<g transform="scale(-1 1)">${hindW}</g>${fore}<g transform="scale(-1 1)">${fore}</g>`
      + `<ellipse cx="0" cy="${f(L * 0.12)}" rx="${f(L * 0.06)}" ry="${f(L * 0.3)}" style="fill:${dark}"/>`
      + `<ellipse cx="0" cy="${f(-L * 0.2)}" rx="${f(L * 0.08)}" ry="${f(L * 0.12)}" style="fill:${dark}"/><circle cx="0" cy="${f(-L * 0.34)}" r="${f(L * 0.055)}" style="fill:${dark}"/>`
      + `<path d="M${f(-L * 0.03)} ${f(-L * 0.37)} q ${f(-L * 0.08)} ${f(-L * ant * 0.8)} ${f(-L * ant)} ${f(-L * ant)} M${f(L * 0.03)} ${f(-L * 0.37)} q ${f(L * 0.08)} ${f(-L * ant * 0.8)} ${f(L * ant)} ${f(-L * ant)}" style="stroke:${dark}" stroke-width="${aw}" fill="none" stroke-linecap="round"/></g>`;
  }
  function moth(sp, seed, size = 72) {
    const off = rnd(seed + 5) * 20;
    return `<svg class="k-crop" viewBox="0 0 72 72" width="${size}" height="${size}" role="img" aria-label="${window.OS.LABEL[sp] || 'Insect'} on the liner, photo crop"><rect width="72" height="72" fill="var(--liner, #f4f2e8)"/><path d="M${off} 0V72M${off + 48} 0V72M0 ${off + 6}H72M0 ${off + 54}H72" stroke="var(--liner-grid, #c9c6b6)" stroke-width="1"/>${mothShape(sp, seed, 36, 37, 1.2)}</svg>`;
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
