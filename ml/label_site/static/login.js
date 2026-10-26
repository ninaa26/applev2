// The login page's moth: it flies in from off screen, wanders about for a few seconds, lands on a paint
// splotch and flaps its wings twice. With reduced motion it is simply sitting there.
(() => {
  const moth = document.getElementById("moth"), SIZE = 58;
  if (!moth) return;
  const W = () => innerWidth, H = () => innerHeight;

  // A spot on a splotch for it to land: inside the blob's paint, on screen, clear of the form.
  function landing() {
    const form = document.querySelector("form").getBoundingClientRect();
    const spots = (blob, gap, edge) => {  // points inside the blob's paint, on screen, `gap` px clear of the form
      const path = blob.querySelector(".main"), m = path.getScreenCTM().inverse(), pt = blob.createSVGPoint(), out = [];
      for (let y = edge; y < H() - edge; y += 12) for (let x = edge; x < W() - edge; x += 12) {
        if (x > form.left - gap && x < form.right + gap && y > form.top - gap && y < form.bottom + gap) continue;
        pt.x = x; pt.y = y;
        if (path.isPointInFill(pt.matrixTransform(m))) out.push([x, y]);
      }
      return out;
    };
    // Roomy first; on a phone the form covers most of the paint, so then any visible bit beside it will do.
    for (const [gap, edge, min] of [[50, 40, 30], [SIZE / 2, SIZE / 2, 4]]) for (const blob of document.querySelectorAll(".blob")) {
      const good = spots(blob, gap, edge);
      if (good.length >= min) {  // the middle of the visible paint, so it isn't perched on an edge
        const cx = good.reduce((s, p) => s + p[0], 0) / good.length, cy = good.reduce((s, p) => s + p[1], 0) / good.length;
        return good.reduce((a, b) => Math.hypot(b[0] - cx, b[1] - cy) < Math.hypot(a[0] - cx, a[1] - cy) ? b : a);
      }
    }
    return [W() * 0.15, H() * 0.2];
  }

  const place = (x, y, deg) => { moth.style.transform = `translate(${x - SIZE / 2}px, ${y - SIZE / 2}px) rotate(${deg}deg)`; };
  const REST = -18;  // heading once it has landed

  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const [x, y] = landing(); place(x, y, REST); moth.style.visibility = "visible"; return;
  }

  // Waypoints as shares of the screen: in from the left edge, a loop round the page, then the landing spot.
  const [lx, ly] = landing();
  const pts = [[-0.1, 0.78], [0.18, 0.6], [0.36, 0.2], [0.62, 0.12], [0.84, 0.38], [0.7, 0.72], [0.42, 0.88], [0.2, 0.62]]
    .map(([x, y]) => [x * W(), y * H()]);
  pts.push([lx + 60, ly + 70], [lx, ly]);
  const P = [pts[0], ...pts, pts[pts.length - 1]];  // Catmull-Rom needs a point beyond each end
  const at = (u) => {  // u in 0..1 along the whole route
    const n = pts.length - 1, s = Math.min(n - 1e-9, u * n), i = Math.floor(s), t = s - i;
    const [p0, p1, p2, p3] = [P[i], P[i + 1], P[i + 2], P[i + 3]];
    const c = (k) => 0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t
      + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t * t * t);
    return [c(0), c(1)];
  };

  const DUR = 7000, t0 = performance.now() + 600;
  let heading = 90, last = at(0);
  moth.classList.add("flying");
  function frame(now) {
    const k = Math.max(0, (now - t0) / DUR);
    if (k >= 1) return land();
    const u = 1 - Math.pow(1 - k, 1.8);  // slows down as it comes in to land
    const [x, y] = at(u), bob = Math.sin(now / 90) * 3 * (1 - k);  // flutter, settling as it lands
    const dir = Math.atan2(y - last[1], x - last[0]) * 180 / Math.PI + 90;  // the drawing faces up
    if (Math.hypot(x - last[0], y - last[1]) > 0.3) heading += ((((dir - heading) % 360) + 540) % 360 - 180) * 0.15;
    last = [x, y];
    place(x, y + bob, k > 0.92 ? heading + (REST - heading) * (k - 0.92) / 0.08 : heading);
    moth.style.visibility = "visible";
    requestAnimationFrame(frame);
  }
  function land() {
    place(lx, ly, REST);
    moth.classList.remove("flying");
    setTimeout(() => moth.classList.add("flap2"), 450);  // settles, then two slow flaps
  }
  requestAnimationFrame(frame);
  addEventListener("resize", () => { if (!moth.classList.contains("flying")) { const [x, y] = landing(); place(x, y, REST); } });
})();
