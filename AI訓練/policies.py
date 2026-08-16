# -*- coding: utf-8 -*-
"""
推論模組（部署級）：三案的策略前向全部在此，★純標準函式庫★——
Pi 5 上不需要 numpy/PyTorch，權重一律 JSON。

介面與 baselines.py 一致：reset() / act(obs, t) → duty。
安全鏈不在這裡：AI 輸出照樣要過環境（=韌體）的警報與聯鎖。
"""
import json
import math
import os

from sim_config import SimConfig, fan_power_w
import plume

ACTIONS = (0, 70, 220, 255)          # 與 incense_env.DISCRETE_DUTIES 一致
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

# obs_vector 的正規化（訓練與部署必須同一份——改這裡要重訓）
_SCALES = {"co2": 1 / 1000.0, "slope": 1 / 100.0, "pm": 1 / 100.0,
           "t_stove": 1 / 100.0, "duty_prev": 1 / 255.0}


def normalize(obs, keys):
    return [float(obs[k]) * _SCALES.get(k, 1.0) for k in keys]


def _load(name):
    with open(os.path.join(MODELS_DIR, name), encoding="utf-8") as f:
        return json.load(f)


# ═══ 方案 A：線性策略（44+ 參數，CEM 訓練）═══════════════
class LinearPolicy:
    """duty = ACTIONS[argmax(W·x + b)]。權重 JSON：{"W": 4×13, "b": 4}"""

    def __init__(self, model="linearA.json", keys=None):
        d = _load(model) if isinstance(model, str) else model
        self.W, self.b = d["W"], d["b"]
        self.keys = keys or d["obs_keys"]

    def reset(self):
        pass

    def act(self, obs, t):
        x = normalize(obs, self.keys)
        best, best_v = 0, -1e18
        for i in range(len(self.W)):
            v = self.b[i] + sum(w * xi for w, xi in zip(self.W[i], x))
            if v > best_v:
                best, best_v = i, v
        return ACTIONS[best]


# ═══ 方案 C：小型 MLP（DQN 訓練，純 Python 前向）═════════
class MLPPolicy:
    """tanh 隱藏層＋線性輸出，argmax 選動作。
    權重 JSON：{"layers": [[W,b],...], "obs_keys": [...]}
    部署（Pi）走純 Python 前向（1 Hz 下 <5 ms 綽綽有餘）；
    評比端若裝有 numpy 則自動加速——兩條路徑數值相同。"""

    def __init__(self, model="dqnC.json"):
        d = _load(model) if isinstance(model, str) else model
        self.layers = d["layers"]
        self.keys = d["obs_keys"]
        try:                                    # 評比加速用；部署可無
            import numpy as _np
            self._np = _np
            self._npl = [(_np.array(W), _np.array(b))
                         for W, b in self.layers]
        except ImportError:
            self._np = None

    def reset(self):
        pass

    def _forward(self, x):
        if self._np is not None:
            h = self._np.array(x)
            for li, (W, b) in enumerate(self._npl):
                z = W @ h + b
                h = self._np.tanh(z) if li < len(self._npl) - 1 else z
            return h.tolist()
        h = x
        for li, (W, b) in enumerate(self.layers):
            z = [bi + sum(w * xi for w, xi in zip(row, h))
                 for row, bi in zip(W, b)]
            h = [math.tanh(v) for v in z] if li < len(self.layers) - 1 else z
        return h

    def act(self, obs, t):
        q = self._forward(normalize(obs, self.keys))
        return ACTIONS[max(range(len(q)), key=q.__getitem__)]


# ═══ 強基線：日曆排程規則（手寫，無學習）══════════════════
class CalendarRule:
    """誠實的強基線：懂日曆的排程規則。
    平日：晨暮雙峰（08–10、16–18）跑 S2；其餘關機（省預算）。
    初一/十五（由 obs 的 lunar 相位判斷）：峰段 S2、其餘開廟時段 S1。
    電量 <5% 直接關機保命。"""

    PEAKS = ((8, 10), (16, 18))

    def reset(self):
        pass

    def act(self, obs, t):
        if obs["battery"] < 0.05:
            return 0
        hour = (t % 86400.0) / 3600.0
        if not obs["is_open"]:
            return 0
        # lunar_sin/cos → 農曆日；初一 ≈ 0、十五 ≈ 14.8
        ld = (math.atan2(obs["lunar_sin"], obs["lunar_cos"])
              / (2 * math.pi)) % 1.0 * 29.530588
        lunar_peak = ld < 1.0 or 14.0 <= ld < 15.5
        in_peak = any(a <= hour < b for a, b in self.PEAKS)
        if in_peak:
            return 220
        return 70 if lunar_peak else 0


