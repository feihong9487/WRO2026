#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MATRIX Mini R4 韌體靜態驗證
================================================================
本機無法編譯 Arduino 程式碼，改用靜態檢查抓「編譯得過但行為錯」的問題：

  A. 括號平衡（最基本的語法健檢）
  B. ★門檻值與 pi_fsm.py 一致★
     本地 FSM 是 Pi 失聯時的接手者，門檻若不一致，
     降級瞬間風扇轉速會跳變——這在實機上極難察覺
  C. 腳位不得與 MATRIX 函式庫佔用的腳衝突
     （MiniR4.begin() 內 PS2.config_gamepad(11, 4, 12, 5)）
  D. 輸出的 JSON 格式合法，且欄位涵蓋 pi_fsm.py 與雲端儀表板所需

執行：python3 驗證韌體.py
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
INO = HERE / "matrix_mini_r4.ino"
PI_FSM = HERE.parent.parent / "PI5" / "pi_fsm.py"

# MiniR4.begin() 內 PS2.config_gamepad(11, 4, 12, 5) 佔用的腳
PS2_PINS = {11, 4, 12, 5}
# LED.begin(7)、Buzzer.begin(6)
BOARD_PINS = {7, 6}

problems, notes = [], []


def check_braces(src):
    """括號平衡（字串與註解感知）。"""
    depth = {"{": 0, "(": 0}
    pairs = {"}": "{", ")": "("}
    i, n = 0, len(src)
    in_s = in_c = in_lc = in_bc = False
    while i < n:
        c, nxt = src[i], src[i + 1] if i + 1 < n else ""
        if in_lc:
            if c == "\n": in_lc = False
        elif in_bc:
            if c == "*" and nxt == "/": in_bc = False; i += 1
        elif in_s:
            if c == "\\": i += 1
            elif c == '"': in_s = False
        elif in_c:
            if c == "\\": i += 1
            elif c == "'": in_c = False
        else:
            if c == "/" and nxt == "/": in_lc = True; i += 1
            elif c == "/" and nxt == "*": in_bc = True; i += 1
            elif c == '"': in_s = True
            elif c == "'": in_c = True
            elif c in depth: depth[c] += 1
            elif c in pairs: depth[pairs[c]] -= 1
        i += 1
    for k, v in depth.items():
        if v != 0:
            problems.append(f"A: {k} 括號不平衡，差 {v}")
    if not any(v for v in depth.values()):
        notes.append("A: 括號平衡 ✓")


def const_ino(src, name):
    m = re.search(rf"^\s*const\s+\w+\s+{re.escape(name)}\s*=\s*([-\d.]+)", src, re.M)
    return float(m.group(1)) if m else None


def const_py(src, name):
    m = re.search(rf"^{re.escape(name)}\s*=\s*([-\d.]+)", src, re.M)
    return float(m.group(1)) if m else None


def check_thresholds(ino, py):
    """本地 FSM 門檻必須與 pi_fsm.py 相同。"""
    pairs = [
        ("CO2_IDLE",     "CO2_IDLE",       1),
        ("T1",           "T1",             1),
        ("T1_EXIT",      "T1_EXIT",        1),
        ("SLOPE_TH",     "SLOPE_TH",       1),
        ("T_LOCK",       None,             None),   # 僅韌體有
        ("T_RELEASE",    None,             None),
        ("PI_TIMEOUT_MS", None,            None),
    ]
    ok = 0
    for cname, pname, _ in pairs:
        cv = const_ino(ino, cname)
        if cv is None:
            problems.append(f"B: 韌體找不到常數 {cname}")
            continue
        if pname is None:
            continue
        pv = const_py(py, pname)
        if pv is None:
            problems.append(f"B: pi_fsm.py 找不到常數 {pname}")
        elif abs(cv - pv) > 1e-9:
            problems.append(f"B: 門檻不一致 {cname}={cv} vs pi_fsm.py {pname}={pv}")
        else:
            ok += 1

    # 秒 vs 毫秒的單位換算
    ino_hold = const_ino(ino, "IDLE_HOLD_MS")
    py_hold = const_py(py, "IDLE_HOLD_S")
    if ino_hold is None or py_hold is None:
        problems.append("B: 找不到 IDLE_HOLD_MS / IDLE_HOLD_S")
    elif abs(ino_hold - py_hold * 1000) > 1e-9:
        problems.append(f"B: IDLE_HOLD_MS={ino_hold} 應為 IDLE_HOLD_S({py_hold})×1000")
    else:
        ok += 1

    # DUTY 表：pi_fsm.py 是 dict，韌體是 localFSM() 的 return 值
    m = re.search(r"DUTY\s*=\s*\{([^}]*)\}", py)
    if m:
        duty = dict(re.findall(r'"(S\d)"\s*:\s*(\d+)', m.group(1)))
        fsm = re.search(r"uint8_t localFSM\(\)(.*?)\n\}", ino, re.S)
        if fsm:
            body = fsm.group(1)
            checks = [("S0", r'strcmp\(localState, "S0"\) == 0\) return (\d+)'),
                      ("S2", r'strcmp\(localState, "S2"\) == 0\) return (\d+)')]
            for st, pat in checks:
                mm = re.search(pat, body)
                if mm and duty.get(st) and mm.group(1) != duty[st]:
                    problems.append(f"B: {st} duty 韌體={mm.group(1)} vs pi_fsm.py={duty[st]}")
                elif mm:
                    ok += 1
            mm = re.search(r"return (\d+);\s*//\s*S1", body)
            if mm and duty.get("S1") and mm.group(1) != duty["S1"]:
                problems.append(f"B: S1 duty 韌體={mm.group(1)} vs pi_fsm.py={duty['S1']}")
            elif mm:
                ok += 1
    notes.append(f"B: 門檻與 pi_fsm.py 逐項比對，{ok} 項一致 ✓")


