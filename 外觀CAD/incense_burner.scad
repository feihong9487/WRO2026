/* =============================================================================
 * 智慧香爐 — 桌上型展示機外觀（參數化 CAD）
 * =============================================================================
 * 用途：WRO 2026 競賽展示用的完整香爐，含燃燒艙、集煙罩、抽風道與電子艙。
 * 製造：FDM 3D 列印（分件列印後組裝）
 *
 * 開啟方式：OpenSCAD（免費，openscad.org）→ F5 預覽 → F6 算繪 → 匯出 STL
 *
 * -----------------------------------------------------------------------------
 * ★ 核心設計約束：熱 ★
 * -----------------------------------------------------------------------------
 * 熱電偶聯鎖 T_LOCK = 150°C、T_RELEASE = 130°C（2026-08-02 調高，臨時值）。
 * 交接文件把熱電偶懸於爐面上方 2-3cm，該處預估 120°C——燃燒艙外殼會接近這個溫度。
 * FDM 材料熱變形溫度：PLA 55-60°C（會軟化）／PETG 70-80°C（邊界）／ABS·ASA 95-105°C。
 *
 * 因此本設計「不讓塑膠靠近熱源」：
 *   1. 燃燒由★金屬爐盆★（使用者自備不鏽鋼碗）承接，塑膠不直接接觸火源
 *   2. 爐盆與塑膠殼之間留 AIR_GAP 空氣間隙——空氣是最好的絕熱材
 *   3. 熱電偶貼在爐盆外壁，量到的是真實爐面溫度
 *   4. 電子艙在最底層，與燃燒艙之間有隔熱間隙＋對流通風孔
 *
 * ★ 材料建議：燃燒艙與集煙罩用 ABS/ASA/PETG；底座可用 PLA ★
 *
 * -----------------------------------------------------------------------------
 * 氣流路徑
 * -----------------------------------------------------------------------------
 *   香在金屬爐盆燃燒 → 煙自然上升 → 集煙罩捕捉 → 後方煙道
 *   → 5015 鼓風機（軸向進氣、徑向出風）抽出 → 後方排氣口
 *
 * -----------------------------------------------------------------------------
 * 列印方向（皆免支撐或僅需極少支撐）
 * -----------------------------------------------------------------------------
 *   base        底面朝下
 *   chamber     底面朝下
 *   hood        ★開口朝下倒著印★（避免懸空）
 *   fan_mount   背面朝下
 *   sensor_pod  背面朝下
 * ============================================================================= */

// ═══════════════════════════════════════════════════════════════════════════
// 輸出選擇：改這一行即可切換要算繪的零件
// ═══════════════════════════════════════════════════════════════════════════
part = "assembly";  // ["assembly", "base", "chamber", "hood", "fan_mount", "sensor_pod", "print_plate"]

// 剖半檢視：切掉一半看內部結構。
// 加這個是因為外觀算繪看不出內部有沒有做對——例如集煙罩的投香口有沒有真的開通。
SECTION = false;    // true = 剖半
SECTION_AXIS = "y"; // "x" 或 "y"

// 干涉檢查用（part="interference" 時生效）
PAIR_A = "base";
PAIR_B = "chamber";

// ═══════════════════════════════════════════════════════════════════════════
// 列印參數
// ═══════════════════════════════════════════════════════════════════════════
NOZZLE      = 0.4;              // 噴嘴直徑
WALL        = NOZZLE * 6;       // 2.4mm＝6 走線，強度足夠且不浪費時間
FLOOR       = NOZZLE * 5;       // 2.0mm 底/頂厚（0.2 層高 × 10 層）
FIT         = 0.3;              // 組裝件之間的配合間隙（FDM 常用 0.2-0.4）
CHAMFER     = 1.2;              // 底緣倒角，改善首層附著
BED         = 220;              // 列印床尺寸，驗證腳本會檢查零件是否放得下

