/* =============================================================================
 * 智慧香爐 — 外購元件：超音波霧化模組 ＋ 罩內 LED 側光
 * =============================================================================
 * ★★ 外購品的示意模型，尺寸皆為估值、未實測 ★★（CLAUDE.md §7）
 * 霧化模組泡在爐盆的水裡；LED 貼在集煙罩內側，側向打光讓霧看得清楚。
 * ============================================================================= */

include <../params.scad>

// 原點：模組底面圓心（放在爐盆底）
module mist_module() {
    color("#d8dce0") cylinder(h = MIST_MOD_H, d = MIST_MOD_D);
    color("#9aa0a6") translate([0, 0, MIST_MOD_H])
        cylinder(h = 1.5, d = MIST_DISC_D);
}

// 原點：燈條中心，貼在罩內壁上
module hood_led() {
    color("#f2e6c8") cube([HOODLED_W, HOODLED_T, HOODLED_H], center = true);
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
mist_module();
translate([0, 40, 0]) hood_led();
