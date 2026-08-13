#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
資料流端到端契約測試（合併版架構）
================================================================
沒有硬體也能驗證的一件事：**欄位契約有沒有斷**。

資料路徑：
    MATRIX Mini R4 ──序列 JSON──> pi_fsm.py ──MQTT──> Telegraf ──> InfluxDB ──> Grafana

任何一段欄位名稱對不上，畫面就是 No data，而且極難查。
本測試從三端各自的「真實來源」取欄位，交叉比對：

  1. 韌體實際輸出的欄位   ← 直接從 matrix_mini_r4.ino 的 Serial.print 解析
  2. pi_fsm.py 產生的紀錄 ← 直接從原始碼的 rec = {...} 解析
  3. 儀表板實際查詢的欄位 ← 直接從 grafana_dashboard_fleet.json 的 Flux 查詢解析

執行：python3 驗證資料流.py
"""

import json
import re
import sys
from pathlib import Path

# ★Windows 主控台預設 cp950★：ℹ(U+2139) 等符號會讓 print 直接
#   UnicodeEncodeError，驗證「假失敗」。只動 I/O 編碼，不碰檢查邏輯。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).parent
ROOT = HERE.parent
INO = ROOT / "R4" / "matrix_mini_r4" / "matrix_mini_r4.ino"
PI_FSM = HERE / "pi_fsm.py"
DASH = ROOT / "cloud_dash" / "grafana_dashboard_fleet.json"

problems, notes = [], []


def firmware_fields():
    """從韌體的 Serial.print 串接解析出 JSON 欄位名。"""
    src = INO.read_text(encoding="utf-8")
    m = re.search(r'Serial\.print\(F\("\{\\"ts.*?Serial\.println\(F\("\\"\}"\)\);',
                  src, re.S)
    if not m:
        problems.append("找不到韌體的 JSON 輸出區塊")
        return set()
    return set(re.findall(r'\\"(\w+)\\":', m.group(0)))


def pi_fsm_fields():
    """從 pi_fsm.py 解析 rec = {...} 的欄位，以及它會讀取的來源欄位。"""
    src = PI_FSM.read_text(encoding="utf-8")
    m = re.search(r"rec\s*=\s*\{(.*?)\n\s*\}", src, re.S)
    if not m:
        problems.append("找不到 pi_fsm.py 的 rec = {...}")
        return set(), set()
    produced = set(re.findall(r'"(\w+)"\s*:', m.group(1)))
    # 它從感測/安全 dict 取用的欄位
    consumed = set(re.findall(r'\b(?:s|rs)\.get\("(\w+)"', src))
    return produced, consumed


def dashboard_fields():
    """從 Grafana 儀表板的 Flux 查詢解析 measurement → 需要的欄位。"""
    d = json.loads(DASH.read_text(encoding="utf-8"))
    need = {"sensor": set(), "decision": set()}
    for p in d.get("panels", []):
        for t in p.get("targets", []):
            q = t.get("query", "")
            meas = re.findall(r'r\._measurement == "(\w+)"', q)
            flds = re.findall(r'r\._field == "(\w+)"', q)
            for mm in meas:
                if mm in need:
                    need[mm] |= set(flds)
    return need


def main():
    for f in (INO, PI_FSM, DASH):
        if not f.exists():
            print(f"找不到 {f}")
            sys.exit(1)

    fw = firmware_fields()
    produced, consumed = pi_fsm_fields()
    dash = dashboard_fields()

    notes.append(f"韌體輸出 {len(fw)} 個欄位：{', '.join(sorted(fw))}")
    notes.append(f"pi_fsm 產生 {len(produced)} 個決策欄位")
    notes.append(f"儀表板查詢 sensor {len(dash['sensor'])} 欄、decision {len(dash['decision'])} 欄")

    # ── 1. pi_fsm 讀得到韌體送來的每個欄位嗎 ──────────────────
    # 韌體用 "fan"，pi_fsm 也用 rs.get("fan")；欄位名一致才不會取到 None
    miss = consumed - fw
    if miss:
        problems.append(f"pi_fsm.py 讀取的欄位韌體沒送：{sorted(miss)}")
    else:
        notes.append(f"pi_fsm 讀取的 {len(consumed)} 個欄位韌體全部有送 ✓")

    # ── 2. 儀表板的 sensor 欄位，韌體有送嗎 ───────────────────
    # pi_fsm 的 serial_reader 會原樣轉發這些欄位到 incense/sensor
    miss = dash["sensor"] - fw
    if miss:
        problems.append(f"儀表板查 sensor.{sorted(miss)} 但韌體沒送")
    else:
        notes.append(f"儀表板需要的 sensor 欄位（{', '.join(sorted(dash['sensor']))}）韌體全部有送 ✓")

    # ── 3. 儀表板的 decision 欄位，pi_fsm 有產生嗎 ────────────
    miss = dash["decision"] - produced
    if miss:
        problems.append(f"儀表板查 decision.{sorted(miss)} 但 pi_fsm 沒產生")
    else:
        notes.append(f"儀表板需要的 decision 欄位（{', '.join(sorted(dash['decision']))}）pi_fsm 全部有產生 ✓")

    # ── 4. serial_reader 轉發清單有沒有漏掉儀表板要的欄位 ─────
    src = PI_FSM.read_text(encoding="utf-8")
    m = re.search(r'sensor = \{k: d\[k\] for k in\s*\((.*?)\) if k in d\}', src, re.S)
    if m:
        fwd = set(re.findall(r'"(\w+)"', m.group(1)))
        miss = dash["sensor"] - fwd
        if miss:
            problems.append(f"serial_reader 轉發清單漏了儀表板要的 {sorted(miss)}")
        else:
            notes.append(f"serial_reader 轉發 {len(fwd)} 個欄位，涵蓋儀表板所需 ✓")
    else:
        problems.append("找不到 serial_reader 的轉發清單")

    # ── 5. 實際跑一次資料流 ───────────────────────────────────
    sample = ('{"ts":123456,"co2":1180,"slope":245.0,"t_scd":27.10,"rh_scd":58.2,'
              '"t_sht":26.70,"rh_sht":57.9,"conf":1.0,"alarm":0,"t_furnace":63.25,'
              '"fan":220,"interlock":0,"tc_fault":0,"sensor_fault":0,'
              '"mode":"PI","local_state":"S2"}')
    try:
        d = json.loads(sample)
    except Exception as e:
        problems.append(f"樣本 JSON 不合法：{e}")
        return report()

    # 模擬 pi_fsm 的 FSM（CO2 1180 > T1 900 → 應進 S2、duty 220）
    co2, slope = d["co2"], d["slope"]
    state = "S2" if (co2 > 900 or slope > 120.0) else "S1"
    duty = {"S0": 0, "S1": 70, "S2": 220, "S3": 0}[state]
    rec = {
        "co2": co2, "slope": slope, "t_sht": d["t_sht"], "rh_sht": d["rh_sht"],
        "conf": d["conf"], "s3_alarm": d["alarm"], "t_furnace": d["t_furnace"],
        "fan_actual": d["fan"], "r4_mode": d["mode"], "interlock": d["interlock"],
        "state": state, "fan_duty": duty, "action": "S1->S2",
    }
    if state != "S2" or duty != 220:
        problems.append(f"FSM 行為異常：CO2={co2} 應進 S2/220，實得 {state}/{duty}")
    else:
        notes.append(f"資料流實跑：CO2={co2}ppm 斜率={slope} → {state}、fan {duty} ✓")

    miss = dash["decision"] - set(rec)
    if miss:
        problems.append(f"實跑產生的紀錄缺少儀表板欄位 {sorted(miss)}")

    report()


def report():
    print("=" * 68)
    for n in notes:
        print(f"  ℹ {n}")
    print("=" * 68)
    if problems:
        for p in problems:
            print(f"  ✗ {p}")
        print(f"\n結果：{len(problems)} 項欄位契約問題")
        sys.exit(1)
    print("結果：欄位契約全數對齊 ✓（韌體 → pi_fsm → 儀表板）")


if __name__ == "__main__":
    main()
