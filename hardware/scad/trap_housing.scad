// Orchard Sentinel: weatherproof camera head that retrofits onto a stock delta trap (Pi 5 build).
// Spec, part list and install steps: hardware/HOUSING.md. Prototype v1, not yet test-printed.
//
// Axes: X across the trap, Y along it, Z up. z = 0 is the top of the sticky card lying on the
// trap floor. Everything is in mm.
//
// The trap stays the farmer's own Alpha Scents red delta trap (hardware/TRAP.md: 195 mm floor,
// 110 mm to the inside of the apex, 227 mm long). One 36 x 76 mm slot is cut in the middle of the
// roof peak (printed template). Then:
//   - the head (sealed box: Pi 5, battery cartridge, power boards) sits on a saddle over the peak;
//     its camera tube drops through the slot so the lens looks down through glass at the apex;
//   - the light bar sits inside the apex, carries the two diffused LED strips, and two hand
//     knobs pull it up against the roof, clamping the roof between saddle and light bar;
//   - the whole thing hangs from the two eyes on the head; the trap hangs from the clamp.
// The card still slides in and out of the trap the usual way; an optional card guide taped to
// the floor makes every card land in the same spot.
//
// Pick a part below (or pass -D 'part="saddle"' on the command line) and export STL.
// hardware/scad/export_housing.sh exports every part and the preview images.

part = "assembly"; // [assembly, exploded, section, head_box, head_lid, sun_shade, saddle, light_bar, camera_cradle, electronics_plate, battery_cartridge, battery_lid, sht_shield, knob, clamp_knob, card_guide, lure_clip, hole_template]

/* [Stock trap: Alpha Scents red delta (measure yours)] */
floor_w = 195;     // inner floor width at card level
apex_z  = 110;     // card to the inside of the roof apex
trap_len = 227;    // open end to open end
flap_h = 25.5;     // end flaps
roof_t = 4;        // roof wall thickness (corrugated plastic)
gasket_t = 1.5;    // closed-cell foam tape on the saddle and the light bar

/* [Sticky card] */
card_w = 174; card_l = 198; card_t = 0.6;

/* [Camera: Arducam B0392-type IMX219 board, 25 x 24 mm, M12 lens] */
lens_z    = 112;   // front of the lens above the card (bench calibration: ~110; 112 gives ~15 px/mm)
lens_len  = 17;    // front of the lens to the underside of the camera board: measure yours
cam_holes = [21, 12.5];
cam_lens_off = [0, 0];   // lens centre relative to the centre of the hole pattern: measure yours
glass_d = 25; glass_t = 2;   // flashlight replacement glass, 25 x 2 mm

/* [Head] */
head_len = 208; box_w = 116; box_h = 52; wall = 3; floor_t = 3; rim_w = 7; lid_t = 5;
shade_gap = 8; shade_t = 3; shade_over = 12;

/* [Light bar] */
bar_t = 9;          // thickness, measured square to the roof
bar_len = 184;      // along the ridge
led_len = 170;      // COB strip length per side

/* [Print] */
fit = 0.25;
insert_d = 4.0;      // hole for M3 brass heat-set inserts (M3 x 5.7)
insert4_d = 5.6;     // hole for M4 inserts (M4 x 8.1)
m3 = 3.4; m4 = 4.5;
$fn = 48;
eps = 0.01;

// ---------- derived geometry ----------
ha = atan((floor_w / 2) / apex_z);       // roof angle from vertical (41.6 deg)
sa = sin(ha);
kk = tan(ha);
nrm = [cos(ha), sin(ha)];               // outward normal of the right roof panel (XZ)
function zl(x, t = 0) = apex_z - x / kk + t / sa;      // roof line offset t outward: height at x
function xl(z, t = 0) = kk * (apex_z + t / sa - z);   // ... and its x at height z
function on_line(x, t) = [x, zl(x, 0)] + t * nrm;

ts = roof_t + gasket_t;                 // saddle underside, as an offset from the inner roof
hb = zl(0, ts) + 3;                     // underside of the head box
box_top = hb + box_h;
shade_top = box_top + lid_t + shade_gap + shade_t;
eye_z = shade_top + 9;
sad_x = 38;                              // saddle half width

slot = [36, 76];                          // obround slot in the roof peak (x, y)
tube_od = 30;
tube_bot = lens_z - 1.5 - glass_t;       // glass 1.5 mm in front of the lens, flush with the tube end
clamp_y = 32;                             // the two clamp screws (M4) at (0, +-clamp_y)
boss_bot = apex_z - 5;
cradle_z = lens_z + lens_len;            // underside of the camera board
cradle_top = cradle_z - 1.5;             // 1.5 mm standoffs under the board
floor_top = hb + floor_t;

