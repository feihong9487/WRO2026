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

import math
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
# （2026-08-16 移除：理香機構）
# =============================================================
# 插孔板、導正套筒、磁力矩陣（電磁鐵 ×4）整組自設計移除（使用者決定）。
# 香直接插進爐盆／香灰，投香口改為漏斗大口（見 外觀CAD/params.scad）。
# 連帶移除：電磁鐵的電源預算與互鎖約束、相關 L1/L2 規則、
#           電路上的 PCF8574 電磁鐵四路輸出、R4 韌體的電磁鐵控制。
# 舊參數見 git 歷史（2026-08-16 之前的版本）。

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

# 理香機構移除後，近爐區已無自製零件（燃燒艙／集煙罩屬外觀 CAD，
# 材料規則由 外觀CAD/驗證CAD.py 的 E 檢查把關）。此清單保留機制：
# 未來任何新零件都要登記進來，near_censer=True 者受禁 PLA 規則約束。
PARTS: List[Part] = [
    Part("感測器外殼", PLA, near_censer=False,
         notes="呼吸高度，遠離爐面"),
]

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
# 2026-08-16 電磁鐵移除後，這條匯流排只剩風扇、霧化、LED 與控制器，
# 3A 電源餘裕大幅放寬；原本「搭配互鎖才夠」的約束隨電磁鐵一併消失。
PSU_VOLTAGE_V   = 12.0
PSU_CURRENT_A   = 3.0            # BOM：12V 3A
FAN_CURRENT_A    = 0.2           # 5015 每顆
CTRL_CURRENT_A   = 0.5           # MATRIX Mini R4 板子本身
PSU_MARGIN       = 0.8           # 電源使用率上限（留 20% 餘裕）

# ── ★現行建置 vs 完整設計★ ────────────────────────────────
# FAN_COUNT 描述的是「完整廟宇爐」（P3）；桌上型展示機（目前的 P0/P1）
# 實際掛在 12V 上的是控制器、1 顆風扇與霧化模組。
# 兩者混為一談的後果是「用未來的負載去判現在的電源夠不夠」——
# 結論會是錯的。跨層規則會拿電路圖逐項比對這裡的宣告。
FAN_COUNT_NOW    = 1             # 與 佈線定義.py 一致（跨層規則會比對）
MIST_COUNT_NOW   = 1             # 超音波霧化模組（無明火展示的煙源）
MIST_CURRENT_A   = 0.35          # ★估值，未實測★
MIST_MEASURED    = False

# 無刷風扇的啟動突波倍率。★這才是這條匯流排真正的暫態★——
# 會有大啟動電流的是馬達（風扇）與電容性負載。
FAN_STARTUP_FACTOR = 2.5         # ★估值，未實測★
FAN_STARTUP_MEASURED = False

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

# =============================================================
# 建置組態（2026-08-07）
# =============================================================
# 同一套設計有兩種建置，差別不只是尺度，★還有「有沒有明火」★：
#
#   展示機：大會禁明火 → 香不點燃 → ★根本沒有熱區★
#   廟宇爐：真的燒香 → 近爐區高溫 → 材料耐熱是硬要求
#
# 把它做成組態，是因為「近爐零件要耐 120°C」這條規則在展示機上
# ★不成立也不該成立★——那裡沒有 120°C。用同一條絕對規則去驗兩種
# 本質不同的建置，驗出來的結論會是錯的。
#
# ★但廟宇爐的耐熱衝突沒有因此消失★：它會進 pending_build_conflicts()，
#   每次跑測試都印出來。不是把問題藏起來，是把它歸到它真正屬於的組態。
BUILD_CONFIGS = {
    "展示機": dict(
        open_flame=False,
        # 無明火 → 近爐區溫度就是環境溫度（感測器艙同級）
        near_censer_temp_c=SENSOR_ZONE_TEMP_C,
        note="WRO 會場禁明火；香不點燃，霧化煙源與 CO2 分級照常展示",
    ),
    "廟宇爐": dict(
        open_flame=True,
        near_censer_temp_c=NEAR_CENSER_TEMP_C,
        note="實地佈署，真的燒香",
    ),
}
CURRENT_BUILD = "展示機"


def build_cfg(name: str = None) -> dict:
    return BUILD_CONFIGS[name or CURRENT_BUILD]