// ═══════════════════════════════════════════════════════════════════════════
// 外型主尺寸
// ═══════════════════════════════════════════════════════════════════════════
BASE_W      = 180;              // 電子艙寬（也是整機最大寬度）
BASE_D      = 180;              // 電子艙深
BASE_H      = 62;               // 電子艙高

CHMB_W      = 156;              // 燃燒艙寬（比底座小，形成階梯造型）
CHMB_D      = 156;
CHMB_H      = 72;

HOOD_H      = 62;               // 集煙罩高
HOOD_TOP_W  = 96;               // 罩頂開口寬（投香口）

CORNER_R    = 10;               // 外型圓角半徑——柔和的圓角讓造型接近傳統香爐

// ═══════════════════════════════════════════════════════════════════════════
// 燃燒區
// ═══════════════════════════════════════════════════════════════════════════
// ★使用者自備金屬爐盆★：常見不鏽鋼碗／香灰盆。買到後請實測並改這兩個值。
BOWL_D      = 110;              // 爐盆外徑
BOWL_H      = 45;               // 爐盆深度
AIR_GAP     = 8;                // ★爐盆與塑膠之間的空氣間隙（絕熱關鍵）★
BOWL_LIP    = 4;                // 承接爐盆邊緣的環寬
RIB_W       = 6;                // 承接肋寬——僅 4 條，把導熱路徑降到最低

// 燃燒艙與電子艙之間的隔熱層
ISO_GAP     = 14;               // 空氣層厚度
ISO_VENT_W  = 5;                // 對流通風縫寬
ISO_RIB_W   = 3;                // 隔熱層支撐肋寬
ISO_RIB_N   = 3;                // 每軸肋條數
// ★為什麼要肋條★ 隔熱層是從底部挖空的，其天花板（爐盆井的樓板）
//   原本是 151mm 無支撐的水平面——列印時橋接跨距太長必定下垂。
//   肋條把跨距切成 ~38mm 的區塊，同時提升剛性。
//   刻意用細肋而非實心：導熱路徑降到最低，空氣層功能不受影響。

// ═══════════════════════════════════════════════════════════════════════════
// 5015 鼓風機（離心式：軸向進氣、徑向出風）
// ═══════════════════════════════════════════════════════════════════════════
FAN_W       = 51;               // 本體寬（標稱 50，留餘量）
FAN_H       = 51;               // 本體高
FAN_T       = 16;               // 厚度（標稱 15）
FAN_INLET_D = 40;               // 軸向進氣口直徑
FAN_OUT_W   = 20;               // 徑向出風口寬
FAN_OUT_H   = 20;               // 徑向出風口高
FAN_SCREW_D = 3.2;              // M3 通孔
FAN_SCREW_S = 42;               // 螺絲孔間距（5015 常見值，請實測確認）

// 煙道
// ★煙道只開在集煙罩上★ 煙從爐盆上升、在罩內聚集，那裡才是該抽的位置。
//   原本燃燒艙也開了一個，位置在爐盆側面（煙不會往那走），
//   而且與罩子的開口差 12mm 完全對不上——2026-08-02 移除。
DUCT_W      = 46;               // 煙道寬
DUCT_H      = 30;               // 煙道高
DUCT_Z_HOOD = 6;                // 開口下緣在集煙罩局部座標的高度
PAD_MARGIN  = 7;                // 風扇安裝墊台四周比開口多出的邊

// ═══════════════════════════════════════════════════════════════════════════
// 電子元件（★以下尺寸多為估值，拿到實體請實測後修改★）
// ═══════════════════════════════════════════════════════════════════════════
// MATRIX Mini R4：官方未公佈尺寸。以 Arduino UNO 外型（68.6×53.4）為基礎，
// 因周邊埠較多而放寬。★務必實測★
MATRIX_W    = 90;    MATRIX_D = 70;    MATRIX_SCREW = [[4,4],[86,4],[4,66],[86,66]];
// Raspberry Pi 5：官方尺寸 85×56，螺孔 58×49 間距、距邊 3.5
PI_W        = 85;    PI_D     = 56;    PI_SCREW    = [[3.5,3.5],[61.5,3.5],[3.5,52.5],[61.5,52.5]];
// D4184 MOSFET 模組：常見尺寸
D4184_W     = 42;    D4184_D  = 34;

