# -*- coding: utf-8 -*-
"""
加速實驗 — 用完整真實歷史對兩個 AI 做模型擴充與靈敏度分析。

★評估協定（先寫死，跑完不得回頭改；與 `模型方案.md` 凍結精神一致）★
  - 資料：aroma01 分鐘級 CO₂ 完整真實段（2026-08-08 01:15 後），
    聚合成 30 分鐘粒度的「香支負載代理量」（高程/26，模擬換算）
  - E2 模型競賽：滾動起點 CV——訓練截點 {55%,65%,75%,85%}，各測其後 10%；
    主指標＝四折平均 MAE；判優需四折中 ≥3 折較低且平均較低
  - E3 遷移實驗：測試段固定為最後 30%；訓練量 {24,48,72,96,全部}h 畫學習曲線
  - E4 靈敏度：注入已知故障於真實分鐘資料，量 AI-2 偵測率（門檻不動）
  - 誠實條款：挑戰者模型輸給部署版 ridge-12 → 如實報告「簡單方法已足夠」

★誠實邊界★：居家環境作息資料；負載為模擬換算代理量；所有結論限
「預測機制」層次，非廟宇負載成效。

    python 加速實驗.py           # 全部（首跑會抓雲端資料，約 1-2 分鐘）
    python 加速實驗.py --offline # 只用本地快取
"""
import importlib.util
import json
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
CACHE = os.path.join(HERE, "data", "aroma01_co2_minutely.json")

plt.rcParams["font.family"] = "Microsoft JhengHei"
plt.rcParams["axes.unicode_minus"] = False
RED, GOLD, INK, GREY, BLUE = "#9E3B2F", "#C9A227", "#33302B", "#8A8377", "#3A6B8A"

spec = importlib.util.spec_from_file_location(
    "ai_online", os.path.join(ROOT, "cloud_dash", "ai_online_learning.py"))
svc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(svc)
UTC = timezone.utc

# ══════════════ E1. 資料擴充：完整分鐘級歷史 ══════════════
print("═══ E1. 資料擴充 ═══")
if "--offline" not in sys.argv or not os.path.exists(CACHE):
    src = svc.GrafanaPublicSource()
    assert src.ok(), "公開 API 連不上，改用 --offline"
    got = src.series("sensor", ["co2"], "2026-08-08T01:15:00+08:00", every="1m")
    minutely = got["co2"]
    old = {}
    if os.path.exists(CACHE):
        old = json.load(open(CACHE, encoding="utf-8"))
    for t, v in minutely:
        old[t.astimezone(UTC).isoformat(timespec="seconds")] = round(v, 1)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(old, f)
minu = sorted((datetime.fromisoformat(k), v)
              for k, v in json.load(open(CACHE, encoding="utf-8")).items()
              if v and v > 0)
print(f"分鐘級真實 CO₂：{len(minu)} 筆"
      f"（{minu[0][0].astimezone(svc.TPE):%m-%d %H:%M} ～ "
      f"{minu[-1][0].astimezone(svc.TPE):%m-%d %H:%M} 台北）")

# 聚合成 30 分鐘粒度（窗內中位數；窗中心當時戳）
def agg(minu, step_min):
    byw = {}
    for t, v in minu:
        w = t.timestamp() // (step_min * 60)
        byw.setdefault(w, []).append(v)
    out = []
    for w, vs in sorted(byw.items()):
        if len(vs) >= step_min // 3:                      # 窗內≥1/3 樣本才採
            tc = datetime.fromtimestamp(w * step_min * 60 + step_min * 30, UTC)
            out.append((tc, float(np.median(vs))))
    return out

half = agg(minu, 30)
# 高程（當日台北最小值為基線；日樣本 < 12 個半小時窗不採）
bydate = {}
for t, v in half:
    bydate.setdefault(t.astimezone(svc.TPE).date(), []).append((t, v))
data = []
for d, rows in sorted(bydate.items()):
    if len(rows) < 12:
        continue
    base = min(v for _, v in rows)
    data.extend((t, max(0.0, (v - base) / svc.PPM_PER_STICK)) for t, v in rows)
