/*
 * AH.knockblock dual-panel enclosure
 *
 * Two Waveshare RGB-Matrix-P2.5-64x32 modules, stacked vertically.
 * Units are millimetres. Set `part` and export one STL at a time.
 */

part = "assembly"; // assembly, bezel, diffuser, spacer, cradle, back_shell, retainer_clip, fit_coupon

// Measured hardware. Recheck both panels before the production print.
panel_width = 160;
panel_height = 80;
panel_depth = 14.7;
panel_pocket = 161;

// Optical stack.
diffuser_width = 164;
diffuser_thickness = 2;
diffuser_clearance = 0.4;
diffuser_corner_clip = 8;
diffuser_gap = 10;
view_opening = 159.5;

// Case envelope.
case_width = 180;
corner_radius = 7;
bezel_depth = 4;
cradle_depth = 16;
electronics_depth = 32;
wall = 3;

// Hardware clearances. Tune these for your printer and inserts.
face_screw_diameter = 3.4;
face_countersink_diameter = 6.4;
insert_hole_diameter = 4.2;
face_screw_offset = 82;
clip_screw_diameter = 3.4;
clip_insert_diameter = 4.2;

$fn = 48;
epsilon = 0.02;

module rounded_square_2d(size, radius) {
    offset(r = radius)
        square([size - 2 * radius, size - 2 * radius], center = true);
}

module rounded_block(size, depth, radius) {
    linear_extrude(height = depth)
        rounded_square_2d(size, radius);
}

module chamfered_square_2d(size, chamfer) {
    half = size / 2;
    polygon(points = [
        [-half + chamfer, -half], [half - chamfer, -half],
        [half, -half + chamfer], [half, half - chamfer],
        [half - chamfer, half], [-half + chamfer, half],
        [-half, half - chamfer], [-half, -half + chamfer]
    ]);
}

module face_hole(height, countersink = false) {
    translate([0, 0, -epsilon])
        cylinder(d = face_screw_diameter, h = height + 2 * epsilon);
    if (countersink)
        translate([0, 0, -epsilon])
            cylinder(
                d1 = face_countersink_diameter,
                d2 = face_screw_diameter,
                h = 2.1 + epsilon
            );
}

module four_face_holes(height, countersink = false) {
    for (x = [-face_screw_offset, face_screw_offset])
        for (y = [-face_screw_offset, face_screw_offset])
            translate([x, y, 0]) face_hole(height, countersink);
}

module bezel() {
    pocket_depth = diffuser_thickness + diffuser_clearance;
    difference() {
        rounded_block(case_width, bezel_depth, corner_radius);

        // The smaller front opening leaves a narrow ledge that retains the
        // diffuser. The rear pocket gives the sheet replaceable clearance.
        translate([0, 0, -epsilon])
            linear_extrude(height = bezel_depth + 2 * epsilon)
                square([view_opening, view_opening], center = true);
        translate([0, 0, bezel_depth - pocket_depth])
            linear_extrude(height = pocket_depth + epsilon)
                chamfered_square_2d(
                    diffuser_width + diffuser_clearance,
                    diffuser_corner_clip
                );

        four_face_holes(bezel_depth, true);
    }
}

module spacer() {
    retaining_lip = 1.5;
    difference() {
        rounded_block(case_width, diffuser_gap, corner_radius);

        // Narrow front and rear lips retain the diffuser and stop the panels.
        // The middle opens wider so light can spread before reaching the sheet.
        translate([0, 0, -epsilon])
            linear_extrude(height = diffuser_gap + 2 * epsilon)
                square([view_opening, view_opening], center = true);
        translate([0, 0, retaining_lip])
            linear_extrude(height = diffuser_gap - 2 * retaining_lip)
                chamfered_square_2d(diffuser_width + 2, 6);
        four_face_holes(diffuser_gap);
    }
}

module clip_insert_holes() {
    // Select only the positions that avoid connectors on your panel revision.
    positions = [-55, 0, 55];
    edge = (case_width + panel_pocket) / 4;

    for (p = positions) {
        translate([p, edge, cradle_depth - 6])
            cylinder(d = clip_insert_diameter, h = 6 + epsilon);
        translate([p, -edge, cradle_depth - 6])
            cylinder(d = clip_insert_diameter, h = 6 + epsilon);
        translate([edge, p, cradle_depth - 6])
            cylinder(d = clip_insert_diameter, h = 6 + epsilon);
        translate([-edge, p, cradle_depth - 6])
            cylinder(d = clip_insert_diameter, h = 6 + epsilon);
    }
}

module cradle() {
    difference() {
        rounded_block(case_width, cradle_depth, corner_radius);
        translate([0, 0, -epsilon])
            linear_extrude(height = cradle_depth + 2 * epsilon)
                square([panel_pocket, panel_pocket], center = true);
        four_face_holes(cradle_depth);
        clip_insert_holes();
    }
}

module keyhole_cut(depth) {
    // Insert the screw head through the circle, then lower the case so the
    // screw shaft rests in the narrow upper slot.
    union() {
        cylinder(d = 8.5, h = depth);
        translate([-2, 0, 0]) cube([4, 12, depth]);
    }
}

