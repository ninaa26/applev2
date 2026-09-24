"""Make a 1:1 cut-and-fold template (SVG) for a mockup delta trap, and check the camera's view.

The defaults are a stand-in for the Trécé Pherocon VI (≈16.5 cm tall per retailer
listings). MEASURE A REAL TRAP AND LINER and pass the numbers in; everything else
(panel sizes, cable slot, LED holes, whether the liner is fully in view)
follows from them.

    python mockup_template.py --floor-width 200 --length 280 --apex 165 --liner 180x180 -o mockup.svg

Print the SVG at 100 % (no "fit to page") on large paper or tile it, check the
50 mm scale bar with a ruler, then cut from corrugated plastic or foam board.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

# Camera Module 3 Wide (Raspberry Pi docs): 102° horizontal, 67° vertical, focuses from 5 cm.
HFOV, VFOV = 102.0, 67.0
SENSOR_PX = (4608, 2592)


def coverage(height_mm: float) -> tuple[float, float]:
    """Width × depth (mm) the camera sees on the floor from `height_mm` above it."""
    return (2 * height_mm * math.tan(math.radians(HFOV / 2)), 2 * height_mm * math.tan(math.radians(VFOV / 2)))


def camera_check(apex: float, cam_drop: float, liner_w: float, liner_l: float) -> list[str]:
    h = apex - cam_drop
    along, across = coverage(h)  # wide axis runs along the trap's length
    mm_per_px = across / SENSOR_PX[1]
    lines = [
        f"Camera lens {h:.0f} mm above the liner (apex {apex:.0f} mm − {cam_drop:.0f} mm mount).",
        f"View on the floor: {along:.0f} mm along the trap × {across:.0f} mm across.",
        f"Liner {liner_l:.0f} × {liner_w:.0f} mm: "
        + ("fully in view." if along >= liner_l and across >= liner_w else "NOT fully in view: raise the camera or use a smaller liner."),
        f"Resolution ≈ {mm_per_px:.3f} mm/px (≈ {1 / mm_per_px:.0f} px per mm): OFM (~6 mm) ≈ {6 / mm_per_px:.0f} px long.",
    ]
    if h < 50:
        lines.append("WARNING: closer than the 5 cm minimum focus distance.")
    return lines


def svg_template(floor_w: float, length: float, apex: float, liner_w: float, liner_l: float,
                 window: float, led_d: float) -> str:
    slant = math.hypot(floor_w / 2, apex)          # each roof panel's width (floor edge to apex)
    tab = 15.0
    margin = 20.0
    # Flat pattern, left to right: glue tab | roof A | roof B | floor | glue tab. Fold lines between.
    xs = [margin, margin + tab, margin + tab + slant, margin + tab + 2 * slant, margin + tab + 2 * slant + floor_w,
          margin + 2 * tab + 2 * slant + floor_w]
    W, H = xs[-1] + margin, length + 2 * margin + 60
    y0, y1 = margin, margin + length
    apex_x = xs[2]  # the fold between the two roof panels is the apex
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
        '<style>.cut{fill:none;stroke:#000;stroke-width:0.4}.fold{fill:none;stroke:#1a6;stroke-width:0.4;stroke-dasharray:4 3}'
        '.mark{fill:none;stroke:#b22;stroke-width:0.4}.txt{font:5px sans-serif;fill:#222}</style>',
        f'<rect class="cut" x="{xs[0]}" y="{y0}" width="{xs[-1] - xs[0]}" height="{length}"/>',
    ]
    for x in xs[1:-1]:
        out.append(f'<line class="fold" x1="{x}" y1="{y0}" x2="{x}" y2="{y1}"/>')
    # Ribbon-cable slot on the apex fold, at the cable end of the camera mount (mount sits halfway along).
    cy = (y0 + y1) / 2
    out.append(f'<rect class="cut" x="{apex_x - 3}" y="{cy + 20}" width="6" height="{window}"/>')
    out.append(f'<text class="txt" x="{apex_x + 5}" y="{cy + 26}">cable slot (camera mount centred on this fold, halfway along)</text>')
    # LED holes: one on each roof panel, 40 % of the way down from the apex, a quarter of the length from each end.
    for side in (-1, 1):
        lx = apex_x + side * 0.4 * slant
        for fy in (0.25, 0.75):
            out.append(f'<circle class="cut" cx="{lx}" cy="{y0 + fy * length}" r="{led_d / 2}"/>')
    # Liner outline on the floor panel (centred), and the lure spot.
    fx = (xs[3] + xs[4]) / 2
    out.append(f'<rect class="mark" x="{fx - liner_w / 2}" y="{cy - liner_l / 2}" width="{liner_w}" height="{liner_l}"/>')
    out.append(f'<rect class="mark" x="{fx - 12}" y="{cy - 6}" width="24" height="12"/>')
    out.append(f'<text class="txt" x="{fx - liner_w / 2}" y="{cy - liner_l / 2 - 2}">liner {liner_w:.0f} × {liner_l:.0f} mm · red box = lure spot (masked)</text>')
    labels = [("glue tab", xs[0], xs[1]), ("roof A", xs[1], xs[2]), ("roof B", xs[2], xs[3]), ("floor", xs[3], xs[4]), ("tab", xs[4], xs[5])]
    for name, a, b in labels:
        out.append(f'<text class="txt" x="{(a + b) / 2 - 8}" y="{y0 + 10}">{name}</text>')
    # Scale bar to check the print.
    sy = y1 + 20
    out.append(f'<line class="cut" x1="{margin}" y1="{sy}" x2="{margin + 50}" y2="{sy}"/>')
    out.append(f'<text class="txt" x="{margin}" y="{sy + 8}">50 mm: measure this after printing (print at 100 %)</text>')
    out.append(
        f'<text class="txt" x="{margin}" y="{sy + 18}">floor {floor_w:.0f} mm · length {length:.0f} mm · apex {apex:.0f} mm · '
        f'roof panels {slant:.1f} mm wide · green dashed = fold · black = cut</text>'
    )
    out.append("</svg>")
    return "\n".join(out)


def parse_wxh(s: str) -> tuple[float, float]:
    a, b = s.lower().split("x")
    return float(a), float(b)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--floor-width", type=float, default=200, help="mm, inside width of the trap floor")
    ap.add_argument("--length", type=float, default=280, help="mm, trap length (open end to open end)")
    ap.add_argument("--apex", type=float, default=165, help="mm, floor to roof peak (inside)")
    ap.add_argument("--liner", type=parse_wxh, default=(180, 180), help="mm, WIDTHxLENGTH of the sticky liner")
    ap.add_argument("--cam-drop", type=float, default=25, help="mm the lens sits below the apex in its mount")
    ap.add_argument("--window", type=float, default=18, help="mm, cable slot length at the apex")
    ap.add_argument("--led", type=float, default=6, help="mm, LED hole diameter")
    ap.add_argument("-o", "--out", type=Path, default=Path("mockup_template.svg"))
    args = ap.parse_args(argv)

    for line in camera_check(args.apex, args.cam_drop, args.liner[0], args.liner[1]):
        print(line)
    args.out.write_text(svg_template(args.floor_width, args.length, args.apex, args.liner[0], args.liner[1], args.window, args.led))
    print(f"Template written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
