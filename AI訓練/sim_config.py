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

    # ── 源強（附錄 C＋文獻，見 文獻參數.md）─────────────
    EF_MG_PER_STICK = 10.0     # 排放因子。文獻：Jetter et al. 2002
                               # （Sci Total Environ 295:51–67，23 種香實測）
                               # PM2.5 EF 5–56 mg/g、排放率 7–202 mg/h；
                               # 台式立香 1.5–3 g/支 → 5–170 mg/支量級。
                               # 預設沿附錄 C 的 10（與 8.7 支反推自洽）  EST
    BURN_MIN = 45.0            # 單支燃燒時間（附錄 C：常見線香）
    CO2_PPM_S_PERSON = 0.01    # 每人呼出 CO2 於 500 m³ 之 ppm/s。
                               # 文獻：Persily & de Jonge 2017（Indoor Air
                               # 27:868–879）辦公均值 0.0048 L/s/人，
                               # 站立輕活動略高 → 取 0.005 L/s ✓文獻支持
    DEP_RATE_H = 0.1           # PM2.5 表面沉降速率 h⁻¹。文獻：Thatcher/
                               # Lai/Nazaroff 系列，室內 0.02–0.55 h⁻¹；
                               # 線香超細粒（0.1–0.4 µm）取低端        EST

    # ── 煙羽擴散（第 17/20 週；見 plume.py）─────────────
    W_PLUME_1 = 0.40           # 單支煙羽速度 @z=0.2m（第 17 週 Zukoski）
    DS_M = 0.11                # 爐盆有效源徑 ⌀110mm（第 20 週；§5.2 實驗 3）EST
    DB_DZ = 0.14               # 煙羽擴張率。文獻：MTT 純煙羽捲吸係數
                               # α≈0.12–0.14（Morton/Taylor/Turner 1956 及
                               # 後續實驗）→ db/dz=(6/5)α≈0.14–0.17，
                               # 取值落在文獻帶內（⚠ 本爐仍待 §5.2 實驗 2）EST
    Z_HOOD_M = 0.20            # 罩口離爐面高度（D33 幾何：> h_spec）   EST

    # ── 橫流與側裙（B8：全案最脆弱假設）──────────────────
    U_CROSS_MEAN = 0.20        # 室內橫流均值 m/s（常見 0.15–0.50）    EST
    SKIRT_ATTEN = 4.0          # 側裙衰減倍率（B8 假設 3–10×）         EST
    DOOR_GUSTS_PER_H = 2.0     # 開門陣風事件/h（×3 橫流、持續 60 s）  EST

    # ── 風扇與捕集 ─────────────────────────────────────
    # ★2026-08-16 使用者指定★：訓練調控風扇＝建準 SUNON 4020
    # （40×40×20 mm、DC12V、PWM、磁浮軸承），安裝於★罩口★。
    # 未指定確切型號檔位（4020 家族多檔轉速）——以下取家族典型中值，
    # 拿到 datasheet 後回填並收窄 RAND 範圍。
    FAN_NOTE = "SUNON 4020 12V PWM 磁浮軸承・罩口安裝（型號檔位待定）"
    Q_MAX_M3H = 12.0           # duty=255 工作點風量。4020 free-air 約
                               # 10–20 m³/h，裝罩口含阻力後取保守中值；
                               # ⚠ 遠低於 D26 規格 43.3——已知缺口，
                               # 見 README「設計張力」                  EST
    FAN_MIN_DUTY = 26          # 最低啟轉 duty（≈10%；磁浮啟動摩擦低，
                               # PWM 規格常見 0–20%；低於此風扇不轉）   EST
    HOOD_DIA_M = 0.18          # 漏斗罩口 HOOD_TOP_W=180mm（D32）
    ETA_GEO = 0.90             # 幾何捕集上限（假設）                  EST
    ETA_A = 2.6                # 速度競爭因子係數（假設）              EST
    FILTER_EFF = 0.995         # HEPA 級（假設）                       EST

    # ── 文化與噪音約束（D11：硬約束，不入權重）───────────
    H_SPEC_M = 0.18            # 本機保證可見煙柱（D31/D33）
    SPL_MAX_DBA = 45.0         # 噪音上限（附錄 C ⚠ 暫定）             EST
    SPL_BASE = 12.0            # SPL = SPL_BASE + SPL_GAIN·(duty/255)^0.6
    SPL_GAIN = 18.0            #   4020 磁浮全速約 30 dBA（家族典型；
                               #   在 45 dBA 上限下有大幅餘裕）        EST

    # ── 熱與安全（R4 韌體 matrix_mini_r4.ino 為真相來源）─
    T_AMB = 25.0
    T_STICK_GAIN = 11.0        # T_ss = T_AMB + GAIN·N^0.8（假設）     EST
    T_TAU_S = 120.0            # 爐溫一階時間常數（假設）              EST
    T_LOCK = 150.0             # 聯鎖觸發（韌體 T_LOCK）
    T_RELEASE = 130.0          # 聯鎖解除（韌體 T_RELEASE）
    CO2_ALARM_PPM = 1500       # CO2 硬警報（韌體 CO2_ALARM_PPM）

    # ── 風扇功耗（SUNON 4020 家族約 0.5–2.5 W）───────────
    FAN_P_MAX_W = 1.0          # P = P_MAX·(duty/255)^3（風扇相似定律）EST

    # ── 感測器模型 ─────────────────────────────────────
    SCD41_PERIOD_S = 5.0       # SCD41 自身 5 s 更新（韌體註解）
    SCD41_NOISE_PPM = 15.0     # 工作雜訊簡化                          EST
    PM_PERIOD_S = 1.0
    PM_NOISE = 4.0             # µg/m³（Plantower 規格 ±10–15 的簡化） EST
    PM_SCALE = 1.0             # 感測器對真值斜率。文獻：PMS 系列場測對
                               # 重量法/TEOM 偏差雙向（低估與高估 1.47×
                               # 皆有；Sayahi 2019、Kelly 2017）→
                               # 預設 1.0、隨機化 0.5–1.5 涵蓋雙向     EST
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
    P_PLANT = 0.10             # 於★本爐★插香之比例（多爐分流＋一爐一炷；
                               # 使尖峰 N 落在日誌缺口表的 9–30 支量級） EST
    START_LUNAR_DAY = 10.0     # 模擬第 0 天的農曆日（0=初一）

    # ── 資源限制（2026-08-16 使用者裁示：AI 在有限電量/算力下訓練）──
    ENERGY_WH_DAY = 4.0        # 每日風扇能量預算 Wh（情境參數：耗盡則
                               # 風扇斷電、CO2 警報也吹不動，午夜重置。
                               # None＝市電無限。4020 全速 1W → 預算只夠
                               # 全速 4 小時，AI 必須把 Wh 花在刀口上）
    # 算力限制不在物理模型內，屬訓練紀律（見 README）：策略要能在
    # Pi 5 以 1 Hz 推論（查表/線性/小網路），obs 維持精簡向量。

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
        "PM_SCALE":       (0.5, 1.5),
        "DEP_RATE_H":     (0.02, 0.55),
        "Q_MAX_M3H":      (6.0, 22.0),   # 4020 家族檔位×工作點不確定度
        "FAN_MIN_DUTY":   (13, 64),      # 最低啟轉 5–25%
        "FAN_P_MAX_W":    (0.5, 2.5),
        "SPL_GAIN":       (12.0, 24.0),
        "LAM_BASE_PER_H": (8.0, 45.0),
        "P_PLANT":        (0.05, 0.30),
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
def fan_running(cfg, duty):
    """低於最低啟轉 duty 風扇不轉（4020 PWM 停轉區）。"""
    return duty >= cfg.FAN_MIN_DUTY


def q_m3s(cfg, duty):
    duty = max(0, min(255, duty))
    if not fan_running(cfg, duty):
        return 0.0
    return cfg.Q_MAX_M3H / 3600.0 * (duty / 255.0)


def hood_area_m2(cfg):
    return math.pi * (cfg.HOOD_DIA_M / 2.0) ** 2


def spl_dba(cfg, duty):
    """噪音（★假設曲線★；4020 磁浮全速約 SPL_BASE+SPL_GAIN ≈ 30 dBA）。"""
    if not fan_running(cfg, duty):
        return 0.0
    return cfg.SPL_BASE + cfg.SPL_GAIN * (duty / 255.0) ** 0.6


def fan_power_w(cfg, duty):
    if not fan_running(cfg, duty):
        return 0.0
    return cfg.FAN_P_MAX_W * (duty / 255.0) ** 3
