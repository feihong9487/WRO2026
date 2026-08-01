#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧香爐 — 跨層一致性測試（L1b）
=============================================================
補上 test_mech_design.py 沒有涵蓋的一整類問題：
**機構、韌體、電控三者的參數散在不同檔案，彼此矛盾時沒有任何
單一領域的檢查抓得到。**

本檔直接從各領域的「真實來源」讀值再交叉比對：
  機構  ← mech_params.py
  韌體  ← R4/matrix_mini_r4/matrix_mini_r4.ino（解析 const 定義）
  外觀  ← 外觀CAD/incense_burner.scad（解析參數區）

★ 見 CLAUDE.md §5.2 ★
  失敗時修正設計參數，不得放寬本檔門檻。
  跨層衝突多半沒有「正確答案」，只有取捨——回報衝突並提選項，讓人決定。

執行：python3 run_tests.py（專案根目錄）
"""

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mech_params as P

HERE = Path(__file__).parent
INO = HERE / ".." / "R4" / "matrix_mini_r4" / "matrix_mini_r4.ino"
SCAD = HERE / ".." / "外觀CAD" / "incense_burner.scad"


# ── 從其他領域的原始檔讀值 ─────────────────────────────────────

def _ino():
    """解析韌體的 const 定義。抓不到檔案時回傳空 dict，相關測試自動略過。"""
    if not INO.exists():
        return {}
    src = INO.read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    out = {}
    for m in re.finditer(r"const\s+\w+(?:\s+\w+)?\s+(\w+)\s*=\s*([-\d.]+)\s*;", src):
        out[m.group(1)] = float(m.group(2))
    fsm = re.search(r"uint8_t localFSM\(\)(.*?)\n\}", src, re.S)
    if fsm:
        body = fsm.group(1)
        for st, pat in (("S0", r'"S0"\) == 0\) return (\d+)'),
                        ("S2", r'"S2"\) == 0\) return (\d+)'),
                        ("S1", r"return (\d+);\s*//\s*S1")):
            mm = re.search(pat, body)
            if mm:
                out[f"DUTY_{st}"] = float(mm.group(1))
    return out


def _scad():
    if not SCAD.exists():
        return {}
    src = SCAD.read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    head = src[:src.find("module ")] if "module " in src else src
    env = {}
    for stmt in head.split(";"):
        m = re.match(r"\s*([A-Za-z_]\w*)\s*=\s*(.+)\s*$", stmt, re.S)
        if not m:
            continue
        try:
            env[m.group(1)] = eval(m.group(2).strip(), {"__builtins__": {}}, dict(env))
        except Exception:
            pass
    return env


INO_V = _ino()
SCAD_V = _scad()


# ═══════════════════════════════════════════════════════════════
# 熱：韌體聯鎖門檻 vs 機構預估溫度
# ═══════════════════════════════════════════════════════════════

def test_熱電偶聯鎖門檻必須高於該位置的預估工作溫度():
    """
    ★最關鍵的一條★
    熱電偶貼在 TC_MOUNT_LOCATION，該處預估 TC_LOCATION_TEMP_C。
    若聯鎖門檻 T_LOCK 低於這個溫度，正常燃燒就會持續觸發聯鎖，
    而韌體的聯鎖優先權高於一切（duty 強制 0），風扇將永遠停擺。

    衝突時的取捨（由人決定，不可由 agent 自行放寬）：
      A. 提高 T_LOCK —— 但要確認材料與安全仍可接受
      B. 把熱電偶移到較低溫的位置，並更新 TC_MOUNT_LOCATION / TC_LOCATION_TEMP_C
      C. 若 120°C 只是保守高估，實測後下修 NEAR_CENSER_TEMP_C
    """
    if not INO_V:
        return
    t_lock = INO_V.get("T_LOCK")
    assert t_lock is not None, "韌體找不到 T_LOCK"
    assert t_lock > P.TC_LOCATION_TEMP_C, (
        f"聯鎖門檻 T_LOCK={t_lock}°C 低於熱電偶位置（{P.TC_MOUNT_LOCATION}）"
        f"的預估溫度 {P.TC_LOCATION_TEMP_C}°C——正常燃燒就會持續觸發聯鎖，"
        f"風扇被強制鎖在 0。三種解法見本測試的 docstring。"
    )


def test_聯鎖解除門檻需低於觸發門檻且有足夠遲滯():
    if not INO_V:
        return
    lock, rel = INO_V.get("T_LOCK"), INO_V.get("T_RELEASE")
    if lock is None or rel is None:
        return
    assert rel < lock, "T_RELEASE 必須低於 T_LOCK，否則無遲滯"
    assert lock - rel >= 10.0, f"遲滯僅 {lock-rel}°C，過小會在門檻附近抖動"


def test_近爐零件耐熱須高於熱電偶位置溫度():
    """材料選擇要以實際熱點為準，不是以 HOT_ZONE_TEMP_C 這個分區門檻為準。"""
    for part in P.PARTS:
        if part.near_censer:
            assert part.material.max_service_temp_c >= P.TC_LOCATION_TEMP_C, (
                f"{part.name} 用 {part.material.name}"
                f"（耐 {part.material.max_service_temp_c}°C），"
                f"低於熱點預估 {P.TC_LOCATION_TEMP_C}°C"
            )


# ═══════════════════════════════════════════════════════════════
# 感測器：位置決定於耐溫，不是只看 near_censer 布林值
# ═══════════════════════════════════════════════════════════════

def test_SCD41安裝位置溫度不可超過其工作上限():
    """
    SCD41 工作上限約 60°C。它是 CO2 唯一來源，燒掉等於整個 FSM 失明。
    這條規則補上 PARTS 只有 near_censer 布林值、沒有量化溫度的缺口。
    """
    assert P.SENSOR_ZONE_TEMP_C < P.SCD41_MAX_OP_TEMP_C, (
        f"感測器艙預估 {P.SENSOR_ZONE_TEMP_C}°C，超過 SCD41 上限 "
        f"{P.SCD41_MAX_OP_TEMP_C}°C")


def test_感測器不可裝在煙道或近爐區():
    """
    量測目的決定位置：FSM 用 CO2 斜率偵測人潮，要量的是參拜者呼吸到的空氣。
    裝進煙道量到的是廢氣濃度，對前饋削峰沒有意義，感測器本身也會過熱。
    """
    for part in P.PARTS:
        if "感測" in part.name:
            assert not part.near_censer, (
                f"{part.name} 被標為近爐區——量測意義與耐溫都不成立")


# ═══════════════════════════════════════════════════════════════
# 風扇：機構規劃數量 vs 韌體實際驅動路數
# ═══════════════════════════════════════════════════════════════

def test_韌體驅動路數需涵蓋機構規劃的風扇數量():
    """
    機構規劃 FAN_COUNT 顆風扇，但韌體只有 FIRMWARE_FAN_CHANNELS 路 PWM。
    若兩顆並聯在同一路，必須確認 D4184 電流餘裕，且兩顆會同步同速。
    """
    if P.FAN_COUNT > P.FIRMWARE_FAN_CHANNELS:
        assert P.FAN_COUNT * P.FAN_CURRENT_A <= 15.0 * 0.5, (
            f"{P.FAN_COUNT} 顆風扇並聯於 1 路 D4184，"
            f"總電流 {P.FAN_COUNT*P.FAN_CURRENT_A:.1f}A 需在模組額定的一半以內")


def test_風扇靜壓需大於過濾鏈壓損():
    """
    三段過濾串聯壓損不小。若風扇靜壓不足，風量會趨近於零——
    面板上看得到 duty 220，實際卻幾乎不抽風，是很難察覺的失效。
    """
    drop = P.filter_chain_pressure_drop_pa()
    assert P.FAN_STATIC_PRESSURE_PA > drop * 1.3, (
        f"過濾鏈壓損 {drop:.0f}Pa，風扇靜壓 {P.FAN_STATIC_PRESSURE_PA:.0f}Pa，"
        f"餘裕不足 1.3 倍——實際風量會遠低於標稱")


# ═══════════════════════════════════════════════════════════════
# 電源預算
# ═══════════════════════════════════════════════════════════════

def test_12V匯流排電流不可超過電源供給():
    """最壞情況：電磁鐵同時作動 ＋ 風扇全速 ＋ 控制器。"""
    draw = P.total_current_draw_a()
    budget = P.PSU_CURRENT_A * P.PSU_MARGIN
    assert draw <= budget, (
        f"估計總電流 {draw:.2f}A 超過電源可用量 {budget:.2f}A"
        f"（{P.PSU_CURRENT_A}A × 餘裕 {P.PSU_MARGIN:.0%}）——"
        f"需加大電源或錯開電磁鐵作動時序")


def test_電磁鐵吸力餘裕在實測前不可寫進報告結論():
    """
    標稱 20N 是零氣隙貼合值，有 3mm 氣隙時衰減很大。
    這條測試不判定吸力夠不夠（那要實測），只確保旗標誠實。
    """
    if not P.MAGNET_FORCE_MEASURED:
        assert P.MAGNET_AIR_GAP > 0, (
            "氣隙為 0 的假設過於樂觀，且與 MAGNET_AIR_GAP 設計值不符")


# ═══════════════════════════════════════════════════════════════
# 幾何介面：機構 ↔ 外觀 CAD
# ═══════════════════════════════════════════════════════════════

def test_煙道截面在機構與外觀CAD之間需相容():
    """機構用 ⌀50 PVC 集煙管，外觀 CAD 用矩形煙道，截面積差太多會有流阻突變。"""
    if not SCAD_V:
        return
    pvc_area = math.pi * (P.DUCT_INNER_DIA / 2) ** 2
    rect_area = SCAD_V.get("DUCT_W", 0) * SCAD_V.get("DUCT_H", 0)
    if rect_area == 0:
        return
    ratio = min(pvc_area, rect_area) / max(pvc_area, rect_area)
    assert ratio >= 0.7, (
        f"PVC 管截面 {pvc_area:.0f}mm² vs 外觀 CAD 煙道 {rect_area:.0f}mm²，"
        f"相差 {(1-ratio)*100:.0f}%——接合處會有明顯流阻突變")


def test_外觀CAD的近熱區必須有空氣間隙():
    """把 mech_params 的禁 PLA 紅線延伸到外觀 CAD 的燃燒艙。"""
    if not SCAD_V:
        return
    gap = SCAD_V.get("AIR_GAP", 0)
    assert gap > 0, "外觀 CAD 的 AIR_GAP = 0，塑膠會直接接觸高溫爐盆"
    assert gap >= 6.0, (
        f"AIR_GAP {gap}mm 偏薄。熱點預估 {P.TC_LOCATION_TEMP_C}°C 時，"
        f"間隙不足會讓外殼超過材料耐受")


def test_桌上型展示機與廟宇實體爐的尺度需標明差異():
    """
    mech_params 的 CENSER_INNER_DIA / PLATE_DIA 對應廟宇實體香爐，
    外觀 CAD 是桌上型展示機——兩者尺度不同是刻意的，但必須標明，
    否則報告會出現互相矛盾的尺寸。
    """
    if not SCAD_V:
        return
    demo_w = SCAD_V.get("CHMB_W", 0)
    if demo_w:
        assert demo_w != P.PLATE_DIA, "展示機與實體爐尺寸相同，疑似誤用同一組數字"


# ═══════════════════════════════════════════════════════════════
# FSM duty 與機構的一致性
# ═══════════════════════════════════════════════════════════════

def test_S2高峰duty需明顯高於S1常態():
    """前饋削峰的效果來自 S1→S2 的風量差，差距太小則削峰無感。"""
    if not INO_V or "DUTY_S1" not in INO_V or "DUTY_S2" not in INO_V:
        return
    s1, s2 = INO_V["DUTY_S1"], INO_V["DUTY_S2"]
    assert s2 >= s1 * 2, (
        f"S2 duty {s2:.0f} 僅為 S1 {s1:.0f} 的 {s2/s1:.1f} 倍，削峰效果不明顯")


def test_安全狀態必須停止致動():
    if not INO_V or "DUTY_S0" not in INO_V:
        return
    assert INO_V["DUTY_S0"] == 0, "S0 待機應停止風扇"


# ═══════════════════════════════════════════════════════════════
# 誠實一致性
# ═══════════════════════════════════════════════════════════════

def test_列出跨層待實測項目():
    """永遠通過。用途是把待測清單印出來。"""
    pending = P.unmeasured_items()
    if pending:
        print("\n【尚未實測，報告中僅可稱設計目標】")
        for item in pending:
            print(f"  ・{item}")
    assert True
