# -*- coding: utf-8 -*-
"""
基線控制器——研究日誌 §5.2 第 8 項：★無基線則無法宣稱 AI 有貢獻★。

1. ConstantDuty  定速（最笨的對照）
2. PiFSM         實機 pi_fsm.py 的忠實移植（門檻常數必須與 PI5/pi_fsm.py
                 一字不差——驗證環境.py 有跨層一致性檢查，改這裡之前先改實機）
3. PIDControl    對 PM 感測值的 PID（傳統控制對照；證明前饋的價值要贏它）

任何學習型策略都用同一 obs 介面，直接可比。
"""


class ConstantDuty:
    def __init__(self, duty=70):
        self.duty = duty

    def reset(self):
        pass

    def act(self, obs, t):
        return self.duty


class PiFSM:
    """移植自 PI5/pi_fsm.py（S0/S1/S2＋CO2 相對基線＋斜率前饋＋遲滯）。
    與實機同一套「每分鐘最小值滾動窗」基線演算法；時間用模擬時鐘。"""

    # ★真相來源：PI5/pi_fsm.py——驗證環境.py 會比對這些常數★
    CO2_IDLE_DELTA = 50
    T1_DELTA = 300
    T1_EXIT_DELTA = 200
    BASELINE_WINDOW_MIN = 10
    CO2_BASELINE_INIT = 450
    SLOPE_TH = 120.0
    IDLE_HOLD_S = 60
    DUTY = {"S0": 0, "S1": 70, "S2": 220, "S3": 0}

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "S1"
        self._buckets = [None] * self.BASELINE_WINDOW_MIN
        self._bucket_idx = 0
        self._bucket_min = None
        self._bucket_start = 0.0
        self._idle_since = None

    def _baseline_update(self, v, t):
        if not v:
            return
        self._bucket_min = v if self._bucket_min is None else min(self._bucket_min, v)
        if t - self._bucket_start >= 60.0:
            self._buckets[self._bucket_idx] = self._bucket_min
            self._bucket_idx = (self._bucket_idx + 1) % self.BASELINE_WINDOW_MIN
            self._bucket_min = None
            self._bucket_start = t

    def _baseline(self):
        vals = [b for b in self._buckets if b is not None]
        if vals:
            return min(vals)
        return self._bucket_min if self._bucket_min is not None else self.CO2_BASELINE_INIT

    def act(self, obs, t):
        co2 = int(obs["co2"])
        slope = float(obs["slope"])
        self._baseline_update(co2, t)
        if not co2:
            self.state = "S1"        # 感測失聯 → 保守常態換氣（同實機）
            return self.DUTY[self.state]
        base = self._baseline()
        th_s2 = base + self.T1_DELTA
        th_s2ex = base + self.T1_EXIT_DELTA
        th_idle = base + self.CO2_IDLE_DELTA
        if self.state in ("S0", "S1") and (co2 > th_s2 or slope > self.SLOPE_TH):
            self.state = "S2"                        # 前饋削峰
        elif self.state == "S2" and co2 < th_s2ex and slope < self.SLOPE_TH / 2:
            self.state = "S1"                        # 遲滯退場
        elif self.state == "S1" and co2 < th_idle:
            if self._idle_since is None:
                self._idle_since = t
            elif t - self._idle_since >= self.IDLE_HOLD_S:
                self.state = "S0"
        else:
            self._idle_since = None
            if self.state == "S0":
                self.state = "S1"
        if self.state != "S1":
            self._idle_since = None
        return self.DUTY[self.state]


class PIDControl:
    """對 PM 感測值的 PID，目標 35 µg/m³。輸出限幅 0–255、抗積分飽和。"""

    def __init__(self, kp=6.0, ki=0.05, kd=0.0, target=35.0):
        self.kp, self.ki, self.kd, self.target = kp, ki, kd, target
        self.reset()

    def reset(self):
        self.i = 0.0
        self.prev_e = None
        self.prev_t = None

    def act(self, obs, t):
        e = obs["pm"] - self.target          # 超標為正 → 要加轉速
        dt = (t - self.prev_t) if self.prev_t is not None else 0.0
        d = 0.0
        if dt > 0 and self.prev_e is not None:
            d = (e - self.prev_e) / dt
            self.i += e * dt
            self.i = max(-2000.0, min(2000.0, self.i))
        self.prev_e, self.prev_t = e, t
        u = self.kp * e + self.ki * self.i + self.kd * d
        return max(0, min(255, int(u)))
