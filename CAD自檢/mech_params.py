#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧香爐 — 機構設計參數（唯一真相來源）
=============================================================
所有機構尺寸集中於此。Onshape 的 Variable Studio 應填入相同數值，
STL 匯出後由 verify_stl.py 回頭核對，形成閉環。

★ 單位一律 mm（除非欄位名另有標示）★

★ MEASURED 旗標的意義 ★
  False = 此數值目前是估計值，尚未實測。test_mech_design.py 會把它標為待辦。
  量到真值後改成 True 並更新數值——在那之前，任何基於它的結論都只能稱「設計目標」。
  （對應《實作交接文件》§5.5 誠實一致性）
"""

from dataclasses import dataclass, field
from typing import List

# =============================================================
# 材料
# =============================================================

@dataclass(frozen=True)
class Material:
    name: str
    density_g_cm3: float
    max_service_temp_c: float      # 連續使用溫度上限
    ferromagnetic: bool = False

PLA   = Material("PLA",   1.24, 60.0)     # 60°C 軟化 —— 交接文件 §5.1
PETG  = Material("PETG",  1.27, 80.0)
ALU   = Material("鋁",     2.70, 400.0)
STEEL = Material("碳鋼",   7.85, 400.0, ferromagnetic=True)

# 近爐熱區的定義：此溫度以上的區域禁用 PLA
HOT_ZONE_TEMP_C = 60.0
# 爐面附近預估溫度（用於判定禁 PLA 區）
NEAR_CENSER_TEMP_C = 120.0
NEAR_CENSER_TEMP_MEASURED = False        # ← 待熱電偶實測

# =============================================================
# 香爐本體（借用的實體香爐，必須實地量測）
# =============================================================

CENSER_INNER_DIA = 260.0        # 爐口內徑
CENSER_DEPTH     = 150.0        # 爐內深度
CENSER_MEASURED  = False        # ← 待量測

# =============================================================
# 線香（市售通用規格 —— 可普及性前提）
# =============================================================

INCENSE_SHAFT_DIA_MAX = 3.5     # 香枝最粗直徑（含竹芯）
INCENSE_SHAFT_DIA_MIN = 1.5
INCENSE_MEASURED      = False   # ← 待實地蒐集數種市售香量測

# =============================================================
# 導正套筒（鐵磁，磁路的實際作用對象 —— 交接文件 §5.4）
# =============================================================

SLEEVE_OUTER_DIA   = 10.0       # 鋁管外徑（BOM：鋁管 8-10mm）
SLEEVE_INNER_DIA   = 8.0        # 內徑，供香枝穿過
SLEEVE_LENGTH      = 40.0
SLEEVE_WALL        = (SLEEVE_OUTER_DIA - SLEEVE_INNER_DIA) / 2
SLEEVE_MATERIAL    = ALU        # 管身鋁（耐熱）
SLEEVE_FERRO_RING  = STEEL      # 鐵墊圈提供磁性（BOM：鋁管＋鐵墊圈）
SLEEVE_RING_MASS_G = 4.0        # 鐵墊圈質量（估）
SLEEVE_RING_MEASURED = False    # ← 待量測
# 套筒是外購鋁管，不是 3D 列印件——列印最小特徵規則不適用於它
SLEEVE_IS_PRINTED  = False

# 套筒在插孔板中滑動所需的單邊間隙
SLEEVE_SLIDE_CLEARANCE = 0.4
MIN_SLIDE_CLEARANCE    = 0.2    # 低於此會卡死（3D 列印公差）

# =============================================================
# 插孔板（P3 里程碑主件）
# =============================================================

PLATE_MATERIAL   = PETG         # ★ 禁 PLA 區 —— 交接文件 §5.1
PLATE_DIA        = 240.0        # 需小於爐口內徑並留安裝間隙
PLATE_THICKNESS  = 6.0
PLATE_HOLE_COUNT = 4            # PoC：2×2 磁力矩陣（升級選單 U4）
PLATE_HOLE_DIA   = SLEEVE_OUTER_DIA + 2 * SLEEVE_SLIDE_CLEARANCE
PLATE_HOLE_PITCH = 40.0         # 孔中心距
PLATE_EDGE_MARGIN = 15.0        # 最外側孔中心到板緣

# 列印與結構限制
MIN_WALL_BETWEEN_HOLES = 3.0    # 孔間最小材料厚度
MIN_PRINTABLE_FEATURE  = 1.2    # 3D 列印可靠成形的最小特徵
PLATE_CENSER_CLEARANCE = 10.0   # 板緣到爐壁的最小總間隙

# =============================================================
# 磁力矩陣（單格理香 PoC）
# =============================================================

MAGNET_COUNT       = 2          # 現行 BOM：電磁鐵 ×2（U4 升級到 4 顆做 2×2）
MAGNET_FORCE_N     = 20.0       # 12V 20N（規格書標稱）
MAGNET_DIA         = 25.0
MAGNET_PITCH       = PLATE_HOLE_PITCH
MAGNET_AIR_GAP     = 3.0        # 電磁鐵面到鐵墊圈的氣隙
MAGNET_MAX_AIR_GAP = 5.0        # 超過此距離吸力衰減過大
MAGNET_FORCE_MEASURED = False   # ← 標稱值非實測，待拉力計驗證
MAGNET_STROKE      = 8.0        # 理香需要的套筒位移量

# 摩擦與重力估算（判斷 20N 是否夠用）
SLEEVE_TOTAL_MASS_G = 12.0      # 鋁管＋鐵墊圈（估）
FRICTION_COEFF      = 0.4       # 鋁—PETG 靜摩擦（估）
GRAVITY             = 9.81

# =============================================================
# 過濾鏈（順序即安全 —— 交接文件 §5.3）
# =============================================================

# 氣流方向由前到後，順序不可調換：金屬紗網必須在 HEPA 之前擋火星
FILTER_CHAIN: List[str] = ["金屬紗網", "HEPA", "活性碳濾棉"]

DUCT_INNER_DIA = 50.0           # PVC 集煙管內徑
FAN_MODEL      = "5015 鼓風扇 12V"
FAN_COUNT      = 2

# =============================================================
# 禁 PLA 區宣告（近爐熱區）
# =============================================================

@dataclass(frozen=True)
class Part:
    name: str
    material: Material
    near_censer: bool           # 是否位於近爐熱區
    mass_g: float = 0.0
    notes: str = ""

PARTS: List[Part] = [
    Part("插孔板", PLATE_MATERIAL, near_censer=True,
         notes="禁 PLA 區；或以隔熱墊高"),
    Part("導正套筒管身", ALU, near_censer=True,
         notes="鋁管，直接接觸高溫"),
    Part("導正套筒鐵墊圈", STEEL, near_censer=True,
         notes="磁路作用對象"),
    Part("電磁鐵支架", PETG, near_censer=False,
         notes="位於爐體外側下方"),
    Part("感測器外殼", PLA, near_censer=False,
         notes="呼吸高度，遠離爐面"),
]

# =============================================================
# 材料預算（升級選單 U3：PETG 線材 1kg）
# =============================================================

PETG_SPOOL_G = 1000.0
PRINT_INFILL = 0.35             # 填充率，用於估算實際用料

# =============================================================
# 跨層介面參數（2026-08-02 新增，供 test_integration.py 使用）
# =============================================================
# 這一區的存在理由：機構、韌體、電控三者各有參數檔，
# 彼此矛盾時沒有任何單一領域的檢查抓得到。以下數值是「介面契約」。

# ── 與韌體的介面（R4/matrix_mini_r4/matrix_mini_r4.ino）──
FIRMWARE_INO = "../R4/matrix_mini_r4/matrix_mini_r4.ino"
FIRMWARE_FAN_CHANNELS = 1        # 韌體目前只驅動 1 路 PWM（PIN_FAN）

# ── 感測器耐受度（決定安裝位置，非近爐即可的布林判斷）──
SCD41_MAX_OP_TEMP_C = 60.0       # Sensirion SCD4x 工作溫度上限
SHT31_MAX_OP_TEMP_C = 125.0      # SHT3x 工作溫度上限（讀值精度另計）
SENSOR_ZONE_TEMP_C  = 35.0       # 感測器艙預估溫度（前方、遠離爐面）
SENSOR_ZONE_TEMP_MEASURED = False  # ← 待實測

# ── 電源預算（12V 匯流排）──
PSU_VOLTAGE_V   = 12.0
PSU_CURRENT_A   = 3.0            # BOM：12V 3A（2026-08-07 決定，搭配電磁鐵互鎖）
# ★3A 是「搭配互鎖」才夠★ 若拿掉互鎖讓兩顆電磁鐵同時吸，
#   峰值 2.50A 會超過 3A×80%＝2.40A 的可用量——那時要換 4A。
MAGNET_CURRENT_A = 0.5           # 電磁鐵每顆估計電流（12V 20N 常見值）
MAGNET_CURRENT_MEASURED = False  # ← 待實測（標稱吸力不等於標稱電流）
FAN_CURRENT_A    = 0.2           # 5015 每顆
CTRL_CURRENT_A   = 0.5           # MATRIX Mini R4 板子本身
PSU_MARGIN       = 0.8           # 電源使用率上限（留 20% 餘裕）

# ── ★現行建置 vs 完整設計★ ────────────────────────────────
# MAGNET_COUNT / FAN_COUNT 描述的是「完整廟宇爐」（P3）。
# 桌上型展示機（目前的 P0/P1）實際掛在 12V 上的只有控制器與 1 顆風扇——
# 電磁鐵根本還沒有，電路圖上也沒有。
#   佐證：電路設計/kicad/佈線定義.py 只有一個 Fan-5015、沒有任何電磁鐵，
#         且 +12V 只出現在 MATRIX R4 的 VIN 與 D4184 的 VIN+ 兩處。
# 兩者混為一談的後果是「用未來的負載去判現在的電源夠不夠」——
# 結論會是錯的，而且方向還相反：現況其實很寬裕。
FAN_COUNT_NOW    = 1             # 與 佈線定義.py 一致（跨層規則會比對）
MAGNET_COUNT_NOW = 0             # 磁力矩陣屬 P3，尚未進電路

# 無刷風扇的啟動突波倍率。★這才是這條匯流排真正的暫態★——
# 直流電磁鐵是電阻電感負載，電流是往 V/R 指數上升、不會過衝，沒有湧入問題；
# 會有大啟動電流的是馬達（風扇）與電容性負載。
FAN_STARTUP_FACTOR = 2.5         # ★估值，未實測★
FAN_STARTUP_MEASURED = False

# ── 電磁鐵互鎖（2026-08-07 決定）────────────────────────────
# 一次只准吸一顆。這不是韌體的實作細節，是★電源預算依賴的設計約束★：
#   有互鎖：峰值 2.00A ≤ 3A×80%＝2.40A ✓
#   無互鎖：峰值 2.50A ＞ 2.40A ✗（那就得換 4A）
# 所以互鎖一旦沒做，電源就不夠——這個相依關係必須被追蹤，不能只寫在註解裡。
MAGNET_SIMULTANEOUS_MAX = 1
MAGNET_INTERLOCK_IMPLEMENTED = False   # ← P3 韌體做出互鎖後才可改 True

# ── 過濾鏈壓損（決定風扇選型是否足夠）──
# 5015 鼓風扇靜壓有限，三段過濾串聯的壓損不可忽視
FILTER_PRESSURE_DROP_PA = {"金屬紗網": 5.0, "HEPA": 120.0, "活性碳濾棉": 40.0}
FAN_STATIC_PRESSURE_PA  = 250.0  # 5015 標稱靜壓（估，待實測）
FAN_PRESSURE_MEASURED   = False  # ← 待實測

# ── 熱電偶安裝 ──
# ★依《智慧香爐_硬體設計交接》§7：「熱電偶懸於爐面上方 2–3 cm」★
#   2026-08-02 更正：先前誤填「爐盆外壁」，那是我自行假設的，非設計文件內容。
#   兩者量到的溫度不同——懸空量的是煙氣/輻射，貼壁量的是金屬傳導。
#   ⚠️ 外觀CAD/incense_burner.scad 目前的熱電偶穿線孔是「貼爐盆外壁」設計，
#      與本文件不一致，需擇一（見 test_integration 的卡關回報）。
TC_MOUNT_LOCATION  = "爐面上方 2-3 cm（懸空）"
TC_MOUNT_HEIGHT_MM = 25.0         # 交接文件 §7：2–3 cm
TC_LOCATION_TEMP_C = 120.0        # 該位置預估溫度（＝NEAR_CENSER_TEMP_C，未實測）

# ── 聯鎖門檻（與韌體同步，2026-08-02 決策 B）──
# 原 80/60 低於熱電偶位置的預估工作溫度，正常燃燒就會鎖死風扇。
# 依使用者決策提高為 150/130，但這是【臨時值】：
#   T_LOCK    150 = 預估常態 120 ＋ 30°C 餘裕
#   T_RELEASE 130 = 高於預估常態，聯鎖後回到常態即可解除
# 一旦 NEAR_CENSER_TEMP_MEASURED 轉 True，必須重新檢視這兩個值。
INTERLOCK_LOCK_C    = 150.0
INTERLOCK_RELEASE_C = 130.0
T_LOCK_PROVISIONAL  = True        # ← 實測並重定門檻後改 False

# ── 螺絲規格（2026-08-02 使用者指定：鎖固一律 M4）──
# 例外只有一類：★板卡鎖到殼上★。孔徑是外購板自己的孔，不在我們的圖上，
# M4 桿徑 4.0mm 物理上穿不過去。擴孔會削掉板邊銅箔與接地層，不做。
# 這裡把每個例外的板孔徑一併記下來，test_integration 會逐一驗證
# 「例外是被孔徑逼出來的」，而不是因為 M3 比較好買就退回去。
M4_SHANK_MM = 4.0
SCREW_BOARD_EXEMPT = {
    "Raspberry Pi 5":  ("M2.5", 2.7),   # 官方機構圖
    "MATRIX Mini R4":  ("M3",   3.2),   # UNO 相容孔位
    "D4184 MOSFET 模組": ("M3",  3.0),   # 常見規格，★請實測★
}

# =============================================================
# 里程碑範圍（2026-08-02）
# =============================================================
# 《智慧香爐_硬體設計交接》描述的是完整設計；目前實作只做核心子集。
# 這個宣告讓驗證可以分別跑「現在要做的」與「設計好但還沒做的」，
# 而不是把未來的設計衝突混進當前的自檢結果裡。
#
# ★ 這不是略過測試 ★ 預設仍跑全部；--scope core 只是換個視角看同一組規則。

MILESTONE = "P0/P1"   # 目前：核心感測與致動鏈路

SCOPE_CORE = {
    # R4（MATRIX Mini R4）＋ Pi 5 ＋ SHT31 ＋ SCD41 ＋ 5015 風扇 ＋ MAX6675 熱電偶 ＋ 雲端監測
    "test_熱電偶聯鎖門檻必須高於該位置的預估工作溫度",
    "test_聯鎖解除門檻需低於觸發門檻且有足夠遲滯",
    "test_SCD41安裝位置溫度不可超過其工作上限",
    "test_感測器不可裝在煙道或近爐區",
    "test_韌體驅動路數需涵蓋機構規劃的風扇數量",
    "test_S2高峰duty需明顯高於S1常態",
    "test_安全狀態必須停止致動",
    "test_外觀CAD的近熱區必須有空氣間隙",
    "test_煙道截面在機構與外觀CAD之間需相容",
    "test_桌上型展示機與廟宇實體爐的尺度需標明差異",
    "test_列出尚未實測的項目",
    "test_列出跨層待實測項目",
    "test_韌體聯鎖門檻需與參數檔同步",
    "test_臨時安全門檻必須被標記",
    "test_鎖固一律使用M4且例外必須有物理理由",
    "test_現行配置的12V電流須在電源餘裕內",
    "test_現行風扇數需與電路圖一致",
    "test_電源預算依賴的設計約束不可被遺忘",
    "test_列出電源預算的待辦約束",
}

SCOPE_LATER = {
    "test_完整設計的12V峰值須在電源餘裕內",
    # P3 機構：插孔板、導正套筒、磁力矩陣、過濾鏈
    # 已完成設計但尚未進入實作，其參數多為估計值
    "test_近爐區絕對不可使用PLA", "test_近爐零件的耐熱溫度必須高於熱區溫度",
    "test_套筒管身必須耐得住近爐溫度", "test_磁路作用對象必須是鐵磁材料",
    "test_套筒管身本身不需要導磁", "test_孔徑必須容納套筒並保留滑動間隙",
    "test_孔間壁厚足夠支撐", "test_所有特徵大於列印最小尺寸",
    "test_插孔板必須放得進香爐", "test_孔位陣列不可超出板面",
    "test_套筒長度需大於板厚才能導正", "test_套筒內徑容得下最粗的市售香",
    "test_電磁鐵吸力需大於驅動套筒所需力", "test_氣隙不可超過有效吸附距離",
    "test_電磁鐵間距需與孔距一致", "test_電磁鐵直徑不可大於孔距造成干涉",
    "test_行程需小於套筒長度", "test_金屬紗網必須在HEPA之前",
    "test_活性碳在HEPA之後", "test_插孔板用料不超過一卷PETG",
    "test_近爐零件耐熱須高於熱電偶位置溫度",
    "test_風扇靜壓需大於過濾鏈壓損",
    "test_12V匯流排電流不可超過電源供給",   # 含電磁鐵，屬 P3
    "test_電磁鐵吸力餘裕在實測前不可寫進報告結論",
}

# =============================================================
# 便利函數
# =============================================================

def hole_edge_to_edge() -> float:
    """相鄰兩孔之間剩下的材料厚度。"""
    return PLATE_HOLE_PITCH - PLATE_HOLE_DIA


def plate_volume_mm3() -> float:
    """插孔板實體體積（扣除通孔），供用料估算與 STL 比對。"""
    import math
    disc = math.pi * (PLATE_DIA / 2) ** 2 * PLATE_THICKNESS
    holes = PLATE_HOLE_COUNT * math.pi * (PLATE_HOLE_DIA / 2) ** 2 * PLATE_THICKNESS
    return disc - holes


def plate_print_mass_g() -> float:
    """含填充率的預估列印質量。"""
    return plate_volume_mm3() / 1000.0 * PLATE_MATERIAL.density_g_cm3 * PRINT_INFILL


def sleeve_required_force_n() -> float:
    """驅動套筒所需的最小力＝重力＋靜摩擦（保守估）。"""
    weight = SLEEVE_TOTAL_MASS_G / 1000.0 * GRAVITY
    return weight * (1 + FRICTION_COEFF)


def total_current_draw_a(config: str = "full") -> float:
    """
    12V 匯流排穩態總電流估算。

    config="full"（預設）：完整廟宇爐，電磁鐵同時作動的最壞情況
    config="now"         ：桌上型展示機的實際配置（無電磁鐵、1 顆風扇）

    預設維持 "full"，這樣既有的 P3 規則行為完全不變。
    """
    mag = (min(MAGNET_COUNT, MAGNET_SIMULTANEOUS_MAX) if config == "full"
           else MAGNET_COUNT_NOW)
    fan = FAN_COUNT if config == "full" else FAN_COUNT_NOW
    return mag * MAGNET_CURRENT_A + fan * FAN_CURRENT_A + CTRL_CURRENT_A


def peak_current_draw_a(config: str = "full") -> float:
    """
    含風扇啟動突波的瞬時峰值。

    穩態過關不代表開機那一瞬間過關——風扇啟動時電流是穩態的數倍，
    電源若在此時觸發過流保護，整台機器會在每次開風扇時重啟。
    """
    mag = (min(MAGNET_COUNT, MAGNET_SIMULTANEOUS_MAX) if config == "full"
           else MAGNET_COUNT_NOW)
    fan = FAN_COUNT if config == "full" else FAN_COUNT_NOW
    return (mag * MAGNET_CURRENT_A
            + fan * FAN_CURRENT_A * FAN_STARTUP_FACTOR
            + CTRL_CURRENT_A)


def pending_design_constraints() -> List[str]:
    """
    電源預算「假設成立、但還沒實作」的設計約束。

    ★為什麼要獨立列出來★ 這類約束一旦被遺忘，帳面上的數字仍然漂亮，
    實體卻會在最壞情況下失效——而且失效時看起來像隨機當機，最難查。
    """
    out = []
    if MAGNET_SIMULTANEOUS_MAX < MAGNET_COUNT and not MAGNET_INTERLOCK_IMPLEMENTED:
        out.append(
            f"電磁鐵互鎖（一次最多 {MAGNET_SIMULTANEOUS_MAX} 顆，共 {MAGNET_COUNT} 顆）"
            f"——P3 韌體尚未實作；沒有它 12V 峰值會是 "
            f"{MAGNET_COUNT * MAGNET_CURRENT_A + FAN_COUNT * FAN_CURRENT_A * FAN_STARTUP_FACTOR + CTRL_CURRENT_A:.2f}A，"
            f"超過 {PSU_CURRENT_A}A×{PSU_MARGIN:.0%}＝{PSU_CURRENT_A * PSU_MARGIN:.2f}A")
    return out


def filter_chain_pressure_drop_pa() -> float:
    """三段過濾串聯的總壓損。"""
    return sum(FILTER_PRESSURE_DROP_PA.get(f, 0.0) for f in FILTER_CHAIN)


def unmeasured_items() -> List[str]:
    """列出所有尚未實測的項目——報告中相關數值只能稱「設計目標」。"""
    items = []
    if not CENSER_MEASURED:        items.append("香爐內徑/深度")
    if not INCENSE_MEASURED:       items.append("市售線香直徑分布")
    if not SLEEVE_RING_MEASURED:   items.append("鐵墊圈質量")
    if not MAGNET_FORCE_MEASURED:  items.append("電磁鐵實際吸力")
    if not NEAR_CENSER_TEMP_MEASURED: items.append("近爐區實際溫度")
    if not MAGNET_CURRENT_MEASURED:   items.append("電磁鐵實際電流")
    if not FAN_PRESSURE_MEASURED:     items.append("風扇靜壓（含過濾壓損下的實際風量）")
    if not FAN_STARTUP_MEASURED:      items.append("風扇啟動突波倍率")
    if not SENSOR_ZONE_TEMP_MEASURED: items.append("感測器艙實際溫度")
    return items