// layout inside the head
bay_y = [16, 100];
pi_x0 = -47; pi_y0 = -74;                // Pi 5 corner (HDMI edge faces -Y)
pillar_x = [48, 55];
saddle_screws = [[28, 95], [28, 35], [28, -35], [28, -95]];
cradle_screws = [[20, 0], [-20, 0]];
led_x = [22, 34];
led_wire = [12, -20];
plate_posts = [[38, -92], [-38, -92], [38, -22], [-38, -22]];
sht_pos = [47, -50];
sht_bosses = [[47, -35], [47, -65]];
button_pos = [0, 30];                     // -X wall: y, height above the box underside
vent_pos = [30, 25];
hinge_y = 55;
knob_y = 60;

// ---------- helpers ----------
module xz_prism(pts, y0, y1) { translate([0, y1, 0]) rotate([90, 0, 0]) linear_extrude(height = y1 - y0) polygon(pts); }
function mirror_pts(p) = [for (i = [len(p) - 1:-1:0]) [-p[i][0], p[i][1]]];
module obround(s, h) { hull() for (sy = [-1, 1]) translate([0, sy * (s[1] - s[0]) / 2, 0]) cylinder(d = s[0], h = h); }

// =====================================================================
// Saddle: sits on the outside of the roof peak (on foam tape), carries the head box, and drops
// the camera tube and the two clamp bosses through the slot. Print top face down; no supports.
// =====================================================================
module saddle() {
    difference() {
        union() {
            xz_prism(concat([[sad_x, hb], [sad_x, zl(sad_x, ts)], [0, zl(0, ts)]], mirror_pts([[sad_x, hb], [sad_x, zl(sad_x, ts)]])),
                     -head_len / 2, head_len / 2);
            translate([0, 0, tube_bot]) cylinder(d = tube_od, h = hb - tube_bot);
            for (s = [-1, 1]) translate([0, s * clamp_y, boss_bot]) cylinder(d = 10, h = hb - boss_bot);
        }
        // camera bore, glass recess (glass glued in from below), lens holder clearance
        translate([0, 0, tube_bot - eps]) cylinder(d = glass_d + 0.4, h = glass_t + 0.2);
        translate([0, 0, tube_bot + glass_t]) cylinder(d = 21, h = 3);
        translate([0, 0, tube_bot + glass_t + 3 - eps]) cylinder(d = 24, h = 50);
        // M4 inserts in the clamp bosses, from below
        for (s = [-1, 1]) translate([0, s * clamp_y, boss_bot - eps]) cylinder(d = insert4_d, h = 9);
        // LED wires up from the light bar
        for (s = [-1, 1]) translate([s * led_wire[0], led_wire[1], zl(led_wire[0], ts) - 1]) cylinder(d = 4, h = 60);
        // inserts: box screws and camera-cradle screws come down from inside the box
        for (p = saddle_screws, sx = [-1, 1], sy = [-1, 1]) translate([sx * p[0], sy * p[1], hb - 7]) cylinder(d = insert_d, h = 8);
        for (p = cradle_screws) translate([p[0], p[1], hb - 7]) cylinder(d = insert_d, h = 8);
        // weight relief pockets from the top (closed off by the box floor)
        for (sx = [-1, 1], sy = [-1, 1]) translate([sx * 29, sy * 65, hb - 14]) cube([10, 50, 30], center = true);
    }
}

// =====================================================================
// Light bar: inside the apex. Two COB LED strips behind opal diffusers on its underside faces;
// the cone in the middle keeps out of the lens's view of the card. Two clamp knobs pull it up.
// Print top (roof side) down... it is a chevron: print it on its side, ends down, no supports.
// =====================================================================
function bar_pts() = let (r = [on_line(sad_x - 2, 0), on_line(sad_x - 2, -bar_t)]) concat([[0, apex_z]], r, [[0, zl(0, -bar_t)]], mirror_pts(r));

module led_pocket(side) {
    // pocket for an 8 mm COB strip (3.5 deep) with a 1 mm rabbet for the diffuser cover
    mirror([side < 0 ? 1 : 0, 0, 0]) {
        xz_prism([on_line(led_x[0], -bar_t - 1), on_line(led_x[1], -bar_t - 1), on_line(led_x[1], -bar_t + 3.5), on_line(led_x[0], -bar_t + 3.5)],
                 -led_len / 2, led_len / 2);
        xz_prism([on_line(led_x[0] - 1.2, -bar_t - 1), on_line(led_x[1] + 1.2, -bar_t - 1), on_line(led_x[1] + 1.2, -bar_t + 1), on_line(led_x[0] - 1.2, -bar_t + 1)],
                 -led_len / 2 - 1.2, led_len / 2 + 1.2);
    }
}

