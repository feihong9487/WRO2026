# -*- coding: utf-8 -*-
"""
基線對照示範：同一環境、同一日曆，比較四種控制策略跑 7 天。

    python run_demo.py            # 固定參數（可重現）
    python run_demo.py --dr       # 域隨機化（每天重抽物理參數）

輸出指標：
    人時暴露    Σ 在場人數×(佔用加權濃度−C_bg)×h（近場站爐邊、遠場其餘）
    超標時率    遠場 >35 µg/m³ 的時間比例
    能耗        風扇 Wh
    噪音違反    SPL>45 dBA 的小時數（硬約束 g_noise）
    煙柱違反    h_vis<h_spec 且有香在燒的小時數（硬約束 g_h_vis）
    切換量      Σ|Δduty|/255（平滑度）
    濾材負載    累積捕集 mg

★全部為模擬值。此表的用途是「比較策略相對優劣」，絕對數字無意義。★
依第 19 週的誠實承諾：若學習型策略未優於 PID／FSM 基線，如實報告。
"""
import sys

from incense_env import IncenseEnv
from baselines import ConstantDuty, PiFSM, PIDControl

sys.stdout.reconfigure(encoding="utf-8")

DAYS = 7
SEED = 2026
DR = "--dr" in sys.argv


def run(name, ctrl):
    env = IncenseEnv(randomize=DR, episode_days=DAYS)
    obs = env.reset(seed=SEED)
    ctrl.reset()
    m = {"exp": 0.0, "over_s": 0.0, "wh": 0.0, "noise_h": 0.0,
         "cult_h": 0.0, "switch": 0.0, "loss": 0.0}
    total_s = 0.0
    prev_duty = 0
    done = False
    while not done:
        duty = ctrl.act(obs, env.t)
        obs, r, done, info = env.step(duty)
        dt = env.dt
        h = dt / 3600.0
        total_s += dt
        m["loss"] += -r
        m["exp"] += info["people"] * max(0.0, info["c_w"] - env.cfg.C_BG_PM) * h
        if info["c_pm_true"] > env.cfg.PM_STD:
            m["over_s"] += dt
        m["wh"] += info["power_w"] * h
        if info["g"]["noise"] > 0:
            m["noise_h"] += h
        if info["g"]["h_vis"] > 0:
            m["cult_h"] += h
        m["switch"] += abs(info["applied_duty"] - prev_duty) / 255.0
        prev_duty = info["applied_duty"]
    filt_mg = env.plant.filter_load_ug / 1000.0
    print(f"{name:<14}{m['exp']:>12,.0f}{100*m['over_s']/total_s:>9.1f}%"
          f"{m['wh']:>9.1f}{m['noise_h']:>9.2f}{m['cult_h']:>9.2f}"
          f"{m['switch']:>9.0f}{filt_mg:>10.1f}{m['loss']:>11.1f}")


print(f"模擬 {DAYS} 天｜seed={SEED}｜域隨機化={'開' if DR else '關'}"
      f"｜★模擬值，僅供策略相對比較★")
print(f"{'策略':<14}{'人時暴露':>10}{'超標時率':>8}{'能耗Wh':>8}"
      f"{'噪音違h':>8}{'煙柱違h':>8}{'切換量':>8}{'濾材mg':>9}{'總損失':>10}")
print("─" * 92)
run("關機(duty 0)", ConstantDuty(0))
run("定速 S1(70)", ConstantDuty(70))
run("定速 S2(220)", ConstantDuty(220))
run("實機 FSM", PiFSM())
run("PID(PM→35)", PIDControl())
print("─" * 92)
print("解讀提示：FSM 有 CO2 前饋（人潮先行指標），PID 只看 PM（滯後）。")
print("學習型策略的合格線：總損失低於 FSM 且噪音/煙柱違反不高於 FSM。")
