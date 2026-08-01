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
PSU_CURRENT_A   = 2.0            # 現行 BOM：12V 2A
MAGNET_CURRENT_A = 0.5           # 電磁鐵每顆估計電流（12V 20N 常見值）
MAGNET_CURRENT_MEASURED = False  # ← 待實測（標稱吸力不等於標稱電流）
FAN_CURRENT_A    = 0.2           # 5015 每顆
CTRL_CURRENT_A   = 0.5           # MATRIX Mini R4 板子本身
PSU_MARGIN       = 0.8           # 電源使用率上限（留 20% 餘裕）

# ── 過濾鏈壓損（決定風扇選型是否足夠）──
# 5015 鼓風扇靜壓有限，三段過濾串聯的壓損不可忽視
FILTER_PRESSURE_DROP_PA = {"金屬紗網": 5.0, "HEPA": 120.0, "活性碳濾棉": 40.0}
FAN_STATIC_PRESSURE_PA  = 250.0  # 5015 標稱靜壓（估，待實測）
FAN_PRESSURE_MEASURED   = False  # ← 待實測

# ── 熱電偶安裝 ──
TC_MOUNT_LOCATION = "爐盆外壁"    # 熱電偶貼附位置
TC_LOCATION_TEMP_C = 120.0        # ★該位置的預估溫度＝NEAR_CENSER_TEMP_C★

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


def total_current_draw_a() -> float:
    """12V 匯流排總電流估算（電磁鐵同時作動為最壞情況）。"""
    return (MAGNET_COUNT * MAGNET_CURRENT_A
            + FAN_COUNT * FAN_CURRENT_A
            + CTRL_CURRENT_A)


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
    if not SENSOR_ZONE_TEMP_MEASURED: items.append("感測器艙實際溫度")
    return items
