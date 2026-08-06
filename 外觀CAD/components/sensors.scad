/* =============================================================================
 * 智慧香爐 — 外購元件：感測器模組（SCD41／SHT31）
 * =============================================================================
 * ★★ 這不是列印件，是外購品的示意模型 ★★
 * 尺寸來自 ../params.scad，★皆為估值★，拿到模組請實測板長寬與感測器本體高度。
 * 用途：組裝干涉檢查、螺絲可及性、目視確認裝得下。
 * ★不可當成實際尺寸寫進報告★（CLAUDE.md §7）
 *
 * 原點：PCB 左下角、z=0 為板背面（貼向前壁那一側）
 * ============================================================================= */

include <../params.scad>


// 兩個模組共用一組畫法：綠色 PCB ＋ 上面的感測器本體
module sensor_module(w, h, t, sensor_w) {
    color("#1c6b3c") linear_extrude(PCB_T) square([w, h]);
    color("#e8e4d9")
        translate([w / 2 - sensor_w / 2, h / 2 - sensor_w / 2, PCB_T])
            cube([sensor_w, sensor_w, t - PCB_T]);
}
module scd41() { sensor_module(SCD41_W, SCD41_D, SCD41_T, 10); }
module sht31() { sensor_module(SHT31_W, SHT31_D, SHT31_T, 5); }
module sensors() {
    scd41();
    translate([0, SCD41_D + 6, 0]) sht31();
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
sensors();