STANDOFF_H  = 6;                // 螺柱高（板底離殼底的距離，留走線空間）
STANDOFF_D  = 7;                // 螺柱外徑
SCREW_PILOT = 2.5;              // M3 自攻底孔（螺絲直接旋入塑膠）

// ═══════════════════════════════════════════════════════════════════════════
// 感測器艙（前方，遠離熱源，朝向參拜者呼吸帶）
// ═══════════════════════════════════════════════════════════════════════════
POD_W       = 62;
POD_D       = 26;
POD_H       = 58;   // 需容納兩模組堆疊（驗證腳本會檢查）
SCD41_W     = 25;    SCD41_D = 21;     // GY-SCD41 模組（估值，請實測）
SHT31_W     = 18;    SHT31_D = 14;     // GY-SHT31-D 模組（估值，請實測）

// ═══════════════════════════════════════════════════════════════════════════
// 定位榫（層與層之間的對位）
// ═══════════════════════════════════════════════════════════════════════════
TENON_D     = 8;                // 榫柱直徑
TENON_H     = 6;                // 榫柱高
LEDGE_W     = 11;               // 頂緣內側承接台階寬——榫柱要坐在實體上，不能懸空
LEDGE_H     = 3;                // 台階高
TENON_INSET = WALL + LEDGE_W / 2;  // ★必須落在台階上★（原本 22 會讓榫柱浮空）

$fn = 48;                       // 圓弧精細度（算繪時可調高到 96）

// ═══════════════════════════════════════════════════════════════════════════
// 共用輔助模組
// ═══════════════════════════════════════════════════════════════════════════

// 圓角方柱：用 4 根圓柱做 hull，比 minkowski 快很多
module rrect(w, d, h, r) {
    hull() {
        for (x = [r, w - r], y = [r, d - r])
            translate([x, y, 0]) cylinder(h = h, r = r);
    }
}

// 圓角方柱（底緣倒角版）：改善首層附著並讓外型更柔和
module rrect_chamfered(w, d, h, r, c = CHAMFER) {
    union() {
        // 倒角裙邊
        hull() {
            for (x = [r, w - r], y = [r, d - r])
                translate([x, y, 0]) cylinder(h = c, r1 = r - c, r2 = r);
        }
        translate([0, 0, c]) rrect(w, d, h - c, r);
    }
}

// 螺柱座（含自攻底孔）
module standoff(h = STANDOFF_H) {
    difference() {
        cylinder(h = h, d = STANDOFF_D);
        translate([0, 0, -0.1]) cylinder(h = h + 0.2, d = SCREW_PILOT);
    }
}

// 通風柵格：一排長圓孔。用於側面進氣與感測器艙開口。
module vent_slots(n, slot_w, slot_h, pitch, depth) {
    for (i = [0 : n - 1])
        translate([i * pitch, 0, 0])
            hull() {
                translate([0, slot_h / 2 - slot_w / 2, 0])
                    cylinder(h = depth, d = slot_w, $fn = 16);
                translate([0, -slot_h / 2 + slot_w / 2, 0])
                    cylinder(h = depth, d = slot_w, $fn = 16);
            }
}

// 頂緣承接台階：讓定位榫有實體可坐，同時作為上層零件的落座面
module top_ledge(w, d, z, r) {
    translate([0, 0, z])
        difference() {
            translate([WALL, WALL, 0])
                rrect(w - WALL * 2, d - WALL * 2, LEDGE_H, r - WALL);
            translate([WALL + LEDGE_W, WALL + LEDGE_W, -0.1])
                rrect(w - (WALL + LEDGE_W) * 2, d - (WALL + LEDGE_W) * 2,
                      LEDGE_H + 0.2, max(r - WALL - LEDGE_W, 0.5));
        }
}

