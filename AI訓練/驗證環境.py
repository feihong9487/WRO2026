# -*- coding: utf-8 -*-
"""
模擬環境自檢（純標準函式庫，照專案 run_tests.py 的精神：修設計不修測試）。

    python 驗證環境.py

檢查層次：
  A. 物理自洽 —— 解析錨點（附錄 C：8.7 支→97 µg/m³；η=0.805→35）＋雙區
  B. 煙羽模型 —— 對照研究日誌第 17 週的速度表（N=1/9/20 → 0.40/0.83/1.08）
  C. 特性性質 —— η 的單調性（duty↑、N↓、橫流↓、側裙↑）
  D. 跨層一致 —— PiFSM 移植常數 vs PI5/pi_fsm.py、R4 韌體逐一比對
  E. 行為正確 —— 安全聯鎖、決定性、日曆結構、域隨機化、觀測隔離
  F. 訓練適性 —— F7 梯度可用性檢驗（最佳定速 ≠ 0）、對偶上升方向
  G. 誠實檢查 —— EST 清單非空、README 標示模擬
"""
import io
import math
import os
import random
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sim_config import SimConfig, q_m3s                          # noqa: E402
from plant import IncensePlant                                    # noqa: E402
from visitors import VisitorModel, is_lunar_peak                  # noqa: E402
from incense_env import IncenseEnv, DualAscent                    # noqa: E402
from baselines import PiFSM                                       # noqa: E402
import plume                                                      # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + (f"　{detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def make_plant(cfg, seed=1, calm=True):
    p = IncensePlant(cfg, random.Random(seed))
    if calm:                       # 關掉隨機橫流，物理錨點才有解析解
        p._step_cross = lambda t, dt: cfg.U_CROSS_MEAN / cfg.SKIRT_ATTEN * 0
    return p


# ═══ A. 物理自洽（解析錨點）═══════════════════════════════
print("A. 物理自洽")
cfg = SimConfig()

# A1：無風扇、N=9 穩態遠場 → C_bg + S/Q_nat（附錄 C 自洽性檢查邏輯）
g_stick = cfg.EF_MG_PER_STICK * 1000.0 / (cfg.BURN_MIN * 60.0)
q_nat = cfg.ACH * cfg.V_ROOM_M3 / 3600.0
c9 = cfg.C_BG_PM + 9 * g_stick / q_nat
c87 = cfg.C_BG_PM + 8.7 * g_stick / q_nat
p = make_plant(cfg)
p.stick_ends = [float("inf")] * 9
for i in range(80000):
    p.step(i * 5.0, 5.0, 0, 0)
check("A1 無風扇遠場穩態＝解析解", abs(p.c_pm - c9) / c9 < 0.03,
      f"模擬 {p.c_pm:.1f} vs 解析 {c9:.1f} µg/m³（8.7 支解析={c87:.1f}≈97）")

# A2：近場穩態 = 遠場 + S/Q_nx（雙區暴露模型：爐邊高於殿內均值）
q_nx = cfg.NEAR_EXCH_M3S * 1.0     # calm：u_cross 項為 0
cn_an = c9 + 9 * g_stick / q_nx
check("A2 近場穩態＝遠場＋S/Q_nx", abs(p.c_near - cn_an) / cn_an < 0.05,
      f"模擬 {p.c_near:.1f} vs 解析 {cn_an:.1f} µg/m³（近場>遠場 ✓）")

# A3：η=0.805 時遠場 ≈ 35（設計目標之解析再現）
c_eta = cfg.C_BG_PM + (1 - 0.805) * 8.7 * g_stick / q_nat
check("A3 η=80.5% → 我國標準 35", abs(c_eta - 35.0) < 1.0, f"{c_eta:.1f} µg/m³")

# A4：CO2 穩態＝解析解（30 人、無風扇）
p2 = make_plant(cfg)
for i in range(60000):
    p2.step(i * 5.0, 5.0, 0, 30)
