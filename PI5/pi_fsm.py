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
SERIAL_PORT = "/dev/r4"           # udev 固定名（99-r4.rules），重列舉不再跳 ACM0/ACM1
BAUD        = 115200

# 感測資料來源：MATRIX Mini R4 一條序列同時送感測值與安全狀態，
# Pi 收到後轉發 incense/sensor 上雲（雲端資料模型不變）。
# （原三板版的 MQTT 感測來源已於 2026-08-07 隨兩板定案移除，
#   需要時見 git 歷史的 SENSOR_SOURCE 開關。）
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

# ════════ AI 影子模式（2026-08-16 新增）═══════════════════
# B 案（日曆負載預測＋電量預算 DP 排程）的★影子部署★：
#   只計算「AI 會建議什麼 duty」寫進決策紀錄（ai_duty 欄位）與上雲，
#   ★完全不影響送往 R4 的實際 duty★——先累積實機對比資料，
#   致動切換是之後由人拍板的另一步。
# 模型檔：與本檔同目錄之 ai_predictor.json。2026-08-21 起為
# ★真實資料訓練版★（cloud_dash/ai_models/ai_predictor_real.json 的部署
# 快照，v4、128.5h 居家實測、MAE 9.0 vs 基線 11.7/12.2；原模擬訓練版
# ＝AI訓練/models/predictorB.json 仍在 repo 可還原）。
# 檔案不存在或壞損 → 影子模式自動停用（ai_duty=None），資料流不受影響。
# 簡化註記：效益函數以 duty/255 線性近似捕集率（完整煙羽模型在
# AI訓練/plume.py；影子排序用線性近似已足夠，且 Pi 端零相依）。
import math as _math
import os as _os

AI_ACTIONS = (0, 70, 220, 255)
AI_BUDGET_WH = 4.0          # 與訓練情境一致（D40；耗盡假設見 AI訓練/README）
AI_FAN_P_MAX = 1.0          # SUNON 4020 家族典型（EST）


class ShadowAdvisor:
    _SYN = 29.530588
    _EPOCH = 947182440.0    # 2000-01-06 18:14 UTC（朔）近似

    def __init__(self, path):
        self.w = None
        try:
            with open(path, encoding="utf-8") as f:
                self.w = json.load(f)["w"]
        except Exception:
            return                       # 無模型 → 停用
        self._sched, self._slot = None, -1
        self._spent_wh, self._spent_day = 0.0, None

    @staticmethod
    def _feats(hour, ld, dow, is_open):
        morning = _math.exp(-((hour - 8.0) ** 2) / 8.0)
        evening = _math.exp(-((hour - 17.0) ** 2) / 12.5)
        lp = 1.0 if (ld < 1.0 or 14.0 <= ld < 15.5) else 0.0
        we = 1.0 if dow >= 5 else 0.0
        return [1.0, _math.sin(2 * _math.pi * hour / 24.0),
                _math.cos(2 * _math.pi * hour / 24.0),
                morning, evening, lp, we, is_open,
                is_open * morning * lp, is_open * evening * lp,
                is_open * we, is_open * lp]

    def _load_hat(self, hour, ld, dow):
        is_open = 1.0 if 6 <= hour < 21 else 0.0
        f = self._feats(hour, ld, dow, is_open)
        return max(0.0, sum(a * b for a, b in zip(self.w, f)))

    def suggest(self, co2, now, base=480.0):
        """base＝FSM 的滾動 CO2 基線（2026-08-21 修正：nowcast 原用固定
        480，在背景漂移的場域會把「持續偏高的背景」誤讀成負載——與
        FSM 門檻同尺（相對基線）後，影子建議與 FSM 的分歧只剩真實的
        決策差異。模擬端 policies.py 與凍結評比不動。"""
        if self.w is None:
            return None
        if self._spent_day != now.date():
            self._spent_day, self._spent_wh = now.date(), 0.0
        ld = ((now.timestamp() - self._EPOCH) / 86400.0) % self._SYN
        dow = now.weekday()
        hour = now.hour
        slot = (now.hour * 2) + (1 if now.minute >= 30 else 0)
        if self._sched is None or slot != self._slot:
            budget = max(0.0, AI_BUDGET_WH - self._spent_wh)
            nb = int(budget / 0.05) + 1
            dp = [(0.0, [])] * nb
            for h in range(23, hour - 1, -1):
                nhat = self._load_hat(h, ld, dow)
                if h == hour and co2:            # nowcast 混入當前時段
                    nhat = max(nhat, (co2 - base) / 26.0)
                if nhat < 0.3:
                    nhat = 0.0           # 微弱預測視為無負載（防雜訊倒預算）
                opts = [(d, int(round(AI_FAN_P_MAX * (d / 255.0) ** 3 / 0.05)),
                         (d / 255.0) * nhat) for d in AI_ACTIONS]
                ndp = [None] * nb
                for b in range(nb):
                    best = (-1.0, 0, [])
                    for d, c, ben in opts:
                        if c <= b:
                            v, ch = dp[b - c]
                            if ben + v > best[0]:
                                best = (ben + v, d, ch)
                    ndp[b] = (best[0], [best[1]] + best[2])
                dp = ndp
            self._sched = {h: d for h, d in
                           zip(range(hour, 24), dp[nb - 1][1])}
            self._slot = slot
        d = self._sched.get(hour, 0)
        self._spent_wh += AI_FAN_P_MAX * (d / 255.0) ** 3 / 3600.0
        return d


_advisor = ShadowAdvisor(_os.path.join(_os.path.dirname(
    _os.path.abspath(__file__)), "ai_predictor.json"))
# ═════════════════════════════════════════════════════════

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
    print("MQTT 已連線（僅發布，感測資料走序列）")


def serial_reader(ser, client):
    """
    背景執行緒：持續讀控制器每秒回報的狀態 JSON。

    MATRIX Mini R4 送來的一行 JSON 同時含感測值與安全狀態，
    欄位名稱與原本的 sensor / R4 狀態一致，因此同一份 dict
    可直接供 latest（感測）與 r4（安全）共用。
    另需轉發 incense/sensor 上雲，否則雲端 sensor measurement 會斷。
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
                latest = d
                latest_t = time.time()
            # 只挑感測欄位轉發，維持雲端沿用的 payload 結構
            sensor = {k: d[k] for k in
                      ("ts", "co2", "slope", "t_scd", "rh_scd",
                       "t_sht", "rh_sht", "t_ds", "conf", "alarm") if k in d}
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

        # AI 影子建議（只記錄、絕不影響上面已送出的實際 duty）
        try:
            ai_duty = _advisor.suggest(co2, datetime.now(),
                                       base=float(co2_baseline()))
        except Exception:
            ai_duty = None

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
            "ai_duty": ai_duty,          # 影子模式：AI 的建議值（未致動）
            "action": action,
        }
        logf.write(json.dumps(rec, ensure_ascii=False) + "\n")
        client.publish("incense/decision", json.dumps(rec, ensure_ascii=False))

        ai_txt = f" AI影子={ai_duty}" if ai_duty is not None else ""
        print(f"[{state}] CO2={co2:4d}ppm 斜率={slope:+7.1f}/min "
              f"爐溫={rs.get('t_furnace', '--')}°C fan={duty:3d} "
              f"R4={rs.get('mode', '?')}{ai_txt} {action}")


if __name__ == "__main__":
    main()