// 定位榫（公）：四角
module tenons_male(w, d, z) {
    for (x = [TENON_INSET, w - TENON_INSET], y = [TENON_INSET, d - TENON_INSET])
        translate([x, y, z])
            cylinder(h = TENON_H, d1 = TENON_D, d2 = TENON_D - 1.2);  // 帶錐度好插入
}

// 定位榫（母）：對應的孔
module tenons_female(w, d, z) {
    for (x = [TENON_INSET, w - TENON_INSET], y = [TENON_INSET, d - TENON_INSET])
        translate([x, y, z - 0.1])
            cylinder(h = TENON_H + 0.2, d = TENON_D + FIT * 2);
}

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
                for (p = PI_SCREW) translate([p[0], p[1], 0]) standoff();
            // D4184 兩點固定即可
            translate([BASE_W - 20 - D4184_W, 20, FLOOR]) {
                translate([4, 4, 0]) standoff();
                translate([D4184_W - 4, D4184_D - 4, 0]) standoff();
            }
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

// ═══════════════════════════════════════════════════════════════════════════
// 零件 3：集煙罩
// ═══════════════════════════════════════════════════════════════════════════
// ★列印方向：開口朝下倒印，全部斜面都變成自支撐★
module hood() {
    // 錐面上任一高度的外輪廓寬度／圓角（線性內插）
    function w_at(z) = CHMB_W + (HOOD_TOP_W - CHMB_W) * z / HOOD_H;
    function r_at(z) = CORNER_R + (CORNER_R * 0.6 - CORNER_R) * z / HOOD_H;

