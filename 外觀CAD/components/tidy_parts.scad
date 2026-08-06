/* =============================================================================
 * 智慧香爐 — 外購元件：導正套筒（鋁管＋鐵墊圈）與電磁鐵
 * =============================================================================
 * ★★ 這不是列印件，是外購品的示意模型 ★★
 * 尺寸來自 ../params.scad，★皆為估值，未實測★（CLAUDE.md §7）
 *
 * 磁力作用在★套筒底部的鐵墊圈★上，不是作用在香枝上——
 * 所以市售任何香都能用，這是這個機構最關鍵的設計選擇（交接文件 §7）。
 * ============================================================================= */

include <../params.scad>

// 原點：套筒底面圓心（鐵墊圈的底面）
module guide_sleeve() {
    color("#b9bec4") difference() {                 // 鋁管
        translate([0, 0, TIDY_WASHER_T])
            cylinder(h = TIDY_SLEEVE_LEN, d = TIDY_SLEEVE_OD);
        translate([0, 0, TIDY_WASHER_T - 0.1])
            cylinder(h = TIDY_SLEEVE_LEN + 0.2, d = TIDY_SLEEVE_ID);
    }
    color("#6b6f73") difference() {                 // 鐵墊圈（磁力的實際作用對象）
        cylinder(h = TIDY_WASHER_T, d = TIDY_WASHER_OD);
        translate([0, 0, -0.1])
            cylinder(h = TIDY_WASHER_T + 0.2, d = TIDY_SLEEVE_ID);
    }
}

// 四支一組（對應 2×2 陣列）
module guide_sleeves() {
    o = TIDY_HOLE_PITCH / 2;
    for (x = [-o, o], y = [-o, o]) translate([x, y, 0]) guide_sleeve();
}

// 原點：電磁鐵頂面（吸合面）圓心，往下長
module electromagnet() {
    color("#3a3f45") translate([0, 0, -TIDY_MAGNET_H])
        cylinder(h = TIDY_MAGNET_H, d = TIDY_MAGNET_DIA);
    color("#8a4b2a") translate([0, 0, -TIDY_MAGNET_H + 3])   // 線圈示意
        cylinder(h = TIDY_MAGNET_H - 6, d = TIDY_MAGNET_DIA - 3);
}

module electromagnets() {
    o = TIDY_HOLE_PITCH / 2;
    for (x = [-o, o], y = [-o, o]) translate([x, y, 0]) electromagnet();
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
guide_sleeves();
translate([0, 0, -20]) electromagnets();
