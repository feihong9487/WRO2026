# -*- coding: utf-8 -*-
"""
凍結評比協定（訓練前定案，不得因結果回頭改——與預註冊統計計畫同精神）。

  驗證 seed：1001–1010（10 個，與所有訓練 seed 空間不重疊）
  情境：域隨機化【開】、每回合 3 天、每日電量預算 4 Wh
  主指標：平均每日總損失（第 15 週損失函數）
  副指標：人時暴露、能耗、無電時數、超標時率
  判贏（對強基線・日曆規則）：10 個 seed 中 ≥8 個損失更低
  （配對符號檢定 n=10, k≥8 → p≈0.055），且平均損失更低
  ★全部為模擬值。輸了照第 19 週承諾如實報告。★

    python 評比.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from incense_env import IncenseEnv, DISCRETE_DUTIES
from baselines import ConstantDuty, PiFSM, PIDControl
from policies import (ACTIONS, LinearPolicy, MLPPolicy, CalendarRule,
                      PredictSchedule)

assert tuple(ACTIONS) == tuple(DISCRETE_DUTIES), "動作集不同步"

SEEDS = list(range(1001, 1011))
DAYS = 3


def run(ctrl, seed):
    env = IncenseEnv(randomize=True, episode_days=DAYS)
    obs = env.reset(seed=seed)
    ctrl.reset()
    m = {"loss": 0.0, "exp": 0.0, "wh": 0.0, "dead_h": 0.0, "over_s": 0.0}
    total_s, done = 0.0, False
    while not done:
        obs, r, done, info = env.step(ctrl.act(obs, env.t))
        h = env.dt / 3600.0
        total_s += env.dt
        m["loss"] += -r
        m["exp"] += info["people"] * max(0.0, info["c_w"] - env.cfg.C_BG_PM) * h
        m["wh"] += info["power_w"] * h
        if info["battery_wh"] <= 0.0:
            m["dead_h"] += h
        if info["c_pm_true"] > env.cfg.PM_STD:
            m["over_s"] += env.dt
    m["over_pct"] = 100.0 * m["over_s"] / total_s
    for k in ("loss", "exp", "wh", "dead_h"):
        m[k] /= DAYS                        # 每日均值
    return m


CONTENDERS = [
    ("關機",        lambda: ConstantDuty(0)),
    ("定速 S1",     lambda: ConstantDuty(70)),
    ("實機 FSM",    PiFSM),
    ("PID",         PIDControl),
    ("日曆規則★",   CalendarRule),          # 強基線（判贏對照）
    ("A 線性CEM",   lambda: LinearPolicy("linearA.json")),
    ("B 預測+DP",   lambda: PredictSchedule("predictorB.json")),
    ("C DQN",       lambda: MLPPolicy("dqnC.json")),
]

results = {}
for name, mk in CONTENDERS:
    per_seed = [run(mk(), s) for s in SEEDS]
    results[name] = per_seed
    avg = {k: sum(p[k] for p in per_seed) / len(per_seed)
           for k in per_seed[0]}
    print(f"{name:<10} 日損失={avg['loss']:>9.1f}  日人時暴露={avg['exp']:>9,.0f}  "
          f"日能耗={avg['wh']:.2f}Wh  無電={avg['dead_h']:.1f}h/日  "
          f"超標={avg['over_pct']:.1f}%")

print("\n── 配對判贏（vs 日曆規則★，n=10、勝 ≥8 才算贏）──")
base = results["日曆規則★"]
for name in ("A 線性CEM", "B 預測+DP", "C DQN", "實機 FSM", "PID"):
    wins = sum(1 for p, b in zip(results[name], base)
               if p["loss"] < b["loss"])
    avg_d = (sum(p["loss"] for p in results[name])
             - sum(b["loss"] for b in base)) / len(SEEDS)
    verdict = "✅ 贏" if wins >= 8 else ("─ 平手區" if wins >= 5 else "❌ 輸")
    print(f"{name:<10} 勝 {wins}/10　Δ日損失={avg_d:+.1f}　{verdict}")
print("\n★模擬值；依第 19 週承諾，結果不論如何照實寫進日誌★")
