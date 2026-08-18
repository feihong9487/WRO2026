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
// 零件 4：風扇座（40mm 四線 PWM 軸流風扇；★2026-08-18 改為軸向貫穿★）
// ═══════════════════════════════════════════════════════════════════════════
// 軸流風扇：氣流「直接貫穿」——煙從集煙罩煙道進來（法蘭側），順著中央圓孔
// 被風扇軸向抽過去、從排氣面吹出。中央必須是一個真正貫穿的孔。
//
// ★原設計的封死坑（本次修正的重點）★
//   舊版軸向進氣孔寫成 cylinder(h = WALL + 0.2) 從 z=-0.1 起——只切穿底面
//   那層 WALL，停在與沉槽底幾乎共平面的位置。params.scad OVER 段警告過：
//   停在共平面時 CGAL 不保證切穿，會留下一層退化薄膜，孔實際上是封死的
//   （參數對、Volumes=2、F5 預覽都看不出來，只有 F6/匯出 STL 才現形）。
//   這裡改成從 -OVER 一路挖穿沉槽底、再穿過煙道法蘭，軸向真的通到底。
module fan_mount() {
    body_w = FAN_W + WALL * 2;
    body_h = FAN_H + WALL * 2;
    body_t = FAN_T + WALL * 2;
    flange_h = 10;                       // = incense_burner.scad 的 FAN_FLANGE_H

    difference() {
        union() {
            rrect_chamfered(body_w, body_h, body_t, 4);
            // 煙道法蘭：套住集煙罩後方開口、插進後壁定位
            translate([body_w / 2 - (DUCT_W + WALL * 2) / 2,
                       body_h / 2 - (DUCT_H + WALL * 2) / 2, body_t])
                cube([DUCT_W + WALL * 2, DUCT_H + WALL * 2, flange_h]);
        }

        // 風扇沉槽（軸流風扇本體嵌入，排氣面那側朝外）
        translate([WALL, WALL, WALL]) cube([FAN_W, FAN_H, FAN_T + 1]);

        // ★軸向貫穿孔——空氣真的通得過去★
        //   從 -OVER 一路穿到法蘭頂 +OVER，跨過沉槽底與法蘭，杜絕退化薄膜。
        translate([body_w / 2, body_h / 2, -OVER])
            cylinder(h = body_t + flange_h + OVER * 2, d = FAN_INLET_D);

        // 煙道內孔（法蘭段矩形，對接集煙罩煙道 DUCT_W×DUCT_H；與圓孔匯流）
        translate([body_w / 2 - DUCT_W / 2, body_h / 2 - DUCT_H / 2, WALL])
            cube([DUCT_W, DUCT_H, body_t - WALL + flange_h + OVER]);

        // M4 固定孔（40mm 軸流風扇，間距 FAN_SCREW_S＝32）——穿透底面法蘭
        for (x = [-1, 1], y = [-1, 1])
            translate([body_w / 2 + x * FAN_SCREW_S / 2,
                       body_h / 2 + y * FAN_SCREW_S / 2, -OVER])
                cylinder(h = WALL + OVER * 2, d = FAN_SCREW_D);
    }
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
fan_mount();
