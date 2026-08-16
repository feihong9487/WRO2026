# -*- coding: utf-8 -*-
"""
每案三圖（A/B/C × 損失變化、損失比較、混淆矩陣）＝ 9 張，輸出至 圖表/。

- 損失變化圖：A＝CEM 各代（v2 固定配置集，跨代可比）；B＝學習曲線
  （訓練天數 vs 驗證 MAE）＋λ 掃描；C＝回合損失＋TD 誤差
- 損失比較圖：對日曆規則★的配對 Δ日損失，v1（優化前）vs v2（優化後）
  逐 seed 並排——凍結協定（評比.py）之輸出
- 混淆矩陣：B＝負載分級（無/低/中/高，有真值標籤的 ML 部件）；
  A/C＝動作混淆矩陣，對照「事後全知規則」（知道真實香支數與電量：
  有香且有電→S2(220)，否則→0）——控制策略的真值代理

★全部為模擬值★    python 圖表2.py（前置：三案 v2 已訓、評比.py 已重跑）
"""
import json
import math
import os
import random
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "圖表")
os.makedirs(OUT, exist_ok=True)

plt.rcParams["font.family"] = "Microsoft JhengHei"
plt.rcParams["axes.unicode_minus"] = False
RED, GOLD, INK, BLUE, GREY = "#9E3B2F", "#C9A227", "#33302B", "#2E5A8A", "#8A8377"


def load(name):
    with open(os.path.join(HERE, "models", name), encoding="utf-8") as f:
        return json.load(f)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("saved", name)


# ═══ 1. 損失變化圖 ═══════════════════════════════════════
# A：v2 固定配置集 → 跨代可比
a = load("cemA_history.json")
fig, ax = plt.subplots(figsize=(7, 4.2))
it = [r[0] for r in a["iters"]]
ax.plot(it, [-r[2] for r in a["iters"]], "o-", color=GOLD, label="族群平均損失")
ax.plot(it, [-r[1] for r in a["iters"]], "s-", color=RED, label="族群最佳損失")
ax.set_xlabel("CEM 代數")
ax.set_ylabel("固定配置集 4 回合平均損失")
ax.set_title("方案 A v2｜CEM 訓練損失變化\n（固定配置集評分——跨代可比，F35 根治版）★模擬★")
ax.legend(); ax.grid(alpha=0.3)
save(fig, "A_損失變化圖.png")

# B：學習曲線＋λ 掃描
b = load("predictorB_history.json")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.0))
days = [r[0] for r in b["learning_curve_days_mae"]]
maes = [r[1] for r in b["learning_curve_days_mae"]]
ax1.plot(days, maes, "o-", color=RED)
ax1.axhline(b["const_baseline_mae"], color=GREY, ls="--",
            label=f"常數預測基線 {b['const_baseline_mae']:.2f}")
ax1.set_xlabel("訓練資料量（天）"); ax1.set_ylabel("驗證 MAE（支）")
ax1.set_title("學習曲線"); ax1.legend(); ax1.grid(alpha=0.3)
lams = list(b["lambda_sweep"].keys())
vals = [b["lambda_sweep"][k] for k in lams]
ax2.bar(range(len(lams)), vals,
        color=[RED if float(k) == b["chosen_lambda"] else GREY for k in lams])
ax2.set_xticks(range(len(lams)), [f"λ={k}" for k in lams])
ax2.set_ylabel("驗證 MAE（支）")
ax2.set_title(f"λ 掃描（選 λ={b['chosen_lambda']}）")
ax2.grid(axis="y", alpha=0.3)
fig.suptitle("方案 B v2｜負載預測器損失變化（★合成資料★）", y=1.03)
save(fig, "B_損失變化圖.png")

# C：回合損失＋TD 誤差
c = load("dqnC_history.json")
fig, ax = plt.subplots(figsize=(7.5, 4.2))
ep = c["episode_returns"]
ax.bar(range(1, len(ep) + 1), [-r for r in ep], color=BLUE, alpha=0.55,
       label="各回合損失（域隨機化，難度不一）")
ax.set_yscale("log")
ax.set_xlabel("訓練回合（1 回合＝1 模擬日）")
ax.set_ylabel("回合總損失（log）")
ax2 = ax.twinx()
td = c["td_history"]
ax2.plot([t[0] / 1000 for t in td], [t[1] for t in td], color=RED, lw=1.3,
         label="TD 誤差（右軸，千步）")
ax2.set_ylabel("平均 |TD 誤差|", color=RED)
ax2.tick_params(axis="y", labelcolor=RED)
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, fontsize=9)
ax.set_title("方案 C v2｜n-step Double DQN 訓練損失變化 ★模擬★")
save(fig, "C_損失變化圖.png")

