/* =============================================================================
 * 智慧香爐 — 外購元件：Raspberry Pi 5
 * =============================================================================
 * ★★ 這不是列印件，是外購品的示意模型 ★★
 * 尺寸來自 ../params.scad，板外形 85×56 與孔位為官方公開值，連接器高度為常見規格（估）。
 * 用途：組裝干涉檢查、螺絲可及性、目視確認裝得下。
 * ★不可當成實際尺寸寫進報告★（CLAUDE.md §7）
 *
 * 原點：PCB 左下角、z=0 為板底
 * ============================================================================= */

include <../params.scad>


module pi5() {
    // PCB
    color("#1c6b3c") linear_extrude(PCB_T)
        offset(r = 3) offset(r = -3) square([PI_W, PI_D]);

    color("#b8bcc0") {
        // ── 短邊（x = PI_W 側）：RJ45 ＋ 兩組雙層 USB-A ──
        // 連接器外露到板外，這正是干涉檢查要看的：後面板開孔對不對得上
        translate([PI_W - PI_RJ45_L + 3, 2, PCB_T])
            cube([PI_RJ45_L, PI_RJ45_W, PI_RJ45_H]);
        for (y = [21, 38])
            translate([PI_W - PI_USB_L + 3, y, PCB_T])
                cube([PI_USB_L, PI_USB_W, PI_USB_H]);
    }

    // ── 長邊（y = 0 側）：USB-C 供電 ＋ 兩個 micro-HDMI ──
    color("#d0d3d6") {
        translate([9, -1, PCB_T])  cube([PI_USBC_W, 4, PI_USBC_H]);
        translate([26, -1, PCB_T]) cube([PI_HDMI_W, 4, PI_HDMI_H]);
        translate([39, -1, PCB_T]) cube([PI_HDMI_W, 4, PI_HDMI_H]);
    }

    // ── 長邊（y = PI_D 側）：40 針 GPIO ──
    color("#2b2b2b")
        translate([3.5, PI_D - PI_GPIO_W - 3.5, PCB_T])
            cube([PI_GPIO_L, PI_GPIO_W, PI_GPIO_H]);

    // 安裝孔（★M4 穿不過★ ⌀2.7，只能 M2.5——見 params.scad 螺絲規格）
    color("#8a8f94") for (p = PI_SCREW)
        translate([p[0], p[1], -0.2]) cylinder(h = PCB_T + 0.4, d = 2.7, $fn = 24);
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
pi5();