module rear_vent_cut(depth) {
    for (x = [-54, -36, -18, 0, 18, 36, 54])
        for (y = [-36, -18, 0, 18, 36])
            translate([x - 6, y - 2, 0]) cube([12, 4, depth]);
}

module side_vent_cuts() {
    // Bottom inlets and top outlets maintain convection when the rear panel
    // is close to a wall.
    for (x = [-60, -30, 0, 30, 60]) {
        translate([x - 8, case_width / 2 - wall - epsilon, 10])
            cube([16, wall + 2 * epsilon, 12]);
        translate([x - 8, -case_width / 2 - epsilon, 10])
            cube([16, wall + 2 * epsilon, 12]);
    }
}

module back_shell() {
    inner_width = case_width - 2 * wall;
    back_panel = wall;
    boss_radius = 4.5;

    difference() {
        union() {
            difference() {
                rounded_block(case_width, electronics_depth, corner_radius);

                // Open front cavity; leave a solid wall-facing rear panel.
                translate([0, 0, -epsilon])
                    linear_extrude(height = electronics_depth - back_panel + epsilon)
                        rounded_square_2d(
                            inner_width,
                            max(1, corner_radius - wall)
                        );
            }

            // Full-height corner bosses receive inserts from the open front.
            for (x = [-face_screw_offset, face_screw_offset])
                for (y = [-face_screw_offset, face_screw_offset])
                    translate([x, y, 0])
                        cylinder(r = boss_radius, h = electronics_depth);
        }

        // Heat-set insert holes enter from the open front.
        for (x = [-face_screw_offset, face_screw_offset])
            for (y = [-face_screw_offset, face_screw_offset])
                translate([x, y, -epsilon])
                    cylinder(d = insert_hole_diameter, h = 7);

        // Low-voltage cable exit in the bottom wall.
        translate([-10, -case_width / 2 - epsilon, 5])
            cube([20, wall + 2 * epsilon, 10]);

        // Wall-mount keyholes and a ventilation/tie-point grid.
        translate([-55, 48, electronics_depth - back_panel - epsilon])
            keyhole_cut(back_panel + 2 * epsilon);
        translate([55, 48, electronics_depth - back_panel - epsilon])
            keyhole_cut(back_panel + 2 * epsilon);
        translate([0, 0, electronics_depth - back_panel - epsilon])
            rear_vent_cut(back_panel + 2 * epsilon);
        side_vent_cuts();
    }
}

module retainer_clip() {
    // Rotate the long end over a clear section of PCB and add a foam pad.
    difference() {
        hull() {
            translate([-5, 0, 0]) cylinder(d = 10, h = 3);
            translate([11, 0, 0]) cylinder(d = 8, h = 3);
        }
        translate([-5, 0, -epsilon])
            cylinder(d = clip_screw_diameter, h = 3 + 2 * epsilon);
    }
}

module fit_coupon() {
    // Two gauges in one small print: the panel-depth channel on the left
    // and the diffuser slot on the right.
    difference() {
        cube([70, 30, 22]);
        translate([5, 4, 4])
            cube([28, panel_depth + 0.8, 22]);
        translate([40, 4, 4])
            cube([25, diffuser_thickness + diffuser_clearance, 22]);
    }
}

module diffuser_preview() {
    color([0.82, 0.88, 0.9, 0.45])
        translate([0, 0, bezel_depth - diffuser_thickness / 2])
            linear_extrude(height = diffuser_thickness, center = true)
                chamfered_square_2d(diffuser_width, diffuser_corner_clip);
}

module diffuser() {
    linear_extrude(height = diffuser_thickness)
        chamfered_square_2d(diffuser_width, diffuser_corner_clip);
}

module panels_preview(z) {
    color([0.08, 0.08, 0.08]) {
        translate([0, panel_height / 2, z])
            cube([panel_width, panel_height, panel_depth], center = true);
        translate([0, -panel_height / 2, z])
            cube([panel_width, panel_height, panel_depth], center = true);
    }
}

module assembly() {
    explode = 3;
    color("black") bezel();
    diffuser_preview();

    translate([0, 0, bezel_depth + explode])
        color([0.12, 0.12, 0.12]) spacer();
    translate([0, 0, bezel_depth + diffuser_gap + 2 * explode])
        color([0.16, 0.16, 0.16]) cradle();

    panels_preview(
        bezel_depth + diffuser_gap + 2 * explode + panel_depth / 2
    );

    translate([
        0,
        0,
        bezel_depth + diffuser_gap + cradle_depth + 3 * explode
    ]) color([0.2, 0.2, 0.2]) back_shell();
}

if (part == "bezel") bezel();
else if (part == "diffuser") diffuser();
else if (part == "spacer") spacer();
else if (part == "cradle") cradle();
else if (part == "back_shell") back_shell();
else if (part == "retainer_clip") retainer_clip();
else if (part == "fit_coupon") fit_coupon();
else assembly();