    // 內腔上下各超出 OVER，確保真的切穿。
    // ★這裡踩過坑★ 原本內腔頂面停在 HOOD_H，與外殼頂面共平面，
    //   結果不是切穿而是留下一層退化頂蓋——投香口被封死。
    //   參數檢查與 Volumes=2 都抓不到（封起來的罩子仍是合法單一實體），
    //   是用 SECTION=true 剖半算繪才看出來的。
    OVER = 2;

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

// ═══════════════════════════════════════════════════════════════════════════
// 零件 5：感測器艙
// ═══════════════════════════════════════════════════════════════════════════
// 位置在前方下緣，遠離熱源，開口朝向參拜者呼吸帶——
// 這符合 FSM 用 CO2 斜率偵測人潮的設計意圖：量的是「人呼吸到的空氣」。
module sensor_pod() {
    difference() {
        union() {
            rrect_chamfered(POD_W, POD_D, POD_H, 5);
            // 背面掛耳（鎖到底座前壁）
            translate([POD_W / 2 - 14, POD_D - WALL, POD_H - 12]) cube([28, WALL, 10]);
        }

        // 內部挖空（背面開放，方便置入模組與走線）
        translate([WALL, WALL, FLOOR])
            rrect(POD_W - WALL * 2, POD_D - WALL, POD_H - FLOOR * 2, 5 - WALL);

        // 前面通風柵格——感測器必須接觸到外界空氣才量得準
        translate([12, -0.5, POD_H / 2]) rotate([-90, 0, 0])
            vent_slots(5, 3.5, 26, 8, WALL + 1);

        // 模組卡槽（滑入式）
        translate([POD_W / 2 - SCD41_W / 2 - FIT, WALL + 2, FLOOR + 4])
            cube([SCD41_W + FIT * 2, 1.8, SCD41_D + FIT * 2]);
        translate([POD_W / 2 - SHT31_W / 2 - FIT, WALL + 2, FLOOR + 4 + SCD41_D + 6])
            cube([SHT31_W + FIT * 2, 1.8, SHT31_D + FIT * 2]);

        // 掛耳螺絲孔
        translate([POD_W / 2 - 8, POD_D - WALL - 0.1, POD_H - 7]) rotate([-90, 0, 0])
            cylinder(h = WALL + 0.2, d = SCREW_PILOT);
        translate([POD_W / 2 + 8, POD_D - WALL - 0.1, POD_H - 7]) rotate([-90, 0, 0])
            cylinder(h = WALL + 0.2, d = SCREW_PILOT);
    }
}

// ═══════════════════════════════════════════════════════════════
// 組裝定位
// ═══════════════════════════════════════════════════════════════
// ★所有零件的擺放位置集中在 place()★
//   assembly() 與干涉檢查共用同一組變換——這是單一真相來源。
//   若分開寫，改了組裝卻忘了改檢查，干涉檢查就會驗到錯的位置。

PARTS_LIST = ["base", "chamber", "hood", "fan_mount", "sensor_pod"];
PART_COLOR = ["#5b6670", "#8b6f47", "#a8825c", "#3f4a52", "#2f6f5a"];

// 風扇座定位計算（外掛在燃燒艙後方）
FAN_BODY_T   = FAN_T + WALL * 2;                  // 本體厚
FAN_FLANGE_H = 10;                                // 煙道法蘭高
FAN_PENETR   = 4;                                 // 法蘭插入燃燒艙後壁的深度
CHMB_BACK_Y  = (BASE_D - CHMB_D) / 2 + CHMB_D;    // 燃燒艙後壁外緣

module part_by_name(name) {
    if      (name == "base")       base();
    else if (name == "chamber")    chamber();
    else if (name == "hood")       hood();
    else if (name == "fan_mount")  fan_mount();
    else if (name == "sensor_pod") sensor_pod();
}

module place(name, explode = 0) {
    if (name == "base")
        children();
    else if (name == "chamber")
        translate([(BASE_W - CHMB_W) / 2, (BASE_D - CHMB_D) / 2, BASE_H + explode])
            children();
    else if (name == "hood")
        translate([(BASE_W - CHMB_W) / 2, (BASE_D - CHMB_D) / 2,
                   BASE_H + CHMB_H + explode * 2])
            children();
    else if (name == "fan_mount")
        // rotate([90,0,0]) 使局部 +z → 全域 -y，所以 y 必須往後推整個深度，
        // 只留 FAN_PENETR 讓法蘭插進燃燒艙後壁。
        // ★原本少推這一段，30.8mm 的風扇座整個埋在燃燒艙裡（2026-08-02 修正）★
        // z：對齊集煙罩煙道開口的中心（rotate 後局部 y → 全域 z）
        translate([BASE_W / 2 - (FAN_W + WALL * 2) / 2,
                   CHMB_BACK_Y + FAN_BODY_T + FAN_FLANGE_H - FAN_PENETR + explode,
                   BASE_H + CHMB_H + DUCT_Z_HOOD + DUCT_H / 2 - (FAN_H + WALL * 2) / 2])
            rotate([90, 0, 0]) children();
    else if (name == "sensor_pod")
        // 本體在底座前方外側，只有掛耳貼上前壁
        translate([BASE_W / 2 - POD_W / 2, -POD_D - explode, BASE_H - POD_H - 2])
            children();
}

module placed(name, explode = 0) { place(name, explode) part_by_name(name); }

module assembly(explode = 0) {
    for (i = [0 : len(PARTS_LIST) - 1])
        color(PART_COLOR[i]) placed(PARTS_LIST[i], explode);

