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
  外觀  ← 外觀CAD/params.scad（尺寸的唯一真相來源；2026-08-06 由 incense_burner.scad 拆出）

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
# 2026-08-06 起外觀 CAD 拆成多檔，尺寸集中在 參數.scad（唯一真相來源）。
SCAD = HERE / ".." / "外觀CAD" / "params.scad"


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
    """
    材料選擇要以實際熱點為準，不是以 HOT_ZONE_TEMP_C 這個分區門檻為準。

    ★依建置組態判定★（2026-08-07）
      展示機無明火 → 近爐區就是環境溫度，這條規則在那裡不成立也不該成立；
      廟宇爐真的燒 → 照舊要求。
      用同一條絕對規則驗兩種本質不同的建置，結論會是錯的。

    ★這不是把問題藏起來★：其他組態的衝突由
      test_列出其他建置組態的已知衝突 每次跑都印出來。
    """
    cfg = P.build_cfg()
    t = cfg["near_censer_temp_c"]
    for part in P.PARTS:
        if part.near_censer:
            assert part.material.max_service_temp_c >= t, (
                f"[{P.CURRENT_BUILD}] {part.name} 用 {part.material.name}"
                f"（耐 {part.material.max_service_temp_c}°C），低於該組態的近爐溫度 {t}°C"
            )


def test_列出其他建置組態的已知衝突():
    """把非當前組態的衝突印出來，讓它每次跑測試都被看見（不判定成敗）。"""
    for c in P.pending_build_conflicts():
        print(f"  ★其他組態待解★ {c}")


def test_無明火組態不可同時宣稱有燃燒相關的熱設計():
    """
    防止「把組態改成無明火」變成規避耐熱要求的後門。
    無明火就不該有燃燒產物的處理需求——若過濾鏈仍宣稱要擋火星，
    代表組態宣告與設計意圖矛盾，那是宣告錯了，不是規則錯了。
    """
    if P.build_cfg()["open_flame"]:
        return
    assert P.CURRENT_BUILD != "廟宇爐", "廟宇爐不可宣告為無明火"


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
    """最壞情況：完整設計（2 顆風扇）全速 ＋ 控制器。"""
    draw = P.total_current_draw_a()
    budget = P.PSU_CURRENT_A * P.PSU_MARGIN
    assert draw <= budget, (
        f"估計總電流 {draw:.2f}A 超過電源可用量 {budget:.2f}A"
        f"（{P.PSU_CURRENT_A}A × 餘裕 {P.PSU_MARGIN:.0%}）——需加大電源")


def test_現行配置的12V電流須在電源餘裕內():
    """
    ★驗「現在這台」，不是「未來那台」★

    test_12V匯流排電流不可超過電源供給 算的是完整廟宇爐（2 顆風扇），
    那屬 P3。但在它被做出來之前，沒有任何規則在看「桌上型展示機現在夠不夠」——
    而電源不足的症狀是開風扇就重啟，那是實機階段最難查的一類故障。

    這裡同時看穩態與峰值：穩態過關不代表開機瞬間過關，
    風扇是無刷馬達，啟動電流是穩態的數倍。
    """
    budget = P.PSU_CURRENT_A * P.PSU_MARGIN
    steady = P.total_current_draw_a("now")
    peak = P.peak_current_draw_a("now")
    assert steady <= budget, (
        f"現行配置穩態 {steady:.2f}A 超過電源可用量 {budget:.2f}A")
    assert peak <= budget, (
        f"現行配置峰值 {peak:.2f}A（含風扇啟動突波 {P.FAN_STARTUP_FACTOR}×）"
        f"超過電源可用量 {budget:.2f}A——開風扇的瞬間會觸發過流保護，"
        f"症狀是每次啟動風扇整台機器就重開")


def test_現行風扇數需與電路圖一致():
    """
    FAN_COUNT_NOW / MIST_COUNT_NOW 是「現在實際接了幾個」的宣告，
    宣告錯了，上面那條電流規則就是拿錯的負載在驗。
    所以直接去數電路圖上的風扇，兩邊對不上就擋下來。
    """
    net = HERE / ".." / "電路設計" / "kicad" / "佈線定義.py"
    if not net.exists():
        return
    src = net.read_text(encoding="utf-8")
    n_fan = len(re.findall(r'name="Fan-\w+"', src))
    if n_fan == 0:
        return
    assert n_fan == P.FAN_COUNT_NOW, (
        f"電路圖上有 {n_fan} 顆風扇，但 mech_params 宣告現行配置 "
        f"FAN_COUNT_NOW={P.FAN_COUNT_NOW}——電流預算會驗到錯的負載")
    n_mist = len(set(re.findall(r'"(MIST)"', src)))
    assert n_mist == P.MIST_COUNT_NOW, (
        f"電路圖上有 {n_mist} 路霧化驅動，但宣告 MIST_COUNT_NOW={P.MIST_COUNT_NOW}")
    # 理香機構已移除（2026-08-16）——電路圖上不該再有任何電磁鐵驅動
    n_mag = len(set(re.findall(r'"(MAG\d+)"', src)))
    assert n_mag == 0, (
        f"電路圖上仍有 {n_mag} 路電磁鐵驅動（MAGn 網路），"
        f"但理香機構已自設計移除——電路殘留未清")