# ═══ 方案 B：預測＋最佳化（ridge 負載預測 × DP 預算排程）══
class PredictSchedule:
    """
    1) ridge 預測今日各小時的同時燃燒香支數 N̂_h（特徵＝純日曆）
    2) DP 解多選背包：在剩餘電量下，把各小時的 duty 檔位配到
       預期捕集量（η(duty,N̂)·N̂）總和最大
    3) v3：★CO2 nowcast★——由當前 CO2 高程反推「現在」的香支數
       （穩態換算：人數≈高程/12、每人在燒支數≈0.46 → N≈高程/26），
       當前時段取 max(日曆預測, nowcast)，並改為每 30 分鐘滾動重解。
       取代 v2 的「升一檔」補丁——反應能力進入最佳化本體而非外掛。
    權重 JSON：{"w": [...], "feat_names": [...]}
    """

    GRID = 0.05                     # 預算離散格 Wh
    RESOLVE_S = 1800                # v3：30 分鐘滾動重解
    NOWCAST_DEADBAND = 60.0         # CO2 高於戶外+60 ppm 才啟動 nowcast
    NOWCAST_PPM_PER_STICK = 26.0    # ★穩態換算，模擬推導之近似★

    def __init__(self, model="predictorB.json", cfg=None):
        d = _load(model) if isinstance(model, str) else model
        self.w = d["w"]
        self.cfg = cfg or SimConfig()
        self.reset()

    def reset(self):
        self._sched = None
        self._sched_slot = -1

    # ── 預測 ──
    @staticmethod
    def feats(hour, ld, dow, is_open):
        """日曆特徵（訓練與部署共用；改動即需重訓）。
        hour 0–24、ld 農曆日 0–29.53、dow 0–6（0=週一）。"""
        morning = math.exp(-((hour - 8.0) ** 2) / 8.0)
        evening = math.exp(-((hour - 17.0) ** 2) / 12.5)
        lunar_pk = 1.0 if (ld < 1.0 or 14.0 <= ld < 15.5) else 0.0
        weekend = 1.0 if dow >= 5 else 0.0
        return [1.0,
                math.sin(2 * math.pi * hour / 24.0),
                math.cos(2 * math.pi * hour / 24.0),
                morning, evening, lunar_pk, weekend, is_open,
                is_open * morning * lunar_pk, is_open * evening * lunar_pk,
                is_open * weekend, is_open * lunar_pk]

    def predict_load(self, hour, obs):
        cfg = self.cfg
        is_open = 1.0 if cfg.OPEN_HOUR <= hour < cfg.CLOSE_HOUR else 0.0
        ld = (math.atan2(obs["lunar_sin"], obs["lunar_cos"])
              / (2 * math.pi)) % 1.0 * 29.530588
        dow = round((math.atan2(obs["dow_sin"], obs["dow_cos"])
                     / (2 * math.pi)) % 1.0 * 7.0) % 7
        f = self.feats(hour, ld, dow, is_open)
        return max(0.0, sum(w * x for w, x in zip(self.w, f)))

    def nowcast(self, obs):
        """由當前 CO2 高程反推現在的香支數（★近似★）。感測失聯回 0。"""
        if not obs["co2"]:
            return 0.0
        elev = obs["co2"] - self.cfg.CO2_OUT - self.NOWCAST_DEADBAND
        return max(0.0, elev / self.NOWCAST_PPM_PER_STICK)

    # ── 排程（多選背包 DP）──
    def _solve(self, obs, from_hour, budget_wh):
        cfg = self.cfg
        hours = list(range(from_hour, 24))
        nb = int(budget_wh / self.GRID) + 1
        # dp[b] = (最大效益, 選擇串)
        dp = [(0.0, [])] * nb
        for h in reversed(hours):
            nhat = self.predict_load(h, obs)
            if h == from_hour:                    # v3：當前時段混入 nowcast
                nhat = max(nhat, self.nowcast(obs))
            opts = []
            for d in ACTIONS:
                cost = int(round(fan_power_w(cfg, d) / self.GRID))
                ben = (plume.capture(cfg, d, max(nhat, 0.1),
                                     cfg.U_CROSS_MEAN)[0] * nhat
                       if nhat > 0.05 else 0.0)
                opts.append((d, cost, ben))
            ndp = [None] * nb
            for b in range(nb):
                best = (-1.0, 0, [])
                for d, cost, ben in opts:
                    if cost <= b:
                        v, ch = dp[b - cost]
                        if ben + v > best[0]:
                            best = (ben + v, d, ch)
                ndp[b] = (best[0], [best[1]] + best[2])
            dp = ndp
        return {h: d for h, d in zip(hours, dp[nb - 1][1])}

    def act(self, obs, t):
        cfg = self.cfg
        hour = int((t % 86400.0) // 3600.0)
        slot = int((t % 86400.0) // self.RESOLVE_S)
        if self._sched is None or slot != self._sched_slot:
            budget = (obs["battery"] * cfg.ENERGY_WH_DAY
                      if cfg.ENERGY_WH_DAY is not None else 24.0)
            self._sched = self._solve(obs, hour, budget)
            self._sched_slot = slot
        return self._sched.get(hour, 0)
