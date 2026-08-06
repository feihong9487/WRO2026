/* =============================================================================
 * 智慧香爐 — 外購元件：MATRIX Mini R4 控制器
 * =============================================================================
 * ★★ 這不是列印件，是外購品的示意模型 ★★
 * 尺寸來自 ../params.scad，★官方未公佈外形，整組為推估★（以 UNO 外型放寬）。
 * 用途：組裝干涉檢查、螺絲可及性、目視確認裝得下。
 * ★不可當成實際尺寸寫進報告★（CLAUDE.md §7）
 *
 * 原點：PCB 左下角、z=0 為板底
 * ============================================================================= */

include <../params.scad>


module matrix_r4() {
    color("#0d3b66") linear_extrude(PCB_T)
        offset(r = 3) offset(r = -3) square([MATRIX_W, MATRIX_D]);

    // 周邊埠座：四邊各一排（D1/D4、I2C、馬達埠…）。
    // ★不是實際佈局★——是「周邊被埠座佔掉多少空間」的包絡，
    //   拿到實體板請改成真實位置，否則干涉檢查會驗到錯的東西。
    color("#1a1a1a") {
        translate([6, 2, PCB_T])              cube([MATRIX_W - 12, 8, MATRIX_CONN_H]);
        translate([6, MATRIX_D - 10, PCB_T])  cube([MATRIX_W - 12, 8, MATRIX_CONN_H]);
    }
    // USB-C（供電與燒錄）——外露到板外，後面板要留孔
    color("#d0d3d6")
        translate([MATRIX_W / 2 - MATRIX_USB_W / 2, -1, PCB_T])
            cube([MATRIX_USB_W, 4, MATRIX_USB_H]);

    color("#8a8f94") for (p = MATRIX_SCREW)
        translate([p[0], p[1], -0.2]) cylinder(h = PCB_T + 0.4, d = 3.2, $fn = 24);
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
matrix_r4();