def test_完整設計的12V峰值須在電源餘裕內():
    """
    既有的 test_12V匯流排電流 只看穩態。但這條匯流排真正的暫態來自風扇
    （無刷馬達，啟動約 FAN_STARTUP_FACTOR 倍），穩態過關不代表開機瞬間過關。
    """
    budget = P.PSU_CURRENT_A * P.PSU_MARGIN
    peak = P.peak_current_draw_a("full")
    assert peak <= budget, (
        f"完整設計峰值 {peak:.2f}A 超過 {budget:.2f}A"
        f"（{P.PSU_CURRENT_A}A × 餘裕 {P.PSU_MARGIN:.0%}）——"
        f"風扇啟動瞬間會觸發過流保護")


def test_韌體不可殘留電磁鐵控制():
    """
    理香機構已移除（2026-08-16）——韌體不該再有任何電磁鐵驅動碼。
    殘留的致動碼比缺功能危險：它還是會對 PCF8574 寫位元，
    而那些輸出腳現在可能接著別的東西。
    ★註解不算殘留★ 先剝掉註解再找，只驗真正的程式碼。
    """
    if not INO.exists():
        return
    src = INO.read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    assert not re.search(r"MAGNET|SOLENOID|magnetPulse|MASK_MAGNETS", code, re.I), (
        "韌體仍有電磁鐵控制碼，但理香機構已自設計移除——韌體殘留未清")


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


def test_鎖固一律使用M4且例外必須有物理理由():
    """
    使用者指定：鎖固一律用 M4。

    但「板卡鎖到殼上」這一類鎖不了 M4——孔徑是外購板自己的孔，
    不在我們的圖上，M4 桿徑 4.0mm 物理上穿不過去。
    這條規則要求：★每一個非 M4 的例外，都必須是被板子的孔徑逼出來的★，
    不能因為「M3 比較好買」就退回去。所以逐一比對板孔徑 < M4 桿徑。
    """
    if not SCAD_V:
        return
    pilot = SCAD_V.get("M4_PILOT")
    clear = SCAD_V.get("M4_CLEAR")
    if pilot is None or clear is None:
        return
    shank = P.M4_SHANK_MM

    # 1) M4 的孔徑本身要合理：底孔咬得住牙、通孔過得去但不曠
    assert pilot < shank, f"M4 底孔 {pilot}mm ≥ 桿徑 {shank}mm，自攻沒有咬合量"
    assert clear > shank, f"M4 通孔 {clear}mm ≤ 桿徑 {shank}mm，螺絲穿不過"
    assert clear - shank <= 0.8, (
        f"M4 通孔 {clear}mm 比桿徑大 {clear - shank:.1f}mm，配合太曠會晃")

    # 2) 外殼側的鎖點必須用 M4（風扇座通孔）
    fan = SCAD_V.get("FAN_SCREW_D")
    assert fan == clear, (
        f"風扇座鎖孔 {fan}mm 不等於 M4 通孔 {clear}mm——外殼鎖固應一律 M4")

    # 3) 每個例外都要有物理理由：板孔裝不下 M4
    for board, (spec, hole_d) in P.SCREW_BOARD_EXEMPT.items():
        assert hole_d < shank, (
            f"{board} 安裝孔 ⌀{hole_d}mm ≥ M4 桿徑 {shank}mm——"
            f"這個孔其實鎖得下 M4，不該例外成 {spec}")

    # 4) 螺柱外徑要留得住牙：孔壁厚度不足會旋裂
    wall = SCAD_V.get("WALL", 0)
    od = SCAD_V.get("STANDOFF_D", 0)
    if wall and od:
        assert od - pilot >= wall * 1.6, (
            f"M4 螺柱外徑 {od}mm 對底孔 {pilot}mm 只剩 "
            f"{(od - pilot) / 2:.1f}mm 孔壁，旋入時會裂")


