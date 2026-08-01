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

執行：python3 驗證CAD.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
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
    notes.append("E: ★材料提醒★ 爐面常態 60–80°C（聯鎖門檻），"
                 "燃燒艙與集煙罩請用 ABS/ASA/PETG，勿用 PLA（HDT 55–60°C）")


def check_duct(src, p):
    """煙道尺寸在三個零件中必須一致，否則接不起來。"""
    body = strip_comments(src)
    for mod in ("chamber", "hood", "fan_mount"):
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
    exe = find_openscad()
    if not exe:
        warnings.append("G: 找不到 OpenSCAD，跳過實際算繪檢查"
                        "（裝了之後這一關才會驗證 manifold 與浮空塊）")
        return

    is_exe = exe.endswith(".exe")
    # ★暫存目錄必須放在 .scad 旁邊★
    #   Windows 的 openscad.exe 看不到 WSL 的 /tmp，只認得 /mnt/<碟> 對應的路徑
    tmp = Path(tempfile.mkdtemp(prefix=".scadchk_", dir=SCAD.parent))
    results = []
    for part in PARTS:
        out = tmp / f"{part}.stl"
        cmd = [exe, "-o", win_path(out) if is_exe else str(out),
               "-D", f'part="{part}"',
               win_path(SCAD) if is_exe else str(SCAD)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except Exception as e:
            problems.append(f"G: {part} 算繪失敗 — {e}")
            continue
        log = r.stdout + r.stderr
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

    shutil.rmtree(tmp, ignore_errors=True)
    if results:
        notes.append("G: OpenSCAD 實際算繪 — " + "、".join(
            f"{n}(V={v},F={f})" for n, s, v, f in results))
        if all(v == 2 for _, _, v, _ in results):
            notes.append("G: 5 個零件皆為單一 manifold 實體（Volumes=2）✓")


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
        check_render()

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