co2_an = cfg.CO2_OUT + cfg.CO2_PPM_S_PERSON * 30 / (q_nat / cfg.V_ROOM_M3)
check("A4 CO2 穩態＝解析解", abs(p2.c_co2 - co2_an) / co2_an < 0.02,
      f"模擬 {p2.c_co2:.0f} vs 解析 {co2_an:.0f} ppm")

# ═══ B. 煙羽模型（對照日誌第 17 週速度表）══════════════════
print("B. 煙羽擴散模型")
tbl = [(1, 0.40), (9, 0.83), (20, 1.08)]
ok_w = all(abs(plume.w_plume(cfg, 0.2, n) - w) < 0.01 for n, w in tbl)
check("B1 w(0.2m,N) 對照第 17 週表", ok_w,
      "，".join(f"N={n}:{plume.w_plume(cfg,0.2,n):.2f}" for n, _ in tbl))
check("B2 煙羽半徑線性擴張 b(z)=DS/2+0.14z",
      abs(plume.b_plume(cfg, 0.2) - (0.055 + 0.14 * 0.2)) < 1e-9)
t02 = plume.rise_time(cfg, 0.2, 9)
check("B3 上升時間量級合理（0.2m、N=9 約 0.2–0.4 s）", 0.1 < t02 < 0.5,
      f"{t02:.2f} s")
# B4 橫流→偏移→捕集下降（F29 的再現）
e_calm, _ = plume.capture(cfg, 220, 9, 0.05)
e_wind, _ = plume.capture(cfg, 220, 9, 0.50)
check("B4 橫流 0.05→0.50 使 η 下降（F29 裕度脆弱性）", e_wind < e_calm,
      f"η {e_calm:.2f} → {e_wind:.2f}")
# B5 側裙有效性方向（B8）：衰減倍率越高 η 越好
cfg_ns = cfg.copy()
cfg_ns.SKIRT_ATTEN = 1.0
e_nskirt, _ = plume.capture(cfg_ns, 220, 9, 0.50)
check("B5 側裙衰減提升 η（B8 假設的方向）", e_wind > e_nskirt,
      f"有側裙 {e_wind:.2f} vs 無側裙 {e_nskirt:.2f}")

# ═══ C. 特性性質 ═════════════════════════════════════════
print("C. 特性曲線性質")
uc = cfg.U_CROSS_MEAN
mono_u = all(plume.capture(cfg, d, 9, uc)[0] <=
             plume.capture(cfg, d + 5, 9, uc)[0] + 1e-12
             for d in range(0, 250, 5))
mono_n = all(plume.capture(cfg, 220, n, uc)[0] >=
             plume.capture(cfg, 220, n + 1, uc)[0] - 1e-12
             for n in range(1, 30))
check("C1 η 隨 duty 單調上升", mono_u)
check("C2 η 隨 N 單調下降（第 17 週 η(u,N) 方向）", mono_n)
check("C3 η ∈ [0, ETA_GEO]",
      0.0 <= plume.capture(cfg, 255, 1, uc)[0] <= cfg.ETA_GEO + 1e-9)
check("C4 風量線性：duty=255 → Q_MAX",
      abs(q_m3s(cfg, 255) * 3600 - cfg.Q_MAX_M3H) < 1e-6)
check("C5 可見煙柱：正常抽排 ≥ h_spec（D33 幾何保證）",
      plume.h_visible(cfg, 220, 9) >= cfg.H_SPEC_M)
check("C5b 過度抽吸使煙柱變矮（文化約束有作用面）",
      plume.h_visible(cfg, 255, 1) < plume.h_visible(cfg, 70, 1))

# ═══ D. 跨層一致（真相來源比對）══════════════════════════
print("D. 跨層一致性（基線移植 vs 實機程式碼）")
root = os.path.dirname(HERE)
pi_src = io.open(os.path.join(root, "PI5", "pi_fsm.py"), encoding="utf-8").read()
ino_src = io.open(os.path.join(root, "R4", "matrix_mini_r4", "matrix_mini_r4.ino"),
                  encoding="utf-8", errors="ignore").read()


