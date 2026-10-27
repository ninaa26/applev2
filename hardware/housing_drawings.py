"""Dimensioned drawings of the retrofit camera head, cut from scad/trap_housing.scad.

Each part is cut (or projected) with OpenSCAD, so the outlines are the model's own geometry;
this script only arranges them and adds dimensions and labels. Needs OpenSCAD 2025 or newer
on PATH (manifold backend).

    python housing_drawings.py      # writes housing_end.svg, housing_side.svg, housing_head.svg and
                                    # housing_slot.svg next to this file

The numbers quoted in the dimensions are recomputed below from the same parameters as the
.scad file; keep the two in step.
"""

from __future__ import annotations

import math
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCAD = HERE / "scad" / "trap_housing.scad"

# --- the .scad parameters the dimensions quote ---
FLOOR_W, APEX_Z, TRAP_LEN, ROOF_T, GASKET_T = 195, 110, 227, 4, 1.5
CARD_W, CARD_L = 174, 198
LENS_Z, GLASS_D, GLASS_T = 112, 25, 2
HEAD_LEN, BOX_W, BOX_H, LID_T, SHADE_GAP, SHADE_T, SHADE_OVER = 208, 116, 52, 5, 8, 3, 12
BAR_T, BAR_LEN, LED_LEN = 9, 184, 170
SLOT = (36, 76)
CLAMP_Y = 32
HA = math.atan((FLOOR_W / 2) / APEX_Z)


def zl(x: float, t: float = 0) -> float:
    return APEX_Z - x / math.tan(HA) + t / math.sin(HA)


HB = zl(0, ROOF_T + GASKET_T) + 3
BOX_TOP = HB + BOX_H
SHADE_TOP = BOX_TOP + LID_T + SHADE_GAP + SHADE_T
EYE_Z = SHADE_TOP + 9
TUBE_BOT = LENS_Z - 1.5 - GLASS_T
BAR_BOT = zl(0, -BAR_T)

STYLE = {
    "asa": ("#d9dde3", "#4a5563"),
    "asa_dark": ("#9aa3ae", "#3b4450"),
    "behind": ("#eef0f3", "#c3c9d1"),
    "trap": ("#e8a29a", "#9b2c22"),
    "card": ("#f3e38a", "#8a7a1c"),
    "glass": ("#bfe3f5", "#2f7aa3"),
    "pcb": ("#5fae6d", "#24572e"),
    "metal": ("#c7c7c7", "#555555"),
    "cell": ("#6f8fd6", "#22397a"),
    "led": ("#ffe066", "#b08a00"),
    "slot": ("#ffffff", "#c2410c"),
}
DIM = "#c2410c"
CHAR_W = 6.0   # px per character at 11 px


