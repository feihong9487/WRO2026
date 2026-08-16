# -*- coding: utf-8 -*-
"""
模擬環境參數（單一真相來源）。

★誠實邊界★：本目錄所有輸出皆為模擬，依 CLAUDE.md §7 不得寫成實測。
每個參數都標註出處；標 EST 者為估計值（對應研究日誌附錄 C 的 ⚠ 項），
域隨機化（randomize）就是為了讓訓練出的策略不依賴這些估計值的精確度
——研究日誌第 19 週的 sim-to-real 對策（η 擾動、ACH、源強、感測延遲、
C_bg 重採樣），再加上煙羽與橫流參數（B8 側裙假設不可被策略依賴）。

對應架構：研究日誌第 17 週「四層解耦」的 L3（0-D 質量平衡＋煙羽擴散）
＋ L4 介面。特性曲線依附錄 C 為 ★假設曲線★，實測（§5.2）後回填。
"""
import math
import random


class SimConfig:
    # ── 空間與背景（附錄 C）─────────────────────────────
    V_ROOM_M3 = 500.0          # 殿堂體積（附錄 C ⚠ 假設值）          EST
    ACH = 3.0                  # 自然換氣（附錄 C ⚠；結果對此不敏感）  EST
    C_BG_PM = 20.0             # 戶外背景 PM2.5 µg/m³（附錄 C ⚠ 保守） EST
    CO2_OUT = 420.0            # 戶外 CO2 ppm                          EST

    # ── 近場/遠場雙區（日誌雙區暴露模型的程式化）─────────
    V_NEAR_M3 = 40.0           # 爐邊呼吸區體積（假設）                EST
    NEAR_EXCH_M3S = 0.5        # 近↔遠交換流量 m³/s（假設）            EST
    P_NEAR = 0.3               # 在場香客位於爐邊近場的比例（假設）    EST

    # ── 源強（附錄 C）───────────────────────────────────
    EF_MG_PER_STICK = 10.0     # 排放因子（附錄 C ⚠ 文獻 7–200 跨 29 倍）EST
    BURN_MIN = 45.0            # 單支燃燒時間（附錄 C：常見線香）
    CO2_PPM_S_PERSON = 0.01    # 每人呼出 CO2 ≈0.005 L/s 於 500 m³     EST

    # ── 煙羽擴散（第 17/20 週；見 plume.py）─────────────
    W_PLUME_1 = 0.40           # 單支煙羽速度 @z=0.2m（第 17 週 Zukoski）
    DS_M = 0.11                # 爐盆有效源徑 ⌀110mm（第 20 週；§5.2 實驗 3）EST
    DB_DZ = 0.14               # 煙羽擴張率（⚠ §5.2 實驗 2：0.18 則裕度幾乎耗盡）EST
    Z_HOOD_M = 0.20            # 罩口離爐面高度（D33 幾何：> h_spec）   EST

    # ── 橫流與側裙（B8：全案最脆弱假設）──────────────────
    U_CROSS_MEAN = 0.20        # 室內橫流均值 m/s（常見 0.15–0.50）    EST
    SKIRT_ATTEN = 4.0          # 側裙衰減倍率（B8 假設 3–10×）         EST
    DOOR_GUSTS_PER_H = 2.0     # 開門陣風事件/h（×3 橫流、持續 60 s）  EST

    # ── 風扇與捕集 ─────────────────────────────────────
    Q_MAX_M3H = 65.0           # duty=255 之風量。所需 43.3（D26），
                               # 裕度 2.2–5.2 倍（第 20 週 Q1）取下緣   EST
    HOOD_DIA_M = 0.18          # 漏斗罩口 HOOD_TOP_W=180mm（D32）
    ETA_GEO = 0.90             # 幾何捕集上限（假設）                  EST
    ETA_A = 2.6                # 速度競爭因子係數（假設）              EST
    FILTER_EFF = 0.995         # HEPA 級（假設）                       EST

    # ── 文化與噪音約束（D11：硬約束，不入權重）───────────
    H_SPEC_M = 0.18            # 本機保證可見煙柱（D31/D33）
    SPL_MAX_DBA = 45.0         # 噪音上限（附錄 C ⚠ 暫定）             EST
    SPL_BASE = 25.0            # SPL = SPL_BASE + SPL_GAIN·(duty/255)^0.6
    SPL_GAIN = 22.0            #   （假設曲線；duty=220 → ≈45 dBA）    EST

    # ── 熱與安全（R4 韌體 matrix_mini_r4.ino 為真相來源）─
    T_AMB = 25.0
    T_STICK_GAIN = 11.0        # T_ss = T_AMB + GAIN·N^0.8（假設）     EST
    T_TAU_S = 120.0            # 爐溫一階時間常數（假設）              EST
    T_LOCK = 150.0             # 聯鎖觸發（韌體 T_LOCK）
    T_RELEASE = 130.0          # 聯鎖解除（韌體 T_RELEASE）
    CO2_ALARM_PPM = 1500       # CO2 硬警報（韌體 CO2_ALARM_PPM）

    # ── 風扇功耗（BOM：5015 12V 0.2A ×2）────────────────
    FAN_P_MAX_W = 4.8          # P = P_MAX·(duty/255)^3（風扇相似定律）

    # ── 感測器模型 ─────────────────────────────────────
    SCD41_PERIOD_S = 5.0       # SCD41 自身 5 s 更新（韌體註解）
    SCD41_NOISE_PPM = 15.0     # 工作雜訊簡化                          EST
    PM_PERIOD_S = 1.0
    PM_NOISE = 4.0             # µg/m³                                EST
    PM_UNDERCOUNT = 0.85       # 光學下限低估超細粒（建議書方向 1）    EST
    TC_NOISE_C = 2.0           # MAX6675 擾動                          EST
    SENSOR_DELAY_S = 0.0       # 感測延遲（域隨機化項，第 19 週）
    DROPOUT_PER_DAY = 0.5      # 感測失聯事件次數/日（每次 30–120 s）  EST

    # ── 香客模型（合成負載，僅供訓練）────────────────────
    OPEN_HOUR = 6.0
    CLOSE_HOUR = 21.0
    LAM_BASE_PER_H = 20.0      # 平日基礎到訪率 人/h                  EST
    WEEKEND_X = 2.2            # 週末倍率                             EST
    LUNAR_X = 6.0              # 初一/十五倍率                         EST
    FESTIVAL_X = 12.0          # 節慶倍率                              EST
    FESTIVAL_P = 0.02          # 任一日為節慶日之機率                  EST
    TOURBUS_PER_DAY = 0.3      # 進香團事件/日（+25 人 / 20 min）      EST
    STAY_MEAN_MIN = 15.0       # 停留時間 lognormal 均值               EST
    P_PLANT = 0.7              # 插香機率；支數：三炷 60% / 一炷 40%   EST
    START_LUNAR_DAY = 10.0     # 模擬第 0 天的農曆日（0=初一）

    # ── 模擬節奏 ───────────────────────────────────────
    DT_S = 5.0                 # 步長
    EPISODE_DAYS = 1

    # ── 損失函數權重（第 15 週定義；各項理由見日誌）───────
    #   L = w_E·[(C−C_bg) + QUAD·max(0,C−35)²] + w_P·u³ + w_F·u + w_S·Δu²
    #   文化（h_vis ≥ h_spec）與噪音（SPL ≤ 45）★不在此列★——
    #   它們是硬約束，違反量走 info["g"]，由對偶上升處理（D11）。
    W_EXP_LIN = 1.0            # 暴露線性項（無閾值、扣 C_bg）
    W_EXP_QUAD = 0.05          # 超標二次項（法規不連續性）
    W_POWER = 0.5              # 能耗 u³（風扇相似定律）
    W_FILTER = 0.2             # 濾材 u（壽命正比總風量）
    W_SMOOTH = 5.0             # 平滑 Δu²（變動噪音比穩定噪音更干擾）
    PM_STD = 35.0              # 我國 PM2.5 標準（法規）

    # ── 域隨機化範圍（第 19 週規格＋煙羽/橫流延伸）────────
    RAND_RANGES = {
        "ETA_GEO":        (0.65, 0.95),
        "ETA_A":          (1.8, 3.4),
        "W_PLUME_1":      (0.30, 0.50),
        "DB_DZ":          (0.10, 0.22),
        "DS_M":           (0.07, 0.15),
        "U_CROSS_MEAN":   (0.05, 0.50),
        "SKIRT_ATTEN":    (1.0, 10.0),   # 1.0 ＝側裙完全無效（B8 失效情境）
        "EF_MG_PER_STICK": (7.0, 100.0),  # log-uniform
        "ACH":            (1.0, 8.0),
        "V_ROOM_M3":      (300.0, 800.0),
        "V_NEAR_M3":      (20.0, 80.0),
        "NEAR_EXCH_M3S":  (0.2, 1.5),
        "C_BG_PM":        (10.0, 35.0),
        "CO2_OUT":        (400.0, 460.0),
        "SENSOR_DELAY_S": (0.0, 15.0),
        "PM_UNDERCOUNT":  (0.5, 1.0),
        "Q_MAX_M3H":      (50.0, 87.0),
        "LAM_BASE_PER_H": (8.0, 45.0),
    }
    LOG_UNIFORM = {"EF_MG_PER_STICK"}

    def copy(self):
        c = SimConfig()
        for k in dir(self):
            if k.isupper():
                setattr(c, k, getattr(self, k))
        return c

    def randomize(self, rng: random.Random):
        """域隨機化：回傳擾動後的新 config（self 不動）。"""
        c = self.copy()
        for k, (lo, hi) in self.RAND_RANGES.items():
            if k in self.LOG_UNIFORM:
                v = math.exp(rng.uniform(math.log(lo), math.log(hi)))
            else:
                v = rng.uniform(lo, hi)
            setattr(c, k, v)
        return c

    # ── 誠實工具 ───────────────────────────────────────
    def unmeasured(self):
        """列出本檔標 EST 的參數名（供報告引用時自查）。"""
        import inspect
        src = inspect.getsource(SimConfig)
        out = []
        for line in src.splitlines():
            s = line.strip()
            if s.endswith("EST") and "=" in s and not s.startswith("#"):
                out.append(s.split("=")[0].strip())
        return out


# 衍生量（不要在別處重算，避免版本分歧）
def q_m3s(cfg, duty):
    return cfg.Q_MAX_M3H / 3600.0 * (max(0, min(255, duty)) / 255.0)


def hood_area_m2(cfg):
    return math.pi * (cfg.HOOD_DIA_M / 2.0) ** 2


def spl_dba(cfg, duty):
    """噪音（★假設曲線★；duty=220 ≈ 45 dBA 即 S2 貼著上限跑）。"""
    if duty <= 0:
        return 0.0
    return cfg.SPL_BASE + cfg.SPL_GAIN * (duty / 255.0) ** 0.6


def fan_power_w(cfg, duty):
    return cfg.FAN_P_MAX_W * (duty / 255.0) ** 3
