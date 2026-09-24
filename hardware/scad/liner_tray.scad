// Orchard Sentinel: slide-in liner tray (the Sticky Pi "drawer" idea).
// Every fresh liner lands in exactly the same place under the camera.
// ArUco markers (hardware/print/tray_markers.png, 15 mm) sit in recessed pockets at
// the corners, OUTSIDE the liner, so alignment survives liner swaps.
// A small raised seat in the middle holds the lure in the spot the software masks out.
// Not yet test-printed. Large trays can be printed in two halves (split = true).

liner_w = 180;   // mm, measured liner width  (across the trap)
liner_l = 180;   // mm, measured liner length (along the trap)
clear   = 1.0;   // slack around the liner
rim     = 18;    // border that carries the markers
base_t  = 2.0;
lip_h   = 1.6;   // how far the rim stands above the liner bed
marker  = 15;    // ArUco size, mm
lure_w  = 24; lure_l = 12;   // lure seat footprint (matches the dashboard's default mask)
split   = false;

W = liner_w + 2 * (clear + rim);
L = liner_l + 2 * (clear + rim);

module tray() {
    difference() {
        cube([W, L, base_t + lip_h]);
        // liner bed
        translate([rim, rim, base_t]) cube([liner_w + 2 * clear, liner_l + 2 * clear, lip_h + 1]);
        // finger notch to lift the liner out
        translate([W / 2, rim - 1, base_t]) cylinder(d = 26, h = lip_h + 1, $fn = 48);
        // marker pockets, 0.4 mm deep, centred in the rim at each corner
        for (p = [[rim / 2, L - rim / 2], [W - rim / 2, L - rim / 2], [W - rim / 2, rim / 2], [rim / 2, rim / 2]])
            translate([p[0] - (marker + 1) / 2, p[1] - (marker + 1) / 2, base_t + lip_h - 0.4]) cube([marker + 1, marker + 1, 1]);
    }
    // lure seat: a low frame in the centre of the bed (the liner has a slit or the lure sits on top)
    translate([W / 2 - lure_w / 2 - 1.2, L / 2 - lure_l / 2 - 1.2, base_t])
        difference() {
            cube([lure_w + 2.4, lure_l + 2.4, 0.8]);
            translate([1.2, 1.2, -0.1]) cube([lure_w, lure_l, 1]);
        }
}

if (split) {
    intersection() { tray(); cube([W, L / 2, 10]); }
    translate([0, 10, 0]) intersection() { tray(); translate([0, L / 2, 0]) cube([W, L / 2, 10]); }
} else {
    tray();
}

echo(str("Tray ", W, " x ", L, " mm. Mask for the dashboard (fractions of the image) is set per trap on the server."));