def grab(src, pat):
    m = re.search(pat, src)
    return m.group(1) if m else None


pairs = [
    ("CO2_IDLE_DELTA", r"CO2_IDLE_DELTA\s*=\s*(\d+)", PiFSM.CO2_IDLE_DELTA),
    ("T1_DELTA",       r"T1_DELTA\s*=\s*(\d+)",       PiFSM.T1_DELTA),
    ("T1_EXIT_DELTA",  r"T1_EXIT_DELTA\s*=\s*(\d+)",  PiFSM.T1_EXIT_DELTA),
    ("BASELINE_WINDOW_MIN", r"BASELINE_WINDOW_MIN\s*=\s*(\d+)",
     PiFSM.BASELINE_WINDOW_MIN),
    ("CO2_BASELINE_INIT", r"CO2_BASELINE_INIT\s*=\s*(\d+)",
     PiFSM.CO2_BASELINE_INIT),
    ("SLOPE_TH",       r"SLOPE_TH\s*=\s*([\d.]+)",    PiFSM.SLOPE_TH),
]
for name, pat, mine in pairs:
    src_v = grab(pi_src, pat)
    check(f"D1 {name} 與 pi_fsm.py 一致",
          src_v is not None and float(src_v) == float(mine),
          f"pi={src_v} / 移植={mine}")
duty_m = re.search(r'DUTY\s*=\s*\{"S0":\s*(\d+),\s*"S1":\s*(\d+),\s*"S2":\s*(\d+)',
                   pi_src)
check("D2 DUTY 表一致", duty_m is not None and
      [int(x) for x in duty_m.groups()] ==
      [PiFSM.DUTY["S0"], PiFSM.DUTY["S1"], PiFSM.DUTY["S2"]])
check("D3 T_LOCK/T_RELEASE 與韌體一致",
      grab(ino_src, r"T_LOCK\s*=\s*([\d.]+)") == "150.0" and
      grab(ino_src, r"T_RELEASE\s*=\s*([\d.]+)") == "130.0" and
      cfg.T_LOCK == 150.0 and cfg.T_RELEASE == 130.0)
check("D4 CO2_ALARM_PPM 與韌體一致",
      grab(ino_src, r"CO2_ALARM_PPM\s*=\s*(\d+)") == str(cfg.CO2_ALARM_PPM))

# ═══ E. 行為正確 ═════════════════════════════════════════
print("E. 環境行為")
rng = random.Random(3)
pa = IncensePlant(cfg, rng)
pa.c_co2 = 2000.0
st = pa.step(0, 5.0, 10, 0)
check("E1a CO2 硬警報覆寫為全速", st["applied_duty"] == 255)
pb = IncensePlant(cfg, rng)
pb.t_stove = 160.0
st2 = pb.step(0, 5.0, 200, 0)
check("E1b 超溫聯鎖覆寫為 0（優先於一切）", st2["applied_duty"] == 0)
pb.t_stove = 140.0
st2b = pb.step(5.0, 5.0, 200, 0)
check("E1c 聯鎖遲滯：130–150 之間維持鎖定", st2b["applied_duty"] == 0)


def run_env(seed, n=800):
    env = IncenseEnv()
    env.reset(seed=seed)
    tot = 0.0
    for _ in range(n):
        _, r, _, info = env.step(70)
        tot += r + info["c_pm_true"]
    return tot


check("E2 同 seed 決定性", run_env(42) == run_env(42))
check("E2b 異 seed 有差異", run_env(42) != run_env(43))

cfg_v = SimConfig()
vm = VisitorModel(cfg_v, random.Random(7), start_weekday=0)
peak, ordn = [], []
for day in range(60):
    lam = vm.rate_per_h(day * 86400 + 12 * 3600)
    (peak if is_lunar_peak(cfg_v, day) else ordn).append(lam)
