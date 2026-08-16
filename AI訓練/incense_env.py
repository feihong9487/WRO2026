# -*- coding: utf-8 -*-
"""
訓練環境（L4 介面）：gym 風格 reset()/step()，純標準函式庫。

    from incense_env import IncenseEnv, DualAscent
    env = IncenseEnv(randomize=True)
    obs = env.reset(seed=0)
    obs, reward, done, info = env.step(duty)   # duty ∈ [0, 255]

損失函數＝研究日誌第 15 週的定義（各項物理理由見日誌，不是任意加權）：
    L = w_E·[(C−C_bg) + q·max(0,C−35)²] + w_P·u³ + w_F·u + w_S·(Δu)²
    reward = −L·dt
文化（h_vis ≥ h_spec）與噪音（SPL ≤ 45）是 ★硬約束★（D11：設為可加權項
＝承認信仰可被交換，已被否決）——環境把違反量放在 info["g"]，訓練端用
DualAscent（λ ← max(0, λ+α·g)）把 λ·max(0,g)² 加進損失，λ 隨訓練自動升高
直到約束被滿足。

設計原則：
1. 策略只看得到感測值（雜訊、更新週期、延遲、失聯）——真值在 info，
   只准診斷用；餵給策略就是 sim-to-real 自殺。
2. 安全聯鎖由環境強制執行（同 R4 韌體）：CO2 硬警報→255、超溫→0，
   info["applied_duty"] 是實際值。
3. randomize=True 每次 reset 重抽物理參數（第 19 週域隨機化）。

★模擬環境。所有數字不得寫成實測。★
"""
import math
import random

from sim_config import SimConfig
from visitors import VisitorModel, lunar_day, SYNODIC
from plant import IncensePlant

DISCRETE_DUTIES = (0, 70, 220, 255)   # S0 / S1 / S2 / 全速


class SensorSuite:
    """感測層：SCD41（5 s 更新＋雜訊）、PM 光學（低估＋雜訊）、熱電偶。
    含資料延遲與隨機失聯（失聯時 co2 回報 0，同實機無效值慣例）。"""

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.rng = rng
        self.co2_reading = 0
        self.pm_reading = 0.0
        self.tc_reading = cfg.T_AMB
        self._co2_next = 0.0
        self._hist = []                 # (t, co2) 供斜率計算
        self._delay_buf = []            # (t_visible, true_dict)
        self._drop_until = -1.0
        self._next_drop = self._sched_drop(0.0)

    def _sched_drop(self, t):
        lam = self.cfg.DROPOUT_PER_DAY
        if lam <= 0:
            return float("inf")
        return t + self.rng.expovariate(lam / 86400.0)

    def sample(self, t, true):
        cfg, rng = self.cfg, self.rng
        self._delay_buf.append((t + cfg.SENSOR_DELAY_S, true))
        vis = None
        while self._delay_buf and self._delay_buf[0][0] <= t:
            vis = self._delay_buf.pop(0)[1]
        if vis is None:
            vis = {"c_co2_true": self.co2_reading or cfg.CO2_OUT,
                   "c_pm_true": self.pm_reading,
                   "t_stove_true": self.tc_reading}
        if t >= self._next_drop:
            self._drop_until = t + rng.uniform(30.0, 120.0)
            self._next_drop = self._sched_drop(self._drop_until)
        dropped = t < self._drop_until

        if t >= self._co2_next:
            self._co2_next = t + cfg.SCD41_PERIOD_S
            if dropped:
                self.co2_reading = 0            # 無效值
            else:
                self.co2_reading = max(0, int(
                    vis["c_co2_true"] + rng.gauss(0, cfg.SCD41_NOISE_PPM)))
                self._hist.append((t, self.co2_reading))
        self._hist = [(tt, v) for tt, v in self._hist if t - tt <= 90.0]

        # PM 感測器裝於殿內（遠場）；近場真值策略看不到——跟實機一樣
        self.pm_reading = max(0.0, vis["c_pm_true"] * cfg.PM_UNDERCOUNT
                              + rng.gauss(0, cfg.PM_NOISE))
        self.tc_reading = vis["t_stove_true"] + rng.gauss(0, cfg.TC_NOISE_C)
        return dropped

    def slope_ppm_min(self, t):
        """與實機同精神：與約 60 秒前讀值之差（ppm/min）。"""
        past = [v for tt, v in self._hist if tt <= t - 55.0]
        if not past or not self.co2_reading:
            return 0.0
        return float(self.co2_reading - past[-1])


