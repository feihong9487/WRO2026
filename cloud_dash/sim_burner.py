#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧香爐 — 虛擬香爐模擬器（多爐展示／平台擴充性測試用）
直接對雲端 broker 發布擬真的 sensor 與 decision 資料。

用法：
  python3 sim_burner.py aroma02 --host <雲主機TailscaleIP> --user burner --password '橋接密碼'

行為：每 4 分鐘模擬一波「人潮」——CO2 緩升緩降、FSM 在 S1/S2 間切換、
爐溫與風扇 duty 連動。

★ 誠實一致性：展示與報告中務必標明此為模擬機。它的用途是驗證平台
  多裝置擴充性，不是偽造第二台實體原型。★
"""

import argparse
import json
import math
import random
import time

import paho.mqtt.client as mqtt

p = argparse.ArgumentParser()
p.add_argument("device", help="爐號，例如 aroma02")
p.add_argument("--host", required=True, help="雲端 broker 位址")
p.add_argument("--port", type=int, default=1883)
p.add_argument("--user", default="burner")
p.add_argument("--password", required=True)
a = p.parse_args()

try:
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
except AttributeError:
    c = mqtt.Client()
c.username_pw_set(a.user, a.password)
c.connect(a.host, a.port, 60)
c.loop_start()
print(f"虛擬香爐 {a.device} 已連上 {a.host}，開始發布（Ctrl+C 結束）")

PERIOD = 240.0          # 一波人潮的週期（秒）
t0 = time.time()
state = "S1"

while True:
    el = time.time() - t0
    wave = max(0.0, math.sin(2 * math.pi * el / PERIOD))          # 0~1 的人潮波
    co2 = 600 + 700 * wave + random.uniform(-15, 15)
    # 對應的斜率（ppm/min），加一點雜訊
    slope = 700 * (2 * math.pi / PERIOD) * math.cos(2 * math.pi * el / PERIOD) * 60
    slope += random.uniform(-8, 8)

    if co2 > 900 or slope > 120:
        state = "S2"
    elif co2 < 800 and slope < 60:
        state = "S1"
    duty = 220 if state == "S2" else 70

    t_env = round(26.5 + 1.2 * wave + random.uniform(-0.1, 0.1), 2)
    sensor = {
        "ts": int(el * 1000),
        "co2": int(co2),
        "slope": round(slope, 1),
        "t_scd": round(t_env + 0.4, 2),
        "rh_scd": round(62 - 3 * wave, 1),
        "t_sht": t_env,
        "rh_sht": round(61 - 3 * wave, 1),
        "conf": 1.0,
        "alarm": 0,
    }
    decision = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "co2": int(co2),
        "slope": round(slope, 1),
        "t_sht": t_env,
        "rh_sht": sensor["rh_sht"],
        "conf": 1.0,
        "s3_alarm": 0,
        "t_furnace": round(45 + 35 * wave + random.uniform(-0.5, 0.5), 2),
        "fan_actual": duty,
        "r4_mode": "PI",
        "interlock": 0,
        "state": state,
        "fan_duty": duty,
        "action": "",
    }
    c.publish(f"incense/{a.device}/sensor", json.dumps(sensor))
    c.publish(f"incense/{a.device}/decision", json.dumps(decision))
    time.sleep(1)