check("E3 初一/十五負載 > 2.5× 平日",
      sum(peak) / max(1, len(peak)) > 2.5 * sum(ordn) / max(1, len(ordn)),
      f"峰均 {sum(peak)/max(1,len(peak)):.0f} vs 平日 {sum(ordn)/max(1,len(ordn)):.0f} 人/h")

r1 = SimConfig().randomize(random.Random(1))
r2 = SimConfig().randomize(random.Random(2))
check("E4 域隨機化落在宣告範圍",
      all(SimConfig.RAND_RANGES[k][0] - 1e-9 <= getattr(r1, k)
          <= SimConfig.RAND_RANGES[k][1] + 1e-9 for k in SimConfig.RAND_RANGES))
check("E4b 兩次抽樣不同", any(getattr(r1, k) != getattr(r2, k)
                              for k in SimConfig.RAND_RANGES))

env = IncenseEnv()
obs = env.reset(seed=1)
check("E5 obs 無 *_true 欄位（策略只看感測）",
      not any(k.endswith("_true") for k in obs))
check("E5b obs_vector 長度＝OBS_KEYS", len(env.obs_vector(obs)) == len(env.OBS_KEYS))

# ═══ F. 訓練適性 ═════════════════════════════════════════
print("F. 訓練適性（F7 教訓：訓練環境須先過梯度可用性檢驗）")


def mean_loss(duty_fixed, seed=5):
    """尖峰時段（07–13 時）定速運轉的平均損失（含對偶罰項近似：噪音超標時
    以 λ=1 計，讓「全速最好」不會平白勝出）。"""
    env = IncenseEnv(episode_days=1)
    env.reset(seed=seed)
    env.t = 7 * 3600.0
    dual = DualAscent(["noise", "h_vis"], lam0=1.0)
    tot, n = 0.0, 0
    while env.t < 13 * 3600.0:
        _, r, _, info = env.step(duty_fixed)
        tot += -r + dual.penalty(info["g"])
        n += 1
    return tot / n


losses = {d: mean_loss(d) for d in (0, 70, 140, 220, 255)}
best = min(losses, key=losses.get)
check("F1 梯度可用性：最佳定速 ≠ 0（F7 的 BFS 死因）", best != 0,
      "，".join(f"{d}:{v:.3f}" for d, v in losses.items()))
check("F1b 最佳定速 ≠ 255（能耗/噪音有作用）", best != 255)

d = DualAscent(["noise"], alpha=0.5)
d.update({"noise": 2.0})
lam1 = d.lam["noise"]
d.update({"noise": 2.0})
check("F2 對偶上升：違反 → λ 單調上升", d.lam["noise"] > lam1 > 0)
d.update({"noise": -5.0})
check("F2b 不違反 → λ 回落且不為負", 0 <= d.lam["noise"] < lam1 + 1.0)

# 樣本吞吐量（第 17 週三準則之三；資訊性，不設門檻但要 >1000 步/s）
import time                                                       # noqa: E402
env = IncenseEnv()
env.reset(seed=9)
t0 = time.time()
for _ in range(5000):
    env.step(70)
sps = 5000 / (time.time() - t0)
check("F3 樣本吞吐量 > 1000 步/s", sps > 1000, f"{sps:,.0f} 步/s")

# ═══ G. 誠實檢查 ═════════════════════════════════════════
print("G. 誠實一致性")
unm = SimConfig().unmeasured()
check("G1 EST（未實測）參數清單非空且可列舉", len(unm) >= 15, f"{len(unm)} 項")
readme = os.path.join(HERE, "README.md")
ok_rd = os.path.exists(readme) and "模擬" in io.open(readme, encoding="utf-8").read()
check("G2 README 存在且標示為模擬", ok_rd)

# ═══ 結果 ═══════════════════════════════════════════════
print()
if FAILS:
    print(f"❌ {len(FAILS)} 項未通過：{FAILS}")
    sys.exit(1)
print("✅ 全數通過——環境可用於訓練。所有輸出仍為模擬值，不得寫成實測。")