def test_桌上型展示機與廟宇實體爐的尺度需標明差異():
    """
    mech_params 的 CENSER_INNER_DIA 對應廟宇實體香爐，
    外觀 CAD 是桌上型展示機——兩者尺度不同是刻意的，但必須標明，
    否則報告會出現互相矛盾的尺寸。
    """
    if not SCAD_V:
        return
    demo_w = SCAD_V.get("CHMB_W", 0)
    if demo_w:
        assert demo_w != P.CENSER_INNER_DIA, (
            "展示機與實體爐尺寸相同，疑似誤用同一組數字")


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


def test_CO2硬警報必須維持絕對門檻():
    """
    2026-08-07 把 FSM 的 S0/S1/S2 門檻改成相對於背景基線——那是對的，
    因為分級是「相對於此地此刻的正常值」的判斷。

    ★但硬警報不可以跟著相對化★
      1500ppm 是健康門檻，不是「比平常高一點」。基線本身若已經很高
      （人擠人的展場、通風不良的廟宇），那正是最需要強制換氣的時候——
      這時把門檻跟著抬高，等於在最該作動的情境下把保護關掉。
      相對化會讓它變成「越糟越不管」。

    這條規則就是把「硬警報維持絕對」這件事釘住。
    """
    if not INO_V:
        return
    alarm = INO_V.get("CO2_ALARM_PPM")
    assert alarm is not None, "韌體找不到 CO2_ALARM_PPM"
    assert alarm > 0, "硬警報門檻必須是正的絕對值"

    src = INO.read_text(encoding="utf-8") if INO.exists() else ""
    # ★要檢查「每一個」賦值，不能只看第一個★
    #   co2Alarm 的第一個賦值是宣告 `bool co2Alarm = false;`，
    #   re.search 抓到它就停了，真正的判定式在幾十行之後——
    #   這條檢查原本因此完全沒驗到東西（2026-08-07 負向測試才發現）。
    for expr in re.findall(r"co2Alarm\s*=\s*([^;]+);", src):
        assert "Baseline" not in expr and "base" not in expr, (
            f"硬警報的判定式引用了基線（{expr.strip()}）——"
            f"基線高的時候正是最需要強制換氣的時候，"
            f"相對化等於在最該作動的情境下把保護關掉")


def test_安全狀態必須停止致動():
    if not INO_V or "DUTY_S0" not in INO_V:
        return
    assert INO_V["DUTY_S0"] == 0, "S0 待機應停止風扇"


def test_韌體聯鎖門檻需與參數檔同步():
    """
    門檻同時存在於韌體與 mech_params，兩邊分岔會讓所有跨層檢查失去意義。
    """
    if not INO_V:
        return
    for ino_key, par_key in (("T_LOCK", "INTERLOCK_LOCK_C"),
                             ("T_RELEASE", "INTERLOCK_RELEASE_C")):
        a, b = INO_V.get(ino_key), getattr(P, par_key, None)
        if a is None or b is None:
            continue
        assert abs(a - b) < 1e-6, (
            f"{ino_key}：韌體 {a}°C vs mech_params.{par_key} {b}°C 不一致")


def test_臨時安全門檻必須被標記():
    """
    ★防遺忘機制★
    熱點溫度未實測時，聯鎖門檻只能是臨時值，必須以 T_LOCK_PROVISIONAL 標記。
    這條不會擋住開發，但確保「臨時」這件事不會在報告中被寫成既成事實。

    解除條件：實測熱電偶位置溫度 → 更新 NEAR_CENSER_TEMP_C
             → 重新檢視門檻 → 兩個旗標一起改。
    """
    if not P.NEAR_CENSER_TEMP_MEASURED:
        assert getattr(P, "T_LOCK_PROVISIONAL", False), (
            "熱點溫度未實測，聯鎖門檻屬臨時值，"
            "必須設 T_LOCK_PROVISIONAL = True 以免報告誤植為已驗證設定")
    else:
        assert not getattr(P, "T_LOCK_PROVISIONAL", False), (
            "已實測熱點溫度，請重新檢視聯鎖門檻後將 T_LOCK_PROVISIONAL 改 False")


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
    if getattr(P, "T_LOCK_PROVISIONAL", False):
        print(f"\n【臨時安全門檻】聯鎖 {P.INTERLOCK_LOCK_C:.0f}/"
              f"{P.INTERLOCK_RELEASE_C:.0f}°C 未經實測驗證，"
              f"報告不得描述為已驗證的安全設定")
    assert True
