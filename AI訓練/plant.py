# -*- coding: utf-8 -*-
"""
受控體：煙羽擴散＋近場/遠場雙區質量平衡（四層架構之 L3）。

煙從香頭出發的路徑（每一步物理見 plume.py）：
    香 → 煙羽上升（w∝N^⅓）→ 罩口高度處被捕集 η 部分
      捕集流 → 濾材（FILTER_EFF）→ 排出
      逃逸流 (1−η)·S → ★近場呼吸區★（香客站的地方）
      近場 ↔ 遠場（殿內大空間）交換 → 自然換氣稀釋到戶外
橫流 u_cross 會把煙羽吹偏、降低 η（B8 的物理；含側裙衰減與開門陣風）。

解析錨點（驗證環境.py 檢查）：
  無風扇穩態  C_far = C_bg + S/Q_nat（附錄 C 自洽檢查：8.7 支 → ≈97）
              C_near = C_far + S/Q_nx（近場高於殿內均值——雙區暴露模型）

★所有輸出為模擬值；係數多為假設（附錄 C ⚠），域隨機化涵蓋其不確定度★
"""
import random

from sim_config import SimConfig, q_m3s, spl_dba, fan_power_w
import plume


class IncensePlant:
    def __init__(self, cfg: SimConfig, rng: random.Random):
        self.cfg = cfg
        self.rng = rng
        self.c_near = cfg.C_BG_PM        # 近場（爐邊呼吸區）PM2.5 真值
        self.c_pm = cfg.C_BG_PM          # 遠場（殿內均值）PM2.5 真值
        self.c_co2 = cfg.CO2_OUT + 20.0  # 殿內 CO2 真值
        self.t_stove = cfg.T_AMB         # 爐面熱電偶位置溫度真值
        self.u_cross = cfg.U_CROSS_MEAN  # 當前橫流（AR(1)＋陣風）
        self._gust_until = -1.0
        self._next_gust = 0.0
        self.stick_ends = []             # 每支香的熄滅時刻（秒）
        self.filter_load_ug = 0.0        # 濾材累積負載
        self.interlock = False           # 超溫聯鎖（150/130 遲滯，同韌體）

    # ── 香 ─────────────────────────────────────────────
    def add_sticks(self, t_s, n):
        for _ in range(n):
            self.stick_ends.append(t_s + self.cfg.BURN_MIN * 60.0)

    def n_burning(self, t_s):
        self.stick_ends = [e for e in self.stick_ends if e > t_s]
        return len(self.stick_ends)

    # ── 橫流過程（AR(1) 回歸均值＋開門陣風事件）──────────
    def _step_cross(self, t, dt):
        cfg, rng = self.cfg, self.rng
        self.u_cross += ((cfg.U_CROSS_MEAN - self.u_cross) * dt / 600.0
                         + rng.gauss(0.0, 0.01) * (dt ** 0.5))
        self.u_cross = max(0.02, min(0.8, self.u_cross))
        if t >= self._next_gust:
            self._gust_until = t + 60.0
            lam = max(1e-9, cfg.DOOR_GUSTS_PER_H / 3600.0)
            self._next_gust = self._gust_until + rng.expovariate(lam)
        return self.u_cross * (3.0 if t < self._gust_until else 1.0)

    # ── 物理步進 ───────────────────────────────────────
    def step(self, t_s, dt, duty, people):
        cfg = self.cfg
        n = self.n_burning(t_s)
        u_cross = self._step_cross(t_s, dt)

        # 安全聯鎖（真相來源：R4 韌體。環境強制執行——策略蓋不過）
        if self.t_stove >= cfg.T_LOCK:
            self.interlock = True
        elif self.t_stove <= cfg.T_RELEASE:
            self.interlock = False
        co2_alarm = self.c_co2 > cfg.CO2_ALARM_PPM
        applied = duty
        if co2_alarm:
            applied = 255                # CO2 硬警報 → 全速（韌體行為）
        if self.interlock:
            applied = 0                  # 聯鎖優先於一切 → 停止致動

        # 源強與煙羽捕集
        g_per_stick = cfg.EF_MG_PER_STICK * 1000.0 / (cfg.BURN_MIN * 60.0)
        s_ug_s = n * g_per_stick                      # µg/s
        eta, diag = plume.capture(cfg, applied, n, u_cross)

        v_n = cfg.V_NEAR_M3
        v_f = max(1.0, cfg.V_ROOM_M3 - v_n)
        q_nat = cfg.ACH * cfg.V_ROOM_M3 / 3600.0      # m³/s（整殿換氣）
        q_fan = q_m3s(cfg, applied)
        q_nx = cfg.NEAR_EXCH_M3S * (1.0 + u_cross)    # 橫流越強混合越快

        # 近場：逃逸煙直接進呼吸區，再與遠場交換
        escape = (1.0 - eta) * s_ug_s + (1.0 - cfg.FILTER_EFF) * eta * s_ug_s
        dcn = (escape / v_n + (q_nx / v_n) * (self.c_pm - self.c_near))
        self.c_near = max(0.0, self.c_near + dcn * dt)

        # 遠場：近場流入＋自然換氣＋風扇順帶濾室內空氣
        dcf = ((q_nx / v_f) * (self.c_near - self.c_pm)
               + (q_nat / v_f) * (cfg.C_BG_PM - self.c_pm)
               - (q_fan * cfg.FILTER_EFF / v_f) * self.c_pm)
        self.c_pm = max(0.0, self.c_pm + dcf * dt)

        captured = eta * s_ug_s * dt + q_fan * cfg.FILTER_EFF * self.c_pm * dt
        self.filter_load_ug += captured

        # CO2（單區即可：人呼出的 CO2 不走煙羽）
        dco2 = (cfg.CO2_PPM_S_PERSON * people * (500.0 / cfg.V_ROOM_M3)
                + ((q_nat + q_fan) / cfg.V_ROOM_M3) * (cfg.CO2_OUT - self.c_co2))
        self.c_co2 = max(cfg.CO2_OUT, self.c_co2 + dco2 * dt)

        # 爐溫（一階趨近穩態；★假設模型★）
        t_ss = cfg.T_AMB + cfg.T_STICK_GAIN * (n ** 0.8 if n else 0.0)
        self.t_stove += (t_ss - self.t_stove) * (dt / cfg.T_TAU_S)

        return {
            "n_sticks": n,
            "applied_duty": applied,
            "co2_alarm": co2_alarm,
            "interlock": self.interlock,
            "eta": eta,
            "plume": diag,                     # f_geo/f_vel/δ/b/w 診斷
            "u_cross": u_cross,
            "c_near_true": self.c_near,
            "c_pm_true": self.c_pm,
            "c_co2_true": self.c_co2,
            "t_stove_true": self.t_stove,
            "h_vis": plume.h_visible(cfg, applied, n),
            "spl": spl_dba(cfg, applied),
            "power_w": fan_power_w(cfg, applied),
            "captured_ug": captured,
        }
