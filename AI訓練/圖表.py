# -*- coding: utf-8 -*-
"""
產出三張報告用圖（全部標示模擬）：
  1) 損失變化圖：A（CEM 各代）＋ C（DQN 回合報酬與 TD 誤差）
  2) 損失比較圖：凍結評比八參賽者的日損失（均值柱＋各 seed 散點）
  3) 混淆矩陣：B 負載預測器的分級（無/低/中/高，保留日資料）

前置：訓練 A/B/C 完成＋`評比.py` 已輸出 models/評比結果.json
    python 圖表.py
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
RED, GOLD, INK, BLUE, GREEN = "#9E3B2F", "#C9A227", "#33302B", "#2E5A8A", "#3F7A4E"


def load(name):
    with open(os.path.join(HERE, "models", name), encoding="utf-8") as f:
        return json.load(f)


# ═══ 圖 1｜損失變化圖 ═══════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
a = load("cemA_history.json")
it = [r[0] for r in a["iters"]]
best = [-r[1] for r in a["iters"]]      # 報酬→損失（取負）
meanv = [-r[2] for r in a["iters"]]
ax = axes[0]
ax.plot(it, meanv, "o-", color=GOLD, label="族群平均損失")
ax.plot(it, best, "s-", color=RED, label="族群最佳損失")
ax.set_yscale("log")
ax.set_xlabel("CEM 代數")
ax.set_ylabel("單日損失（log）")
ax.set_title("方案 A｜CEM 訓練過程\n（各代物理配置不同，跨代高度僅供參考）")
ax.legend()
ax.grid(alpha=0.3)

c = load("dqnC_history.json")
ax = axes[1]
ep = c["episode_returns"]
ax.bar(range(1, len(ep) + 1), [-r for r in ep], color=BLUE, alpha=0.55,
       label="各回合損失（域隨機化，難度不一）")
ax.set_yscale("log")
ax.set_xlabel("訓練回合（1 回合＝1 模擬日）")
ax.set_ylabel("回合總損失（log）")
ax2 = ax.twinx()
td = c["td_history"]
ax2.plot([t[0] / 1000 for t in td], [t[1] for t in td],
         color=RED, lw=1.4, label="TD 誤差（右軸，千步）")
ax2.set_ylabel("平均 |TD 誤差|", color=RED)
ax2.tick_params(axis="y", labelcolor=RED)
ax.set_title("方案 C｜DQN 訓練過程")
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, fontsize=9)
fig.suptitle("模型訓練損失變化（★模擬環境訓練，非實測★）", y=1.02)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "損失變化圖.png"), dpi=150,
            bbox_inches="tight")
print("saved 損失變化圖.png")

# ═══ 圖 2｜損失比較圖（凍結評比：絕對值＋配對差值）═══════
r = load("評比結果.json")
names = list(r["results"].keys())
base = r["results"]["日曆規則★"]
fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.5, 4.8),
                               gridspec_kw={"width_ratios": [1.15, 1]})
xs = np.arange(len(names))
means, colors = [], []
for i, n in enumerate(names):
    losses = [p["loss"] for p in r["results"][n]]
    means.append(np.mean(losses))
    colors.append(RED if n[0] in "ABC" else
                  (GOLD if "日曆" in n else "#8A8377"))
    axL.scatter([i] * len(losses), losses, s=16, color=INK, alpha=0.5,
                zorder=3)
axL.bar(xs, means, color=colors, alpha=0.85, zorder=2)
for i, m in enumerate(means):
    axL.text(i, m * 1.06, f"{m/1000:,.0f}k", ha="center", fontsize=8.5)
axL.set_xticks(xs)
axL.set_xticklabels(names, fontsize=9, rotation=15)
axL.set_yscale("log")
axL.set_ylabel("平均每日總損失（log）")
axL.set_title("絕對值：柱＝均值、點＝各 seed\n（域隨機化使 seed 間差百倍，故差異要看右圖配對）")
axL.grid(axis="y", alpha=0.3)

cand = [n for n in names if "日曆" not in n]
deltas, wins = [], []
for n in cand:
    d = [p["loss"] - b["loss"] for p, b in zip(r["results"][n], base)]
    deltas.append(np.mean(d))
    wins.append(sum(1 for x in d if x < 0))
cs = [RED if n[0] in "ABC" else "#8A8377" for n in cand]
bars = axR.barh(range(len(cand)), deltas, color=cs, alpha=0.9)
for i, (d, w, n) in enumerate(zip(deltas, wins, cand)):
    mark = "贏" if w >= 8 else ("平手" if w >= 5 else "輸")
    axR.text(min(d, 0) - 250, i, f"{d:+,.0f}｜勝{w}/10 {mark}",
             va="center", ha="right", fontsize=9)
axR.axvline(0, color=INK, lw=1)
axR.set_yticks(range(len(cand)), cand, fontsize=9)
axR.set_xlabel("配對 Δ日損失 vs 日曆規則★（負＝更好）")
axR.set_title("配對差值（同 seed 相減；判贏門檻＝勝 ≧8/10）")
axR.set_xlim(min(deltas) * 1.9, max(500, max(deltas) * 1.3))
axR.grid(axis="x", alpha=0.3)
fig.suptitle(f"凍結評比（{len(r['seeds'])} seed × {r['days']} 天、"
             "域隨機化開、4 Wh/日）★模擬值★", y=1.02)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "損失比較圖.png"), dpi=150,
            bbox_inches="tight")
print("saved 損失比較圖.png")

# ═══ 圖 3｜混淆矩陣（B 負載預測分級）════════════════════
from sim_config import SimConfig                       # noqa: E402
from visitors import VisitorModel, lunar_day           # noqa: E402
from policies import PredictSchedule                   # noqa: E402

BINS = [(-1, 0.5, "無"), (0.5, 5, "低"), (5, 20, "中"), (20, 1e9, "高")]


def binidx(v):
    for i, (lo, hi, _) in enumerate(BINS):
        if lo <= v < hi:
            return i
    return len(BINS) - 1


pred_w = load("predictorB.json")["w"]
rng = random.Random(888)                # 與訓練 seed 777 不同（保留集）
cm = np.zeros((4, 4), int)
err = []
for ci in range(10):
    cfg = SimConfig().randomize(rng)
    sd = rng.randrange(7)
    vm = VisitorModel(cfg, random.Random(rng.randrange(10 ** 9)),
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
                acc += len(ends)
                cnt += 1
            truth = acc / cnt
            is_open = 1.0 if cfg.OPEN_HOUR <= hour < cfg.CLOSE_HOUR else 0.0
            f = PredictSchedule.feats(hour, ld, dow, is_open)
            pred = max(0.0, sum(w * x for w, x in zip(pred_w, f)))
            cm[binidx(truth), binidx(pred)] += 1
            err.append(abs(pred - truth))

acc_pct = 100.0 * np.trace(cm) / cm.sum()
fig, ax = plt.subplots(figsize=(6.4, 5.6))
norm = cm / np.maximum(1, cm.sum(axis=1, keepdims=True))
im = ax.imshow(norm, cmap="Reds", vmin=0, vmax=1)
labels = [b[2] for b in BINS]
ax.set_xticks(range(4), labels)
ax.set_yticks(range(4), labels)
ax.set_xlabel("預測負載等級")
ax.set_ylabel("實際負載等級（模擬真值）")
for i in range(4):
    for j in range(4):
        ax.text(j, i, f"{cm[i, j]:,}\n{100*norm[i, j]:.0f}%",
                ha="center", va="center", fontsize=10,
                color="white" if norm[i, j] > 0.5 else INK)
ax.set_title(f"方案 B 負載預測混淆矩陣（保留集 10 配置×20 天）\n"
             f"分級準確率 {acc_pct:.1f}%｜MAE {np.mean(err):.2f} 支"
             f"｜★合成資料，待真實歷史重驗★")
fig.colorbar(im, label="列內比例")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "混淆矩陣.png"), dpi=150,
            bbox_inches="tight")
print(f"saved 混淆矩陣.png（分級準確率 {acc_pct:.1f}%）")
