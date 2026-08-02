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
// ★切穿用的超出量★ 任何要「切開表面」的 difference()，被切體都必須
//   超出表面至少 OVER。停在共平面的位置時，CGAL 不保證切穿——
//   會留下一層退化薄膜，開口實際上是封死的，而且：
//     · 參數檢查抓不到（尺寸都對）
//     · Volumes=2 抓不到（封起來仍是合法的單一實體）
//     · F5 預覽看起來是開的（OpenCSG 容忍共平面），只有 F6／匯出 STL 才現形
//   集煙罩投香口踩過一次。是否觸發跟周邊幾何有關，不是每次共面都會出事——
//   正因為不可預測，才一律超出，不去賭這一次會不會過。
OVER        = 2;
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
BOWL_ALPHA  = 1;                // 組裝圖裡爐盆的不透明度（1=實心；見 assembly() 註解）
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
// 螺絲規格
// ═══════════════════════════════════════════════════════════════════════════
// 指定：鎖固一律用 M4。
//
// ★但有三處鎖不了 M4，而且不是設計選擇的問題★
//   孔徑是外購板卡「自己」的孔，不在我們的圖上：
//     Raspberry Pi 5   官方安裝孔 Ø2.7  → 只能 M2.5
//     MATRIX Mini R4   UNO 相容孔 Ø3.2  → 只能 M3
//     D4184 MOSFET 模組 常見 Ø3.0       → 只能 M3
//   M4 螺絲桿徑 4.0 mm，物理上穿不過去。要嘛把板子的孔擴孔（會削掉
//   板邊銅箔與接地層，不建議），要嘛這三處照板子的規格走。此處選後者。
//
//   結論：★外殼、風扇、感測器艙一律 M4；板卡→殼依板子的孔徑★
M4_PILOT   = 3.3;    // M4 自攻進 PETG 的底孔（旋入式，不用螺帽）
M4_CLEAR   = 4.5;    // M4 通孔
M4_HEAD_D  = 8.0;    // M4 螺帽／華司外徑 → 決定螺柱、掛耳的最小尺寸
M4_ENGAGE  = 8.0;    // 自攻最小旋入深度（≒2×公稱徑，塑膠件的經驗值）

M3_PILOT   = 2.5;    // MATRIX / D4184
M25_PILOT  = 2.1;    // Raspberry Pi 5

// ═══════════════════════════════════════════════════════════════════════════
// 5015 鼓風機（離心式：軸向進氣、徑向出風）
// ═══════════════════════════════════════════════════════════════════════════
FAN_W       = 51;               // 本體寬（標稱 50，留餘量）
FAN_H       = 51;               // 本體高
FAN_T       = 16;               // 厚度（標稱 15）
FAN_INLET_D = 40;               // 軸向進氣口直徑
FAN_OUT_W   = 20;               // 徑向出風口寬
FAN_OUT_H   = 20;               // 徑向出風口高
FAN_SCREW_D = M4_CLEAR;         // M4 通孔（風扇耳孔多為 Ø4，M4 可過；★請實測★）
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
// 螺柱外徑由底孔決定：孔壁至少要留 2.4mm（＝6 條 0.4 走線）才不會旋裂。
// 板卡螺柱走 M3/M2.5（見上方「螺絲規格」說明），不是 M4。
function standoff_od(pilot) = pilot + 2 * WALL;
STANDOFF_D  = standoff_od(M3_PILOT);   // = 7.3

// ═══════════════════════════════════════════════════════════════════════════
// 感測器艙（前方，遠離熱源，朝向參拜者呼吸帶）
// ═══════════════════════════════════════════════════════════════════════════
POD_W       = 62;
POD_D       = 26;
POD_H       = 58;   // 需容納兩模組堆疊（驗證腳本會檢查）
SCD41_W     = 25;    SCD41_D = 21;     // GY-SCD41 模組（估值，請實測）
SHT31_W     = 18;    SHT31_D = 14;     // GY-SHT31-D 模組（估值，請實測）
// 背面掛耳：M4×2 鎖到底座前壁。厚度與高度要吃得住 M4 的鎖緊力，
// 孔緣到耳邊至少留 M4_HEAD_D/2，否則鎖下去會把耳朵撕開。
// ★掛耳必須橫跨整個背面開口★ 背面是全開的，中央一小片掛耳沒有任何
//   東西可以接——會變成浮空的獨立實體（CGAL Volumes 會從 2 變 3）。
//   所以做成一條橫樑，兩端埋進側壁、上緣埋進頂壁，三面都咬住。
POD_EAR_T     = 5;                     // 掛耳厚（M4 通孔穿過）
POD_EAR_H     = 14;                    // ≥ M4_HEAD_D + 2×壁厚
POD_EAR_PITCH = 20;                    // 兩孔間距
POD_EAR_EMBED = 1;                     // 埋進側壁／頂壁的深度（確保實體相交而非共面）
POD_EAR_W     = POD_W - WALL * 2 + POD_EAR_EMBED * 2;
POD_EAR_X     = WALL - POD_EAR_EMBED;
POD_EAR_Z     = POD_H - FLOOR + POD_EAR_EMBED - POD_EAR_H;
// 前面通風槽的 x 位置。定位肋佔用的 x 區間（艙寬 62、中心 31）：
//   SCD41 肋 15.2–18.2、43.8–46.8　｜　SHT31 肋 18.7–21.7、40.3–43.3
// 剩下的淨空帶：2.4–15.2 / 21.7–40.3 / 46.8–59.6，槽只能開在這三帶裡。
// 槽寬 3.5，所以中心距肋緣至少要 1.75+1.2。★驗證腳本 L 會檢查★
POD_VENT_X    = [9, 25, 31, 37, 53];

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

