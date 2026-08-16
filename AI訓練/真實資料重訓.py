# -*- coding: utf-8 -*-
"""
B 案預測器的第一次真實資料驗證（sim-to-real 橋的第一塊板）。

資料：aroma01（真實 Pi5＋R4＋SCD41）上雲之 CO₂ 小時均值，
2026-08-11 起（雲端真實段；08-08~10 因兩段切換有缺口）。
★誠實定位★：這是「居家環境的人員作息 CO₂」，不是廟宇香客負載——
本驗證測的是 B 案的核心機制「日曆特徵能否預測 CO₂ 高程」在真實
資料上的遷移，不得宣稱為廟宇負載預測成效。

流程：
  1) 讀 data/aroma01_co2_hourly.csv（可用 --fetch 重抓雲端 InfluxDB）
  2) 目標＝CO₂ 高程（當日最小值當基線，與實機 FSM 同一哲學）
  3) 時序切分（前 70% 訓練、後 30% 測試——不可隨機切，防洩漏）
  4) ridge（λ 掃描）vs 常數基線 vs 前一日同時刻（persistence）
  5) 產出 models/realB_co2.json＋圖表/真實資料驗證.png

    python 真實資料重訓.py
"""
import csv
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "data", "aroma01_co2_hourly.csv")
TPE = timezone(timedelta(hours=8))

plt.rcParams["font.family"] = "Microsoft JhengHei"
plt.rcParams["axes.unicode_minus"] = False
RED, GOLD, INK, GREY = "#9E3B2F", "#C9A227", "#33302B", "#8A8377"

# ── 讀資料 ─────────────────────────────────────────────
rows = []
with open(CSV, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if not r.get("_value"):
            continue
        t = datetime.fromisoformat(r["_time"].replace("Z", "+00:00"))
        rows.append((t.astimezone(TPE), float(r["_value"])))
rows.sort()
print(f"真實小時樣本 {len(rows)} 筆"
      f"（{rows[0][0]:%m-%d %H:%M} ～ {rows[-1][0]:%m-%d %H:%M} 台北）")

# ── 目標：CO₂ 高程（當日最小值為基線）──────────────────
bydate = {}
for t, v in rows:
    bydate.setdefault(t.date(), []).append(v)
base = {d: min(vs) for d, vs in bydate.items()}
data = [(t, v - base[t.date()]) for t, v in rows]


def feats(t):
    h = t.hour + t.minute / 60.0
    return [1.0,
            math.sin(2 * math.pi * h / 24.0),
            math.cos(2 * math.pi * h / 24.0),
            math.sin(4 * math.pi * h / 24.0),
            math.cos(4 * math.pi * h / 24.0),
            math.exp(-((h - 8.0) ** 2) / 8.0),
            math.exp(-((h - 17.0) ** 2) / 12.5),
            math.exp(-((h - 23.0) ** 2) / 8.0),
            1.0 if t.weekday() >= 5 else 0.0]


X = np.array([feats(t) for t, _ in data])
Y = np.array([y for _, y in data])
n_tr = int(len(data) * 0.7)
Xtr, Ytr, Xte, Yte = X[:n_tr], Y[:n_tr], X[n_tr:], Y[n_tr:]
t_te = [t for t, _ in data[n_tr:]]

# ── ridge（λ 於訓練段內再切 8:2 選擇）──────────────────
n_v = int(n_tr * 0.8)
best = (1e18, None)
for lam in (0.1, 1.0, 10.0, 100.0):
    w = np.linalg.solve(Xtr[:n_v].T @ Xtr[:n_v] + lam * np.eye(X.shape[1]),
                        Xtr[:n_v].T @ Ytr[:n_v])
    m = float(np.mean(np.abs(np.maximum(0, Xtr[n_v:] @ w) - Ytr[n_v:])))
    if m < best[0]:
        best = (m, lam)
lam = best[1]
w = np.linalg.solve(Xtr.T @ Xtr + lam * np.eye(X.shape[1]), Xtr.T @ Ytr)
pred = np.maximum(0.0, Xte @ w)
mae = float(np.mean(np.abs(pred - Yte)))

# ── 基線 ──────────────────────────────────────────────
mae_const = float(np.mean(np.abs(Ytr.mean() - Yte)))
# persistence：前一日同時刻（找不到就跳過該點）
lookup = {(t.date(), t.hour): y for t, y in data}
pairs = [(lookup.get((t.date() - timedelta(days=1), t.hour)), y)
         for t, y in data[n_tr:]]
pairs = [(p, y) for p, y in pairs if p is not None]
mae_pers = float(np.mean([abs(p - y) for p, y in pairs]))

print(f"測試段 MAE：ridge={mae:.1f} ppm｜常數={mae_const:.1f}"
      f"｜前日同時刻={mae_pers:.1f}（n={len(Yte)}，λ={lam}）")

# ── 存檔 ──────────────────────────────────────────────
os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
with open(os.path.join(HERE, "models", "realB_co2.json"), "w",
          encoding="utf-8") as f:
    json.dump({"w": w.tolist(), "lambda": lam,
               "test_mae_ppm": round(mae, 1),
               "const_mae_ppm": round(mae_const, 1),
               "persistence_mae_ppm": round(mae_pers, 1),
               "n_hours": len(data), "train_frac": 0.7,
               "data": "aroma01 真實 CO₂（居家作息，2026-08-11 起）；"
                       "★驗證預測機制之遷移，非廟宇負載成效★"},
              f, ensure_ascii=False, indent=1)

# ── 圖 ────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.2),
                               gridspec_kw={"width_ratios": [2, 1]})
ax1.plot(t_te, Yte, "-", color=INK, lw=1.2, label="實際 CO2 高程")
ax1.plot(t_te, pred, "-", color=RED, lw=1.4, label="日曆特徵 ridge 預測")
ax1.set_ylabel("CO2 高程（ppm，基線＝當日最小）")
ax1.set_title("測試段（時序後 30%，模型未見過）")
ax1.legend()
ax1.grid(alpha=0.3)
for lbl in ax1.get_xticklabels():
    lbl.set_rotation(20)
bars = [("ridge\n(日曆特徵)", mae, RED), ("常數", mae_const, GREY),
        ("前日同時刻", mae_pers, GOLD)]
ax2.bar(range(3), [b[1] for b in bars], color=[b[2] for b in bars])
ax2.set_xticks(range(3), [b[0] for b in bars])
ax2.set_ylabel("測試 MAE（ppm）")
ax2.set_title("對基線比較")
for i, b in enumerate(bars):
    ax2.text(i, b[1] * 1.02, f"{b[1]:.0f}", ha="center")
ax2.grid(axis="y", alpha=0.3)
fig.suptitle("B 案預測機制的第一次真實資料驗證——aroma01 實測 CO2"
             "（居家作息；★非廟宇負載成效★）", y=1.03)
fig.tight_layout()
out = os.path.join(HERE, "圖表", "真實資料驗證.png")
fig.savefig(out, dpi=150, bbox_inches="tight")
print("saved", out)
