#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧香爐 P0 — 決策層 FSM（Raspberry Pi 5）
-------------------------------------------------------------
訂閱 S3 的 MQTT 感測資料 → 狀態機（S0 待機 / S1 常態 / S2 高峰 / S3 異常）
→ 經 USB 序列指揮 R4 風扇 → 每秒一筆 JSON Lines 決策紀錄（可重演）。

進 S2：co2 > T1 或 CO2 斜率 > SLOPE_TH（前饋 θ_ff）
退 S2：co2 < T1_EXIT 且斜率回落（遲滯 T1' < T1）
S3   ：R4 回報 interlock 或 tc_fault（安全事件由 R4 就地執行，Pi 只記錄狀態）

注意：今天沒有 PMS5003，T1 門檻暫由 CO2 絕對值代打，讓 FSM 完整演練；
      PMS5003 到貨後把 T1 換回 PM 濃度即可（欄位已預留擴充）。

安裝：sudo apt install -y mosquitto mosquitto-clients python3-paho-mqtt python3-serial
執行：python3 pi_fsm.py
"""

import json
import time
import threading
from datetime import datetime

import serial
import paho.mqtt.client as mqtt

# ====== 依環境修改 ======
MQTT_HOST   = "localhost"
TOPIC       = "incense/sensor"
SERIAL_PORT = "/dev/ttyACM0"      # 控制器；用 ls /dev/ttyACM* 確認
BAUD        = 115200

# 感測資料來源：
#   "SERIAL" — 合併版。MATRIX Mini R4 一條序列同時送感測值與安全狀態，
#              Pi 收到後轉發 incense/sensor 上雲（雲端資料模型不變）。
#   "MQTT"   — 原三板版。ESP32-S3 經 WiFi 發布 incense/sensor，Pi 訂閱。
SENSOR_SOURCE = "SERIAL"
# ========================

# ---- 門檻與輸出（桌面測試值；燃燒艙實驗後再調） ----
# ★門檻相對於背景基線，不是絕對值★（2026-08-07，與 R4 韌體同步）
#   絕對門檻只在背景穩定時成立。安靜的廟宇清晨約 450ppm，
#   人多的展場大廳 1000–2000ppm——用絕對值在展場會永遠卡在 S2、
#   S0 永遠到不了，分級響應完全看不出來。廟宇實裝也會隨季節與通風漂移。
#   基線＝過去 BASELINE_WINDOW_MIN 分鐘內每分鐘最小值的最小值。
#   ★取最小不取平均★：要的是「沒人時的底」；用平均會被人潮拉高，
#   變成「人越多門檻越高」的正回饋，方向剛好相反。
CO2_IDLE_DELTA = 50      # 高於基線 <50 且持續 → S0 待機
T1_DELTA       = 300     # 高於基線 300 → 進 S2（呼氣即可達到）
T1_EXIT_DELTA  = 200     # 退 S2（遲滯）
BASELINE_WINDOW_MIN = 10
CO2_BASELINE_INIT   = 450
SLOPE_TH       = 120.0   # ppm/min，CO2 前饋門檻 θ_ff
IDLE_HOLD_S    = 60
SENSOR_STALE_S = 10      # 感測資料多久沒更新視為失聯
DUTY = {"S0": 0, "S1": 70, "S2": 220, "S3": 0}   # 0-255

# ── CO2 背景基線（與 R4 韌體同一套演算法）──────────────────
_buckets: list = [None] * BASELINE_WINDOW_MIN
_bucket_idx = 0
_bucket_min = None
_bucket_start = time.time()


def baseline_update(v: int) -> None:
    """每分鐘記一個「該分鐘的最小值」，滾動保留 BASELINE_WINDOW_MIN 個。"""
    global _bucket_idx, _bucket_min, _bucket_start
    if not v:
        return                                  # 無效讀值不進基線
    _bucket_min = v if _bucket_min is None else min(_bucket_min, v)
    if time.time() - _bucket_start >= 60:
        _buckets[_bucket_idx] = _bucket_min
        _bucket_idx = (_bucket_idx + 1) % BASELINE_WINDOW_MIN
        _bucket_min = None
        _bucket_start = time.time()


def co2_baseline() -> int:
    vals = [b for b in _buckets if b is not None]
    if vals:
        return min(vals)
    return _bucket_min if _bucket_min is not None else CO2_BASELINE_INIT

latest, r4 = {}, {}
latest_t = 0.0
lock = threading.Lock()


def on_conn(client, *args):
    if SENSOR_SOURCE == "MQTT":
        client.subscribe(TOPIC)
        print(f"MQTT 已連線並訂閱 {TOPIC}")
    else:
        print("MQTT 已連線（僅發布，感測資料走序列）")


def on_msg(client, userdata, m):
    global latest, latest_t
    try:
        d = json.loads(m.payload.decode())
    except Exception:
        return
    with lock:
        latest = d
        latest_t = time.time()


def serial_reader(ser, client):
    """
    背景執行緒：持續讀控制器每秒回報的狀態 JSON。

    SENSOR_SOURCE == "SERIAL"（合併版）：
        MATRIX Mini R4 送來的一行 JSON 同時含感測值與安全狀態，
        欄位名稱與原本的 sensor / R4 狀態一致，因此同一份 dict
        可直接供 latest（感測）與 r4（安全）共用。
        另需轉發 incense/sensor 上雲，否則雲端 sensor measurement 會斷。

    SENSOR_SOURCE == "MQTT"（原三板版）：
        序列只送 R4 安全狀態，感測值另由 on_msg() 從 MQTT 取得。
    """
    global r4, latest, latest_t
    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if not line.startswith("{"):
                continue
            d = json.loads(line)
            with lock:
                r4 = d
                if SENSOR_SOURCE == "SERIAL":
                    latest = d
                    latest_t = time.time()
            if SENSOR_SOURCE == "SERIAL":
                # 只挑感測欄位轉發，維持與原 ESP32-S3 相同的 payload 結構
                sensor = {k: d[k] for k in
                          ("ts", "co2", "slope", "t_scd", "rh_scd",
                           "t_sht", "rh_sht", "conf", "alarm") if k in d}
                client.publish(TOPIC, json.dumps(sensor, ensure_ascii=False))
        except Exception:
            time.sleep(0.5)


def main():
    # paho-mqtt v1 / v2 相容
    try:
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
    except AttributeError:
        client = mqtt.Client()
    client.on_connect = on_conn
    client.on_message = on_msg
    client.connect(MQTT_HOST, 1883, 60)
    client.loop_start()

    ser = serial.Serial(SERIAL_PORT, BAUD, timeout=1)
    threading.Thread(target=serial_reader, args=(ser, client), daemon=True).start()

    logname = datetime.now().strftime("incense_log_%Y%m%d_%H%M%S.jsonl")
    logf = open(logname, "a", buffering=1)
    print(f"決策紀錄 → {logname}")

    state = "S1"
    idle_since = None

    while True:
        time.sleep(1.0)                      # 決策週期 1 s
        with lock:
            s, rs = dict(latest), dict(r4)
            age = time.time() - latest_t if latest_t else 999

        co2 = s.get("co2", 0) or 0
        baseline_update(co2)                 # 每筆有效讀值都餵給基線追蹤
        slope = s.get("slope", 0.0) or 0.0
        action = ""

        # 感測失聯判定。合併版的序列每秒都會來，即使感測器已死，
        # 故不能只看資料新舊，還要採信控制器自己回報的 sensor_fault。
        stale = age > SENSOR_STALE_S or bool(s.get("sensor_fault"))
        anomaly = bool(rs.get("interlock") or rs.get("tc_fault"))

        prev = state
        if anomaly:
            state = "S3"                     # 安全事件 R4 已就地處置，這裡記錄狀態
        elif state == "S3":
            state = "S1"
            action = "ANOMALY_CLEARED"
        elif stale:
            state = "S1"                     # 感測失聯 → 保守常態換氣，交由 S3 警報線兜底
            action = "SENSOR_STALE"
        else:
            base = co2_baseline()
            th_s2, th_s2ex = base + T1_DELTA, base + T1_EXIT_DELTA
            th_idle = base + CO2_IDLE_DELTA
            if state in ("S0", "S1") and (co2 > th_s2 or slope > SLOPE_TH):
                state = "S2"                 # 前饋削峰：人潮（CO2 斜率）先行
            elif state == "S2" and co2 < th_s2ex and slope < SLOPE_TH / 2:
                state = "S1"                 # 遲滯退場，避免抖動
            elif state == "S1" and co2 and co2 < th_idle:
                if idle_since is None:
                    idle_since = time.time()
                elif time.time() - idle_since > IDLE_HOLD_S:
                    state = "S0"
            if co2 >= th_idle:
                idle_since = None
                if state == "S0":
                    state = "S1"

        if state != prev and not action:
            action = f"{prev}->{state}"

        duty = DUTY[state]
        try:
            ser.write(f"FAN {duty}\n".encode())
        except Exception:
            action = (action + " SERIAL_ERR").strip()

        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "co2": co2,
            "slope": round(slope, 1),
            "t_sht": s.get("t_sht"),
            "rh_sht": s.get("rh_sht"),
            "conf": s.get("conf"),
            "s3_alarm": s.get("alarm"),
            "t_furnace": rs.get("t_furnace"),
            "fan_actual": rs.get("fan"),
            "r4_mode": rs.get("mode"),
            "interlock": rs.get("interlock"),
            "state": state,
            "fan_duty": duty,
            "action": action,
        }
        logf.write(json.dumps(rec, ensure_ascii=False) + "\n")
        client.publish("incense/decision", json.dumps(rec, ensure_ascii=False))

        print(f"[{state}] CO2={co2:4d}ppm 斜率={slope:+7.1f}/min "
              f"爐溫={rs.get('t_furnace', '--')}°C fan={duty:3d} "
              f"R4={rs.get('mode', '?')} {action}")


if __name__ == "__main__":
    main()
