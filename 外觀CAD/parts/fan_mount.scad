/* =============================================================================
 * 智慧香爐 — 零件：風扇座
 * =============================================================================
 * 尺寸全部來自 ../params.scad，本檔不寫死任何數字。
 *
 * 單獨開這個檔（F5／F6）會直接看到這個零件；被 incense_burner.scad 以
 * ★use<>★ 引入時，檔尾的預覽呼叫不會執行——use 只帶進模組、不執行對方的
 * 頂層敘述，這正是「一檔一零件」又不污染組合件的作法。
 * ============================================================================= */

include <../common.scad>

// ═══════════════════════════════════════════════════════════════════════════
// 零件 4：風扇座（5015 鼓風機）
// ═══════════════════════════════════════════════════════════════════════════
// 離心風扇：軸向進氣（對接煙道）、徑向出風（朝後排氣）
module fan_mount() {
    body_w = FAN_W + WALL * 2;
    body_h = FAN_H + WALL * 2;
    body_t = FAN_T + WALL * 2;

    difference() {
        union() {
            rrect_chamfered(body_w, body_h, body_t, 4);
            // 煙道法蘭：接到燃燒艙後方開口
            translate([body_w / 2 - DUCT_W / 2 - WALL, body_h / 2 - DUCT_H / 2 - WALL, body_t])
                cube([DUCT_W + WALL * 2, DUCT_H + WALL * 2, 10]);
        }

        // 風扇本體凹槽
        translate([WALL, WALL, WALL]) cube([FAN_W, FAN_H, FAN_T + 1]);

        // 軸向進氣口（貫穿到煙道側）
        translate([body_w / 2, body_h / 2, -0.1]) cylinder(h = WALL + 0.2, d = FAN_INLET_D);

        // 煙道內孔
        translate([body_w / 2 - DUCT_W / 2, body_h / 2 - DUCT_H / 2, WALL])
            cube([DUCT_W, DUCT_H, 20]);

        // 徑向出風口（朝後）
        translate([body_w - WALL - 0.5, body_h / 2 - FAN_OUT_H / 2, WALL + 2])
            cube([WALL + 1, FAN_OUT_H, FAN_OUT_W]);

        // M3 固定孔
        for (x = [-1, 1], y = [-1, 1])
            translate([body_w / 2 + x * FAN_SCREW_S / 2,
                       body_h / 2 + y * FAN_SCREW_S / 2, -0.1])
                cylinder(h = WALL + 0.2, d = FAN_SCREW_D);
    }
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
fan_mount();
