/* =============================================================================
 * 智慧香爐 — 零件：集煙罩（漏斗狀，2026-08-16 改版）
 * =============================================================================
 * 尺寸全部來自 ../params.scad，本檔不寫死任何數字。
 *
 * ★造型：下段直筒 ＋ 上段外擴喇叭口★
 *   舊版是上窄下寬的縮口錐（罩頂 96），使用者插香要對準小口，不好用。
 *   改成漏斗：直筒段外形與燃燒艙同寬，後方煙道開口與風扇座法蘭都靠在
 *   這段的垂直後壁上（斜面貼不平法蘭，所以這段必須直）；
 *   直筒之上外擴到 HOOD_TOP_W，向上開的大口，插香不必對準。
 *
 * ★不能用單一 hull() 做整個外殼★ 「直筒＋喇叭」是非凸形狀，
 *   hull() 會把腰身填掉、直筒段變成斜面——所以直筒與喇叭各自成體再 union。
 *
 * ★列印方向：開口朝下倒印★ 喇叭大口貼床、斜面約 34°（<45°）自支撐，
 *   直筒段垂直，整件免支撐。
 *
 * 單獨開這個檔（F5／F6）會直接看到這個零件；被 incense_burner.scad 以
 * ★use<>★ 引入時，檔尾的預覽呼叫不會執行——use 只帶進模組、不執行對方的
 * 頂層敘述，這正是「一檔一零件」又不污染組合件的作法。
 * ============================================================================= */

include <../common.scad>

// ═══════════════════════════════════════════════════════════════════════════
// 零件 3：集煙罩
// ═══════════════════════════════════════════════════════════════════════════
module hood() {
    difference() {
        hood_shell();
        // 後方煙道出口（穿透直筒段後壁）——★留在 hood() 裡★，
        // 這樣「煙道尺寸三處一致」的檢查 F 才看得到 DUCT_W/DUCT_H。
        // 開口整個落在直筒段（驗證CAD.py 的 F 檢查會驗），
        // 後壁是垂直平面，風扇座法蘭直接貼平，不再需要安裝墊台。
        translate([CHMB_W / 2 - DUCT_W / 2, CHMB_D - 30, DUCT_Z_HOOD])
            cube([DUCT_W, 40, DUCT_H]);
    }
}

module hood_shell() {
    flare_h = HOOD_H - HOOD_COLLAR_H;    // 喇叭段高
    // 喇叭錐面上任一高度（以喇叭段底為 0）的外輪廓寬度／圓角（線性內插）
    function w_at(z) = CHMB_W + (HOOD_TOP_W - CHMB_W) * z / flare_h;
    function r_at(z) = CORNER_R + (CORNER_R * 0.6 - CORNER_R) * z / flare_h;

    // 內腔上下各超出 OVER（全域定義，見 params.scad「切穿用的超出量」）。
    // ★這裡踩過坑★ 舊版內腔頂面停在 HOOD_H，與外殼頂面共平面，
    //   結果不是切穿而是留下一層退化頂蓋——投香口被封死。
    difference() {
        union() {
            // 直筒段：外形與燃燒艙同尺寸
            rrect(CHMB_W, CHMB_D, HOOD_COLLAR_H, CORNER_R);
            // 喇叭段：由直筒頂外擴到罩頂大口
            translate([0, 0, HOOD_COLLAR_H]) hull() {
                rrect(CHMB_W, CHMB_D, 0.1, CORNER_R);
                translate([(CHMB_W - HOOD_TOP_W) / 2, (CHMB_D - HOOD_TOP_W) / 2,
                           flare_h - 0.1])
                    rrect(HOOD_TOP_W, HOOD_TOP_W, 0.1, CORNER_R * 0.6);
            }
        }

        // 直筒段內腔（上下各超出 OVER，確保與喇叭內腔、底面都切穿）
        translate([WALL, WALL, -OVER])
            rrect(CHMB_W - WALL * 2, CHMB_D - WALL * 2,
                  HOOD_COLLAR_H + OVER * 2, max(CORNER_R - WALL, 0.5));

        // 喇叭段內腔（沿同一錐度延伸到外殼之外）
        translate([0, 0, HOOD_COLLAR_H]) hull() {
            for (z = [-OVER, flare_h + OVER])
                let (w = w_at(z), r = max(r_at(z) - WALL, 0.5))
                    translate([(CHMB_W - w) / 2 + WALL, (CHMB_D - w) / 2 + WALL, z])
                        rrect(w - WALL * 2, w - WALL * 2, 0.1, r);
        }

        // 底面定位榫孔（母）
        tenons_female(CHMB_W, CHMB_D, 0);

    }
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
hood();
