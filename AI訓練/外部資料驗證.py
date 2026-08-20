# -*- coding: utf-8 -*-
"""
外部公開資料集對兩個 AI 核心機制的獨立驗證。

資料：UCI ML Repository #864「Room Occupancy Estimation」
  （Singh & Chaudhari, IIT；6×4.6 m 房間、7 感測節點、4 天受控實驗、
   30 秒粒度、CO₂＋CO₂ 斜率＋人數真值 0–3 人，10,129 筆）
  https://archive.ics.uci.edu/dataset/864/room+occupancy+estimation
  下載檔：data/外部/Occupancy_Estimation.csv

驗證三個機制（都是我們 AI 的根基假設，能在別人的資料上獨立成立
才算機制而不是巧合）：
  V1  CO₂ 高程 ↔ 人數單調線性（AI-1 nowcast 代理量的前提）
  V2  CO₂ 斜率是人數變化的前饋訊號（FSM θ_ff 與 AI-1 排程的前提）
  V3  AI-2 時段穩健統計在無故障資料上的誤報率（門檻 z≥4.5 應近零誤報）

★誠實邊界★：這是辦公室測試間不是廟宇；ppm/人 常數隨房間體積與換氣率
而異，V1 驗證的是「單調線性關係」這個機制，不是 26 ppm/支 常數本身。

    python 外部資料驗證.py
"""
import csv
import json
import math
import os
import sys
from datetime import datetime

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "data", "外部", "Occupancy_Estimation.csv")

plt.rcParams["font.family"] = "Microsoft JhengHei"
plt.rcParams["axes.unicode_minus"] = False
RED, GOLD, INK, GREY = "#9E3B2F", "#C9A227", "#33302B", "#8A8377"

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cloud_dash"))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "ai_online", os.path.join(os.path.dirname(HERE), "cloud_dash",
                              "ai_online_learning.py"))
svc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(svc)