data.sort()
print(f"30 分鐘粒度訓練列：{len(data)}（小時粒度舊法約 {len(data)//2}）")

X12 = np.array([svc.feats_at(t) for t, _ in data])
Y = np.array([y for _, y in data])

# ══════════════ E2. 模型競賽（滾動起點 CV）══════════════
print("═══ E2. 模型競賽 ═══")

def feats_ext(t):
    """挑戰者特徵：12 維部署特徵＋2 次諧波＋午/夜高斯（16 維，仍純日曆）。"""
    base = svc.feats_at(t)
    tl = t.astimezone(svc.TPE)
    h = tl.hour + tl.minute / 60.0
    return base + [math.sin(4 * math.pi * h / 24), math.cos(4 * math.pi * h / 24),
                   math.exp(-((h - 13.0) ** 2) / 8.0),
                   math.exp(-((h - 22.5) ** 2) / 4.5)]

X16 = np.array([feats_ext(t) for t, _ in data])

def fit_ridge(X, Y, lam_grid=(0.1, 1.0, 10.0, 100.0)):
    n_v = int(len(X) * 0.8)
    best = (1e18, None)
    for lam in lam_grid:
        w = np.linalg.solve(X[:n_v].T @ X[:n_v] + lam * np.eye(X.shape[1]),
                            X[:n_v].T @ Y[:n_v])
        m = float(np.mean(np.abs(np.maximum(0, X[n_v:] @ w) - Y[n_v:])))
        if m < best[0]:
            best = (m, lam)
    lam = best[1]
    return np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ Y), lam

class MLP:
    """12→16→1，tanh，Adam，早停於內部驗證段。純 numpy。"""

    def __init__(self, d, h=16, seed=0):
        r = np.random.default_rng(seed)
        self.W1 = r.normal(0, 1 / math.sqrt(d), (d, h))
        self.b1 = np.zeros(h)
        self.W2 = r.normal(0, 1 / math.sqrt(h), h)
        self.b2 = 0.0

    def fwd(self, X):
        return np.maximum(0.0, np.tanh(X @ self.W1 + self.b1) @ self.W2 + self.b2)

    def fit(self, X, Y, epochs=800, lr=3e-3):
        n_v = int(len(X) * 0.8)
        Xt, Yt, Xv, Yv = X[:n_v], Y[:n_v], X[n_v:], Y[n_v:]
        params = [self.W1, self.b1, self.W2]
        m = [np.zeros_like(p, dtype=float) for p in params] + [0.0]
        v = [np.zeros_like(p, dtype=float) for p in params] + [0.0]
        best, best_state, wait = 1e18, None, 0
        for ep in range(epochs):
            H = np.tanh(Xt @ self.W1 + self.b1)
            out = H @ self.W2 + self.b2
            err = np.where(out > 0, out, 0.0) - Yt
            err *= (out > 0)
            gW2 = H.T @ err / len(Xt)
            gb2 = float(err.mean())
            dH = np.outer(err, self.W2) * (1 - H ** 2)
            gW1 = Xt.T @ dH / len(Xt)
            gb1 = dH.mean(axis=0)
            for i, (p, g) in enumerate(zip(params + [None],
                                           [gW1, gb1, gW2, gb2])):
                m[i] = 0.9 * m[i] + 0.1 * g
                v[i] = 0.999 * v[i] + 0.001 * (g ** 2 if i == 3 else g * g)
                step = lr * m[i] / (np.sqrt(v[i]) + 1e-8)
                if i == 0:
                    self.W1 -= step
                elif i == 1:
                    self.b1 -= step
                elif i == 2:
                    self.W2 -= step
                else:
                    self.b2 -= step
            if ep % 10 == 0:
                mv = float(np.mean(np.abs(self.fwd(Xv) - Yv)))
                if mv < best - 1e-4:
                    best, wait = mv, 0
                    best_state = (self.W1.copy(), self.b1.copy(),
                                  self.W2.copy(), self.b2)
                else:
                    wait += 1
                    if wait >= 12:
                        break
        if best_state:
            self.W1, self.b1, self.W2, self.b2 = best_state
        return self