    // 金屬爐盆（示意，非列印件）
    translate([BASE_W / 2, BASE_D / 2, BASE_H + CHMB_H - BOWL_H + explode])
        color("#b9bec4", 0.55)
            difference() {
                cylinder(h = BOWL_H, d = BOWL_D);
                translate([0, 0, 1.5]) cylinder(h = BOWL_H, d = BOWL_D - 3);
            }
}

// ── 功能性開口的淨空區 ──────────────────────────────────
// 開口外側若被其他零件擋住，功能就失效——但這不是「干涉」
// （沒有實體穿透），干涉檢查抓不到。例如感測器艙擋住底座進氣柵格：
// 兩件沒有相碰，卻讓對流散熱失效。
CLEAR_MM = 12;   // 開口外側需要的淨空深度

module clearance_zone(name) {
    if (name == "base_vent")            // 底座兩側進氣柵格
        for (s = [0, 1])
            translate([s ? BASE_W : -CLEAR_MM, BASE_D / 2 - 30, 14])
                cube([CLEAR_MM, 60, 40]);
    else if (name == "chamber_vent")    // 隔熱層前後對流縫
        for (s = [0, 1])
            translate([(BASE_W - CHMB_W) / 2 + CHMB_W / 2 - 45,
                       s ? (BASE_D - CHMB_D) / 2 + CHMB_D
                         : (BASE_D - CHMB_D) / 2 - CLEAR_MM,
                       BASE_H + 2])
                cube([90, CLEAR_MM, 12]);
    else if (name == "hood_opening")    // 投香口正上方
        translate([BASE_W / 2, BASE_D / 2, BASE_H + CHMB_H + HOOD_H])
            cylinder(h = 40, d = HOOD_TOP_W - WALL * 2);
    else if (name == "pod_vent")        // 感測器艙前方（面向參拜者）
        translate([BASE_W / 2 - POD_W / 2, -POD_D - CLEAR_MM, BASE_H - POD_H - 2])
            cube([POD_W, CLEAR_MM, POD_H]);
}

// 除了指定零件以外的所有零件（檢查淨空區被誰擋住）
module others(except) {
    for (n = PARTS_LIST) if (n != except) placed(n);
}

module blocked(zone, owner) {
    intersection() { clearance_zone(zone); others(owner); }
}

// 兩零件的干涉體積：驗證器匯成 STL 後量體積。
// 體積 > 0 代表兩件互相穿透，實體組裝不起來（也就是畫面上的 z-fighting 破圖）。
module interference(a, b) {
    intersection() { placed(a); placed(b); }
}

// 列印排版：所有零件平鋪，檢查是否放得進列印床
module print_plate() {
    base();
    translate([0, BASE_D + 8, 0]) chamber();
    translate([BASE_W + 8, 0, 0]) hood();
    translate([BASE_W + 8, CHMB_D + 8, 0]) fan_mount();
    translate([BASE_W + 8, CHMB_D + 90, 0]) sensor_pod();
    #translate([-2, -2, -1]) cube([BED, BED, 0.5]);
}

// ═══════════════════════════════════════════════════════════════════════════
// 主輸出
// ═══════════════════════════════════════════════════════════════════════════
module dispatch() {
    if      (part == "assembly")     assembly(0);
    else if (part == "exploded")     assembly(35);
    else if (part == "base")         base();
    else if (part == "chamber")      chamber();
    else if (part == "hood")         hood();
    else if (part == "fan_mount")    fan_mount();
    else if (part == "sensor_pod")   sensor_pod();
    else if (part == "print_plate")  print_plate();
    else if (part == "placed")       placed(PAIR_A);           // 定位後單件（取包圍盒）
    else if (part == "interference") interference(PAIR_A, PAIR_B);
    else if (part == "blocked")      blocked(PAIR_A, PAIR_B);
    else if (part == "none")         ;                          // 供 include 時不算繪
    else                             assembly(0);
}

if (SECTION) {
    difference() {
        dispatch();
        if (SECTION_AXIS == "y")
            translate([-100, BASE_D / 2, -100]) cube([600, 600, 600]);
        else
            translate([BASE_W / 2, -100, -100]) cube([600, 600, 600]);
    }
} else {
    dispatch();
}