class IncenseEnv:
    OBS_KEYS = ("co2", "slope", "pm", "t_stove", "duty_prev",
                "hour_sin", "hour_cos", "lunar_sin", "lunar_cos", "is_open")

    def __init__(self, cfg: SimConfig = None, randomize=False,
                 episode_days=None, dt=None):
        self.base_cfg = cfg or SimConfig()
        self.randomize = randomize
        self.episode_days = episode_days or self.base_cfg.EPISODE_DAYS
        self.dt = dt or self.base_cfg.DT_S
        self.rng = random.Random(0)
        self.cfg = self.base_cfg
        self.t = 0.0

    # ── gym 介面 ───────────────────────────────────────
    def reset(self, seed=None):
        if seed is not None:
            self.rng = random.Random(seed)
        self.cfg = (self.base_cfg.randomize(self.rng)
                    if self.randomize else self.base_cfg)
        self.t = 0.0
        self.duty_prev = 0
        self.visitors = VisitorModel(self.cfg, self.rng,
                                     start_weekday=self.rng.randrange(7))
        self.plant = IncensePlant(self.cfg, self.rng)
        self.sensors = SensorSuite(self.cfg, self.rng)
        self.people = 0
        return self._obs()

    def step(self, duty):
        cfg = self.cfg
        duty = max(0, min(255, int(duty)))
        self.people, new_sticks = self.visitors.step(self.t, self.dt)
        if new_sticks:
            self.plant.add_sticks(self.t, new_sticks)
        st = self.plant.step(self.t, self.dt, duty, self.people)
        dropped = self.sensors.sample(self.t, st)

        # ── 損失（第 15 週定義）──
        h = self.dt / 3600.0
        u = st["applied_duty"] / 255.0
        du = (st["applied_duty"] - self.duty_prev) / 255.0
        # 暴露濃度＝在場者的佔用加權（近場站爐邊、遠場其餘；沒人時取遠場）
        if self.people > 0:
            pn = self.people * cfg.P_NEAR
            pf = self.people - pn
            c_w = (st["c_near_true"] * pn + st["c_pm_true"] * pf) / self.people
        else:
            c_w = st["c_pm_true"]
        terms = {
            "exposure": cfg.W_EXP_LIN * max(0.0, c_w - cfg.C_BG_PM) * h
                        + cfg.W_EXP_QUAD * max(0.0, c_w - cfg.PM_STD) ** 2 * h,
            "power":    cfg.W_POWER * (u ** 3) * h,
            "filter":   cfg.W_FILTER * u * h,
            "smooth":   cfg.W_SMOOTH * (du ** 2),
        }
        loss = sum(terms.values())

        # ── 硬約束違反量（正值＝違反；對偶上升處理，不入固定權重）──
        g = {
            "noise": st["spl"] - cfg.SPL_MAX_DBA,                # dBA
            "h_vis": ((cfg.H_SPEC_M - st["h_vis"]) / cfg.H_SPEC_M
                      if st["n_sticks"] > 0 else -1.0),          # 無因次
        }

        self.duty_prev = st["applied_duty"]
        self.t += self.dt
        done = self.t >= self.episode_days * 86400.0
        info = dict(st)
        info.update({"people": self.people, "loss_terms": terms, "g": g,
                     "c_w": c_w, "sensor_dropped": dropped, "t": self.t})
        return self._obs(), -loss, done, info

    # ── 觀測（策略只准看這個）──────────────────────────
    def _obs(self):
        cfg = self.cfg
        hour = (self.t % 86400.0) / 3600.0
        ld = lunar_day(cfg, self.t / 86400.0)
        return {
            "co2": self.sensors.co2_reading if hasattr(self, "sensors") else 0,
            "slope": (self.sensors.slope_ppm_min(self.t)
                      if hasattr(self, "sensors") else 0.0),
            "pm": self.sensors.pm_reading if hasattr(self, "sensors") else 0.0,
            "t_stove": (self.sensors.tc_reading
                        if hasattr(self, "sensors") else cfg.T_AMB),
            "duty_prev": getattr(self, "duty_prev", 0),
            "hour_sin": math.sin(2 * math.pi * hour / 24.0),
            "hour_cos": math.cos(2 * math.pi * hour / 24.0),
            "lunar_sin": math.sin(2 * math.pi * ld / SYNODIC),
            "lunar_cos": math.cos(2 * math.pi * ld / SYNODIC),
            "is_open": 1.0 if cfg.OPEN_HOUR <= hour < cfg.CLOSE_HOUR else 0.0,
        }

    def obs_vector(self, obs=None):
        """dict → 固定順序 list（餵神經網路用）。"""
        o = obs or self._obs()
        return [float(o[k]) for k in self.OBS_KEYS]


class DualAscent:
    """
    硬約束的對偶上升（第 15 週：λ_j ← max(0, λ_j + α·ḡ_j)）。

    用法（訓練迴圈）：
        dual = DualAscent(["noise", "h_vis"], alpha=0.5)
        ...每步： total_loss = base_loss + dual.penalty(info["g"])
        ...每回合結束： dual.update(平均違反量 dict)
    λ 不是超參數——它由違反量自動長大，直到策略不敢再違反為止。
    """

    def __init__(self, names, alpha=0.5, lam0=0.0):
        self.alpha = alpha
        self.lam = {n: lam0 for n in names}

    def penalty(self, g):
        return sum(self.lam[n] * max(0.0, g[n]) ** 2 for n in self.lam)

    def update(self, g_mean):
        for n in self.lam:
            self.lam[n] = max(0.0, self.lam[n] + self.alpha * g_mean[n])
        return dict(self.lam)