module light_bar() {
    zb_bar = zl(0, -bar_t);
    difference() {
        xz_prism(bar_pts(), -bar_len / 2, bar_len / 2);
        // tube and its view cone
        translate([0, 0, tube_bot - 1]) cylinder(d = tube_od + 1, h = 20);
        translate([0, 0, zb_bar - eps]) cylinder(d1 = 2 * (6 + (lens_z - zb_bar) * 1.3), d2 = tube_od + 1, h = tube_bot - 1 - zb_bar + 2 * eps);
        // clamp bosses come down into pockets; M4 screws up from below with a knob
        for (s = [-1, 1]) translate([0, s * clamp_y, 0]) {
            translate([0, 0, boss_bot - 3]) cylinder(d = 11, h = 20);
            translate([0, 0, zb_bar - 1]) cylinder(d = m4, h = 30);
        }
        for (s = [-1, 1]) led_pocket(s);
        // LED wires: pocket -> top face, then up through the slot
        for (s = [-1, 1]) hull() {
            translate(concat([s * 28], [led_wire[1]], [zl(28, -bar_t + 2)])) sphere(d = 3.5, $fn = 16);
            translate([s * led_wire[0], led_wire[1], zl(led_wire[0]) + 1]) sphere(d = 3.5, $fn = 16);
        }
    }
}

// =====================================================================
// Head box: sealed tub for the Pi, the power boards and the battery cartridge.
// 3 mm walls, a 7 mm rim with a groove for 3 mm silicone cord, hinge on -X, two thumbscrews on +X,
// a hanging eye at each end. Print floor down; no supports.
// =====================================================================
module box_cavity() {
    w0 = box_w - 2 * wall; l0 = head_len - 2 * wall;
    w1 = box_w - 2 * rim_w; l1 = head_len - 2 * rim_w;
    translate([-w0 / 2, -l0 / 2, floor_top]) cube([w0, l0, box_h - floor_t - 12]);
    hull() {
        translate([-w0 / 2, -l0 / 2, box_top - 12 - eps]) cube([w0, l0, eps]);
        translate([-w1 / 2, -l1 / 2, box_top - 8]) cube([w1, l1, eps]);
    }
    translate([-w1 / 2, -l1 / 2, box_top - 8]) cube([w1, l1, 9]);
}

module rim_path(off, w, h, z) {
    translate([0, 0, z]) linear_extrude(height = h) difference() {
        square([box_w - 2 * off + w, head_len - 2 * off + w], center = true);
        square([box_w - 2 * off - w, head_len - 2 * off - w], center = true);
    }
}

module hinge_knuckle(y0, y1) {
    hull() {
        translate([-box_w / 2 - 4.5, y1, box_top]) rotate([90, 0, 0]) cylinder(d = 9, h = y1 - y0);
        translate([-box_w / 2 - eps, y0, box_top - 14]) cube([eps, y1 - y0, 14]);
    }
}

module boss(p, h, d = 9) {
    difference() {
        translate([p[0], p[1], floor_top - eps]) cylinder(d = d, h = h);
        translate([p[0], p[1], floor_top + h - 6]) cylinder(d = insert_d, h = 7);
    }
}