def check_pins(ino):
    pins = {}
    for m in re.finditer(r"^\s*const\s+int\s+(PIN_\w+)\s*=\s*(\d+)", ino, re.M):
        pins[m.group(1)] = int(m.group(2))
    if not pins:
        problems.append("C: 找不到任何 PIN_ 定義")
        return
    for name, p in pins.items():
        if p in PS2_PINS:
            problems.append(f"C: {name}={p} 與 MiniR4.begin() 的 PS2 手把介面衝突（佔用 11/4/12/5）")
        if p in BOARD_PINS:
            problems.append(f"C: {name}={p} 與板載 LED(7)/蜂鳴器(6) 衝突")
    dup = [p for p in pins.values() if list(pins.values()).count(p) > 1]
    if dup:
        problems.append(f"C: 腳位重複指派 {sorted(set(dup))}")
    # 風扇必須在 PWM 腳上（MATRIX：3=D1左, 5=D2左, 11=D3右, 10=D4右）
    pwm_ok = {3, 5, 11, 10}
    if "PIN_FAN" in pins and pins["PIN_FAN"] not in pwm_ok:
        problems.append(f"C: PIN_FAN={pins['PIN_FAN']} 不是 PWM 腳（可用 {sorted(pwm_ok)}）")
    notes.append("C: 腳位 " + "、".join(f"{k}={v}" for k, v in sorted(pins.items(), key=lambda x: x[1]))
                 + " — 無衝突 ✓")


def check_json(ino):
    """把 Serial.print 串接還原成一行 JSON，驗證格式合法且欄位齊全。"""
    m = re.search(r"Serial\.print\(F\(\"\{\\\"ts.*?Serial\.println\(F\(\"\\\"\}\"\)\);", ino, re.S)
    if not m:
        problems.append("D: 找不到 JSON 輸出區塊")
        return
    block = m.group(0)

    # 逐段解析：字面字串照抄，變數以型別對應的假值代入
    out = []
    fake = {"millis()": "123456", "co2": "815", "outDuty": "70"}
    for mm in re.finditer(r'Serial\.print(?:ln)?\(\s*(.*?)\s*\);', block, re.S):
        arg = mm.group(1)
        fm = re.fullmatch(r'F\("((?:[^"\\]|\\.)*)"\)', arg.strip())
        if fm:
            out.append(fm.group(1).replace('\\"', '"').replace("\\\\", "\\"))
            continue
        dm = re.fullmatch(r'(.+?)\s*,\s*(\d)', arg.strip())
        if dm:
            out.append(f"{1.0:.{int(dm.group(2))}f}")
            continue
        a = arg.strip()
        if a in fake:
            out.append(fake[a])
        elif "?" in a:                       # 三元運算子 → 0/1 或字串
            out.append("0")
        elif a in ("mode",):
            out.append("PI")
        elif a in ("localState",):
            out.append("S1")
        else:
            out.append("0")
    s = "".join(out)

    try:
        obj = json.loads(s)
    except Exception as e:
        problems.append(f"D: 產生的 JSON 不合法 — {e}\n     {s}")
        return

    need_sensor = {"ts", "co2", "slope", "t_scd", "rh_scd", "t_sht", "rh_sht", "conf", "alarm"}
    need_safety = {"t_furnace", "fan", "interlock", "tc_fault", "mode"}
    miss = (need_sensor | need_safety) - set(obj)
    if miss:
        problems.append(f"D: JSON 缺少欄位 {sorted(miss)}")
    else:
        notes.append(f"D: JSON 合法，{len(obj)} 個欄位，感測＋安全欄位齊全 ✓")
        notes.append(f"D: 範例 → {s[:96]}…")


def main():
    if not INO.exists():
        print(f"找不到 {INO}"); sys.exit(1)
    if not PI_FSM.exists():
        print(f"找不到 {PI_FSM}"); sys.exit(1)
    ino = INO.read_text(encoding="utf-8")
    py = PI_FSM.read_text(encoding="utf-8")

    check_braces(ino)
    check_thresholds(ino, py)
    check_pins(ino)
    check_json(ino)

    print("=" * 66)
    for n in notes:
        print(f"  ℹ {n}")
    print("=" * 66)
    if problems:
        for p in problems:
            print(f"  ✗ {p}")
        print(f"\n結果：{len(problems)} 項問題")
        sys.exit(1)
    print("結果：靜態檢查全數通過 ✓（仍需實機編譯與燒錄驗證）")


if __name__ == "__main__":
    main()