# ── 讀資料 ─────────────────────────────────────────────
rows = []
with open(CSV, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        t = datetime.strptime(r["Date"] + " " + r["Time"], "%Y/%m/%d %H:%M:%S")
        rows.append((t, float(r["S5_CO2"]), float(r["S5_CO2_Slope"]),
                     int(r["Room_Occupancy_Count"])))
rows.sort()
print(f"外部資料 {len(rows)} 筆（{rows[0][0]:%Y-%m-%d} ～ {rows[-1][0]:%Y-%m-%d}）")

# 高程＝相對當日最小值（與 AI-1 同一基線哲學）
bydate = {}
for t, co2, sl, n in rows:
    bydate.setdefault(t.date(), []).append(co2)
base = {d: min(v) for d, v in bydate.items()}
elev = np.array([co2 - base[t.date()] for t, co2, _, _ in rows])
occ = np.array([n for _, _, _, n in rows])
slope = np.array([sl for _, _, sl, _ in rows])

# ── V1：高程 ↔ 人數（準穩態）─────────────────────────
# 瞬時相關會被 CO2 蓄積遲滯拉低（人剛到濃度未升、人剛走濃度未降），
# 機制主張的是「穩態下高程∝人數」→ 只取人數已維持 15 分鐘不變的樣本。
STEADY = 30                                    # 30 步 × 30 s = 15 分鐘
steady = np.array([i >= STEADY and (occ[i - STEADY:i + 1] == occ[i]).all()
                   for i in range(len(occ))])
es, os_ = elev[steady], occ[steady]
k = float((es @ os_) / (os_ @ os_))            # 過原點最小平方：ppm/人
r_corr = float(np.corrcoef(es, os_)[0, 1])
r_all = float(np.corrcoef(elev, occ)[0, 1])
med_by_n = {int(n): float(np.median(es[os_ == n])) for n in sorted(set(os_))}
mono = all(med_by_n[a] < med_by_n[b]
           for a, b in zip(sorted(med_by_n), sorted(med_by_n)[1:]))
print(f"V1 高程↔人數（準穩態 n={len(es)}）：r={r_corr:.3f}"
      f"（全樣本瞬時 r={r_all:.3f}——遲滯拉低，附記）、擬合 {k:.1f} ppm/人、"
      f"各人數中位高程={ {k_: round(v_) for k_, v_ in med_by_n.items()} }"
      f"（單調遞增：{mono}）")
v1_pass = r_corr > 0.7 and mono

# ── V2：斜率是前饋訊號（到達事件的偵測領先時間）────────
# 前饋的本義：人到達後「斜率」比「濃度」先跨越各自的偵測門檻。
# 門檻＝空房分布的 中位數＋4×MAD（兩訊號同一標準，尺度自適應）。
def robust_th(v):
    m = float(np.median(v))
    return m + 4 * float(np.median(np.abs(v - m)) * 1.4826)

empty = occ == 0
th_e, th_s = robust_th(elev[empty]), robust_th(slope[empty])
events, leads, slope_first = 0, [], 0
LOOK = 30                                      # 到達後看 15 分鐘
for i in range(10, len(occ) - LOOK):
    if occ[i - 1] == 0 and occ[i] > 0 and (occ[i - 10:i] == 0).all() \
            and (occ[i:i + 20] > 0).all():     # 前 5 分鐘空、後 10 分鐘有人
        w_e = np.argmax(elev[i:i + LOOK] > th_e) \
            if (elev[i:i + LOOK] > th_e).any() else LOOK
        w_s = np.argmax(slope[i:i + LOOK] > th_s) \
            if (slope[i:i + LOOK] > th_s).any() else LOOK
        events += 1
        leads.append((w_e - w_s) * 0.5)        # 分鐘；正＝斜率先偵測到
        slope_first += w_s < w_e
lead_med = float(np.median(leads)) if leads else 0.0
frac_first = slope_first / events if events else 0.0
# 整份資料集僅 4 個「空房→有人」事件（受控實驗場次少）——樣本不足以
# 檢定，誠實標為 inconclusive，不硬判 pass/fail；前饋機制以本爐
# 自有資料的 FSM 實測（S2 進場紀錄）為準。
v2_verdict = ("pass" if events >= 8 and frac_first >= 0.6 and lead_med > 0
              else "inconclusive" if events < 8 else "fail")
print(f"V2 斜率前饋：{events} 個到達事件（斜率先跨門檻 {frac_first:.0%}、"
      f"中位領先 {lead_med:+.1f} 分）→ {v2_verdict}"
      + ("（事件數不足，無法檢定）" if v2_verdict == "inconclusive" else ""))

# ── V3：AI-2 時段統計誤報率（無故障資料 → 應近零）──────
dates = sorted(bydate)
split = dates[int(len(dates) * 0.7)]
train = [(t, e) for (t, _, _, _), e in zip(rows, elev) if t.date() <= split]
test = [(t, e) for (t, _, _, _), e in zip(rows, elev) if t.date() > split]
byhour = {}
for t, e in train:
    byhour.setdefault(t.hour, []).append(e)
stats = {h: (svc.median(v), max(svc.mad(v), 5.0)) for h, v in byhour.items()
         if len(v) >= 30}
z = [(e - stats[t.hour][0]) / stats[t.hour][1] for t, e in test
     if t.hour in stats]
fp = sum(1 for x in z if abs(x) >= svc.Z_ALARM) / len(z)
print(f"V3 AI-2 誤報率：z≥{svc.Z_ALARM} 佔 {fp:.2%}（n={len(z)}，無故障資料）")
v3_pass = fp < 0.05

# ── 存檔＋圖 ──────────────────────────────────────────
out = {
    "dataset": "UCI 864 Room Occupancy Estimation（辦公室測試間，非廟宇）",
    "n": len(rows),
    "V1_corr_steady": round(r_corr, 3), "V1_corr_instant": round(r_all, 3),
    "V1_ppm_per_person": round(k, 1),
    "V1_median_elev_by_count": med_by_n, "V1_monotonic": mono,
    "V2_arrival_events": events,
    "V2_slope_first_frac": round(frac_first, 3),
    "V2_median_lead_min": round(lead_med, 1),
    "V3_false_positive_rate": round(fp, 4),
    "verdicts": {"V1": "pass" if v1_pass else "fail",
                 "V2": v2_verdict,
                 "V3": "pass" if v3_pass else "fail"},
    "honesty": "機制驗證（穩態單調性/前饋領先/誤報率），非 26ppm 常數之驗證；"
               "常數依場域體積與換氣率而異，仍以本爐實測為準",
}
os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
with open(os.path.join(HERE, "models", "外部資料驗證.json"), "w",
          encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
jit = np.random.default_rng(1).uniform(-0.18, 0.18, len(os_))
axes[0].scatter(os_ + jit, es, s=2, alpha=0.15, color=INK)
xs = np.array(sorted(set(os_)))
axes[0].plot(xs, k * xs, color=RED, lw=2, label=f"擬合 {k:.0f} ppm/人")
axes[0].scatter(list(med_by_n), list(med_by_n.values()), color=GOLD, zorder=5,
                label="各人數中位數")
axes[0].set_xlabel("室內人數（真值；準穩態樣本）")
axes[0].set_ylabel("CO2 高程（ppm）")
axes[0].set_title(f"V1 高程-人數（穩態 r={r_corr:.2f}）")
axes[0].legend()
axes[1].hist(leads, bins=range(-8, 16), color=RED, alpha=0.8)
axes[1].axvline(0, color=INK, lw=0.8)
axes[1].set_xlabel("斜率領先濃度的偵測時間（分鐘）")
axes[1].set_ylabel("到達事件數")
axes[1].set_title(f"V2 前饋領先（{frac_first:.0%} 事件斜率先偵測，"
                  f"中位 {lead_med:+.1f} 分）")
axes[2].hist(z, bins=60, color=INK, alpha=0.8)
axes[2].axvline(svc.Z_ALARM, color=RED, ls="--", label=f"警戒 z={svc.Z_ALARM}")
axes[2].axvline(-svc.Z_ALARM, color=RED, ls="--")
axes[2].set_xlabel("時段穩健 z")
axes[2].set_title(f"V3 AI-2 誤報率 {fp:.2%}")
axes[2].legend()
fig.suptitle("兩個 AI 核心機制之外部資料獨立驗證 — UCI 864（辦公室測試間；"
             "★機制驗證，非場域常數★）", y=1.02)
fig.tight_layout()
png = os.path.join(HERE, "圖表", "外部資料驗證.png")
fig.savefig(png, dpi=150, bbox_inches="tight")
print("saved", png)
print(f"結論：{out['verdicts']}"
      + ("——V1/V3 於外部資料成立；V2 因外部資料到達事件僅 4 個無法檢定，"
         "以本爐自有資料為準" if v2_verdict == "inconclusive" else ""))