module head_box() {
    difference() {
        union() {
            translate([-box_w / 2, -head_len / 2, hb]) cube([box_w, head_len, box_h]);
            for (s = [-1, 1]) hinge_knuckle(s * hinge_y - 7, s * hinge_y + 7);
            for (s = [-1, 1]) hull() {    // thumbscrew ears, 45 deg underside
                translate([box_w / 2 - eps, s * knob_y - 8, box_top - 12]) cube([12, 16, 12]);
                translate([box_w / 2 - eps, s * knob_y - 8, box_top - 24]) cube([eps, 16, 1]);
            }
            for (s = [-1, 1]) hull() {    // hanging eyes, one per end
                translate([-14, s > 0 ? head_len / 2 - eps : -head_len / 2 - 7, eye_z - 12]) cube([28, 7, 24]);
                translate([-24, s > 0 ? head_len / 2 - eps : -head_len / 2 - 7, box_top - 30]) cube([48, 7, 1]);
                translate([-6, s > 0 ? head_len / 2 - eps : -head_len / 2 - 7, box_top - 50]) cube([12, 7, 1]);
            }
        }
        box_cavity();
        rim_path(3.5, 3.2, 3, box_top - 2.4);                     // gasket groove
        for (s = [-1, 1]) translate([0, s * (head_len / 2 + 3.5), eye_z]) rotate([90, 0, 0]) cylinder(d = 9, h = 20, center = true);
        // camera tube, LED wires, sensor cable
        translate([0, 0, hb - eps]) cylinder(d = 24, h = 10);
        for (s = [-1, 1]) translate([s * led_wire[0], led_wire[1], hb - eps]) cylinder(d = 4, h = 10);
        translate([sht_pos[0], sht_pos[1], hb - eps]) cylinder(d = 5, h = 10);
        // countersunk M3 screws down into the saddle (box, and the camera cradle)
        for (p = saddle_screws, sx = [-1, 1], sy = [-1, 1]) translate([sx * p[0], sy * p[1], hb - eps]) {
            cylinder(d = m3, h = 10);
            translate([0, 0, floor_t - 1.7 + 2 * eps]) cylinder(d1 = m3, d2 = 6.6, h = 1.7);
        }
        for (p = cradle_screws) translate([p[0], p[1], hb - eps]) cylinder(d = m3, h = 10);
        // hinge pins (M3 x 35) and thumbscrew inserts (M4)
        for (s = [-1, 1]) translate([-box_w / 2 - 4.5, s * hinge_y + 20, box_top]) rotate([90, 0, 0]) cylinder(d = m3, h = 40);
        for (s = [-1, 1]) translate([box_w / 2 + 6, s * knob_y, box_top - 10]) cylinder(d = insert4_d, h = 11);
        // "new card" button (16 mm IP67 momentary) and the breather vent (M12 ePTFE) on the -X wall
        translate([-box_w / 2 - eps, button_pos[0], hb + button_pos[1]]) rotate([0, 90, 0]) cylinder(d = 16.2, h = wall + 1);
        translate([-box_w / 2 - eps, vent_pos[0], hb + vent_pos[1]]) rotate([0, 90, 0]) cylinder(d = 12.3, h = wall + 1);
        translate([-box_w / 2 + 0.6, button_pos[0], hb + button_pos[1] + 14]) rotate([90, 0, -90])
            linear_extrude(1) text("NEW CARD", size = 5, halign = "center", valign = "center", font = "Liberation Sans:style=Bold");
    }
    // floor bosses: electronics plate, sensor shield (inserted from below)
    for (p = plate_posts) boss(p, 5);
    for (p = sht_bosses) difference() {
        translate([p[0], p[1], floor_top - eps]) cylinder(d = 8, h = 4);
        translate([p[0], p[1], hb - eps]) cylinder(d = insert_d, h = 6);
    }
    // cartridge guides
    for (s = [-1, 1]) translate([s > 0 ? 47.6 : -50.6, bay_y[0], floor_top - eps]) cube([3, bay_y[1] - bay_y[0], 6]);
    translate([-30, bay_y[0] - 3, floor_top - eps]) cube([60, 3, 6]);
}

// =====================================================================
// Lid: tongue presses the silicone cord; print top face down.
// =====================================================================
module head_lid() {
    difference() {
        union() {
            translate([-box_w / 2, -head_len / 2 + 0.5, box_top]) cube([box_w, head_len - 1, lid_t]);
            rim_path(3.5, 2.0, 1.6 + eps, box_top - 1.6);           // tongue
            for (sx = [-1, 1], sy = [-1, 1]) translate([sx * 40, sy * 80, box_top - 4]) cylinder(d = 9, h = 4 + eps);
            for (s = [-1, 1]) translate([box_w / 2 - eps, s * knob_y - 8, box_top]) cube([12, 16, lid_t]);
            for (s = [-1, 1], o = [-1, 1]) let (y0 = s * hinge_y + o * 12.25)
                hull() {
                    translate([-box_w / 2 - 4.5, y0 + 4.75, box_top]) rotate([90, 0, 0]) cylinder(d = 9, h = 9.5);
                    translate([-box_w / 2 + 4, y0 - 4.75, box_top]) cube([eps, 9.5, lid_t]);
                }
        }
        for (s = [-1, 1]) translate([-box_w / 2 - 4.5, s * hinge_y + 20, box_top]) rotate([90, 0, 0]) cylinder(d = m3, h = 40);
        for (s = [-1, 1]) translate([box_w / 2 + 6, s * knob_y, box_top - eps]) cylinder(d = m4, h = lid_t + 1);
        for (sx = [-1, 1], sy = [-1, 1]) translate([sx * 40, sy * 80, box_top + lid_t - 6.5]) cylinder(d = insert_d, h = 7);
    }
}

