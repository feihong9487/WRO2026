#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧香爐 — 機構設計規則測試（L1 參數迴路）
=============================================================
把《實作交接文件》§5 的工程警告與機構限制，變成毫秒級可判定的規則。
不需要 CAD、不需要建模，改參數立刻知道有沒有違規。

★ 見 CLAUDE.md §5.2 與 .claude/commands/verify.md：★
  失敗時修正設計參數，不得放寬本檔的安全與可製造性門檻。
  尤其禁 PLA 區、過濾鏈順序、滑動間隙下限——這些是安全與可用性紅線。

執行：python3 run_tests.py        （專案根目錄，不需 pytest）
     python3 -m pytest -q         （若已安裝 pytest）
"""

import math

import mech_params as P


# ── 材料與耐熱（交接文件 §5.1：PLA 60°C 軟化）────────────────────

def test_近爐區絕對不可使用PLA():
    """插孔板與套筒區用 PLA 會在燒香時軟化變形，是硬性禁令。"""
    for part in P.PARTS:
        if part.near_censer:
            assert part.material is not P.PLA, (
                f"{part.name} 位於近爐熱區卻使用 PLA —— 違反禁 PLA 區規則"
            )


def test_近爐零件的耐熱溫度必須高於熱區溫度():
    for part in P.PARTS:
        if part.near_censer:
            assert part.material.max_service_temp_c > P.HOT_ZONE_TEMP_C, (
                f"{part.name} 的 {part.material.name} 耐熱不足"
            )


def test_套筒管身必須耐得住近爐溫度():
    assert P.SLEEVE_MATERIAL.max_service_temp_c >= P.NEAR_CENSER_TEMP_C


def test_磁路作用對象必須是鐵磁材料():
    """磁力作用於導正套筒的鐵墊圈，不是香枝——可普及性的前提。"""
    assert P.SLEEVE_FERRO_RING.ferromagnetic, "套筒缺少鐵磁元件，磁力矩陣將無作用對象"


def test_套筒管身本身不需要導磁():
    """管身用鋁（非鐵磁）是刻意選擇：耐熱優先，磁性由墊圈提供。"""
    assert P.SLEEVE_MATERIAL.max_service_temp_c > P.PETG.max_service_temp_c


# ── 插孔板幾何與可製造性 ──────────────────────────────────────

def test_孔徑必須容納套筒並保留滑動間隙():
    clearance = (P.PLATE_HOLE_DIA - P.SLEEVE_OUTER_DIA) / 2
    assert clearance >= P.MIN_SLIDE_CLEARANCE, (
        f"單邊間隙 {clearance:.2f}mm 過小，套筒會卡死"
    )


def test_孔間壁厚足夠支撐():
    wall = P.hole_edge_to_edge()
    assert wall >= P.MIN_WALL_BETWEEN_HOLES, (
        f"孔間僅剩 {wall:.1f}mm 材料，低於最小壁厚 {P.MIN_WALL_BETWEEN_HOLES}mm"
    )


def test_所有特徵大於列印最小尺寸():
    """
    ★2026-08-07 採 A 案（使用者決定）★
      原本這條把導正套筒也算進去，但套筒是【外購鋁管】（SLEEVE_IS_PRINTED = False），
      拿 3D 列印的最小成形特徵去驗擠壓成型的管材是套錯對象。
      改為只驗真正的列印件；外購管材另由
      test_外購管材必須是市售標準規格 把關——★不是不驗，是換對的尺去量★。

      註：本次同時把套筒壁厚由 1.0 改為 1.5mm，但那有它自己的理由
      （薄壁鋁管插拔時易壓成橢圓，會卡在 0.4mm 間隙的孔裡），
      不是為了讓這條規則變綠。
    """
    if P.SLEEVE_IS_PRINTED:
        assert P.SLEEVE_WALL >= P.MIN_PRINTABLE_FEATURE, (
            f"套筒改為自行列印後，壁厚 {P.SLEEVE_WALL:.2f}mm "
            f"低於最小可列印特徵 {P.MIN_PRINTABLE_FEATURE}mm")
    assert P.PLATE_THICKNESS >= P.MIN_PRINTABLE_FEATURE * 2, (
        f"插孔板厚 {P.PLATE_THICKNESS}mm 低於最小可列印特徵的兩倍")


def test_外購管材必須是市售標準規格():
    """
    外購件的可製造性下限不是「印不印得出來」，而是★買不買得到★。
    圖面上完全合理的 OD 9.3 × 壁 1.1，可能沒有任何一家在賣——
    這種錯誤要到採購階段才會爆，那時機構已經定案了。
    """
    if P.SLEEVE_IS_PRINTED:
        return
    od, wall = P.SLEEVE_OUTER_DIA, P.SLEEVE_WALL
    assert (od, round(wall, 2)) in P.STOCK_ALU_TUBE_OD_WALL, (
        f"套筒規格 外徑 {od} × 壁厚 {wall:.2f} 不在常見市售鋁管清單內——"
        f"該外徑可選的壁厚："
        f"{sorted(w for o, w in P.STOCK_ALU_TUBE_OD_WALL if o == od) or '（此外徑不在清單）'}")
    # 內徑仍須容得下最粗的香枝
    assert P.SLEEVE_INNER_DIA > P.INCENSE_SHAFT_DIA_MAX, (
        f"套筒內徑 {P.SLEEVE_INNER_DIA}mm 容不下最粗香枝 "
        f"{P.INCENSE_SHAFT_DIA_MAX}mm")


def test_插孔板必須放得進香爐():
    gap = P.CENSER_INNER_DIA - P.PLATE_DIA
    assert gap >= P.PLATE_CENSER_CLEARANCE, (
        f"板緣間隙僅 {gap:.1f}mm，裝不進去或無法安裝固定件"
    )


def test_孔位陣列不可超出板面():
    """2×2 陣列的最外側孔，加上邊距，必須落在板內。"""
    n_per_side = math.ceil(math.sqrt(P.PLATE_HOLE_COUNT))
    span = (n_per_side - 1) * P.PLATE_HOLE_PITCH + P.PLATE_HOLE_DIA
    needed = span + 2 * P.PLATE_EDGE_MARGIN
    assert needed <= P.PLATE_DIA, (
        f"孔陣列需要 {needed:.1f}mm，板徑僅 {P.PLATE_DIA}mm"
    )


def test_套筒長度需大於板厚才能導正():
    assert P.SLEEVE_LENGTH > P.PLATE_THICKNESS * 2, "套筒太短，無法有效導正香枝"


def test_套筒內徑容得下最粗的市售香():
    assert P.SLEEVE_INNER_DIA > P.INCENSE_SHAFT_DIA_MAX, (
        "套筒內徑不足，會排除部分市售香 —— 違反可普及性前提"
    )


# ── 磁力矩陣 ─────────────────────────────────────────────────

def test_電磁鐵吸力需大於驅動套筒所需力():
    need = P.sleeve_required_force_n()
    assert P.MAGNET_FORCE_N > need * 2, (
        f"需要 {need:.2f}N，標稱 {P.MAGNET_FORCE_N}N，安全係數不足 2 倍"
    )


def test_氣隙不可超過有效吸附距離():
    assert P.MAGNET_AIR_GAP <= P.MAGNET_MAX_AIR_GAP


def test_電磁鐵間距需與孔距一致():
    assert P.MAGNET_PITCH == P.PLATE_HOLE_PITCH, "磁鐵陣列與孔陣列必須對齊"


def test_電磁鐵直徑不可大於孔距造成干涉():
    assert P.MAGNET_DIA < P.MAGNET_PITCH, "相鄰電磁鐵會互相干涉"


def test_行程需小於套筒長度():
    assert P.MAGNET_STROKE < P.SLEEVE_LENGTH / 2, "行程過大，套筒會脫離導引"


# ── 過濾鏈順序（交接文件 §5.3：安全必備）─────────────────────────

def test_金屬紗網必須在HEPA之前():
    """抽風會把火星吸向濾網，紗網是火星前濾，順序錯了會燒起來。"""
    chain = P.FILTER_CHAIN
    assert "金屬紗網" in chain and "HEPA" in chain
    assert chain.index("金屬紗網") < chain.index("HEPA"), (
        "金屬紗網必須裝在 HEPA 之前 —— 火星防護紅線"
    )


def test_活性碳在HEPA之後():
    chain = P.FILTER_CHAIN
    assert chain.index("HEPA") < chain.index("活性碳濾棉")


# ── 材料預算 ─────────────────────────────────────────────────

def test_插孔板用料不超過一卷PETG():
    mass = P.plate_print_mass_g()
    assert mass < P.PETG_SPOOL_G * 0.5, (
        f"單件預估 {mass:.0f}g，超過半卷線材，需重新檢討設計或填充率"
    )


# ── 誠實一致性 ───────────────────────────────────────────────

def test_列出尚未實測的項目():
    """
    這條測試永遠通過，用途是在每次跑迴圈時把待測清單印出來，
    提醒：基於這些估計值的任何數字，在報告中只能稱「設計目標」。
    """
    pending = P.unmeasured_items()
    if pending:
        print("\n【尚未實測，報告中僅可稱設計目標】")
        for item in pending:
            print(f"  ・{item}")
    assert True
