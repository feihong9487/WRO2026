/* =============================================================================
 * 智慧香爐 — 共用輔助模組
 * =============================================================================
 * 圓角方柱、倒角、通風柵格、螺柱、頂緣台階、定位榫。
 * 零件檔一律 include 本檔（會連帶帶進 params.scad）。
 * ============================================================================= */

include <params.scad>

// ═══════════════════════════════════════════════════════════════════════════
// 共用輔助模組
// ═══════════════════════════════════════════════════════════════════════════

// 圓角方柱：用 4 根圓柱做 hull，比 minkowski 快很多
module rrect(w, d, h, r) {
    hull() {
        for (x = [r, w - r], y = [r, d - r])
            translate([x, y, 0]) cylinder(h = h, r = r);
    }
}

// 圓角方柱（底緣倒角版）：改善首層附著並讓外型更柔和
module rrect_chamfered(w, d, h, r, c = CHAMFER) {
    union() {
        // 倒角裙邊
        hull() {
            for (x = [r, w - r], y = [r, d - r])
                translate([x, y, 0]) cylinder(h = c, r1 = r - c, r2 = r);
        }
        translate([0, 0, c]) rrect(w, d, h - c, r);
    }
}

// 螺柱座（含自攻底孔）。pilot 依板子自己的孔徑給，不是統一值。
module standoff(h = STANDOFF_H, pilot = M3_PILOT) {
    difference() {
        cylinder(h = h, d = standoff_od(pilot));
        translate([0, 0, -0.1]) cylinder(h = h + 0.2, d = pilot);
    }
}

// 通風柵格：一排長圓孔。用於側面進氣與感測器艙開口。
module vent_slots(n, slot_w, slot_h, pitch, depth) {
    for (i = [0 : n - 1])
        translate([i * pitch, 0, 0])
            hull() {
                translate([0, slot_h / 2 - slot_w / 2, 0])
                    cylinder(h = depth, d = slot_w, $fn = 16);
                translate([0, -slot_h / 2 + slot_w / 2, 0])
                    cylinder(h = depth, d = slot_w, $fn = 16);
            }
}

// 頂緣承接台階：讓定位榫有實體可坐，同時作為上層零件的落座面
module top_ledge(w, d, z, r) {
    translate([0, 0, z])
        difference() {
            translate([WALL, WALL, 0])
                rrect(w - WALL * 2, d - WALL * 2, LEDGE_H, r - WALL);
            translate([WALL + LEDGE_W, WALL + LEDGE_W, -0.1])
                rrect(w - (WALL + LEDGE_W) * 2, d - (WALL + LEDGE_W) * 2,
                      LEDGE_H + 0.2, max(r - WALL - LEDGE_W, 0.5));
        }
}

// 定位榫（公）：四角
module tenons_male(w, d, z) {
    for (x = [TENON_INSET, w - TENON_INSET], y = [TENON_INSET, d - TENON_INSET])
        translate([x, y, z])
            cylinder(h = TENON_H, d1 = TENON_D, d2 = TENON_D - 1.2);  // 帶錐度好插入
}

// 定位榫（母）：對應的孔
module tenons_female(w, d, z) {
    for (x = [TENON_INSET, w - TENON_INSET], y = [TENON_INSET, d - TENON_INSET])
        translate([x, y, z - 0.1])
            cylinder(h = TENON_H + 0.2, d = TENON_D + FIT * 2);
}