// =====================================================================
// Sun shade: second roof with an 8 mm air gap. Print top face down (standoffs up).
// =====================================================================
module sun_shade() {
    z0 = box_top + lid_t + shade_gap;
    w = box_w + 2 * shade_over;
    difference() {
        union() {
            translate([-w / 2, -head_len / 2 + 0.5, z0]) cube([w, head_len - 1, shade_t]);
            for (s = [-1, 1]) translate([s * (w / 2 - 1.5), 0, z0 - 5]) cube([3, head_len - 1, 10], center = true);   // drip edges
            for (sx = [-1, 1], sy = [-1, 1]) translate([sx * 40, sy * 80, z0 - shade_gap]) cylinder(d = 10, h = shade_gap + eps);
        }
        for (sx = [-1, 1], sy = [-1, 1]) translate([sx * 40, sy * 80, z0 - shade_gap - eps]) {
            cylinder(d = m3, h = 20);
            translate([0, 0, shade_gap + shade_t - 1.7 + 2 * eps]) cylinder(d1 = m3, d2 = 6.6, h = 1.7);
        }
        for (s = [-1, 1]) translate([box_w / 2 - 4, s * knob_y - 14, z0 - 20]) cube([40, 28, 40]);
    }
}

module knob() {
    // printed head for an M4 x 25 stainless hex bolt (lid thumbscrews)
    difference() {
        union() { cylinder(d = 22, h = 10, $fn = 12); cylinder(d = 12, h = 14); }
        translate([0, 0, -eps]) cylinder(d = 4.4, h = 20);
        translate([0, 0, 14 - 3]) cylinder(d = 7.9, h = 4, $fn = 6);
    }
}

module clamp_knob() {
    // printed head for an M4 x 20 bolt that pulls the light bar up (turned by hand from inside the trap)
    difference() {
        union() { cylinder(d = 16, h = 6, $fn = 8); cylinder(d = 9, h = 9); }
        translate([0, 0, -eps]) cylinder(d = 4.4, h = 20);
        translate([0, 0, -eps]) cylinder(d = 7.9, h = 3.5, $fn = 6);
    }
}

// =====================================================================
// Camera cradle: holds the board lens-down over the tube; screws through the box floor into
// the saddle. Shim under it, or change the standoffs, to move the lens.
// =====================================================================
module camera_cradle() {
    z0 = cradle_top - 3;
    difference() {
        union() {
            translate([-26, -14, z0]) cube([52, 28, 3]);
            for (sx = [-1, 1], sy = [-1, 1]) translate([sx * cam_holes[0] / 2 - cam_lens_off[0], sy * cam_holes[1] / 2 - cam_lens_off[1], cradle_top - eps])
                cylinder(d = 4.5, h = cradle_z - cradle_top);
        }
        translate([-9.5, -9.5, z0 - eps]) cube([19, 19, 4]);
        for (sx = [-1, 1], sy = [-1, 1]) translate([sx * cam_holes[0] / 2 - cam_lens_off[0], sy * cam_holes[1] / 2 - cam_lens_off[1], z0])
            cylinder(d = 1.8, h = 6);
        for (p = cradle_screws) translate([p[0], p[1], z0 - eps]) cylinder(d = m3, h = 4);
    }
    if (z0 < floor_top - 0.01) echo("WARNING: camera cradle sits below the box floor: raise lens_z or lengthen lens_len");
}

// =====================================================================
// Electronics plate: Pi 5 (HDMI edge towards -Y so the USB-C plug has room) and an upright wing
// at the -Y end for the boost converter, INA219 and LED MOSFET (zip ties + foam tape).
// =====================================================================
pi_holes = [[3.5, 3.5], [61.5, 3.5], [3.5, 52.5], [61.5, 52.5]];   // Pi 5 drawing, from the USB-C / HDMI corner
module electronics_plate() {
    z0 = floor_top + 5;
    difference() {
        union() {
            translate([-50, -100, z0]) cube([100, 84, 3]);
            translate([-50, -100, z0]) cube([100, 2.5, 28]);
            for (h = pi_holes) translate([pi_x0 + h[0], pi_y0 + h[1], z0 + 3 - eps]) cylinder(d = 6, h = 5);
        }
        for (h = pi_holes) translate([pi_x0 + h[0], pi_y0 + h[1], z0 - eps]) cylinder(d = 2.5, h = 10);
        for (p = plate_posts) translate([p[0], p[1], z0 - eps]) cylinder(d = m3, h = 4);
        for (x = [-26, -6, 0, 30, 34, 46], z = [8, 22]) translate([x, -101, z0 + z]) cube([1.6, 5, 4]);
        for (x = [-40, 20]) translate([x, -98, z0 - eps]) cube([4, 1.6, 4]);
        for (t = [["INA219", -17], ["5V BOOST", 17], ["FET", 41]])
            translate([t[1], -97.4, z0 + 15]) rotate([90, 0, 180]) linear_extrude(1) text(t[0], size = 3.2, halign = "center", font = "Liberation Sans:style=Bold");
        translate([-35, -66, z0 - eps]) cube([40, 36, 4]);
    }
}

