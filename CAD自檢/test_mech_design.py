#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧香爐 — 機構設計規則測試（L1 參數迴路）
=============================================================
把《實作交接文件》§5 的工程警告與機構限制，變成毫秒級可判定的規則。
不需要 CAD、不需要建模，改參數立刻知道有沒有違規。

★ 見 CLAUDE.md §5.2 與 .claude/commands/verify.md：★
  失敗時修正設計參數，不得放寬本檔的安全與可製造性門檻。
  尤其禁 PLA 區、過濾鏈順序——這些是安全與可用性紅線。

（2026-08-16 理香機構移除：插孔板／導正套筒／磁力矩陣的規則
  隨機構一併移除，見 mech_params.py 的移除紀錄。）

執行：python3 run_tests.py        （專案根目錄，不需 pytest）
     python3 -m pytest -q         （若已安裝 pytest）
"""

import mech_params as P


# ── 材料與耐熱（交接文件 §5.1：PLA 60°C 軟化）────────────────────

def test_近爐區絕對不可使用PLA():
    """近爐熱區用 PLA 會在燒香時軟化變形，是硬性禁令。
    目前 PARTS 已無近爐零件，此規則保留給未來登記的新零件。"""
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
