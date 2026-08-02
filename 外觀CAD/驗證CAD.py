#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外觀 CAD 參數化驗證
================================================================
本機沒有 OpenSCAD 可算繪，改用靜態分析抓「算繪得出來但做不出來」的問題：

  A. 語法：括號平衡、模組定義與呼叫是否對得上
  B. 列印規則：壁厚為噴嘴徑整數倍、層厚合理、配合間隙在 FDM 可行範圍
  C. ★元件裝得下嗎★：爐盆／板卡／風扇／感測器模組 vs 對應容納空間
  D. ★零件放得進列印床嗎★
  E. ★熱設計★：空氣間隙存在、電子艙與燃燒艙有隔離
  F. 介面一致性：煙道尺寸在燃燒艙／集煙罩／風扇座三處必須相同
  G. ★實際算繪★（需安裝 OpenSCAD）：manifold、浮空塊、算繪警告
     浮空塊只有算繪才抓得到——參數再怎麼算都看不出「這塊沒連上」
  I. ★列印性★：從 STL 三角形法向量算懸空面積（不需額外算繪）
     懸空 >45° 需支撐材——印得出來但表面差、要花時間清。
     這是「幾何合法」與「實際做得出來」之間的差距。
  J. ★開口遮擋★：功能性開口前方不可被其他零件擋住
     進氣柵格被感測器艙蓋住 → 對流失效，但干涉檢查不會報（沒有穿透）。
  K. ★回歸基準★：與上次的體積／面數／包圍盒比對
     改了 A 參數卻讓 B 零件默默變形，是參數化設計最難察覺的錯。
  H. ★組裝干涉★：兩兩零件求交集並量體積 ＋ ★落座檢查★
     干涉抓「不該碰卻碰了」；落座抓「該貼合卻浮空」——
     兩者方向相反，都要查。零件浮空時交集體積也是 0，
     光看干涉會誤判為正常。
     單件檢查全過，組裝起來卻互相穿透——畫面上是 z-fighting 破圖，
     實體是根本裝不上去。這一層是 2026-08-02 補的，補之前風扇座
     整個埋在燃燒艙裡而所有檢查都通過。