def pending_build_conflicts() -> List[str]:
    """
    其他組態（不是現在在建的那個）已知但尚未解決的衝突。
    ★列出來是為了不讓它消失★——切到那個組態之前必須處理掉。
    """
    out = []
    for name, cfg in BUILD_CONFIGS.items():
        if name == CURRENT_BUILD:
            continue
        t = cfg["near_censer_temp_c"]
        for part in PARTS:
            if part.near_censer and part.material.max_service_temp_c < t:
                out.append(
                    f"[{name}] {part.name} 用 {part.material.name}"
                    f"（耐 {part.material.max_service_temp_c}°C）低於該組態的近爐溫度 {t}°C"
                    f"——FDM 材料無一撐得住，需實測下修或改設計")
    return out

SCOPE_CORE = {
    # R4（MATRIX Mini R4）＋ Pi 5 ＋ SHT31 ＋ SCD41 ＋ 5015 風扇 ＋ MAX6675 熱電偶 ＋ 雲端監測
    "test_熱電偶聯鎖門檻必須高於該位置的預估工作溫度",
    "test_聯鎖解除門檻需低於觸發門檻且有足夠遲滯",
    "test_SCD41安裝位置溫度不可超過其工作上限",
    "test_感測器不可裝在煙道或近爐區",
    "test_韌體驅動路數需涵蓋機構規劃的風扇數量",
    "test_S2高峰duty需明顯高於S1常態",
    "test_安全狀態必須停止致動",
    "test_CO2硬警報必須維持絕對門檻",
    "test_列出其他建置組態的已知衝突",
    "test_無明火組態不可同時宣稱有燃燒相關的熱設計",
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
    "test_韌體不可殘留電磁鐵控制",
}

SCOPE_LATER = {
    "test_完整設計的12V峰值須在電源餘裕內",
    # P3：過濾鏈與廟宇爐尺度。已完成設計但尚未進入實作，參數多為估計值
    "test_近爐區絕對不可使用PLA", "test_近爐零件的耐熱溫度必須高於熱區溫度",
    "test_金屬紗網必須在HEPA之前",
    "test_活性碳在HEPA之後",
    "test_近爐零件耐熱須高於熱電偶位置溫度",
    "test_風扇靜壓需大於過濾鏈壓損",
    "test_12V匯流排電流不可超過電源供給",
}

# =============================================================
# 便利函數
# =============================================================

def total_current_draw_a(config: str = "full") -> float:
    """
    12V 匯流排穩態總電流估算。

    config="full"（預設）：完整廟宇爐（2 顆風扇）的最壞情況
    config="now"         ：桌上型展示機的實際配置（1 顆風扇＋霧化）

    預設維持 "full"，這樣既有的 P3 規則行為完全不變。
    """
    fan = FAN_COUNT if config == "full" else FAN_COUNT_NOW
    mist = MIST_COUNT_NOW if config == "now" else 0   # 霧化只在展示機上
    return fan * FAN_CURRENT_A + mist * MIST_CURRENT_A + CTRL_CURRENT_A


def peak_current_draw_a(config: str = "full") -> float:
    """
    含風扇啟動突波的瞬時峰值。

    穩態過關不代表開機那一瞬間過關——風扇啟動時電流是穩態的數倍，
    電源若在此時觸發過流保護，整台機器會在每次開風扇時重啟。
    """
    fan = FAN_COUNT if config == "full" else FAN_COUNT_NOW
    mist = MIST_COUNT_NOW if config == "now" else 0
    return (fan * FAN_CURRENT_A * FAN_STARTUP_FACTOR
            + mist * MIST_CURRENT_A + CTRL_CURRENT_A)


def filter_chain_pressure_drop_pa() -> float:
    """三段過濾串聯的總壓損。"""
    return sum(FILTER_PRESSURE_DROP_PA.get(f, 0.0) for f in FILTER_CHAIN)


def unmeasured_items() -> List[str]:
    """列出所有尚未實測的項目——報告中相關數值只能稱「設計目標」。"""
    items = []
    if not CENSER_MEASURED:        items.append("香爐內徑/深度")
    if not NEAR_CENSER_TEMP_MEASURED: items.append("近爐區實際溫度")
    if not FAN_PRESSURE_MEASURED:     items.append("風扇靜壓（含過濾壓損下的實際風量）")
    if not FAN_STARTUP_MEASURED:      items.append("風扇啟動突波倍率")
    if not SENSOR_ZONE_TEMP_MEASURED: items.append("感測器艙實際溫度")
    if not MIST_MEASURED:             items.append("超音波霧化模組實際電流")
    return items