FOLDS = (0.55, 0.65, 0.75, 0.85)
models = {"ridge-12（部署版）": lambda tr, te: _ridge_eval(X12, tr, te),
          "ridge-16（擴充日曆）": lambda tr, te: _ridge_eval(X16, tr, te),
          "MLP 12-16-1": lambda tr, te: _mlp_eval(X12, tr, te),
          "常數": lambda tr, te: float(np.mean(np.abs(Y[tr].mean() - Y[te]))),
          "前日同時刻": lambda tr, te: _persist_eval(tr, te)}

def _ridge_eval(X, tr, te):
    w, _ = fit_ridge(X[tr], Y[tr])
    return float(np.mean(np.abs(np.maximum(0, X[te] @ w) - Y[te])))

def _mlp_eval(X, tr, te):
    mlp = MLP(X.shape[1], seed=0).fit(X[tr], Y[tr])
    return float(np.mean(np.abs(mlp.fwd(X[te]) - Y[te])))

def _persist_eval(tr, te):
    lookup = {(data[i][0].astimezone(svc.TPE).date(),
               data[i][0].astimezone(svc.TPE).hour,
               data[i][0].astimezone(svc.TPE).minute // 30): Y[i] for i in tr}
    errs = []
    for i in te:
        tl = data[i][0].astimezone(svc.TPE)
        p = lookup.get((tl.date() - timedelta(days=1), tl.hour, tl.minute // 30))
        if p is not None:
            errs.append(abs(p - Y[i]))
    return float(np.mean(errs)) if errs else float("nan")

cv = {name: [] for name in models}
n = len(data)
for frac in FOLDS:
    cut = int(n * frac)
    te_end = min(n, int(n * (frac + 0.10)))
    tr, te = np.arange(cut), np.arange(cut, te_end)
    for name, fn in models.items():
        cv[name].append(fn(tr, te))
print(f"{'模型':<18}" + "".join(f"折{i+1:>7}" for i in range(len(FOLDS))) + "   平均")
for name, errs in cv.items():
    print(f"{name:<18}" + "".join(f"{e:8.2f}" for e in errs)
          + f" {np.nanmean(errs):6.2f}")
dep = np.array(cv["ridge-12（部署版）"])
verdict = {}
for name in ("ridge-16（擴充日曆）", "MLP 12-16-1"):
    ch = np.array(cv[name])
    wins = int((ch < dep).sum())
    verdict[name] = {"折勝": wins, "平均較低": bool(np.nanmean(ch) < np.nanmean(dep)),
                     "判優": bool(wins >= 3 and np.nanmean(ch) < np.nanmean(dep))}
    print(f"  {name}: 勝 {wins}/4 折、平均{'較低' if verdict[name]['平均較低'] else '較高'}"
          f" → {'判優' if verdict[name]['判優'] else '未勝過部署版'}")

# ══════════════ E3. 模擬預訓練 + 真實微調 ══════════════
print("═══ E3. 遷移學習曲線 ═══")
from sim_config import SimConfig
from visitors import VisitorModel, lunar_day as sim_lunar

rng = random.Random(777)
Xs, Ys = [], []
for ci in range(10):
    cfg = SimConfig().randomize(rng)
    start_dow = rng.randrange(7)
    vm = VisitorModel(cfg, random.Random(rng.randrange(10 ** 9)),
                      start_weekday=start_dow)
    stick_ends = []
    for day in range(20):
        ld = sim_lunar(cfg, day)
        dow = (start_dow + day) % 7
        for hour in range(24):
            acc, cnt = 0.0, 0
            for k in range(60):
                t = day * 86400 + hour * 3600 + k * 60.0
                _, new = vm.step(t, 60.0)
                for _ in range(new):
                    stick_ends.append(t + cfg.BURN_MIN * 60.0)
                stick_ends = [e for e in stick_ends if e > t]
                acc += len(stick_ends)
                cnt += 1
            io = 1.0 if cfg.OPEN_HOUR <= hour < cfg.CLOSE_HOUR else 0.0
            Xs.append(svc.feats(hour, ld, dow, io))
            Ys.append(acc / cnt)
Xs, Ys = np.array(Xs), np.array(Ys)
w_sim, _ = fit_ridge(Xs, Ys)
print(f"模擬預訓練完成（{len(Ys)} 樣本，10 組域隨機化 × 20 天）")

cut = int(n * 0.7)
Xte_, Yte_ = X12[cut:], Y[cut:]
sizes = [48, 96, 144, 192, cut]          # 30 分鐘列數（24h=48 列）
curve_real, curve_tx = [], []
LAM_TX = 30.0
for s in sizes:
    s = min(s, cut)
    Xtr_, Ytr_ = X12[cut - s:cut], Y[cut - s:cut]   # 用測試段前最近 s 列
    w_r, _ = fit_ridge(Xtr_, Ytr_) if s >= 24 else (np.zeros(12), 0)
    curve_real.append(float(np.mean(np.abs(np.maximum(0, Xte_ @ w_r) - Yte_))))
    # 微調＝以 w_sim 為中心的 Tikhonov：(XᵀX+λI)w = XᵀY + λ·w_sim
    w_t = np.linalg.solve(Xtr_.T @ Xtr_ + LAM_TX * np.eye(12),
                          Xtr_.T @ Ytr_ + LAM_TX * w_sim)
    curve_tx.append(float(np.mean(np.abs(np.maximum(0, Xte_ @ w_t) - Yte_))))
w_s_only = float(np.mean(np.abs(np.maximum(0, Xte_ @ w_sim) - Yte_)))
hrs = [s / 2 for s in sizes]
print("訓練時數     ", "  ".join(f"{h:6.0f}" for h in hrs))
print("真實-only MAE", "  ".join(f"{m:6.2f}" for m in curve_real))
print("模擬+微調 MAE", "  ".join(f"{m:6.2f}" for m in curve_tx))
print(f"純模擬（零真實資料）MAE {w_s_only:.2f}")

# ══════════════ E4. AI-2 故障注入靈敏度 ══════════════
print("═══ E4. AI-2 靈敏度矩陣 ═══")
now = minu[-1][0]
h26 = [(t, v) for t, v in minu if t >= now - timedelta(hours=26)]
r = np.random.default_rng(5)
base_min = {"co2": h26,
            "t_scd": [(t, 25.0 + 0.05 * r.standard_normal()) for t, _ in h26],
            "t_sht": [(t, 25.5 + 0.05 * r.standard_normal()) for t, _ in h26],
            "rh_scd": [(t, 50.0 + 0.2 * r.standard_normal()) for t, _ in h26],
            "rh_sht": [(t, 52.0 + 0.2 * r.standard_normal()) for t, _ in h26],
            "fan_duty": [(t, 70.0) for t, _ in h26],
            "fan_actual": [(t, 70.0) for t, _ in h26]}
hourly_real = agg(minu, 60)
am = svc.retrain_anomaly(hourly_real, base_min, {})

def inject(kind, mag):
    m2 = {k: list(v) for k, v in base_min.items()}
    if kind == "t_jump":
        m2["t_scd"] = [(t, v + (mag if t >= now - timedelta(hours=24) else 0))
                       for t, v in m2["t_scd"]]
    elif kind == "dropout":
        keep = now - timedelta(minutes=60 * (1 - mag))
        m2["co2"] = [(t, v) for t, v in m2["co2"]
                     if t < now - timedelta(hours=1) or t >= keep]
    elif kind == "fan_under":
        m2["fan_actual"] = [(t, max(0.0, v - mag)) for t, v in m2["fan_actual"]]
    return m2

matrix = {}
for kind, mags, field in (("t_jump", (0.3, 0.5, 1.0, 2.0), "t_bias_z"),
                          ("dropout", (0.3, 0.5, 0.7, 0.9), "dropout"),
                          ("fan_under", (10, 15, 25, 50), "duty_mismatch")):
    row = {}
    for mag in mags:
        sc = svc.score_anomaly(am, inject(kind, mag), now)
        detected = (abs(sc["t_bias_z"]) >= svc.Z_ALARM if kind == "t_jump"
                    else sc["flag"] == 1)
        row[mag] = {"值": sc[field], "偵測": bool(detected)}
    matrix[kind] = row
    print(f"  {kind}: " + "  ".join(
        f"{m}→{'✔' if row[m]['偵測'] else '✘'}({row[m]['值']})" for m in mags))
sc0 = svc.score_anomaly(am, base_min, now)
print(f"  無故障對照：flag={sc0['flag']}"
      f"（co2_z={sc0['co2_z']}——真實 CO₂ 異常高屬環境事實，見 E4 註記）")

# ══════════════ 存檔＋圖 ══════════════
out = {
    "protocol": "滾動起點 CV {55,65,75,85}%×10%；判優需 ≥3/4 折勝＋平均低；"
                "E3 測試段固定最後 30%；E4 門檻不動",
    "E1_rows_30min": len(data), "E1_minutes": len(minu),
    "E2_cv_mae": {k: [round(float(x), 3) for x in v] for k, v in cv.items()},
    "E2_verdict": verdict,
    "E3_hours": hrs, "E3_real_only": [round(x, 3) for x in curve_real],
    "E3_sim_finetune": [round(x, 3) for x in curve_tx],
    "E3_sim_only": round(w_s_only, 3), "E3_lam_tx": LAM_TX,
    "E4_matrix": {k: {str(m): v for m, v in row.items()}
                  for k, row in matrix.items()},
    "honesty": "居家作息資料、負載為模擬換算代理量；結論限預測機制層次。"
               "挑戰者若未判優，依第 19 週承諾如實報告「簡單方法已足夠」。",
}
with open(os.path.join(HERE, "models", "加速實驗結果.json"), "w",
          encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
names = list(cv)
means = [float(np.nanmean(cv[k])) for k in names]
colors = [RED, BLUE, GOLD, GREY, GREY]
axes[0].bar(range(len(names)), means, color=colors)
axes[0].set_xticks(range(len(names)),
                   [n.replace("（", "\n（") for n in names], fontsize=8)
axes[0].set_ylabel("四折平均 MAE（支）")
axes[0].set_title("E2 模型競賽（滾動起點 CV）")
for i, v in enumerate(means):
    axes[0].text(i, v * 1.01, f"{v:.2f}", ha="center", fontsize=8)
axes[1].plot(hrs, curve_real, "o-", color=INK, label="真實-only")
axes[1].plot(hrs, curve_tx, "s-", color=RED, label="模擬預訓練＋微調")
axes[1].axhline(w_s_only, color=GREY, ls="--", label=f"純模擬 {w_s_only:.1f}")
axes[1].set_xlabel("真實訓練時數")
axes[1].set_ylabel("固定測試段 MAE（支）")
axes[1].set_title("E3 資料飛輪：模擬知識的小樣本增益")
axes[1].legend()
labels, det = [], []
for kind, row in matrix.items():
    for m, v in row.items():
        labels.append(f"{kind}\n{m}")
        det.append(1 if v["偵測"] else 0)
axes[2].bar(range(len(labels)), det,
            color=[RED if d else GREY for d in det])
axes[2].set_xticks(range(len(labels)), labels, fontsize=7)
axes[2].set_yticks([0, 1], ["漏報", "偵測"])
axes[2].set_title("E4 AI-2 故障注入靈敏度（門檻不動）")
fig.suptitle("加速實驗 — 真實資料模型擴充（居家作息；★代理量／機制層次★）",
             y=1.03)
fig.tight_layout()
png = os.path.join(HERE, "圖表", "加速實驗.png")
fig.savefig(png, dpi=150, bbox_inches="tight")
print("saved", png)
