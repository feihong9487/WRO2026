# -*- coding: utf-8 -*-
"""
ACH 反演 — 從 aroma01 真實 CO₂ 衰減段推估換氣率（資料飛輪 → 物理參數）。

原理：無源時段的質量平衡 dC/dt = -λ(C - C_bg)，λ [1/h] 即 ACH。
每晚 CO₂ 從高峰衰減回基線的每一段曲線都是一次「免費的示蹤氣體實驗」
（ASHRAE 110 同族方法；第 20 週已證明微粒完全跟隨氣流）。

方法：
  1. 5 分鐘中位數平滑 → 偵測衰減段（高程≥150 ppm 起跌、持續下降
     ≥45 分鐘、總降幅≥100 ppm）
  2. 每段以 C_bg 網格搜尋＋ln(C−C_bg) 線性擬合，取 R² 最佳者
  3. 只收 R²≥0.95 的段；報告 λ 的中位數與 IQR

★誠實邊界★
  - 這是「aroma01 現所在居家房間」的 ACH——★不是廟宇、也不回填
    sim_config.ACH（那是廟宇殿內參數，RAND_RANGES 1.0–8.0 不動）★
  - 屬「資料推估」，不是 §5.2 儀器實測，不得標 *_MEASURED
  - 價值：(a) 反演方法先在自有資料上跑通，廟宇實裝後同一支程式直接用
    （θ 示蹤實驗的軟體先行）；(b) AI-2 未來的「衰減時間常數追蹤」
    （通風/濾材狀態訊號）用同一數學

    python ACH反演.py
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TPE = timezone(timedelta(hours=8))
RED, GOLD, INK, GREY = "#9E3B2F", "#C9A227", "#33302B", "#8A8377"
plt.rcParams["font.family"] = "Microsoft JhengHei"
plt.rcParams["axes.unicode_minus"] = False

minu = sorted((datetime.fromisoformat(k), v) for k, v in
              json.load(open(os.path.join(HERE, "data",
                                          "aroma01_co2_minutely.json"),
                             encoding="utf-8")).items() if v and v > 0)
print(f"分鐘級資料 {len(minu)} 筆")

# 5 分鐘中位數平滑（時間規則化到 1 分鐘格）
t0 = minu[0][0]
grid = {}
for t, v in minu:
    grid[int((t - t0).total_seconds() // 60)] = v
keys = sorted(grid)
sm = {}
for k in keys:
    win = [grid[j] for j in range(k - 2, k + 3) if j in grid]
    if len(win) >= 3:
        sm[k] = float(np.median(win))
sk = sorted(sm)

# 衰減段偵測（與取樣節奏無關：用 searchsorted 找時間鄰點）
ks = np.array(sk, dtype=float)
vs = np.array([sm[k] for k in sk])
episodes = []
i = 0
while i < len(ks) - 10:
    # 觸發：15±5 分鐘後淨下降 > 8 ppm
    j15 = int(np.searchsorted(ks, ks[i] + 15))
    if j15 >= len(ks) or ks[j15] - ks[i] > 20:
        i += 1
        continue
    if vs[i] - vs[j15] > 8:
        j = i
        seg_min = vs[i]
        while j < len(ks) - 1:
            if ks[j + 1] - ks[j] > 10:             # 資料中斷 → 段結束
                break
            seg_min = min(seg_min, vs[j])
            if vs[j + 1] - seg_min > 15:           # 回升 → 段結束
                break
            j += 1
        dur = ks[j] - ks[i]
        drop = vs[i] - vs[j]
        if dur >= 45 and drop >= 100:
            episodes.append(sk[i:j + 1])
            i = j
    i += 1
print(f"候選衰減段 {len(episodes)} 段")

# 指數擬合（C_bg 網格搜尋）
fits = []
for seg in episodes:
    ts = np.array([k - seg[0] for k in seg], dtype=float) / 60.0   # 小時
    cs = np.array([sm[k] for k in seg])
    best = None
    for cbg in np.arange(cs.min() - 120, cs.min() - 4, 4.0):
        y = cs - cbg
        if (y <= 0).any():
            continue
        ln = np.log(y)
        A = np.vstack([ts, np.ones_like(ts)]).T
        (slope, icpt), res, *_ = np.linalg.lstsq(A, ln, rcond=None)
        pred = A @ [slope, icpt]
        ss_res = float(((ln - pred) ** 2).sum())
        ss_tot = float(((ln - ln.mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        if slope < 0 and (best is None or r2 > best[0]):
            best = (r2, -slope, cbg)
    if best and best[0] >= 0.95:
        t_start = t0 + timedelta(minutes=seg[0])
        fits.append({"start": t_start.astimezone(TPE).isoformat(timespec="minutes"),
                     "dur_min": seg[-1] - seg[0],
                     "drop_ppm": round(sm[seg[0]] - sm[seg[-1]], 0),
                     "ach_per_h": round(best[1], 3),
                     "c_bg": round(best[2], 0), "r2": round(best[0], 4)})

if not fits:
    print("沒有 R²≥0.95 的衰減段——資料不足或環境有持續源")
    sys.exit(0)

ach = np.array([f["ach_per_h"] for f in fits])
med, q1, q3 = np.median(ach), *np.percentile(ach, [25, 75])
print(f"合格擬合 {len(fits)} 段：")
for f in fits:
    print(f"  {f['start']}  {f['dur_min']:4d}min  降{f['drop_ppm']:5.0f}ppm  "
          f"ACH={f['ach_per_h']:.2f}/h  R²={f['r2']}")
print(f"\nACH 中位數 {med:.2f}/h（IQR {q1:.2f}–{q3:.2f}，n={len(fits)}）")
print("文獻參考：住宅自然換氣典型 0.3–1.5/h（門窗關閉）——落點供比對，非驗證")

out = {"n_episodes": len(fits), "ach_median_per_h": round(float(med), 3),
       "ach_iqr": [round(float(q1), 3), round(float(q3), 3)],
       "fits": fits,
       "honesty": "居家房間之資料推估（非儀器實測、非 *_MEASURED；"
                  "非廟宇參數，不回填 sim_config.ACH）。"
                  "方法＝無源段 dC/dt=-λ(C-C_bg) 指數擬合，"
                  "廟宇實裝後同程式直接複用"}
with open(os.path.join(HERE, "models", "ACH反演結果.json"), "w",
          encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.2),
                               gridspec_kw={"width_ratios": [2, 1]})
best_fit = max(fits, key=lambda f: f["dur_min"])
for seg in episodes:
    t_s = (t0 + timedelta(minutes=seg[0])).astimezone(TPE)
    if t_s.isoformat(timespec="minutes") == best_fit["start"]:
        ts = np.array([k - seg[0] for k in seg]) / 60.0
        cs = np.array([sm[k] for k in seg])
        ax1.plot(ts * 60, cs, ".", ms=3, color=INK, label="實測（5min 平滑）")
        cbg, lam = best_fit["c_bg"], best_fit["ach_per_h"]
        c0 = cs[0] - cbg
        ax1.plot(ts * 60, cbg + c0 * np.exp(-lam * ts), color=RED, lw=2,
                 label=f"擬合 ACH={lam:.2f}/h（R²={best_fit['r2']}）")
        ax1.axhline(cbg, color=GREY, ls="--", lw=1, label=f"C_bg≈{cbg:.0f} ppm")
ax1.set_xlabel("時間（分鐘）")
ax1.set_ylabel("CO2（ppm）")
ax1.set_title(f"最長衰減段 {best_fit['start']}")
ax1.legend()
ax2.hist(ach, bins=8, color=RED, alpha=0.85)
ax2.axvline(med, color=INK, lw=2, label=f"中位 {med:.2f}/h")
ax2.set_xlabel("ACH（1/h）")
ax2.set_ylabel("段數")
ax2.set_title(f"全部 {len(fits)} 段分布")
ax2.legend()
fig.suptitle("ACH 反演 — aroma01 真實 CO2 衰減段（居家房間；★資料推估非實測★）",
             y=1.03)
fig.tight_layout()
png = os.path.join(HERE, "圖表", "ACH反演.png")
fig.savefig(png, dpi=150, bbox_inches="tight")
print("saved", png)
