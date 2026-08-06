/* =============================================================================
 * 智慧香爐 — 零件：燃燒艙
 * =============================================================================
 * 尺寸全部來自 ../params.scad，本檔不寫死任何數字。
 *
 * 單獨開這個檔（F5／F6）會直接看到這個零件；被 incense_burner.scad 以
 * ★use<>★ 引入時，檔尾的預覽呼叫不會執行——use 只帶進模組、不執行對方的
 * 頂層敘述，這正是「一檔一零件」又不污染組合件的作法。
 * ============================================================================= */

include <../common.scad>

// ═══════════════════════════════════════════════════════════════════════════
// 零件 2：燃燒艙（含金屬爐盆凹槽與隔熱層）
// ═══════════════════════════════════════════════════════════════════════════
module chamber() {
    bowl_seat_d = BOWL_D + FIT * 2;          // 爐盆落座孔
    well_d      = bowl_seat_d + AIR_GAP * 2; // 外圍空氣間隙
    iso_z       = ISO_GAP;                   // 隔熱層頂面高度

    difference() {
        union() {
            difference() {
                rrect_chamfered(CHMB_W, CHMB_D, CHMB_H, CORNER_R);

                // 隔熱空氣層（底部整層挖空，只留四周牆與支撐肋）
                difference() {
                    translate([WALL, WALL, -0.1])
                        rrect(CHMB_W - WALL * 2, CHMB_D - WALL * 2,
                              iso_z + 0.1, CORNER_R - WALL);
                    // 肋條：把天花板的橋接跨距切成可列印的區塊
                    for (i = [1 : ISO_RIB_N]) {
                        translate([CHMB_W * i / (ISO_RIB_N + 1) - ISO_RIB_W / 2,
                                   WALL, -0.2])
                            cube([ISO_RIB_W, CHMB_D - WALL * 2, iso_z + 0.3]);
                        translate([WALL,
                                   CHMB_D * i / (ISO_RIB_N + 1) - ISO_RIB_W / 2, -0.2])
                            cube([CHMB_W - WALL * 2, ISO_RIB_W, iso_z + 0.3]);
                    }
                }

                // 爐盆外圍的空氣間隙井
                translate([CHMB_W / 2, CHMB_D / 2, iso_z + FLOOR])
                    cylinder(h = CHMB_H, d = well_d);

                // 爐盆落座孔（貫穿到頂）
                translate([CHMB_W / 2, CHMB_D / 2, iso_z + FLOOR])
                    cylinder(h = CHMB_H, d = bowl_seat_d);
            }

            // 爐盆承接環 ＋ 輻射肋
            // ★用肋而非整片實心★：托得住盆，又只留 4 條窄導熱路徑，
            //   絕大部分空氣間隙維持不變（整片實心會把熱直接傳到外殼）
            translate([CHMB_W / 2, CHMB_D / 2, CHMB_H - BOWL_H - FLOOR]) {
                difference() {
                    cylinder(h = FLOOR, d = bowl_seat_d + BOWL_LIP * 2);
                    translate([0, 0, -0.1]) cylinder(h = FLOOR + 0.2, d = bowl_seat_d - 6);
                }
                for (a = [45 : 90 : 359])
                    rotate([0, 0, a])
                        translate([0, -RIB_W / 2, 0])
                            cube([well_d / 2 + 0.5, RIB_W, FLOOR]);
            }

            // 頂緣台階 ＋ 定位榫（公）——集煙罩套上來
            top_ledge(CHMB_W, CHMB_D, CHMB_H - LEDGE_H, CORNER_R);
            tenons_male(CHMB_W, CHMB_D, CHMB_H);
        }

        // 底面定位榫孔（母）——套進底座
        translate([-(BASE_W - CHMB_W) / 2, -(BASE_D - CHMB_D) / 2, 0])
            tenons_female(BASE_W, BASE_D, 0);

        // ── 隔熱層對流通風縫（前後各一排，讓熱空氣流走）──
        for (side = [0, 1])
            translate([CHMB_W / 2 - 40, side ? CHMB_D - WALL - 0.5 : -0.5, ISO_GAP / 2])
                rotate([-90, 0, 0])
                    vent_slots(9, ISO_VENT_W, 8, 9, WALL + 1);

        // ── 熱電偶穿線孔：從隔熱層通到爐盆外壁 ──
        translate([CHMB_W / 2, CHMB_D / 2 - well_d / 2 - 2, ISO_GAP + FLOOR + 6])
            rotate([-90, 0, 0]) cylinder(h = 20, d = 6);

        // ── 中央走線孔（對齊底座頂面）──
        translate([CHMB_W / 2, CHMB_D / 2, -0.1])
            cylinder(h = ISO_GAP + FLOOR + 0.2, d = 26);
    }
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
chamber();