// =====================================================================
// Battery cartridge: 1S4P 21700 Li-ion (4 x ~5 Ah = ~72 Wh) with its 1S protection board,
// a USB-C 3 A charger board and a 4-LED level gauge. Swapped whole; charged indoors.
// =====================================================================
cart = [94, 84, 31];
module battery_cartridge() {
    x0 = -cart[0] / 2; y0 = bay_y[0]; z0 = floor_top;
    difference() {
        union() {
            translate([x0, y0, z0]) cube([cart[0], cart[1], cart[2] - 2]);
            translate([x0, y0 + cart[1] - eps, z0 + cart[2] - 8]) cube([cart[0], 2.0, 2]);
        }
        translate([x0 + 2, y0 + 2, z0 + 2]) cube([cart[0] - 4, cart[1] - 4, 40]);
        translate([x0 + 20, y0 - eps, z0 + 6]) cube([9, 3, 4]);             // XT30 lead
        translate([cart[0] / 2 - 3, y0 + 30, z0 + 20]) cube([4, 10, 4.5]);  // USB-C charge port
    }
    for (i = [0:3]) translate([x0 + 2 + 1.8 + 21.6 / 2 + i * 21.6, y0 + 11, z0 + 2 - eps])
        difference() { translate([-6, 0, 0]) cube([12, 70, 3]); translate([0, -eps, 11]) rotate([-90, 0, 0]) cylinder(d = 21.8, h = 71); }
    for (s = [-1, 1]) difference() {
        translate([s * 40 - 3.5, y0 + 2 - eps, z0]) cube([7, 7, cart[2] - 2]);
        translate([s * 40, y0 + 5.5, z0 + cart[2] - 9]) cylinder(d = insert_d, h = 8);
    }
}

module battery_lid() {
    x0 = -cart[0] / 2; y0 = bay_y[0]; z0 = floor_top + cart[2] - 2;
    difference() {
        union() {
            translate([x0, y0, z0]) cube([cart[0], cart[1], 2]);
            translate([-25, y0 + 30, z0 + 2 - eps]) cube([50, 8, 8]);
            for (s = [-1, 1]) translate([s * 25 - 7, y0 + cart[1], z0 - 8]) {
                cube([14, 2.2, 10]);
                translate([0, 2.2, 0]) cube([14, 2.2, 2.6]);
            }
        }
        translate([-15, y0 + 30 - eps, z0 + 4]) cube([30, 8 + 2 * eps, 4.5]);
        translate([-11, y0 + 50, z0 - eps]) cube([22, 9, 3]);
        for (s = [-1, 1]) translate([s * 40, y0 + 5.5, z0 - eps]) cylinder(d = m3, h = 3);
    }
    translate([0, y0 + 64, z0 + 2 - eps]) linear_extrude(0.6) text("CHARGE WITH USB-C", size = 4, halign = "center", font = "Liberation Sans:style=Bold");
}

// =====================================================================
// Sensor shield for the SHT45: louvred cup under the head's overhang (shaded, ventilated).
// =====================================================================
module sht_shield() {
    translate([sht_pos[0], sht_pos[1], hb]) mirror([0, 0, 1]) difference() {
        union() {
            translate([-6, -21, 0]) cube([12, 42, 3]);
            cylinder(d = 12, h = 30);
            for (z = [6:6:30]) translate([0, 0, z - 4]) difference() { cylinder(d1 = 12, d2 = 20, h = 4); cylinder(d1 = 8, d2 = 16, h = 4 + eps); }
        }
        translate([0, 0, 3]) cylinder(d = 9, h = 30);
        translate([0, 0, -eps]) cylinder(d = 5, h = 4);
        for (z = [5:6:29]) for (r = [0:90:270]) rotate(r) translate([0, -2, z]) cube([8, 4, 2.5]);
        for (y = [-15, 15]) translate([0, y, -eps]) cylinder(d = m3, h = 4);
    }
}