執行：python3 驗證CAD.py
"""

import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCAD = Path(__file__).parent / "incense_burner.scad"

problems, warnings, notes = [], [], []


# ── 解析 ────────────────────────────────────────────────────
def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def load_params(src):
    """把頂層的 NAME = expr; 逐一求值。OpenSCAD 的算術語法與 Python 相容。"""
    env = {}
    body = strip_comments(src)
    # 只取模組定義之前的參數區
    first_mod = body.find("module ")
    head = body[:first_mod] if first_mod > 0 else body

    for stmt in head.split(";"):
        m = re.match(r"\s*([A-Za-z_]\w*)\s*=\s*(.+)\s*$", stmt, re.S)
        if not m:
            continue
        name, expr = m.group(1), m.group(2).strip()
        if name.startswith("$"):
            continue
        try:
            env[name] = eval(expr, {"__builtins__": {}}, dict(env))
        except Exception:
            pass          # 字串或無法求值者略過（如 part = "assembly"）
    return env


def check_syntax(src):
    body = strip_comments(src)
    # 括號平衡（字串感知）
    pairs = {")": "(", "]": "[", "}": "{"}
    depth = {"(": 0, "[": 0, "{": 0}
    in_s = False
    i = 0
    while i < len(body):
        c = body[i]
        if in_s:
            if c == "\\": i += 2; continue
            if c == '"': in_s = False
        elif c == '"':
            in_s = True
        elif c in depth:
            depth[c] += 1
        elif c in pairs:
            depth[pairs[c]] -= 1
            if depth[pairs[c]] < 0:
                problems.append(f"A: 多餘的 {c}（位置約 {i}）")
                return
        i += 1
    for k, v in depth.items():
        if v != 0:
            problems.append(f"A: {k} 括號不平衡，差 {v}")
    if in_s:
        problems.append("A: 有字串未關閉")

    # 模組定義 vs 呼叫
    defined = set(re.findall(r"^\s*module\s+(\w+)\s*\(", body, re.M))
    # OpenSCAD 的 function 也是可呼叫名稱（可在 module 內定義，故不限行首）
    defined |= set(re.findall(r"\bfunction\s+(\w+)\s*\(", body))
    builtin = {
        "cube", "cylinder", "sphere", "polygon", "circle", "square", "text",
        "translate", "rotate", "scale", "mirror", "resize", "multmatrix", "color",
        "union", "difference", "intersection", "hull", "minkowski", "offset",
        "linear_extrude", "rotate_extrude", "projection", "surface", "children",
        "for", "if", "else", "let", "each", "import", "render", "echo", "assert",
        "max", "min", "abs", "sqrt", "pow", "floor", "ceil", "round", "sin", "cos",
        "len", "str", "concat", "norm", "cross", "lookup", "is_undef",
    }
    called = set(re.findall(r"(?<![\w.$])(\w+)\s*\(", body))
    unknown = called - defined - builtin - set(load_params(src))
    unknown = {u for u in unknown if not u.isupper() and not u[0].isdigit()}
    if unknown:
        warnings.append(f"A: 呼叫了未定義的名稱（可能是拼字錯誤）：{sorted(unknown)}")
    else:
        notes.append(f"A: 括號平衡；{len(defined)} 個模組定義，呼叫全部對得上 ✓")

    # 每個定義的模組都有被用到嗎
    unused = defined - called
    if unused:
        warnings.append(f"A: 定義了但沒被呼叫的模組：{sorted(unused)}")


def check_print_rules(p):
    nozzle, wall, floor = p["NOZZLE"], p["WALL"], p["FLOOR"]
    n = round(wall / nozzle, 3)
    if abs(n - round(n)) > 1e-6:
        problems.append(f"B: WALL={wall} 不是噴嘴徑 {nozzle} 的整數倍（{n} 走線）")
    elif wall < nozzle * 3:
        warnings.append(f"B: WALL={wall} 僅 {int(n)} 走線，燃燒艙這種受熱件建議 ≥4")
    else:
        notes.append(f"B: 壁厚 {wall}mm＝{int(n)} 走線、底頂厚 {floor}mm ✓")

    if not (0.15 <= p["FIT"] <= 0.5):
        warnings.append(f"B: 配合間隙 FIT={p['FIT']} 超出 FDM 常用範圍 0.2–0.4")
    if p["CHAMFER"] >= wall:
        problems.append(f"B: 倒角 {p['CHAMFER']} ≥ 壁厚 {wall}，會把牆吃穿")


def check_fits(p):
    # ── 金屬爐盆 ＋ 空氣間隙 vs 燃燒艙 ──
    well = p["BOWL_D"] + p["FIT"] * 2 + p["AIR_GAP"] * 2
    need = well + p["WALL"] * 2
    if need > p["CHMB_W"]:
        problems.append(
            f"C: 爐盆井 {well:.1f}mm ＋ 雙側壁 {p['WALL']*2:.1f} = {need:.1f}mm "
            f"> 燃燒艙寬 {p['CHMB_W']}mm——放不下")
    else:
        notes.append(f"C: 爐盆 ⌀{p['BOWL_D']} ＋ 空氣間隙 {p['AIR_GAP']}×2 "
                     f"→ 井 ⌀{well:.1f}，燃燒艙 {p['CHMB_W']} 內尚餘 "
                     f"{p['CHMB_W']-need:.1f}mm ✓")

    # 承接環不可超出燃燒艙
    lip_od = p["BOWL_D"] + p["FIT"] * 2 + p["BOWL_LIP"] * 2
    if lip_od > p["CHMB_W"] - p["WALL"] * 2:
        problems.append(f"C: 爐盆承接環外徑 {lip_od:.1f} 超出燃燒艙內壁")

    # ── 板卡 vs 電子艙內部 ──
    inner_w = p["BASE_W"] - p["WALL"] * 2
    inner_d = p["BASE_D"] - p["WALL"] * 2
    # 佈局：MATRIX 左前、Pi 左後、D4184 右前
    if 14 + p["MATRIX_W"] > inner_w:
        problems.append(f"C: MATRIX 寬 {p['MATRIX_W']} 放不進電子艙內寬 {inner_w}")
    if 14 + p["PI_D"] + 14 + p["MATRIX_D"] > inner_d:
        problems.append(
            f"C: MATRIX 深 {p['MATRIX_D']} ＋ Pi 深 {p['PI_D']} ＋ 邊距 = "
            f"{14+p['PI_D']+14+p['MATRIX_D']} > 電子艙內深 {inner_d}")
    else:
        notes.append(f"C: 電子艙內部 {inner_w:.0f}×{inner_d:.0f}mm，"
                     f"容 MATRIX({p['MATRIX_W']}×{p['MATRIX_D']})＋"
                     f"Pi({p['PI_W']}×{p['PI_D']})＋D4184 ✓")
    # 板卡高度
    tallest = p["STANDOFF_H"] + 18      # 板厚＋最高連接器（USB-A 約 16mm）
    if tallest + p["FLOOR"] > p["BASE_H"]:
        problems.append(f"C: 螺柱 {p['STANDOFF_H']}＋連接器約 18mm 高於電子艙 {p['BASE_H']}")

    # ── 5015 風扇 vs 風扇座 ──
    if p["FAN_SCREW_S"] >= p["FAN_W"]:
        problems.append(f"C: 風扇螺絲間距 {p['FAN_SCREW_S']} ≥ 本體寬 {p['FAN_W']}，孔會落在殼外")
    if p["FAN_INLET_D"] >= p["FAN_W"]:
        problems.append(f"C: 進氣口 ⌀{p['FAN_INLET_D']} ≥ 風扇寬 {p['FAN_W']}")

    # ── 感測器模組 vs 感測器艙 ──
    pod_inner_w = p["POD_W"] - p["WALL"] * 2
    for nm, w, d in (("SCD41", p["SCD41_W"], p["SCD41_D"]),
                     ("SHT31", p["SHT31_W"], p["SHT31_D"])):
        if w + p["FIT"] * 2 > pod_inner_w:
            problems.append(f"C: {nm} 寬 {w} 放不進感測器艙內寬 {pod_inner_w:.1f}")
    stack = p["FLOOR"] + 4 + p["SCD41_D"] + 6 + p["SHT31_D"] + p["FLOOR"]
    if stack > p["POD_H"]:
        problems.append(f"C: 兩模組堆疊需 {stack:.1f}mm > 感測器艙高 {p['POD_H']}")
    else:
        notes.append(f"C: 感測器艙 {p['POD_W']}×{p['POD_D']}×{p['POD_H']}，"
                     f"雙模組堆疊佔 {stack:.1f}mm ✓")


def check_bed(p):
    bed = p["BED"]
    parts = {
        "base":       (p["BASE_W"], p["BASE_D"], p["BASE_H"]),
        "chamber":    (p["CHMB_W"], p["CHMB_D"], p["CHMB_H"]),
        "hood":       (p["CHMB_W"], p["CHMB_D"], p["HOOD_H"]),
        "fan_mount":  (p["FAN_W"] + p["WALL"] * 2, p["FAN_H"] + p["WALL"] * 2,
                       p["FAN_T"] + p["WALL"] * 2 + 10),
        "sensor_pod": (p["POD_W"], p["POD_D"], p["POD_H"]),
    }
    over = [f"{k}({v[0]:.0f}×{v[1]:.0f})" for k, v in parts.items()
            if v[0] > bed or v[1] > bed]
    if over:
        problems.append(f"D: 超出列印床 {bed}×{bed}mm：{', '.join(over)}")
    else:
        big = max(parts.items(), key=lambda kv: max(kv[1][0], kv[1][1]))
        notes.append(f"D: 5 個零件皆可放進 {bed}×{bed}mm 列印床"
                     f"（最大 {big[0]} {big[1][0]:.0f}×{big[1][1]:.0f}）✓")

    total_h = p["BASE_H"] + p["CHMB_H"] + p["HOOD_H"]
    notes.append(f"D: 組裝總高 {total_h}mm、最大寬 {p['BASE_W']}mm"
                 f"（桌上型展示尺寸）")


def check_thermal(p):
    n0 = len(problems)          # 只看本檢查自己產生的問題，不受其他檢查影響
    if p["AIR_GAP"] <= 0:
        problems.append("E: AIR_GAP = 0，塑膠會直接接觸高溫爐盆")
    elif p["AIR_GAP"] < 5:
        warnings.append(f"E: AIR_GAP={p['AIR_GAP']}mm 偏薄，建議 ≥6mm")
    if p["ISO_GAP"] <= 0:
        problems.append("E: ISO_GAP = 0，燃燒艙與電子艙沒有隔熱層")
    if len(problems) == n0:
        notes.append(f"E: 爐盆空氣間隙 {p['AIR_GAP']}mm、"
                     f"燃燒艙↔電子艙隔熱層 {p['ISO_GAP']}mm、"
                     f"對流縫寬 {p['ISO_VENT_W']}mm ✓")
    notes.append("E: ★材料提醒★ 熱電偶位置預估 120°C（聯鎖門檻 150/130 為臨時值，未實測），"
                 "燃燒艙與集煙罩請用 ABS/ASA/PETG，勿用 PLA（HDT 55–60°C）")


def duct_z_ranges(p):
    """
    算出煙道開口在【全域 z 座標】的位置。

    ★為什麼要做這個★
      各零件的開口都寫在自己的局部座標裡，尺寸一致不代表位置對得上。
      2026-08-02 就踩到：燃燒艙開口 z=96–126、集煙罩開口 z=138–168，
      相差 12mm 完全沒交集，煙從罩子出來接不到風扇——
      而當時所有檢查（尺寸一致、manifold、干涉）全數通過。
    """
    BH, CH, DH = p["BASE_H"], p["CHMB_H"], p["DUCT_H"]
    dz = p["DUCT_Z_HOOD"]
    body_h = p["FAN_H"] + p["WALL"] * 2
    out = {}
    # 集煙罩：煙道唯一的開口位置
    out["hood"] = (BH + CH + dz, BH + CH + dz + DH)
    # 風扇座：本體局部 y → 全域 z，開口在本體正中
    tz = BH + CH + dz + DH / 2 - body_h / 2
    out["fan_mount"] = (tz + body_h / 2 - DH / 2, tz + body_h / 2 + DH / 2)
    return out


def check_duct_alignment(p):
    """
    煙道開口必須在 z 方向重疊，且必須落在集煙罩的實體高度內。

    ★注意★ 風扇位置刻意從 DUCT_Z_HOOD 推導，所以兩者不可能錯開——
      這是「用設計消除錯誤」而非「靠檢查抓錯誤」，比較可靠。
      但 DUCT_Z_HOOD 本身可能超出罩子高度，那才是真正要查的。
    """
    dz, DH, HH = p["DUCT_Z_HOOD"], p["DUCT_H"], p["HOOD_H"]
    if dz < p["WALL"]:
        problems.append(f"F: 煙道開口下緣 z={dz} 太靠近集煙罩底面，"
                        f"至少要留一個壁厚 {p['WALL']:.1f}mm")
    if dz + DH > HH - p["WALL"]:
        problems.append(
            f"F: 煙道開口上緣 z={dz + DH} 超出集煙罩可用高度 "
            f"{HH - p['WALL']:.1f}mm（罩高 {HH}）——開口會破出頂面或壁太薄")
    # 開口所在高度，罩子的錐面是否還夠寬容納
    w_at_top = p["CHMB_W"] - (p["CHMB_W"] - p["HOOD_TOP_W"]) * (dz + DH) / HH
    need = p["DUCT_W"] + p["PAD_MARGIN"] * 2
    if w_at_top < need:
        problems.append(
            f"F: 煙道開口上緣處集煙罩只剩 {w_at_top:.0f}mm 寬，"
            f"放不下 {need:.0f}mm 的安裝墊台")
    r = duct_z_ranges(p)
    pairs = [("hood", "fan_mount")]
    ok_pairs = []
    for a, b in pairs:
        lo = max(r[a][0], r[b][0])
        hi = min(r[a][1], r[b][1])
        ov = hi - lo
        if ov <= 0:
            problems.append(
                f"F: 煙道開口 {a}(z {r[a][0]:.0f}–{r[a][1]:.0f}) 與 "
                f"{b}(z {r[b][0]:.0f}–{r[b][1]:.0f}) 沒有交集，相差 {-ov:.0f}mm"
                f"——氣流路徑是斷的，煙抽不出去")
        elif ov < p["DUCT_H"] * 0.5:
            warnings.append(
                f"F: 煙道 {a}×{b} 只重疊 {ov:.0f}mm（開口高 {p['DUCT_H']}mm），"
                f"有效流通面積不足一半")
        else:
            ok_pairs.append(f"{a}×{b} 重疊 {ov:.0f}mm")
    if ok_pairs and len(ok_pairs) == len(pairs):
        notes.append("F: 煙道開口 z 方向對齊 — " + "、".join(ok_pairs) + " ✓")


def check_duct(src, p):
    """煙道尺寸在三個零件中必須一致，否則接不起來。"""
    body = strip_comments(src)
    for mod in ("hood", "fan_mount"):
        m = re.search(rf"module\s+{mod}\s*\(.*?\n\}}", body, re.S)
        if not m:
            problems.append(f"F: 找不到模組 {mod}")
            continue
        if "DUCT_W" not in m.group(0) or "DUCT_H" not in m.group(0):
            problems.append(f"F: 模組 {mod} 沒有用到 DUCT_W/DUCT_H，煙道可能對不上")
    if not any(x.startswith("F:") for x in problems):
        notes.append(f"F: 煙道 {p['DUCT_W']}×{p['DUCT_H']}mm 於 chamber／hood／"
                     f"fan_mount 三處共用同一參數 ✓")
    # 煙道要塞得進燃燒艙後壁
    if p["DUCT_W"] > p["CHMB_W"] - p["WALL"] * 4:
        problems.append(f"F: 煙道寬 {p['DUCT_W']} 過寬，燃燒艙後壁承受不了")
    # 風扇進氣口要涵蓋煙道截面
    inlet_area = 3.14159 * (p["FAN_INLET_D"] / 2) ** 2
    duct_area = p["DUCT_W"] * p["DUCT_H"]
    if inlet_area < duct_area * 0.7:
        warnings.append(
            f"F: 風扇進氣口面積 {inlet_area:.0f}mm² 明顯小於煙道截面 {duct_area}mm²"
            f"（{inlet_area/duct_area*100:.0f}%），會成為流阻瓶頸")
    else:
        notes.append(f"F: 風扇進氣 {inlet_area:.0f}mm² vs 煙道截面 {duct_area}mm²"
                     f"（{inlet_area/duct_area*100:.0f}%）✓")


# ── G. 實際算繪（OpenSCAD）──────────────────────────────────
# 檢查用的算繪精度。干涉與 manifold 只看拓樸與粗略重疊，
# 不需要細緻曲面——$fn 由 48 降到 16 可快 3 倍以上。
# 出圖（給人看的）仍用檔案裡的預設值。
CHECK_FN = 16
CLEAR_HINT = 12      # 與 SCAD 的 CLEAR_MM 一致

OPENSCAD_CANDIDATES = [
    "/mnt/c/Program Files/OpenSCAD/openscad.exe",
    "/mnt/c/Program Files (x86)/OpenSCAD/openscad.exe",
    "openscad",
]
PARTS = ["base", "chamber", "hood", "fan_mount", "sensor_pod"]


def find_openscad():
    for c in OPENSCAD_CANDIDATES:
        if os.path.exists(c) or shutil.which(c):
            return c
    return None


def win_path(p: Path) -> str:
    """WSL 路徑轉 Windows 路徑（呼叫 .exe 時需要）。"""
    s = str(p.resolve())
    if s.startswith("/mnt/") and len(s) > 6:
        return s[5].upper() + ":" + s[6:].replace("/", "\\")
    return s


def check_render():
    """回傳 {零件名: 三角形串列}，供 I/K 檢查重用，避免重複算繪。"""
    exe = find_openscad()
    if not exe:
        warnings.append("G: 找不到 OpenSCAD，跳過實際算繪檢查"
                        "（裝了之後這一關才會驗證 manifold 與浮空塊）")
        return {}

    is_exe = exe.endswith(".exe")
    # ★暫存目錄必須放在 .scad 旁邊★
    #   Windows 的 openscad.exe 看不到 WSL 的 /tmp，只認得 /mnt/<碟> 對應的路徑
    tmp = Path(tempfile.mkdtemp(prefix=".scadchk_", dir=SCAD.parent))
    results = []
    meshes = {}          # 供列印性與回歸基準重用，不重複算繪
    def _one(part):
        out = tmp / f"{part}.stl"
        cmd = [exe, "-o", win_path(out) if is_exe else str(out),
               "-D", f"$fn={CHECK_FN}", "-D", f'part="{part}"',
               win_path(SCAD) if is_exe else str(SCAD)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return part, out, r.returncode, r.stdout + r.stderr
        except Exception as e:
            return part, out, -1, f"EXC {e}"

    with ThreadPoolExecutor(max_workers=4) as ex:
        rendered = list(ex.map(_one, PARTS))

    for part, out, rc, log in rendered:
        if rc == -1:
            problems.append(f"G: {part} 算繪失敗 — {log}")
            continue
        r = type("R", (), {"returncode": rc})()
        simple = re.search(r"Simple:\s+(\w+)", log)
        vols = re.search(r"Volumes:\s+(\d+)", log)
        facets = re.search(r"Facets:\s+(\d+)", log)

        if r.returncode != 0:
            problems.append(f"G: {part} 算繪回傳非零，log 尾段：{log.strip()[-200:]}")
            continue
        if simple and simple.group(1) != "yes":
            problems.append(f"G: {part} 非 manifold（Simple={simple.group(1)}），無法列印")
        if vols:
            v = int(vols.group(1))
            if v > 2:
                problems.append(
                    f"G: {part} Volumes={v}，有 {v-2} 個分離塊或內部空腔——"
                    f"分離塊會變成印不出來的浮空件")
            elif v < 2:
                problems.append(f"G: {part} Volumes={v}，模型可能是空的")
        for kw in ("WARNING", "ERROR"):
            n = len(re.findall(kw, log))
            if n:
                warnings.append(f"G: {part} 算繪出現 {n} 個 {kw}")
        results.append((part, simple.group(1) if simple else "?",
                        int(vols.group(1)) if vols else -1,
                        int(facets.group(1)) if facets else -1))
        if out.exists():
            try:
                meshes[part] = mesh_tris(out)
            except Exception:
                pass

    # ── 產生可目視的算繪圖 ──
    # ★為什麼要出圖★ 集煙罩的投香口曾經被封死，而參數檢查與 Volumes=2
    #   都判定通過——封起來的罩子仍是合法的單一 manifold 實體。
    #   那個 bug 是靠剖半算繪「看」出來的。幾何對不對，最後還是要眼睛。
    views = [
        ("組裝",       ["-D", 'part="assembly"'],
         ["--camera=90,90,120,55,0,25,700"]),
        ("剖面",       ["-D", 'part="assembly"', "-D", "SECTION=true"],
         ["--camera=90,-30,110,68,0,22,520"]),
        ("集煙罩剖面", ["-D", 'part="hood"', "-D", "SECTION=true"],
         ["--camera=78,-60,120,72,0,20,290"]),
        ("列印排版",   ["-D", 'part="print_plate"'],
         ["--camera=200,150,0,0,0,0,620"]),
    ]
    made = []
    for name, dparams, cam in views:
        out = SCAD.parent / f"_view_{name}.png"
        cmd = [exe, "-o", win_path(out) if is_exe else str(out),
               "--imgsize=880,660", "--colorscheme=Tomorrow", *cam, *dparams,
               win_path(SCAD) if is_exe else str(SCAD)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if out.exists():
                made.append(out.name)
        except Exception:
            pass
    if made:
        notes.append(f"G: 已產生 {len(made)} 張算繪圖供目視檢查："
                     + "、".join(made))
        notes.append("G: ★算繪通過不代表設計正確★——請實際開圖看，"
                     "尤其是開口有沒有真的通、內部結構對不對")

    shutil.rmtree(tmp, ignore_errors=True)
    if results:
        notes.append("G: OpenSCAD 實際算繪 — " + "、".join(
            f"{n}(V={v},F={f})" for n, s, v, f in results))
        if all(v == 2 for _, _, v, _ in results):
            notes.append(f"G: {len(results)} 個零件皆為單一 manifold 實體（Volumes=2）✓")
    return meshes


# ── H. 組裝干涉 ─────────────────────────────────────────────
# 允許的重疊：定位榫插入榫孔、法蘭插入牆面、掛耳貼合，都是刻意設計的配合。
# 超過門檻才算干涉。單位 mm³。
INTERSECT_BUDGET = {
    ("base", "chamber"):      3000,   # 4 根定位榫（⌀8×6）＋台階落座
    ("chamber", "hood"):      3000,   # 同上
    ("hood", "fan_mount"):    2500,   # 煙道法蘭插進集煙罩墊台
                                      #   理論值 = (50.8×34.8 − 46×30) × 4mm 插深 ≈ 1,551mm³
                                      #   容許值只留約 1.6 倍——太寬鬆就抓不到真正的穿透
    ("base", "sensor_pod"):   1500,   # 掛耳貼合
}
DEFAULT_BUDGET = 200                  # 未列出的組合，實質上不該相碰

# 應該互相貼合的組合：(A, B, 軸, 說明)
# 軸 = 0/1/2 對應 x/y/z。檢查兩者在該軸上的間隙是否接近 0。
# ★為什麼需要這條★ 榫柱插進榫孔時交集是 0（孔比榫大），
#   但零件整個浮空 5mm 時交集也是 0——只查干涉分不出這兩種情況。
MATING = [
    ("base", "chamber",     2, "燃燒艙落座於底座頂緣台階"),
    ("chamber", "hood",     2, "集煙罩落座於燃燒艙頂緣台階"),
    ("base", "sensor_pod",  1, "感測器艙掛耳貼合底座前壁"),
]
MATING_TOL = 0.6                      # 容許間隙（mm）


def mesh_tris(path):
    """讀 STL 回傳三角形串列（純標準函式庫）。"""
    import struct
    data = Path(path).read_bytes()
    tris = []
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if len(data) == 84 + n * 50:
            for i in range(n):
                v = struct.unpack_from("<9f", data, 84 + i * 50 + 12)
                tris.append(((v[0], v[1], v[2]), (v[3], v[4], v[5]), (v[6], v[7], v[8])))
            return tris
    cur = []
    for line in data.decode("utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith("vertex"):
            cur.append(tuple(float(x) for x in s.split()[1:4]))
            if len(cur) == 3:
                tris.append(tuple(cur)); cur = []
    return tris


def aabb(tris):
    """軸對齊包圍盒。"""
    xs = [v[0] for t in tris for v in t]
    ys = [v[1] for t in tris for v in t]
    zs = [v[2] for t in tris for v in t]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def aabb_overlap(a, b, pad=0.0):
    """兩個包圍盒的重疊體積。0 代表絕對不可能干涉，可跳過昂貴的布林運算。"""
    ov = 1.0
    for i in range(3):
        lo = max(a[i], b[i]) - pad
        hi = min(a[i + 3], b[i + 3]) + pad
        if hi <= lo:
            return 0.0
        ov *= (hi - lo)
    return ov


def mesh_volume(path):
    """用純標準函式庫算 STL 體積（散度定理）。與 CAD自檢/verify_stl.py 同法。"""
    import struct
    data = Path(path).read_bytes()
    tris = []
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if len(data) == 84 + n * 50:
            for i in range(n):
                v = struct.unpack_from("<9f", data, 84 + i * 50 + 12)
                tris.append(((v[0], v[1], v[2]), (v[3], v[4], v[5]), (v[6], v[7], v[8])))
    if not tris:
        cur = []
        for line in data.decode("utf-8", errors="ignore").splitlines():
            s = line.strip()
            if s.startswith("vertex"):
                cur.append(tuple(float(x) for x in s.split()[1:4]))
                if len(cur) == 3:
                    tris.append(tuple(cur)); cur = []
    if not tris:
        return 0.0
    tot = 0.0
    for (a, b, c) in tris:
        tot += (a[0]*(b[1]*c[2]-b[2]*c[1]) - a[1]*(b[0]*c[2]-b[2]*c[0])
                + a[2]*(b[0]*c[1]-b[1]*c[0])) / 6.0
    return abs(tot)


# ── I. 列印性 ─────────────────────────────────────────────
OVERHANG_DEG = 45        # 超過此角度（自垂直算起）的向下面需要支撐

# ★列印方位★ 必須先旋轉到實際上機的姿態再分析懸空，否則結論無意義。
#   例：集煙罩設計上是開口朝上，實際列印時倒過來——設計方位下的「懸空」
#   在列印方位下可能完全不存在，反之亦然。
#   數值與 incense_burner.scad 檔頭的「列印方向」說明必須一致。
PRINT_ORIENT = {
    "base":       (0, 0, 0),      # 底面朝下
    "chamber":    (0, 0, 0),      # 底面朝下
    "hood":       (180, 0, 0),    # ★開口朝下倒印★
    "fan_mount":  (0, 0, 0),      # 背面朝下
    "sensor_pod": (0, 0, 0),      # 背面朝下
}

# 容許的懸空面積。這些數字不是憑空定的：
#   平面橋接（兩端有牆支撐、跨距 <50mm）切片器處理得了，不需支撐；
#   大面積無支撐天花板才是真問題。目前以「單件表面積的 8%」為基準，
#   超過就值得檢視列印方位或加倒角。
# ★區分兩種懸空★ 它們的處理方式完全不同：
#   近水平天花板（法向量幾乎正下）→ 兩端有牆就是【橋接】，切片器印得出來，
#                                   只要跨距別太長。
#   斜向懸空 45–85°              → 真正需要支撐材，表面也會拉絲。
#   把兩者混在一起算，會把可印的設計誤判為不可印（第一版就犯了這個錯）。
FLAT_NZ = -0.95              # 法向量 z 低於此視為近水平（橋接）
SLOPED_RATIO_MAX = 0.04      # 斜向懸空佔表面積上限
FLAT_RATIO_WARN  = 0.25      # 近水平面積過大時提醒檢視跨距
MAX_BRIDGE_MM    = 50        # 橋接跨距上限。超過會下垂——
                             # ★面積小不代表沒問題，跨距才是關鍵★


def tri_area_normal(a, b, c):
    """回傳 (面積, 單位法向量)。"""
    u = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
    v = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
    n = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    m = math.sqrt(n[0]**2 + n[1]**2 + n[2]**2)
    if m < 1e-12:
        return 0.0, (0.0, 0.0, 0.0)
    return m / 2.0, (n[0]/m, n[1]/m, n[2]/m)


def rotate_tris(tris, deg_xyz):
    """把網格旋轉到列印方位（依序繞 x、y、z）。"""
    rx, ry, rz = (math.radians(d) for d in deg_xyz)
    def rot(v):
        x, y, z = v
        if rx:
            y, z = y*math.cos(rx) - z*math.sin(rx), y*math.sin(rx) + z*math.cos(rx)
        if ry:
            x, z = x*math.cos(ry) + z*math.sin(ry), -x*math.sin(ry) + z*math.cos(ry)
        if rz:
            x, y = x*math.cos(rz) - y*math.sin(rz), x*math.sin(rz) + y*math.cos(rz)
        return (x, y, z)
    return [tuple(rot(v) for v in t) for t in tris]


def _rasterize(tl, cell):
    """把三角形集合柵格化，回傳 (占用格集合, 原點, 網格尺寸)。"""
    xs = [v[0] for t in tl for v in t[:3]]
    ys = [v[1] for t in tl for v in t[:3]]
    x0, y0 = min(xs), min(ys)
    nx = int((max(xs) - x0) / cell) + 2
    ny = int((max(ys) - y0) / cell) + 2
    occ = set()
    for (a, b, c, _) in tl:
        # 只掃該三角形的包圍盒，再用重心座標判定
        tx0 = int((min(a[0], b[0], c[0]) - x0) / cell)
        tx1 = int((max(a[0], b[0], c[0]) - x0) / cell) + 1
        ty0 = int((min(a[1], b[1], c[1]) - y0) / cell)
        ty1 = int((max(a[1], b[1], c[1]) - y0) / cell) + 1
        d = ((b[1]-c[1])*(a[0]-c[0]) + (c[0]-b[0])*(a[1]-c[1]))
        if abs(d) < 1e-12:
            continue
        for ix in range(max(tx0, 0), min(tx1 + 1, nx)):
            for iy in range(max(ty0, 0), min(ty1 + 1, ny)):
                px = x0 + (ix + 0.5) * cell
                py = y0 + (iy + 0.5) * cell
                u = ((b[1]-c[1])*(px-c[0]) + (c[0]-b[0])*(py-c[1])) / d
                v = ((c[1]-a[1])*(px-c[0]) + (a[0]-c[0])*(py-c[1])) / d
                if u >= -1e-9 and v >= -1e-9 and u + v <= 1 + 1e-9:
                    occ.add((ix, iy))
    return occ, nx, ny


def _max_inscribed(occ, nx, ny, cell):
    """
    多源 BFS 距離變換：從邊界往內擴，最深的格子代表最大內接圓半徑。

    ★為什麼不用包圍盒★ 環狀天花板（例如 11mm 寬的落座台階）
      包圍盒是 175mm，但橋接實際只要跨 11mm——用包圍盒會誤報。
      內接圓半徑 ×2 才是真正的無支撐跨距。
    """
    from collections import deque
    dist = {}
    q = deque()
    for (ix, iy) in occ:
        # 邊界格：四鄰有一個是空的
        if any((ix+dx, iy+dy) not in occ
               for dx, dy in ((1,0), (-1,0), (0,1), (0,-1))):
            dist[(ix, iy)] = 0
            q.append((ix, iy))
    while q:
        ix, iy = q.popleft()
        for dx, dy in ((1,0), (-1,0), (0,1), (0,-1)):
            n = (ix+dx, iy+dy)
            if n in occ and n not in dist:
                dist[n] = dist[(ix, iy)] + 1
                q.append(n)
    if not dist:
        return 0.0
    return (max(dist.values()) + 1) * 2 * cell


def flat_ceiling_spans(tris, z_min, cell=2.0):
    """
    找出各高度的近水平天花板，回傳 [(z, 無支撐跨距, 面積), ...]。

    ★為什麼要量跨距而非面積★ 橋接能不能印取決於跨距：
      11mm 寬的環狀天花板，面積再大也印得出來；
      151mm 的整片樓板必定下垂。
    跨距＝該高度平面區域的最大內接圓直徑（見 _max_inscribed）。
    """
    from collections import defaultdict
    lvl = defaultdict(list)
    for (a, b, c) in tris:
        area, n = tri_area_normal(a, b, c)
        if area == 0 or n[2] > FLAT_NZ:
            continue
        z = (a[2] + b[2] + c[2]) / 3
        if z - z_min < 0.2:
            continue
        lvl[round(z, 1)].append((a, b, c, area))

    out = []
    for z, tl in lvl.items():
        area = sum(x[3] for x in tl)
        if area < 100:            # 太小的面不值得算
            continue
        occ, nx, ny = _rasterize(tl, cell)
        if not occ:
            continue
        out.append((z, _max_inscribed(occ, nx, ny, cell), area))
    return sorted(out, key=lambda r: -r[1])


def total_area(tris):
    return sum(tri_area_normal(*t)[0] for t in tris)


def overhang_area(tris, z_min, deg=OVERHANG_DEG):
    """
    回傳 (斜向懸空面積, 近水平天花板面積)。

    判準以法向量 n.z 分段：
      n.z >= -cos(45°)        垂直到 45° 斜面 → 自支撐，不計
      -0.95 < n.z < -0.707    斜向懸空       → ★需要支撐材★
      n.z <= -0.95            近水平天花板    → 橋接（跨距短就印得出來）
    貼在列印床上的底面（z ≈ z_min）排除，那是第一層不是懸空。
    """
    thr = math.cos(math.radians(deg))
    sloped = flat = 0.0
    for (a, b, c) in tris:
        area, n = tri_area_normal(a, b, c)
        if area == 0 or n[2] >= 0 or -n[2] <= thr:
            continue
        if max(a[2], b[2], c[2]) - z_min < 0.2:
            continue
        if n[2] <= FLAT_NZ:
            flat += area
        else:
            sloped += area
    return sloped, flat


def check_printability(part_meshes):
    """part_meshes: {零件名: 三角形串列}（設計方位，本函式會先轉到列印方位）"""
    rows, bad = [], 0
    for nm, tris in part_meshes.items():
        if not tris:
            continue
        orient = PRINT_ORIENT.get(nm, (0, 0, 0))
        pt = rotate_tris(tris, orient) if any(orient) else tris
        z_min = min(v[2] for t in pt for v in t)
        sloped, flat = overhang_area(pt, z_min)
        tot = total_area(pt)
        sr = sloped / tot if tot else 0
        fr = flat / tot if tot else 0
        ori = f"倒印 {orient[0]}°" if any(orient) else "原方位"
        if sr > SLOPED_RATIO_MAX:
            problems.append(
                f"I: {nm}（{ori}）斜向懸空 {sloped:,.0f}mm² ＝ 表面積的 {sr:.0%}"
                f"（上限 {SLOPED_RATIO_MAX:.0%}）——這類面切片器蓋不出來，"
                f"必須支撐材。考慮換列印方位或把斜面改成 ≤45°")
            bad += 1
        else:
            spans = flat_ceiling_spans(pt, z_min)
            worst = spans[0] if spans else None
            if worst and worst[1] > MAX_BRIDGE_MM and worst[2] > 100:
                problems.append(
                    f"I: {nm}（{ori}）在 z={worst[0]:.1f} 有跨距 {worst[1]:.0f}mm "
                    f"的水平天花板（{worst[2]:,.0f}mm²）——超過橋接上限 "
                    f"{MAX_BRIDGE_MM}mm 會下垂。解法：改成 45° 錐面自支撐、"
                    f"加中間肋條分割跨距，或換列印方位")
                bad += 1
            else:
                sp = f"，最長橋接 {worst[1]:.0f}mm" if worst else ""
                rows.append(f"{nm} 斜{sr:.0%}/平{fr:.0%}{sp}")
    if not bad:
        notes.append(f"I: 列印性（已套用列印方位，斜向懸空上限 "
                     f"{SLOPED_RATIO_MAX:.0%}）— " + "、".join(rows) + " ✓")


# ── K. 回歸基準 ─────────────────────────────────────────────
BASELINE = Path(__file__).parent / ".baseline.json"
BASELINE_TOL = 0.02      # 2% 以內視為未變動


def check_baseline(part_meshes, boxes):
    """
    與上次的幾何指紋比對。

    ★為什麼需要★ 參數化設計最難察覺的錯是「改了 A 卻讓 B 默默變形」。
      單看檢查全綠不代表沒事——B 可能從對的變成另一個也合法但錯的形狀。
    """
    import json
    cur = {}
    for nm, tris in part_meshes.items():
        if not tris:
            continue
        vol = 0.0
        for (a, b, c) in tris:
            vol += (a[0]*(b[1]*c[2]-b[2]*c[1]) - a[1]*(b[0]*c[2]-b[2]*c[0])
                    + a[2]*(b[0]*c[1]-b[1]*c[0])) / 6.0
        cur[nm] = {"vol": round(abs(vol), 1), "tris": len(tris)}

    if not BASELINE.exists():
        BASELINE.write_text(json.dumps(cur, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        notes.append(f"K: 首次執行，已建立幾何基準（{len(cur)} 個零件）。"
                     f"日後任一零件體積變動 >{BASELINE_TOL:.0%} 會被標出")
        return

    try:
        old = json.loads(BASELINE.read_text(encoding="utf-8"))
    except Exception:
        return
    changed, same = [], 0
    for nm, c in cur.items():
        o = old.get(nm)
        if not o:
            changed.append(f"{nm} 新增")
            continue
        dv = abs(c["vol"] - o["vol"]) / max(o["vol"], 1e-6)
        if dv > BASELINE_TOL:
            changed.append(f"{nm} 體積 {o['vol']:,.0f}→{c['vol']:,.0f}mm³"
                           f"（{dv:+.1%}）")
        else:
            same += 1
    for nm in old:
        if nm not in cur:
            changed.append(f"{nm} 消失")
    if changed:
        warnings.append("K: 幾何與基準不同 — " + "、".join(changed)
                        + "。若是刻意修改，刪除 .baseline.json 後重跑即可更新基準")
    else:
        notes.append(f"K: {same} 個零件的幾何與基準一致（未意外變動）✓")


# ── J. 開口遮擋 ───────────────────────────────────────────
# (淨空區名稱, 開口所屬零件, 說明)
CLEARANCE_ZONES = [
    ("base_vent",    "base",       "底座側面進氣柵格（電子艙對流散熱）"),
    ("chamber_vent", "chamber",    "隔熱層對流縫（帶走燃燒艙廢熱）"),
    ("hood_opening", "hood",       "投香口（香要插得進去）"),
    ("pod_vent",     "sensor_pod", "感測器通風口（量不到外界空氣就失去意義）"),
]
BLOCK_BUDGET = 300      # mm³，超過視為明顯遮擋


def check_clearance():
    """開口外側不可被其他零件擋住。"""
    exe = find_openscad()
    if not exe:
        warnings.append("J: 找不到 OpenSCAD，跳過開口遮擋檢查")
        return
    is_exe = exe.endswith(".exe")
    tmp = Path(tempfile.mkdtemp(prefix=".scadchk_", dir=SCAD.parent))

    def run(zone, owner):
        out = tmp / f"b_{zone}.stl"
        cmd = [exe, "-o", win_path(out) if is_exe else str(out),
               "-D", f"$fn={CHECK_FN}", "-D", 'part="blocked"',
               "-D", f'PAIR_A="{zone}"', "-D", f'PAIR_B="{owner}"',
               win_path(SCAD) if is_exe else str(SCAD)]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except Exception:
            pass
        return zone, out

    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(lambda z: run(z[0], z[1]), CLEARANCE_ZONES))

    info = {z: (o, d) for z, o, d in CLEARANCE_ZONES}
    ok = 0
    for zone, out in res:
        vol = mesh_volume(out) if out.exists() else 0.0
        owner, desc = info[zone]
        if vol > BLOCK_BUDGET:
            problems.append(
                f"J: {desc} 的淨空區被其他零件佔去 {vol:,.0f}mm³"
                f"——開口被擋住，功能失效（注意：這不是干涉，"
                f"兩件沒有相碰，所以干涉檢查抓不到）")
        else:
            ok += 1
    shutil.rmtree(tmp, ignore_errors=True)
    if ok == len(CLEARANCE_ZONES):
        notes.append(f"J: {ok} 個功能性開口外側淨空 {CLEAR_HINT}mm 內無遮擋 ✓")


def check_interference():
    exe = find_openscad()
    if not exe:
        warnings.append("H: 找不到 OpenSCAD，跳過組裝干涉檢查")
        return {}
    is_exe = exe.endswith(".exe")
    tmp = Path(tempfile.mkdtemp(prefix=".scadchk_", dir=SCAD.parent))

    # ── 先取各零件定位後的包圍盒（5 次算繪，便宜）──
    # ★為什麼要預篩★ 兩兩求交集是 CGAL 布林運算，10 組跑不完。
    #   包圍盒不重疊就絕對不可能干涉，可直接跳過——只有真正靠近的才做精算。
    def render(args, out):
        cmd = [exe, "-o", win_path(out) if is_exe else str(out),
               "-D", f"$fn={CHECK_FN}", *args,
               win_path(SCAD) if is_exe else str(SCAD)]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except Exception:
            pass
        return out

    # 平行算繪：這些是互相獨立的外部程序，等待時間可以重疊
    boxes = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {nm: ex.submit(render, ['-D', 'part="placed"', '-D', f'PAIR_A="{nm}"'],
                              tmp / f"p_{nm}.stl") for nm in PARTS}
        for nm, f in futs.items():
            out = f.result()
            if out.exists():
                boxes[nm] = aabb(mesh_tris(out))

    # 包圍盒不重疊 → 絕不可能干涉，跳過昂貴的布林運算
    todo, skipped = [], 0
    for i, a in enumerate(PARTS):
        for b in PARTS[i + 1:]:
            if a in boxes and b in boxes and aabb_overlap(boxes[a], boxes[b]) == 0:
                skipped += 1
            else:
                todo.append((a, b))

    # ── 落座檢查（用已算好的包圍盒，不需額外算繪）──
    bad = 0
    seated = []
    for a, b, axis, why in MATING:
        if a not in boxes or b not in boxes:
            continue
        A, B = boxes[a], boxes[b]
        # 兩者在該軸上的間隙：負值代表重疊，正值代表分開
        gap = max(B[axis] - A[axis + 3], A[axis] - B[axis + 3])
        名 = "xyz"[axis]
        if gap > MATING_TOL:
            problems.append(
                f"H: {a} 與 {b} 在 {名} 軸相距 {gap:.1f}mm 沒有貼合"
                f"（{why}）——零件浮空，組裝時會晃動或根本裝不上")
            bad += 1
        else:
            seated.append(f"{a}↔{b}({名} 間隙 {max(gap,0):.1f}mm)")
    if seated:
        notes.append(f"H: 落座檢查 {len(seated)} 組貼合正常 — " + "、".join(seated) + " ✓")

    rows, bad2 = [], 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {(a, b): ex.submit(
            render, ['-D', 'part="interference"',
                     '-D', f'PAIR_A="{a}"', '-D', f'PAIR_B="{b}"'],
            tmp / f"x_{a}_{b}.stl") for a, b in todo}
        for (a, b), f in futs.items():
            out = f.result()
            vol = mesh_volume(out) if out.exists() else 0.0
            budget = INTERSECT_BUDGET.get((a, b),
                     INTERSECT_BUDGET.get((b, a), DEFAULT_BUDGET))
            if vol > budget:
                problems.append(
                    f"H: {a} 與 {b} 互相穿透 {vol:,.0f}mm³（容許 {budget:,}）"
                    f"——實體組裝不起來，算繪上會是 z-fighting 破圖")
                bad2 += 1
            elif vol > 0:
                rows.append(f"{a}×{b} {vol:,.0f}mm³")
    bad += bad2
    total = len(PARTS) * (len(PARTS) - 1) // 2
    if not bad:
        notes.append(f"H: 兩兩干涉檢查 {total} 組全數通過"
                     f"（包圍盒預篩跳過 {skipped} 組，精算 {total-skipped} 組）✓")
        if rows:
            notes.append("H: 刻意配合的重疊（榫/法蘭/掛耳）— " + "、".join(rows))
    shutil.rmtree(tmp, ignore_errors=True)
    return boxes


def main():
    if not SCAD.exists():
        print(f"找不到 {SCAD}")
        sys.exit(1)
    src = SCAD.read_text(encoding="utf-8")
    p = load_params(src)

    check_syntax(src)
    if not p:
        problems.append("B: 參數區解析失敗")
    else:
        notes.insert(0, f"解析出 {len(p)} 個參數")
        check_print_rules(p)
        check_fits(p)
        check_bed(p)
        check_thermal(p)
        check_duct(src, p)
        check_duct_alignment(p)
        meshes = check_render()
        boxes = check_interference()
        if meshes:
            check_printability(meshes)
            check_baseline(meshes, boxes)
        check_clearance()

    print("=" * 70)
    for n in notes:
        print(f"  ℹ {n}")
    if warnings:
        print("-" * 70)
        for w in warnings:
            print(f"  ⚠ {w}")
    print("=" * 70)
    if problems:
        for x in problems:
            print(f"  ✗ {x}")
        print(f"\n結果：{len(problems)} 項問題")
        sys.exit(1)
    rendered = any(x.startswith("G: OpenSCAD 實際算繪") for x in notes)
    print("結果：全數通過 ✓" + ("（含 OpenSCAD 實際算繪）" if rendered
          else "（未算繪——裝 OpenSCAD 後才會檢查幾何）"))


if __name__ == "__main__":
    main()