def cut(part: str, view: str, at: float = 0, cut: bool = True) -> list[list[tuple[float, float]]]:
    """Outline loops of one part, in drawing coordinates (mm, y up)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "v.svg"
        subprocess.run(
            ["openscad", "--backend=manifold", "-q", "-D", 'part="view2d"', "-D", f'view_part="{part}"',
             "-D", f'view="{view}"', "-D", f"view_at={at}", "-D", f"view_cut={'true' if cut else 'false'}",
             "-o", str(out), str(SCAD)],
            check=True, capture_output=True)
        text = out.read_text()
    loops = []
    for sub in re.findall(r"M([^Mz]+)z", text):
        pts = [(float(a), -float(b)) for a, b in re.findall(r"(-?[\d.e+-]+),(-?[\d.e+-]+)", sub)]
        if len(pts) > 2:
            loops.append(pts)
    return loops


class Sheet:
    def __init__(self, title: str, subtitle: str, xmin: float, xmax: float, ymin: float, ymax: float, scale: float = 2.6):
        self.title, self.subtitle, self.s = title, subtitle, scale
        self.x0, self.y1 = xmin, ymax
        self.w = (xmax - xmin) * scale
        self.h = (ymax - ymin) * scale + 70
        self.items: list[str] = []

    def P(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.x0) * self.s, (self.y1 - y) * self.s + 70

    def shape(self, loops, style: str, opacity: float = 1.0, dash: bool = False) -> None:
        fill, stroke = STYLE[style]
        d = " ".join("M" + " L".join(f"{self.P(x, y)[0]:.2f},{self.P(x, y)[1]:.2f}" for x, y in loop) + "Z" for loop in loops)
        da = ' stroke-dasharray="5 3"' if dash else ""
        self.items.append(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="0.8" fill-rule="evenodd" opacity="{opacity}"{da}/>')

    def text(self, x, y, s, anchor="start", size=11, color="#1f2933", weight=400) -> None:
        px, py = self.P(x, y)
        self.items.append(f'<text x="{px:.1f}" y="{py:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{color}" '
                          f'font-weight="{weight}" font-family="Helvetica, Arial, sans-serif">{s}</text>')

    def line(self, x1, y1, x2, y2, color="#1f2933", width=0.7, dash="") -> None:
        a, b = self.P(x1, y1), self.P(x2, y2)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.items.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="{color}" stroke-width="{width}"{da}/>')

    def _arrow(self, x, y, ang) -> None:
        px, py = self.P(x, y)
        a = math.radians(ang)
        pts = [(px, py), (px - 7 * math.cos(a - 0.3), py + 7 * math.sin(a - 0.3)), (px - 7 * math.cos(a + 0.3), py + 7 * math.sin(a + 0.3))]
        self.items.append(f'<polygon points="{" ".join(f"{u:.1f},{v:.1f}" for u, v in pts)}" fill="{DIM}"/>')

    def dim_h(self, x1, x2, y, label, ext_from=None) -> None:
        if ext_from is not None:
            for x in (x1, x2):
                self.line(x, ext_from, x, y + (1.5 if y > ext_from else -1.5), DIM, 0.5)
        self.line(x1, y, x2, y, DIM, 0.8)
        self._arrow(x2, y, 0)
        self._arrow(x1, y, 180)
        self.text((x1 + x2) / 2, y + 1.3, label, "middle", 11, DIM, 600)

    def dim_v(self, x, y1, y2, label, ext_from=None, side="right", label_y=None) -> None:
        if ext_from is not None:
            for y in (y1, y2):
                self.line(ext_from, y, x + (1.5 if x > ext_from else -1.5), y, DIM, 0.5)
        self.line(x, y1, x, y2, DIM, 0.8)
        self._arrow(x, y2, 90 if y2 > y1 else -90)
        self._arrow(x, y1, -90 if y2 > y1 else 90)
        off = 1.5 if side == "right" else -1.5
        ly = (y1 + y2) / 2 - 1.5 if label_y is None else label_y
        self.text(x + off, ly, label, "start" if side == "right" else "end", 11, DIM, 600)

    def label(self, fx, fy, tx, ty, s, side) -> None:
        """Margin label: text sits on a shoulder at (tx, ty); the leader runs from the shoulder's inner end
        to the feature. side 'L': text ends at tx (left margin); 'R': text starts at tx."""
        w = len(s) * CHAR_W / self.s
        x_a, x_b = (tx - w, tx) if side == "L" else (tx, tx + w)
        self.line(x_a, ty, x_b, ty, "#6b7280", 0.6)
        inner = x_b if side == "L" else x_a
        self.line(inner, ty, fx, fy, "#6b7280", 0.6)
        px, py = self.P(fx, fy)
        self.items.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2" fill="#6b7280"/>')
        self.text(x_a, ty + 1.2, s, "start", 11)

    def legend(self, x, y, entries) -> None:
        for i, (style, label) in enumerate(entries):
            fill, stroke = STYLE[style]
            px, py = self.P(x, y - i * 6.5)
            self.items.append(f'<rect x="{px:.1f}" y="{py - 9:.1f}" width="14" height="10" fill="{fill}" stroke="{stroke}" stroke-width="0.8"/>')
            self.text(x + 7, y - i * 6.5 - 0.8, label, "start", 10.5)

    def save(self, path: Path) -> None:
        head = (f'<text x="16" y="28" font-size="18" font-weight="600" font-family="Helvetica, Arial, sans-serif" fill="#111827">{self.title}</text>'
                f'<text x="16" y="48" font-size="12" font-family="Helvetica, Arial, sans-serif" fill="#4b5563">{self.subtitle}</text>')
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w:.0f}" height="{self.h:.0f}" viewBox="0 0 {self.w:.0f} {self.h:.0f}">'
               f'<rect width="100%" height="100%" fill="#ffffff"/>{head}{"".join(self.items)}</svg>\n')
        path.write_text(svg)
        print(path)


def end_section() -> Sheet:
    sh = Sheet("End section through the camera (plane y = 0)",
               "Retrofit on the stock Alpha Scents delta trap, looking along it. mm; the card top is z = 0. Pale: parts behind the cut.",
               -225, 225, -28, 216)
    sh.shape(cut("head_box", "end", 0, False), "behind")
    sh.shape(cut("sht_shield", "end", 0, False), "behind")
    sh.shape(cut("knobs", "end", 0, False), "behind")
    for part, style in [("stock_trap", "trap"), ("card", "card"), ("light_bar", "asa"), ("leds", "led"), ("saddle", "asa"),
                        ("glass", "glass"), ("head_box", "asa"), ("camera", "pcb"), ("camera_cradle", "asa_dark"),
                        ("head_lid", "asa"), ("sun_shade", "asa")]:
        sh.shape(cut(part, "end", 0), style)
    sh.shape(cut("clamp_knobs", "end", 0, False), "metal")
    sh.dim_h(-FLOOR_W / 2, FLOOR_W / 2, -20, "195 stock trap floor", -4)
    sh.dim_h(-CARD_W / 2, CARD_W / 2, 12, "174 card", 0)
    sh.dim_h(-BOX_W / 2, BOX_W / 2, 210, "116 head box", BOX_TOP + LID_T)
    sh.dim_h(-38, 38, 50, "76 saddle", zl(38, ROOF_T + GASKET_T))
    sh.dim_v(-5, 0, APEX_Z, "110 to inner apex", None, "left", 36)
    sh.dim_v(5, 0, LENS_Z, "112 lens", None, "right", 36)
    sh.dim_v(84, HB, BOX_TOP, "52", 58)
    sh.dim_v(84, BOX_TOP + LID_T, BOX_TOP + LID_T + SHADE_GAP, "8 air gap", 58)
    sh.dim_v(112, -4, EYE_Z + 12, f"{EYE_Z + 12 + 4:.0f} overall", 0)
    sh.text(-60, 24, f"roof {90 - math.degrees(HA):.1f}° (stock trap, unchanged)", "start", 11, DIM, 600)
    for (fx, fy, ty, s) in [
        (-50, SHADE_TOP - 1.5, 196, "sun shade, 8 mm air gap"),
        (-45, BOX_TOP + 1, 178, "lid on a 3 mm silicone cord gasket"),
        (-56, HB + 25, 160, "sealed head box (Pi, battery, boards)"),
        (-8, LENS_Z + 18, 142, "camera board in its cradle"),
        (-30, HB - 8, 124, "saddle, on foam tape over the peak"),
        (-11, TUBE_BOT + 1, 106, "Ø25 glass at the end of the camera tube"),
        (-28, zl(28, -BAR_T) + 1, 88, "light bar: LED strip + diffuser each side"),
        (-70, zl(70, 2), 64, "stock roof (slot cut in the peak)"),
    ]:
        sh.label(fx, fy, -128, ty, s, "L")
    for (fx, fy, ty, s) in [
        (0, EYE_Z, 206, "hanging eye at each end"),
        (64, BOX_TOP + LID_T + 8, 190, "lid thumbscrews (M4, printed knob)"),
        (47, HB - 18, 112, "temp/RH sensor shield"),
        (6, BAR_BOT - 5, 70, "clamp knobs (M4) pull the light bar up"),
        (60, 0.3, 30, "sticky card, as before"),
    ]:
        sh.label(fx, fy, 122, ty, s, "R")
    sh.legend(122, 160, [("asa", "printed, ASA"), ("trap", "stock trap"), ("glass", "glass"), ("led", "LED strip"),
                         ("card", "sticky card"), ("pcb", "electronics")])
    return sh


def side_section() -> Sheet:
    sh = Sheet("Side section along the ridge (plane x = 0)",
               "Battery end on the right. mm. Pale: cells and the Pi behind the cut.", -225, 225, -28, 216, 2.3)
    sh.shape(cut("cells", "side", 0, False), "behind")
    sh.shape(cut("pi", "side", 0, False), "behind")
    for part, style in [("stock_trap", "trap"), ("card", "card"), ("light_bar", "asa"), ("clamp_knobs", "metal"), ("saddle", "asa"),
                        ("glass", "glass"), ("head_box", "asa"), ("camera", "pcb"), ("camera_cradle", "asa_dark"),
                        ("electronics_plate", "asa_dark"), ("pi", "pcb"), ("battery_cartridge", "cell"), ("battery_lid", "cell"),
                        ("head_lid", "asa"), ("sun_shade", "asa")]:
        sh.shape(cut(part, "side", 0), style)
    sh.dim_h(-TRAP_LEN / 2, TRAP_LEN / 2, -20, "227 stock trap", -4)
    sh.dim_h(-CARD_L / 2, CARD_L / 2, 12, "198 card", 0)
    sh.dim_h(-HEAD_LEN / 2 - 7, HEAD_LEN / 2 + 7, 212, "222 head incl. eyes", EYE_Z + 12)
    sh.dim_h(-BAR_LEN / 2, BAR_LEN / 2, 60, f"{BAR_LEN} light bar", BAR_BOT)
    sh.dim_h(-SLOT[1] / 2, SLOT[1] / 2, 80, f"{SLOT[1]} slot", APEX_Z)
    sh.dim_h(16, 100, 172 - 30, "84 battery bay", HB + 3)
    sh.dim_h(-100, -16, 172 - 30, "84 Pi + boards", HB + 3)
    for (fx, fy, ty, s) in [
        (-90, SHADE_TOP - 1.5, 196, "sun shade"),
        (-60, HB + 12, 176, "Pi 5 on the electronics plate"),
        (-99, HB + 22, 158, "boost, INA219, LED FET on the wing"),
        (-20, HB - 6, 100, "saddle (foam tape on the roof)"),
        (-CLAMP_Y, BAR_BOT - 4, 40, "clamp knob"),
    ]:
        sh.label(fx, fy, -122, ty, s, "L")
    for (fx, fy, ty, s) in [
        (0, EYE_Z, 206, "hanging eye"),
        (40, HB + 25, 180, "battery cartridge, lifted out by its grip"),
        (0, TUBE_BOT + 1, 104, "camera tube + glass through the slot"),
        (60, BAR_BOT + 3, 86, "light bar inside the apex"),
    ]:
        sh.label(fx, fy, 122, ty, s, "R")
    return sh


def head_plan() -> Sheet:
    sh = Sheet("Head, plan view inside the box (lid off, cut through the button and vent)",
               "mm. Hinge on the left (-X), thumbscrews on the right (+X), battery end at the top.", -175, 175, -122, 122, 2.6)
    sh.shape(cut("head_box", "plan", HB + 4), "behind")
    sh.shape(cut("head_box", "plan", HB + 28), "asa")
    sh.shape(cut("electronics_plate", "plan", 0, False), "asa_dark")
    sh.shape(cut("pi", "plan", 0, False), "pcb")
    sh.shape(cut("camera_cradle", "plan", 0, False), "asa_dark")
    sh.shape(cut("camera", "plan", 0, False), "pcb")
    sh.shape(cut("battery_cartridge", "plan", 0, False), "cell")
    sh.shape(cut("cells", "plan", HB + 3 + 13), "cell")
    sh.shape(cut("knobs", "plan", 0, False), "metal")
    sh.dim_h(-BOX_W / 2, BOX_W / 2, -116, "116", -HEAD_LEN / 2 - 7)
    sh.dim_v(100, -HEAD_LEN / 2, HEAD_LEN / 2, "208 box", 70)
    sh.dim_v(84, 16, 100, "84 bay", 50)
    sh.dim_h(-47, 47, 112, "94 cartridge", 100)
    sh.dim_h(-47, 41, -86, "88 Pi 5 (HDMI edge to -Y)", -74)
    for (fx, fy, ty, s) in [
        (-62, 55, 75, "hinge, M3 pins"),
        (-58, 30, 40, "M12 breather vent"),
        (-58, 0, 8, "NEW CARD button"),
        (-40, -99, -95, "wing: boost, INA219, FET"),
        (-20, -40, -50, "Pi 5"),
    ]:
        sh.label(fx, fy, -75, ty, s, "L")
    for (fx, fy, ty, s) in [
        (64, 60, 80, "thumbscrew"),
        (12, 60, 50, "1S4P 21700 cartridge"),
        (0, 0, 15, "camera over the tube"),
        (0, 108, 118, "hanging eye"),
    ]:
        sh.label(fx, fy, 112, ty, s, "R")
    return sh


def slot_and_bar() -> Sheet:
    sh = Sheet("Roof slot and light bar, seen from below",
               "mm. Cut the slot with the printed template, centred on the peak; the light bar's knobs reach up through it.",
               -150, 150, -105, 112, 2.6)
    sh.shape(cut("light_bar", "plan", 0, False), "asa")
    sh.shape(cut("leds", "plan", 0, False), "led")
    sh.shape(cut("slot", "plan", 0, True), "slot", 1, True)
    sh.shape(cut("glass", "plan", 0, False), "glass")
    sh.shape(cut("clamp_knobs", "plan", 0, False), "metal")
    sh.dim_v(50, -LED_LEN / 2, LED_LEN / 2, f"{LED_LEN} LED strip", 34, "right", 20)
    sh.dim_v(95, -BAR_LEN / 2, BAR_LEN / 2, f"{BAR_LEN} light bar", 37, "right", -20)
    sh.dim_h(-36, 36, -103, "72", -BAR_LEN / 2)
    sh.dim_h(-SLOT[0] / 2, SLOT[0] / 2, 104, f"{SLOT[0]} slot", SLOT[1] / 2 - 10)
    sh.dim_v(-50, -SLOT[1] / 2, SLOT[1] / 2, f"{SLOT[1]} slot", -15, "left")
    sh.dim_h(22, 34, -96, "strips 22-34 from the centre line", -LED_LEN / 2)
    for (fx, fy, ty, s) in [(0, 0, -20, "Ø25 glass"), (0, CLAMP_Y, 45, "clamp knob (2)")]:
        sh.label(fx, fy, 95, ty, s, "R")
    return sh


if __name__ == "__main__":
    end_section().save(HERE / "housing_end.svg")
    side_section().save(HERE / "housing_side.svg")
    head_plan().save(HERE / "housing_head.svg")
    slot_and_bar().save(HERE / "housing_slot.svg")
