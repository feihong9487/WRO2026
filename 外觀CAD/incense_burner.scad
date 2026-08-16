/* =============================================================================
 * 智慧香爐 — 桌上型展示機外觀（參數化 CAD）
 * =============================================================================
 * 用途：WRO 2026 競賽展示用的完整香爐，含燃燒艙、集煙罩、抽風道與電子艙。
 * 製造：FDM 3D 列印（分件列印後組裝）
 *
 * 開啟方式：OpenSCAD（免費，openscad.org）→ F5 預覽 → F6 算繪 → 匯出 STL
 *
 * -----------------------------------------------------------------------------
 * 檔案結構（2026-08-06 由單一檔案拆分）
 * -----------------------------------------------------------------------------
 *   params.scad          所有尺寸——★唯一真相來源★
 *   common.scad          圓角方柱、倒角、柵格、螺柱、定位榫
 *   parts/ 底下          5 個列印件，一個零件一個檔（可單獨開）
 *   components/ 底下     外購件模型（板卡、風扇、感測器、爐盆）★尺寸多為估值★
 *   本檔                 組裝定位 place()、組合件、驗證用模組、輸出分派
 *   STEP/                匯出的 STEP（由 export_step.py 產生，供 Onshape 匯入）
 *
 * 零件檔用 use<> 而非 include<>：use 只帶進模組、不執行對方的頂層敘述，
 * 所以零件檔可以自帶一行預覽呼叫，單獨開檔看得到，又不會污染組合件。
 *
 * ★檔名一律 ASCII★ Windows 版 OpenSCAD 的 include/use 路徑不吃中文。
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
// 相依檔案
// ═══════════════════════════════════════════════════════════════════════════
// include：帶進變數（參數）與模組——組裝定位自己也要用到這些尺寸
include <common.scad>

// use：只帶進模組，不執行零件檔尾端的預覽呼叫
use <parts/base.scad>
use <parts/chamber.scad>
use <parts/hood.scad>
use <parts/fan_mount.scad>
use <parts/sensor_pod.scad>

// 外購元件（非列印件）。★尺寸多為估值，見各檔開頭★
use <components/bowl.scad>
use <components/matrix_r4.scad>
use <components/pi5.scad>
use <components/d4184.scad>
use <components/blower_5015.scad>
use <components/sensors.scad>
use <components/max6675.scad>
use <components/mist_led.scad>

// ═══════════════════════════════════════════════════════════════
// 組裝定位
// ═══════════════════════════════════════════════════════════════
// ★所有零件的擺放位置集中在 place()★
//   assembly() 與干涉檢查共用同一組變換——這是單一真相來源。
//   若分開寫，改了組裝卻忘了改檢查，干涉檢查就會驗到錯的位置。

PARTS_LIST = ["base", "chamber", "hood", "fan_mount", "sensor_pod"];
PART_COLOR = ["#5b6670", "#8b6f47", "#a8825c", "#3f4a52", "#2f6f5a"];

// 外購元件——不列印，但要佔位置。★把它們畫出來才驗得到「裝得下、鎖得到」★
// 沒有它們的時候，干涉檢查只檢查殼跟殼，等於默認「裡面一定塞得下」。
COMP_LIST = ["bowl", "matrix_r4", "pi5", "d4184",
             "blower", "scd41", "sht31", "max6675", "tc_probe",
             "mist", "hood_led"];

// 風扇座定位計算（外掛在燃燒艙後方）
FAN_BODY_T   = FAN_T + WALL * 2;                  // 本體厚
FAN_FLANGE_H = 10;                                // 煙道法蘭高
FAN_PENETR   = 4;                                 // 法蘭插入燃燒艙後壁的深度
CHMB_BACK_Y  = (BASE_D - CHMB_D) / 2 + CHMB_D;    // 燃燒艙後壁外緣

module part_by_name(name) {
    // 列印件
    if      (name == "base")       base();
    else if (name == "chamber")    chamber();
    else if (name == "hood")       hood();
    else if (name == "fan_mount")  fan_mount();
    else if (name == "sensor_pod") sensor_pod();
    // 外購元件
    else if (name == "bowl")       bowl();
    else if (name == "matrix_r4")  matrix_r4();
    else if (name == "pi5")        pi5();
    else if (name == "d4184")      d4184();
    else if (name == "blower")     blower_5015();
    else if (name == "scd41")      scd41();
    else if (name == "sht31")      sht31();
    else if (name == "max6675")    max6675_board();
    else if (name == "tc_probe")   tc_probe();
    else if (name == "mist")       mist_module();
    else if (name == "hood_led")   hood_led();
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

    // ── 外購元件 ────────────────────────────────────────────
    // ★沿用同一組 place()★ 這樣元件的定位與組合件、干涉檢查永遠一致；
    //   另外寫一份就會有「組裝圖對、檢查驗錯位置」的經典錯誤。
    else if (name == "mist")
        // 泡在爐盆底部的水裡（壓電片要沒入水中，建議水位 MIST_WATER_MM）
        translate([BASE_W / 2, BASE_D / 2,
                   BASE_H + CHMB_H - BOWL_H + BOWL_WALL + explode]) children();
    else if (name == "hood_led")
        // 貼在集煙罩直筒段內側前壁，側向打光——霧被側光打亮時可見度差好幾倍
        // （漏斗改版後直筒段牆面垂直，直接貼壁即可，不再有錐面內縮量）
        translate([BASE_W / 2,
                   (BASE_D - CHMB_D) / 2 + WALL + HOODLED_T / 2,
                   BASE_H + CHMB_H + 16 + explode]) children();
    else if (name == "bowl")
        translate([BASE_W / 2, BASE_D / 2, BASE_H + CHMB_H - BOWL_H + explode])
            children();
    else if (name == "matrix_r4")
        translate([14, 14, FLOOR + STANDOFF_H - explode]) children();
    else if (name == "pi5")
        translate([14, BASE_D - 14 - PI_D, FLOOR + STANDOFF_H - explode]) children();
    else if (name == "d4184")
        translate([BASE_W - 20 - D4184_W, 20, FLOOR + STANDOFF_H - explode]) children();
    else if (name == "blower")
        // 裝進風扇座的凹槽。鏡射 z 讓軸向進氣面朝向煙道那一側。
        place("fan_mount", explode)
            translate([WALL, WALL, WALL + FAN_T]) mirror([0, 0, 1]) children();
    else if (name == "scd41")
        // 立起來夾在定位肋之間，感測器本體朝向前面的通風槽
        place("sensor_pod", explode)
            translate([POD_W / 2 - SCD41_W / 2, POD_Y_SCD + SCD41_T, FLOOR])
                rotate([90, 0, 0]) children();
    else if (name == "sht31")
        place("sensor_pod", explode)
            translate([POD_W / 2 - SHT31_W / 2, WALL + SHT31_T,
                       FLOOR + SCD41_D + FIT * 2 + 8])
                rotate([90, 0, 0]) children();
    else if (name == "max6675")
        translate([120, 70, FLOOR + STANDOFF_H - explode]) children();
    else if (name == "tc_probe")
        // ★這是「應該在哪」，不是「已經固定在哪」★
        //   交接文件要求探頭懸於爐面上方 TC_TIP_ABOVE_BOWL，
        //   但目前★沒有任何零件提供這個支架★——畫出來就是要讓它顯眼。
        //   探頭尖端朝下、位於指定高度，本體往上延伸（真實安裝一定是吊掛式，
        //   不可能從爐盆底下穿上來）。
        //   ★不納入干涉／淨空檢查★（見 驗證CAD.py 的 COMP_NO_CHECK）：
        //   它沒有支架，位置只是規格上的目標，拿它去驗會驗到不存在的東西。
        translate([BASE_W / 2, BASE_D / 2,
                   BASE_H + CHMB_H + TC_TIP_ABOVE_BOWL + explode])
            rotate([180, 0, 0]) children();
}

module placed(name, explode = 0) { place(name, explode) part_by_name(name); }

module assembly(explode = 0, with_components = true) {
    for (i = [0 : len(PARTS_LIST) - 1])
        color(PART_COLOR[i]) placed(PARTS_LIST[i], explode);
    if (with_components)
        for (c = COMP_LIST) placed(c, explode);
}

// 只有列印件的組合件（看外觀用）
module shell_only(explode = 0) { assembly(explode, false); }



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
    if (name == "hood_opening")
        // ★2026-08-16 改回全口徑探針★ 理香機構移除後，投香口就是一個
        //   向上開的漏斗大口，香直接插進爐盆——要驗的回到「口是通的」。
        //   探針從罩頂上方沿軸線伸進罩內（穿過喇叭段進到直筒段），
        //   與集煙罩自身求交集必須 ≈ 0；共面退化薄膜或任何殘留頂蓋
        //   都會被抓到。直徑比直筒內寬（151.2）小 40mm，留餘量給圓角。
        translate([BASE_W / 2, BASE_D / 2, BASE_H + CHMB_H + HOOD_H - 20])
            cylinder(h = 40, d = CHMB_W - WALL * 2 - 40);
    else if (name == "pod_back")         // 感測器艙背面（要開放才裝得進模組與走線）
        // ★探針起點由「最後一排定位肋的背面」推導，不是手調的數字★
        //   肋條是刻意存在的結構，探針若壓在肋上，量到的是設計本身而不是缺陷
        //   （2026-08-06 第一版就是這樣誤報 240mm³）。
        //   這裡驗的是「肋之後到艙外確實是通的」；
        //   至於「肋之後還剩多少走線深度夠不夠」，另外由 驗證CAD.py 的 C 規則管，
        //   不靠探針隱含——把要求寫成規則，才不會下次改肋深時無聲失效。
        translate([BASE_W / 2 - POD_W / 2 + 10,
                   -POD_D + POD_Y_SHT + POD_RIB_D_SHT + 1,
                   BASE_H - POD_H + 3])
            cube([POD_W - 20, POD_D - (POD_Y_SHT + POD_RIB_D_SHT) + 2, 35]);
    else if (name == "pod_vent")         // 每一道通風槽，由外面戳進內腔
        for (vx = POD_VENT_X)
            translate([BASE_W / 2 - POD_W / 2 + vx - 1.2, -POD_D - 2,
                       BASE_H - POD_H - 2 + POD_H / 2 - 9])
                cube([2.4, 2 + WALL + POD_RIB_D_SCD + 1, 18]);
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
    else if (part == "probe")        throughway(PAIR_A);          // ★探針自己★（防檢查空轉）
    else if (part == "shell")        shell_only(0);               // 只有列印件
    else if (part == "component")    placed(PAIR_A);              // 定位後的單一元件
    else if (part == "solo")         part_by_name(PAIR_A);        // 未定位的單一零件／元件
    else if (part == "none")         ;                          // 供 include 時不算繪
    // ★不要靜默退回組合件★ 打錯名字時退回 assembly 是「算得出東西、
    //   但算的是別的東西」——2026-08-06 匯出 STEP 時踩到：元件名稱在這裡
    //   沒有對應分支，於是每個元件都在算整台組合件，一個爐盆跑了十幾分鐘。
    else                             assert(false, str("未知的 part：", part,
                                             "（單件請用 solo/placed ＋ PAIR_A）"));
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