// =====================================================================
// Card guide (optional): a low U-frame taped to the trap floor with VHB, open at the loading
// end, so every card lands in the same spot under the camera. Print flat.
// =====================================================================
module card_guide() {
    w = card_w + 2; l = card_l + 1;
    difference() {
        translate([-w / 2 - 4, -card_l / 2 - 5, -card_t]) cube([w + 8, l + 5, 2.6]);
        translate([-w / 2, -card_l / 2 - 1, -card_t - 1]) cube([w, l + 10, 5]);
        translate([-w / 2 + 6, -card_l / 2 - 6, -card_t - 1]) cube([w - 12, 6, 5]);   // open middle at the back: drains, saves plastic
    }
    // lips the card slides under
    for (sx = [-1, 1]) translate([sx > 0 ? w / 2 - 2 : -w / 2 - eps, -card_l / 2 + 20, 0.4]) cube([2 + eps, card_l - 40, 1.6]);
}

// =====================================================================
// Lure clip (optional): pushes onto the top of an end flap and holds a rubber septum lure over
// the card's printed header, out of the counted area.
// =====================================================================
module lure_clip() {
    difference() {
        union() {
            translate([-8, 0, 0]) cube([16, 2.5, 16]);
            translate([-8, 2.5 + roof_t + 0.3, 6]) cube([16, 2.5, 10]);
            translate([-8, 0, 16 - eps]) cube([16, 5 + roof_t + 0.3, 2.5]);
            translate([0, -10, 6]) difference() { cylinder(d = 20, h = 8); translate([0, 0, 2]) cylinder(d = 16, h = 8); }
        }
        for (r = [0:60:300]) translate([0, -10, 9]) rotate(r) translate([0, -2, 0]) cube([12, 4, 10]);
    }
}

// =====================================================================
// Hole template: sits on the roof peak; mark the slot through it (or cut along it with a knife).
// =====================================================================
module hole_template() {
    difference() {
        xz_prism(concat([[0, zl(0, roof_t) + 3]], [[45, zl(45, roof_t) + 3], [45, zl(45, roof_t)]], [[0, zl(0, roof_t)]],
                        mirror_pts([[45, zl(45, roof_t) + 3], [45, zl(45, roof_t)]])), -55, 55);
        translate([0, 0, 0]) obround(slot, 200);
        translate([0, 0, zl(0, roof_t) + 2]) linear_extrude(2) for (s = [-1, 1]) translate([0, s * 46, 0]) text("CENTRE", size = 5, halign = "center", valign = "center");
    }
}

// =====================================================================
// The stock trap, for the views only
// =====================================================================
module stock_trap() {
    difference() {
        union() {
            for (s = [-1, 1]) mirror([s < 0 ? 1 : 0, 0, 0])
                xz_prism([[xl(-card_t), -card_t], [xl(-card_t, roof_t), -card_t], [0, zl(0, roof_t)], [0, apex_z]], -trap_len / 2, trap_len / 2);
            translate([-floor_w / 2 - 3, -trap_len / 2, -card_t - roof_t]) cube([floor_w + 6, trap_len, roof_t]);
            for (s = [-1, 1]) translate([-floor_w / 2, s > 0 ? trap_len / 2 - roof_t : -trap_len / 2, -card_t]) cube([floor_w, roof_t, flap_h]);
        }
        obround(slot, 300);
    }
}

module card_in_place() { translate([-card_w / 2, -card_l / 2, -card_t]) cube([card_w, card_l, card_t]); }

module pi_dummy() {
    z = floor_top + 5 + 3 + 5;
    color("green") translate([pi_x0, pi_y0, z]) cube([85, 56, 1.6]);
    color("silver") translate([pi_x0 + 62, pi_y0 + 2, z + 1.6]) cube([26, 52, 16]);
}

module leds() {
    for (s = [-1, 1]) mirror([s < 0 ? 1 : 0, 0, 0])
        xz_prism([on_line(led_x[0] + 1, -bar_t + 1.2), on_line(led_x[1] - 1, -bar_t + 1.2), on_line(led_x[1] - 1, -bar_t + 3.4), on_line(led_x[0] + 1, -bar_t + 3.4)],
                 -led_len / 2, led_len / 2);
}

