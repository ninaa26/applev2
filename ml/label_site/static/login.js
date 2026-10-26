// The login page's moth: it flies in from off screen on a short easy curve, lands on the corner
// of the login card and flaps its wings twice. With reduced motion it is simply sitting there.
(() => {
  const moth = document.getElementById("moth"), SIZE = 58;
  if (!moth) return;
  const W = () => innerWidth, H = () => innerHeight;

  // It lands on the top-left corner of the login card.
  function landing() {
    const r = document.querySelector("form").getBoundingClientRect();
    return [r.left + 8, r.top + 8];
  }

  const place = (x, y, deg) => { moth.style.transform = `translate(${x - SIZE / 2}px, ${y - SIZE / 2}px) rotate(${deg}deg)`; };
  const REST = 135;  // heading once it has landed: facing into the card, wings fanned out to the top left

  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const [x, y] = landing(); place(x, y, REST); moth.style.visibility = "visible"; return;
  }

  // A short, gentle route: in from the left edge, one easy curve, down onto the corner from above and to the left.
  const [lx, ly] = landing();
  const pts = [[-0.06 * W(), ly + 0.28 * H()], [Math.max(40, lx - 0.22 * W()), ly + 0.06 * H()], [lx - 70, ly - 60], [lx, ly]];
  const P = [pts[0], ...pts, pts[pts.length - 1]];  // Catmull-Rom needs a point beyond each end
  const at = (u) => {  // u in 0..1 along the whole route
    const n = pts.length - 1, s = Math.min(n - 1e-9, u * n), i = Math.floor(s), t = s - i;
    const [p0, p1, p2, p3] = [P[i], P[i + 1], P[i + 2], P[i + 3]];
    const c = (k) => 0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t
      + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t * t * t);
    return [c(0), c(1)];
  };

  const DUR = 4500, t0 = performance.now() + 400;
  let heading = 70, last = at(0);
  moth.classList.add("flying");
  function frame(now) {
    const k = Math.max(0, (now - t0) / DUR);
    if (k >= 1) return land();
    const u = k < 0.5 ? 2 * k * k * 0.9 + k * 0.1 : 1 - Math.pow(1 - k, 2) * 2 * 0.9 - (1 - k) * 0.1;  // eases in and out
    const [x, y] = at(u), bob = Math.sin(now / 160) * 1.5 * (1 - k);  // flutter, settling as it lands
    const dir = Math.atan2(y - last[1], x - last[0]) * 180 / Math.PI + 90;  // the drawing faces up
    if (Math.hypot(x - last[0], y - last[1]) > 0.3) heading += ((((dir - heading) % 360) + 540) % 360 - 180) * 0.08;
    last = [x, y];
    place(x, y + bob, k > 0.85 ? heading + ((((REST - heading) % 360) + 540) % 360 - 180) * (k - 0.85) / 0.15 : heading);
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
