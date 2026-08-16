# -*- coding: utf-8 -*-
"""
香客負載模型：日曆驅動的合成人流。

真實負載有極強的日曆結構（初一/十五、週末、節慶、進香團），這正是
「人流預測」研究方向（建議書第一章第 3 項）要學的東西——所以模擬器
必須把這個結構做出來，AI 才有東西可學。

★全部為假設的合成資料，僅供訓練；不得混入任何對外宣稱。★
農曆以朔望月 29.530588 天近似（起始農曆日由 cfg.START_LUNAR_DAY 指定），
不處理閏月與真實曆法——訓練用途足夠，日期對照展示請勿使用。
"""
import math
import random

SYNODIC = 29.530588


def lunar_day(cfg, day_index):
    """模擬第 day_index 天的農曆日（0.0 = 初一凌晨）。"""
    return (cfg.START_LUNAR_DAY + day_index) % SYNODIC


def is_lunar_peak(cfg, day_index):
    """初一（0–1）或 十五（14–15.5）。"""
    d = lunar_day(cfg, day_index)
    return d < 1.0 or 14.0 <= d < 15.5


def _daily_shape(hour):
    """開門時段內的到訪強度形狀（雙峰：晨 08、暮 17），積分≈1 尺度任意。"""
    m = math.exp(-((hour - 8.0) ** 2) / (2 * 2.0 ** 2))
    e = math.exp(-((hour - 17.0) ** 2) / (2 * 2.5 ** 2))
    return 0.25 + m + 0.8 * e


class VisitorModel:
    """
    step(t_s, dt) → (人數, 本步新插香支數)
    - 到訪：非齊次 Poisson，強度 λ(t)
    - 停留：lognormal（均值 STAY_MEAN_MIN）
    - 插香：機率 P_PLANT；三炷 60% / 一炷 40%（民間常見儀軌）
    - 進香團：隨機事件，+25 人在 20 分鐘內湧入
    """

    def __init__(self, cfg, rng: random.Random, start_weekday=0):
        self.cfg = cfg
        self.rng = rng
        self.start_weekday = start_weekday      # 0=週一
        self.leave_times = []                   # 在場者的離場時刻（秒）
        self._day_cache = {}                    # day_index → (倍率, 進香團時刻表)

    # ── 日層級 ─────────────────────────────────────────
    def _day_plan(self, day_index):
        if day_index in self._day_cache:
            return self._day_cache[day_index]
        cfg, rng = self.cfg, self.rng
        mult = 1.0
        weekday = (self.start_weekday + day_index) % 7
        if weekday >= 5:
            mult *= cfg.WEEKEND_X
        if is_lunar_peak(cfg, day_index):
            mult *= cfg.LUNAR_X
        if rng.random() < cfg.FESTIVAL_P:
            mult *= cfg.FESTIVAL_X
        buses = []
        n_bus = self._poisson(cfg.TOURBUS_PER_DAY)
        for _ in range(n_bus):
            h = rng.uniform(cfg.OPEN_HOUR + 1, cfg.CLOSE_HOUR - 2)
            buses.append(h)
        plan = (mult, buses)
        self._day_cache[day_index] = plan
        return plan

    def _poisson(self, lam):
        # Knuth 法（lam 小時足夠）
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= L:
                return k
            k += 1

    # ── 步層級 ─────────────────────────────────────────
    def rate_per_h(self, t_s):
        cfg = self.cfg
        day = int(t_s // 86400)
        hour = (t_s % 86400) / 3600.0
        if not (cfg.OPEN_HOUR <= hour < cfg.CLOSE_HOUR):
            return 0.0
        mult, buses = self._day_plan(day)
        lam = cfg.LAM_BASE_PER_H * mult * _daily_shape(hour)
        for bh in buses:
            if bh <= hour < bh + (20.0 / 60.0):
                lam += 25.0 / (20.0 / 60.0)     # 25 人擠在 20 分鐘
        return lam

    def step(self, t_s, dt):
        cfg, rng = self.cfg, self.rng
        # 離場
        self.leave_times = [x for x in self.leave_times if x > t_s]
        # 到訪
        lam = self.rate_per_h(t_s) * dt / 3600.0
        arrivals = self._poisson(lam) if lam > 0 else 0
        new_sticks = 0
        for _ in range(arrivals):
            stay_min = rng.lognormvariate(
                math.log(cfg.STAY_MEAN_MIN) - 0.18, 0.6)
            self.leave_times.append(t_s + stay_min * 60.0)
            if rng.random() < cfg.P_PLANT:
                new_sticks += 3 if rng.random() < 0.6 else 1
        return len(self.leave_times), new_sticks