module assembly(ex = 0) {
    color("firebrick", 0.85) stock_trap();
    color("khaki") card_in_place();
    color("gainsboro") translate([0, 0, -6 * ex]) light_bar();
    color("gold") translate([0, 0, -6 * ex]) leds();
    color("dimgray") for (s = [-1, 1]) translate([0, s * clamp_y, zl(0, -bar_t) - 9 - 8 * ex]) clamp_knob();
    color("whitesmoke") translate([0, 0, 3 * ex]) saddle();
    color("skyblue") translate([0, 0, tube_bot + 3 * ex]) cylinder(d = glass_d, h = glass_t);
    color("whitesmoke") translate([0, 0, 6 * ex]) head_box();
    color("darkorange") translate([0, 0, 7 * ex]) camera_cradle();
    color("green") translate([0, 0, 7 * ex]) translate([0, 0, lens_z]) { cylinder(d = 14, h = lens_len - 1); translate([-12.5, -12, lens_len]) cube([25, 24, 1]); }
    color("lightgray") translate([0, 0, 8 * ex]) electronics_plate();
    translate([0, 0, 8 * ex]) pi_dummy();
    color("royalblue") translate([0, 0, 10 * ex]) battery_cartridge();
    color("cornflowerblue") translate([0, 0, 11 * ex]) battery_lid();
    color("whitesmoke") translate([0, 0, 13 * ex]) head_lid();
    color("white") translate([0, 0, 16 * ex]) sun_shade();
    color("gainsboro") translate([0, 0, 6 * ex]) sht_shield();
    for (s = [-1, 1]) color("dimgray") translate([box_w / 2 + 6, s * knob_y, box_top + lid_t + 13 * ex]) knob();
}

// 2D cuts for hardware/housing_drawings.py: one part at a time, as seen in the drawings.
// end: plane y = view_at (x right, z up); side: plane x = view_at (y right, z up); plan: plane z = view_at.
view_part = "saddle";
view = "end";
view_at = 0;
view_cut = true;
module part_by_name(n) {
    if (n == "saddle") saddle();
    else if (n == "light_bar") light_bar();
    else if (n == "leds") leds();
    else if (n == "glass") translate([0, 0, tube_bot]) cylinder(d = glass_d, h = glass_t);
    else if (n == "head_box") head_box();
    else if (n == "head_lid") head_lid();
    else if (n == "sun_shade") sun_shade();
    else if (n == "camera_cradle") camera_cradle();
    else if (n == "camera") translate([0, 0, lens_z]) { cylinder(d = 14, h = lens_len - 1); translate([-12.5, -12, lens_len]) cube([25, 24, 1]); }
    else if (n == "electronics_plate") electronics_plate();
    else if (n == "pi") pi_dummy();
    else if (n == "battery_cartridge") battery_cartridge();
    else if (n == "battery_lid") battery_lid();
    else if (n == "cells") for (i = [0:3]) translate([-cart[0] / 2 + 2 + 1.8 + 21.6 / 2 + i * 21.6, bay_y[0] + 11, floor_top + 2 + 11]) rotate([-90, 0, 0]) cylinder(d = 21.4, h = 70);
    else if (n == "stock_trap") stock_trap();
    else if (n == "card") card_in_place();
    else if (n == "card_guide") card_guide();
    else if (n == "sht_shield") sht_shield();
    else if (n == "knobs") for (s = [-1, 1]) translate([box_w / 2 + 6, s * knob_y, box_top + lid_t]) knob();
    else if (n == "clamp_knobs") for (s = [-1, 1]) translate([0, s * clamp_y, zl(0, -bar_t) - 9]) clamp_knob();
    else if (n == "slot") obround(slot, 1);
}
module view_xform() {
    if (view == "end") rotate([-90, 0, 0]) translate([0, -view_at, 0]) children();
    else if (view == "side") multmatrix([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, -view_at], [0, 0, 0, 1]]) children();
    else translate([0, 0, -view_at]) children();
}

if (part == "view2d") projection(cut = view_cut) view_xform() part_by_name(view_part);
else if (part == "assembly") assembly(0);
else if (part == "exploded") assembly(10);
else if (part == "section") intersection() { assembly(0); translate([-200, -150, -50]) cube([400, 150, 400]); }
else if (part == "head_box") head_box();
else if (part == "head_lid") head_lid();
else if (part == "sun_shade") sun_shade();
else if (part == "saddle") saddle();
else if (part == "light_bar") light_bar();
else if (part == "camera_cradle") camera_cradle();
else if (part == "electronics_plate") electronics_plate();
else if (part == "battery_cartridge") battery_cartridge();
else if (part == "battery_lid") battery_lid();
else if (part == "sht_shield") sht_shield();
else if (part == "knob") knob();
else if (part == "clamp_knob") clamp_knob();
else if (part == "card_guide") card_guide();
else if (part == "lure_clip") lure_clip();
else if (part == "hole_template") hole_template();

echo(str("Lens ", lens_z, " mm above the card (inner apex ", apex_z, "); glass underside at ", tube_bot, "; box underside ", hb,
         "; shade top ", shade_top, "; eyes at ", eye_z, "; head ", box_w + 2 * shade_over, " wide x ", head_len + 14, " long (with eyes)."));
echo(str("Roof slot ", slot[0], " x ", slot[1], " mm obround, centred on the peak. Light bar bottom at ", zl(0, -bar_t), "."));
