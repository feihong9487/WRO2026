/* =============================================================================
 * 智慧香爐 — 零件：集煙罩
 * =============================================================================
 * 尺寸全部來自 ../params.scad，本檔不寫死任何數字。
 *
 * 單獨開這個檔（F5／F6）會直接看到這個零件；被 incense_burner.scad 以
 * ★use<>★ 引入時，檔尾的預覽呼叫不會執行——use 只帶進模組、不執行對方的
 * 頂層敘述，這正是「一檔一零件」又不污染組合件的作法。
 * ============================================================================= */

include <../common.scad>

// ═══════════════════════════════════════════════════════════════════════════
// 零件 3：集煙罩
// ═══════════════════════════════════════════════════════════════════════════
// ★列印方向：開口朝下倒印，全部斜面都變成自支撐★
module hood() {
    // 錐面上任一高度的外輪廓寬度／圓角（線性內插）
    function w_at(z) = CHMB_W + (HOOD_TOP_W - CHMB_W) * z / HOOD_H;
    function r_at(z) = CORNER_R + (CORNER_R * 0.6 - CORNER_R) * z / HOOD_H;

    // 內腔上下各超出 OVER（全域定義，見檔頭「切穿用的超出量」）。
    // ★這裡踩過坑★ 原本內腔頂面停在 HOOD_H，與外殼頂面共平面，
    //   結果不是切穿而是留下一層退化頂蓋——投香口被封死。
    difference() {
        union() {
            // 外殼
            hull() {
                rrect(CHMB_W, CHMB_D, 0.1, CORNER_R);
                translate([(CHMB_W - HOOD_TOP_W) / 2, (CHMB_D - HOOD_TOP_W) / 2, HOOD_H - 0.1])
                    rrect(HOOD_TOP_W, HOOD_TOP_W, 0.1, CORNER_R * 0.6);
            }
            hood_pad();
        }

        // 內腔（沿同一錐度延伸到外殼之外）
        hull() {
            for (z = [-OVER, HOOD_H + OVER])
                let (w = w_at(z), r = max(r_at(z) - WALL, 0.5))
                    translate([(CHMB_W - w) / 2 + WALL, (CHMB_D - w) / 2 + WALL, z])
                        rrect(w - WALL * 2, w - WALL * 2, 0.1, r);
        }

        // 底面定位榫孔（母）
        tenons_female(CHMB_W, CHMB_D, 0);

        // 後方煙道出口（穿透墊台與罩壁）
        translate([CHMB_W / 2 - DUCT_W / 2, CHMB_D - 30, DUCT_Z_HOOD])
            cube([DUCT_W, 40, DUCT_H]);
    }
}

// 集煙罩背面的平面安裝墊台
// ★為什麼需要★ 罩子是錐面，風扇法蘭貼上去只會點接觸、漏氣。
//   墊台把安裝面拉回與燃燒艙後壁同一個垂直平面（y = CHMB_D）。
module hood_pad() {
    pw = DUCT_W + PAD_MARGIN * 2;
    ph = DUCT_H + PAD_MARGIN * 2;
    // 錐面在墊台範圍內最內縮的位置（開口上緣）
    y_inner = CHMB_D - (CHMB_D - HOOD_TOP_W) * (DUCT_Z_HOOD + ph) / HOOD_H / 2 - 2;
    translate([CHMB_W / 2 - pw / 2, y_inner, DUCT_Z_HOOD - PAD_MARGIN])
        cube([pw, CHMB_D - y_inner, ph]);
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
hood();
