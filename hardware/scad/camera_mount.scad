// Orchard Sentinel: camera mount that sits in the delta trap's roof apex.
// A wedge that fills the top of the "V", with a pocket for the Camera Module 3 Wide
// (lens facing straight down, out of the open pocket) and a channel for the ribbon cable,
// which leaves through a slot in the roof. The roof itself keeps rain off the camera.
//
// Set floor_w and apex to YOUR measured trap (see hardware/mockup_template.py).
// Camera numbers follow the Raspberry Pi Camera Module 3 board (25 x 24 mm, M2 holes
// on a 21 x 12.5 mm pattern). Check them against the official mechanical drawing
// before printing.
// Not yet test-printed.

/* [Trap] */
floor_w = 200;      // mm, inside floor width
apex    = 165;      // mm, floor to inside apex
/* [Mount] */
mount_len   = 45;   // mm along the trap
drop        = 25;   // mm from the apex down to the camera face (matches --cam-drop); face must be >= 26 mm wide
wall        = 2.4;
/* [Camera Module 3] */
board_w = 25; board_h = 24; board_t = 1.2;
hole_dx = 21; hole_dy = 12.5; hole_d = 2.2; hole_top = 2;   // hole row 2 mm from the board's top edge
back_clear = 3.5;   // room for the connector/components on the back of the board

half = atan((floor_w / 2) / apex);          // roof panel angle from vertical
w_at_face = 2 * drop * tan(half);          // wedge width at the camera face

module wedge() {
    // Triangular prism matching the apex "V" down to the camera face, extruded along the trap.
    rotate([90, 0, 0]) linear_extrude(height = mount_len, center = true)
        polygon([[0, 0], [-w_at_face / 2, -drop], [w_at_face / 2, -drop]]);
}

module camera_pocket() {
    // Board pocket open to the bottom (lens points down), screw holes for M2 self-tappers
    // driven up through the board, and a channel that carries the ribbon to the apex slot.
    translate([0, 0, -drop]) {
        translate([-board_w / 2 - 0.3, -board_h / 2 - 0.3, -0.01]) cube([board_w + 0.6, board_h + 0.6, board_t + back_clear]);
        for (sx = [-1, 1], sy = [0, 1])
            translate([sx * hole_dx / 2, board_h / 2 - hole_top - sy * hole_dy, 0]) cylinder(d = hole_d - 0.4, h = 10, $fn = 24);
        // ribbon: along the pocket's back face to the end of the mount, then straight up to the apex
        translate([-8.5, board_h / 2 - 1, board_t]) cube([17, mount_len, 2.5]);
        translate([-8.5, mount_len / 2 - 3, board_t]) cube([17, 3, drop]);
    }
}

difference() {
    intersection() {
        wedge();
        // keep a solid shell even if the trap is very steep
        translate([-100, -mount_len / 2, -drop]) cube([200, mount_len, drop]);
    }
    camera_pocket();
}

echo(str("Roof half-angle ", half, " deg; wedge face ", w_at_face, " mm wide. The camera face must be >= 26 mm wide: increase drop if not."));
