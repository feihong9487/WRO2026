/* =============================================================================
 * 智慧香爐 — 零件：電子艙（底座）
 * =============================================================================
 * 尺寸全部來自 ../params.scad，本檔不寫死任何數字。
 *
 * 單獨開這個檔（F5／F6）會直接看到這個零件；被 incense_burner.scad 以
 * ★use<>★ 引入時，檔尾的預覽呼叫不會執行——use 只帶進模組、不執行對方的
 * 頂層敘述，這正是「一檔一零件」又不污染組合件的作法。
 * ============================================================================= */

include <../common.scad>

// ═══════════════════════════════════════════════════════════════════════════
// 零件 1：電子艙（底座）
// ═══════════════════════════════════════════════════════════════════════════
module base() {
    difference() {
        union() {
            // 外殼
            difference() {
                rrect_chamfered(BASE_W, BASE_D, BASE_H, CORNER_R);
                // 挖空內部（頂面開放，由燃燒艙蓋住）
                translate([WALL, WALL, FLOOR])
                    rrect(BASE_W - WALL * 2, BASE_D - WALL * 2, BASE_H, CORNER_R - WALL);
            }
            // 板卡螺柱
            translate([14, 14, FLOOR])
                for (p = MATRIX_SCREW) translate([p[0], p[1], 0]) standoff();
            translate([14, BASE_D - 14 - PI_D, FLOOR])
                for (p = PI_SCREW) translate([p[0], p[1], 0]) standoff(pilot = M25_PILOT);
            // D4184 兩點固定即可
            translate([BASE_W - 20 - D4184_W, 20, FLOOR]) {
                translate([4, 4, 0]) standoff();
                translate([D4184_W - 4, D4184_D - 4, 0]) standoff();
            }
            // 感測器艙掛耳的鎖點：M4 自攻螺柱，長在前壁內側
            // ★位置完全由 POD_EAR_* ＋ place("sensor_pod") 推導★
            //   前壁只有 WALL=2.4 厚，M4 自攻進去等於沒有牙，一鎖就滑；
            //   所以往內加 M4_ENGAGE 深的螺柱補足旋入深度。
            for (dx = [-1, 1])
                translate([BASE_W / 2 + dx * POD_EAR_PITCH / 2, 0,
                           BASE_H - POD_H - 2 + POD_EAR_Z + POD_EAR_H / 2])
                    rotate([-90, 0, 0])
                        standoff(h = M4_ENGAGE, pilot = M4_PILOT);

            // 頂緣台階 ＋ 定位榫（公）——燃燒艙套上來
            top_ledge(BASE_W, BASE_D, BASE_H - LEDGE_H, CORNER_R);
            tenons_male(BASE_W, BASE_D, BASE_H);
        }

        // ── 側面進氣柵格（左右各一組，自然對流帶走電子元件廢熱）──
        for (side = [0, 1])
            translate([side ? BASE_W - WALL - 0.5 : -0.5, BASE_D / 2 - 30, 18])
                rotate([0, 90, 0])
                    rotate([0, 0, 90])
                        vent_slots(6, 4, 46, 9, WALL + 1);

        // ── 後面板開孔 ──
        // 12V 電源插孔（DC 5.5/2.1 常見孔徑 8mm）
        translate([BASE_W - 46, BASE_D - WALL - 0.5, 30]) rotate([-90, 0, 0])
            cylinder(h = WALL + 1, d = 8.2);
        // Pi 的 USB-C 電源與 HDMI 走線開口
        translate([26, BASE_D - WALL - 0.5, 16]) rotate([-90, 0, 0])
            hull() {
                translate([0, 6, 0])  cylinder(h = WALL + 1, d = 12, $fn = 24);
                translate([34, 6, 0]) cylinder(h = WALL + 1, d = 12, $fn = 24);
            }

        // ── 頂面走線孔：熱電偶、風扇電源、感測器線 ──
        translate([BASE_W / 2, BASE_D / 2, BASE_H - FLOOR - 0.1])
            cylinder(h = FLOOR + 0.2, d = 26);
        // 前方感測器走線
        translate([BASE_W / 2, 26, BASE_H - FLOOR - 0.1])
            cylinder(h = FLOOR + 0.2, d = 12);

        // ── 底面防滑墊凹槽 ──
        for (x = [24, BASE_W - 24], y = [24, BASE_D - 24])
            translate([x, y, -0.1]) cylinder(h = 1.2, d = 14);
    }
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
base();