# ═══ 2. 損失比較圖（v1 vs v2，對日曆規則配對）═══════════
r_new = load("評比結果.json")["results"]
r_old = load("評比結果_v1.json")["results"]
NAME = {"A": "A 線性CEM", "B": "B 預測+DP", "C": "C DQN"}
for key, nm in NAME.items():
    base_n = r_new["日曆規則★"]
    base_o = r_old["日曆規則★"]
    d_new = [p["loss"] - b_["loss"] for p, b_ in zip(r_new[nm], base_n)]
    d_old = [p["loss"] - b_["loss"] for p, b_ in zip(r_old[nm], base_o)]
    w_new = sum(1 for x in d_new if x < 0)
    w_old = sum(1 for x in d_old if x < 0)
    xs = np.arange(len(d_new))
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar(xs - 0.2, d_old, 0.38, color=GREY,
           label=f"v1 優化前（勝 {w_old}/10，平均Δ={np.mean(d_old):+,.0f}）")
    ax.bar(xs + 0.2, d_new, 0.38, color=RED,
           label=f"v2 優化後（勝 {w_new}/10，平均Δ={np.mean(d_new):+,.0f}）")
    ax.axhline(0, color=INK, lw=1)
    ax.set_xticks(xs, [str(s) for s in load("評比結果.json")["seeds"]],
                  fontsize=8)
    ax.set_xlabel("驗證 seed（凍結協定 1001–1010）")
    ax.set_ylabel("配對 Δ日損失 vs 日曆規則★（負＝更好）")
    ax.set_title(f"方案 {key}｜凍結評比配對比較：優化前後 ★模擬值★")
    ax.legend(); ax.grid(axis="y", alpha=0.3)
    save(fig, f"{key}_損失比較圖.png")

# ═══ 3. 混淆矩陣 ═════════════════════════════════════════
def draw_cm(cm, labels, title, fname, xlabel, ylabel):
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    norm = cm / np.maximum(1, cm.sum(axis=1, keepdims=True))
    im = ax.imshow(norm, cmap="Reds", vmin=0, vmax=1)
    n = len(labels)
    ax.set_xticks(range(n), labels)
    ax.set_yticks(range(n), labels)
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{cm[i, j]:,}\n{100*norm[i, j]:.0f}%",
                    ha="center", va="center", fontsize=9,
                    color="white" if norm[i, j] > 0.5 else INK)
    ax.set_title(title)
    fig.colorbar(im, label="列內比例")
    save(fig, fname)


# B：負載分級（真值標籤）
from sim_config import SimConfig                       # noqa: E402
from visitors import VisitorModel, lunar_day           # noqa: E402
from policies import (PredictSchedule, LinearPolicy, MLPPolicy,  # noqa: E402
                      ACTIONS)
from incense_env import IncenseEnv                     # noqa: E402

BINS = [(-1, 0.5, "無"), (0.5, 5, "低"), (5, 20, "中"), (20, 1e9, "高")]


def binidx(v):
    for i, (lo, hi, _) in enumerate(BINS):
        if lo <= v < hi:
            return i
    return len(BINS) - 1


pw = load("predictorB.json")["w"]
rngx = random.Random(888)
cmB = np.zeros((4, 4), int)
errs = []
for ci in range(10):
    cfg = SimConfig().randomize(rngx)
    sd = rngx.randrange(7)
    vm = VisitorModel(cfg, random.Random(rngx.randrange(10 ** 9)),
                      start_weekday=sd)
    ends = []
    for day in range(20):
        ld = lunar_day(cfg, day)
        dow = (sd + day) % 7
        for hour in range(24):
            acc, cnt = 0.0, 0
            for k in range(60):
                t = day * 86400 + hour * 3600 + k * 60.0
                _, new = vm.step(t, 60.0)
                ends += [t + cfg.BURN_MIN * 60.0] * new
                ends = [e for e in ends if e > t]
                acc += len(ends); cnt += 1
            truth = acc / cnt
            is_open = 1.0 if cfg.OPEN_HOUR <= hour < cfg.CLOSE_HOUR else 0.0
            f = PredictSchedule.feats(hour, ld, dow, is_open)
            pred = max(0.0, sum(w * x for w, x in zip(pw, f)))
            cmB[binidx(truth), binidx(pred)] += 1
            errs.append(abs(pred - truth))
accB = 100.0 * np.trace(cmB) / cmB.sum()
draw_cm(cmB, [b_[2] for b_ in BINS],
        f"方案 B v2｜負載預測混淆矩陣（保留集 10 配置×20 天）\n"
        f"分級準確率 {accB:.1f}%｜MAE {np.mean(errs):.2f} 支｜★合成資料★",
        "B_混淆矩陣.png", "預測負載等級", "實際負載等級（模擬真值）")

# A / C：動作混淆矩陣 vs 事後全知規則
ALBL = [str(d) for d in ACTIONS]


def action_cm(mk_policy):
    cm = np.zeros((len(ACTIONS), len(ACTIONS)), int)
    for seed in (1001, 1002, 1003):
        env = IncenseEnv(randomize=True, episode_days=1)
        obs = env.reset(seed=seed)
        pol = mk_policy()
        pol.reset()
        last = {"n_sticks": 0, "battery_wh": 1.0}
        done = False
        while not done:
            duty = pol.act(obs, env.t)
            oracle = 220 if (last["n_sticks"] > 0
                             and last["battery_wh"] > 0.0) else 0
            cm[ACTIONS.index(oracle), ACTIONS.index(duty)] += 1
            obs, _, done, info = env.step(duty)
            last = info
    return cm


for key, mk in (("A", lambda: LinearPolicy("linearA.json")),
                ("C", lambda: MLPPolicy("dqnC.json"))):
    cm = action_cm(mk)
    agree = 100.0 * np.trace(cm) / cm.sum()
    draw_cm(cm, ALBL,
            f"方案 {key} v2｜動作混淆矩陣（3 驗證 seed × 1 天）\n"
            f"對照『事後全知規則』（有香且有電→220，否則→0）"
            f"｜一致率 {agree:.1f}%｜★模擬★",
            f"{key}_混淆矩陣.png",
            f"方案 {key} 選擇之 duty", "事後全知規則之 duty")