// 螺柱座（含自攻底孔）。pilot 依板子自己的孔徑給，不是統一值。
module standoff(h = STANDOFF_H, pilot = M3_PILOT) {
    difference() {
        cylinder(h = h, d = standoff_od(pilot));
        translate([0, 0, -0.1]) cylinder(h = h + 0.2, d = pilot);
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
// ★2026-08-02 重寫★ 原本掛耳與模組卡槽都寫在 difference() 的 union() 裡，
//   但內部挖空 rrect(..., POD_D - WALL, ...) 從 y=WALL 一路開到 y=POD_D
//   （背面全開），把落在那個範圍內的掛耳與卡槽★整個吃掉★——
//   算出來的仍是合法實體，Volumes=2、watertight、參數檢查全過，
//   但功能特徵根本不存在：艙體鎖不上底座，感測器也沒東西夾。
//   （是把零件單獨算繪出來看背面才發現的，數值檢查一項都沒響。）
//   修法：挖空只作用在「殼」上，掛耳與定位肋在挖空之後才 union 進來。
module pod_ear() {
    difference() {
        cube([POD_EAR_W, POD_EAR_T, POD_EAR_H]);
        for (dx = [-1, 1])
            translate([POD_EAR_W / 2 + dx * POD_EAR_PITCH / 2, -0.1, POD_EAR_H / 2])
                rotate([-90, 0, 0])
                    cylinder(h = POD_EAR_T + 0.2, d = M4_CLEAR);
    }
}

// 模組定位肋：兩側各一道，夾住 PCB 的左右邊緣。
// ★不做成封閉滑槽★ 兩個理由：
//   1) 艙內高度不夠讓 PCB 從上往下滑進槽裡（上方只剩 8mm，板高 14mm）
//   2) 不需要——背面開放，PCB 由背面推入貼著前壁；
//      感測器艙鎖上底座後，底座前壁就是後擋板，把 PCB 壓住
// 肋條一路從艙底（FLOOR）長上來，不從半空開始，否則第一層無支撐。
POD_RIB_W = 3;    // 肋在 x 方向的厚度
POD_RIB_D = 4;    // 肋離前壁內面的深度（＞板厚，才夾得住）
module pod_rails(pcb_w, z0, z_len) {
    span = pcb_w + FIT * 2;
    top  = z0 + z_len;
    for (dx = [-1, 1]) {
        A  = POD_W / 2 + dx * (span / 2);        // PCB 的左／右邊緣
        rx = dx > 0 ? A : A - POD_RIB_W;         // 肋條一律長在 PCB 外側
        // 上擋／下擋：★只在肋條上做往內伸 2mm 的小凸耳，不做橫跨整寬的擋片★
        //   橫跨整寬的擋片會壓在前壁的通風槽上——驗證 L 抓到的就是這個：
        //   兩道擋片共擋掉 115mm³，等於把中間三道槽各截去 2mm 高度。
        //   凸耳只佔 PCB 兩側角落，通風槽的視線完全不受影響。
        // ★凸耳必須埋進肋條 1mm★ 只靠邊對邊接觸會產生非流形邊
        //   （Simple=no，切片器直接拒收）——這也踩過一次。
        tx = dx > 0 ? A - 2 : A - 1;
        translate([rx, WALL, FLOOR])
            cube([POD_RIB_W, POD_RIB_D, top + 2 - FLOOR]);
        translate([tx, WALL, top]) cube([3, POD_RIB_D, 2]);
        if (z0 > FLOOR + 0.01)       // z0 就在艙底時，艙底本身就是落座面
            translate([tx, WALL, z0 - 2]) cube([3, POD_RIB_D, 2]);
    }
}

module sensor_pod() {
    union() {
        difference() {
            rrect_chamfered(POD_W, POD_D, POD_H, 5);

            // 內部挖空（背面開放，方便置入模組與走線）
            // 背面加 OVER，不讓切面停在與外殼共平面的位置（見檔頭 OVER 說明）。
            translate([WALL, WALL, FLOOR])
                rrect(POD_W - WALL * 2, POD_D - WALL + OVER, POD_H - FLOOR * 2,
                      5 - WALL);

            // 前面通風柵格——感測器必須接觸到外界空氣才量得準。
            // ★x 位置必須避開背面的定位肋★ 肋條貼在前壁內面，
            //   壓在槽上就等於把槽封死：外面看得到孔，裡面其實不通氣。
            //   （原本 5 槽等距 pitch=8，正好被兩對肋壓住兩槽）
            for (vx = POD_VENT_X)
                translate([vx, -0.5, POD_H / 2]) rotate([-90, 0, 0])
                    vent_slots(1, 3.5, 26, 0, WALL + 1);
        }

        // 背面掛耳（M4 鎖到底座前壁的螺柱上）——★必須在挖空之後★
        // 用外輪廓 intersection 修邊，橫樑才不會從圓角處凸出去。
        intersection() {
            translate([POD_EAR_X, POD_D - POD_EAR_T, POD_EAR_Z]) pod_ear();
            rrect(POD_W, POD_D, POD_H, 5);
        }

        // 模組定位肋（下 SCD41、上 SHT31）——★同樣必須在挖空之後★
        pod_rails(SCD41_W, FLOOR, SCD41_D + FIT * 2);
        pod_rails(SHT31_W, FLOOR + SCD41_D + FIT * 2 + 8, SHT31_D + FIT * 2);
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
    // ★爐面「條紋狀」的來源就在這兩行★
    //   1) alpha=0.55 的半透明：OpenSCAD 預覽（F5／OpenCSG）不做深度排序，
    //      圓柱的每一個面片以任意前後順序疊合 → 橫向色帶
    //   2) $fn=48 在 Ø110 上每片弦長 7.2mm，掠射角看過去就是一圈階梯
    //   兩者都只是顯示問題，實體幾何是乾淨的（檢查 G：Volumes=2、Simple=yes）。
    //   預設改成不透明＋高細分；要看內部時用 -D BOWL_ALPHA=0.4，
    //   但看到的條紋是預覽假影，不是模型壞掉。
    translate([BASE_W / 2, BASE_D / 2, BASE_H + CHMB_H - BOWL_H + explode])
        color("#b9bec4", BOWL_ALPHA)
            difference() {
                cylinder(h = BOWL_H, d = BOWL_D, $fn = 160);
                translate([0, 0, 1.5]) cylinder(h = BOWL_H, d = BOWL_D - 3, $fn = 160);
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

// ── 開口「內側」的貫通檢查 ────────────────────────────────────
// clearance_zone 問的是「開口外面有沒有被別的零件擋住」；
// throughway 問的是★開口本身到底有沒有通★——
// 探針從外面穿過開口伸進內腔，跟零件★自己★求交集，體積必須 ≈ 0。
//
// 這抓得到兩種現有檢查全都放行的錯，兩種都真的踩過：
//   1) 挖空的終點與外表面共面，CGAL 不保證切穿 → 開口其實是封死的。
//      Volumes=2 過（封起來仍是合法單一實體）、參數檢查過（尺寸都對）、
//      F5 預覽看起來還是開的（OpenCSG 容忍共平面），只有 F6／STL 才現形。
//      —— 集煙罩投香口中過一次。已用「在投香口貼 0.4mm 薄膜」做負向測試：
//         L 抓到 2,328mm³，而 G/J/K 全數放行。
//   2) 開口通了，但內側被自己的肋條／螺柱壓住 → 外面看得到孔，裡面不通氣。
//      —— 這一項是 L 上線當天就抓到的：感測器艙的上下擋片橫跨通風槽，
//         擋掉 115mm³（中間三道槽各被截去 2mm 高度）。
module throughway(name) {
    if (name == "hood_opening")          // 投香口：由上方伸進罩內
        translate([BASE_W / 2, BASE_D / 2, BASE_H + CHMB_H + HOOD_H - 20])
            cylinder(h = 25, d = HOOD_TOP_W - WALL * 2 - 4);
    else if (name == "pod_back")         // 感測器艙背面（要開放才裝得進模組與走線）
        translate([BASE_W / 2 - POD_W / 2 + 10, -8, BASE_H - POD_H + 3])
            cube([POD_W - 20, 11, 35]);
    else if (name == "pod_vent")         // 每一道通風槽，由外面戳進內腔
        for (vx = POD_VENT_X)
            translate([BASE_W / 2 - POD_W / 2 + vx - 1.2, -POD_D - 2,
                       BASE_H - POD_H - 2 + POD_H / 2 - 9])
                cube([2.4, 2 + WALL + POD_RIB_D + 1, 18]);
}

module obstructed(zone, owner) {
    intersection() { throughway(zone); placed(owner); }
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
    else if (part == "obstructed")   obstructed(PAIR_A, PAIR_B);  // 開口有沒有真的通
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