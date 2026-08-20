# -*- coding: utf-8 -*-
"""
AI-1 前瞻預測(forecast)優化 — 真正有價值的問題：預測未來 h 步(30/60分)的負載，
供「前饋削峰」在人潮到達前就啟動。lag 在此是誠實輸入(截至 now 已觀測)，不作弊。

★凍結協定★ 目標 y_{t+h}；特徵僅用截至 t 的資訊 + 日曆(t+h)。
  滾動起點 CV 截點 {55,65,75,85}% 各測後 10%；判優 ≥3/4 折勝且平均更低。
  對照基線：
    - CAL@t+h  ：純日曆(部署版思路，看未來時段的日曆輪廓)
    - persist  ：y_{t+h} ≈ y_t（naive 持平，forecast 的真正對手）
    - persist_day：前一日同時刻
"""
import sys, os, json, math, importlib.util
from datetime import datetime, timedelta, timezone
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("svc", os.path.join(ROOT, "cloud_dash/ai_online_learning.py"))
svc = importlib.util.module_from_spec(spec); spec.loader.exec_module(svc)
TPE, UTC = svc.TPE, timezone.utc; PPM = svc.PPM_PER_STICK

raw = json.load(open(os.path.join(ROOT, "AI訓練/data/aroma01_co2_minutely.json"), encoding="utf-8"))
pts = sorted((datetime.fromisoformat(k), v) for k, v in raw.items())
pts = [(t if t.tzinfo else t.replace(tzinfo=UTC), v) for t, v in pts]
buck = {}
for t, v in pts:
    key = t.replace(minute=(t.minute // 30) * 30, second=0, microsecond=0)
    buck.setdefault(key, []).append(v)
series30 = sorted((k + timedelta(minutes=30), sum(v) / len(v)) for k, v in buck.items())
elev = svc.daily_elevation(series30)
data = [(t, max(0.0, e / PPM)) for t, e in elev]
idx = {t: i for i, (t, _) in enumerate(data)}
def slot(t): tl = t.astimezone(TPE); return (tl.date(), tl.hour, tl.minute // 30)
val = {slot(t): y for t, y in data}
def ystep(i, k): return data[i - k][1] if 0 <= i - k < len(data) else None
def yday(t): tl = t.astimezone(TPE); return val.get((tl.date() - timedelta(days=1), tl.hour, tl.minute // 30))
def rmean(i, k): xs = [data[j][1] for j in range(max(0, i - k), i + 1)]; return sum(xs) / len(xs) if xs else None
def slope(i, k):
    if i - k < 0: return None
    return (data[i][1] - data[i - k][1]) / k

LAMS = (0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0)
def mae(w, X, Y): return sum(abs(svc.predict(w, x) - y) for x, y in zip(X, Y)) / len(Y)
def fit_best(Xtr, Ytr):
    nv = int(len(Xtr) * 0.8); best = (1e18, 1.0)
    for lam in LAMS:
        try: w = svc.ridge_fit(Xtr[:nv], Ytr[:nv], lam)
        except ValueError: continue
        m = mae(w, Xtr[nv:], Ytr[nv:]) if nv < len(Xtr) else 1e18
        if m < best[0]: best = (m, lam)
    return svc.ridge_fit(Xtr, Ytr, best[1]), best[1]

# 特徵建構：t=當下(用 index i)，預測 data[i+h]
def make(h, feats):
    X, Y = [], []
    for i in range(len(data) - h):
        t_now = data[i][0]; t_tgt = data[i + h][0]
        vec = feats(i, t_now, t_tgt)
        if vec is None: continue
        X.append(vec); Y.append(data[i + h][1])
    return X, Y

def F_cal(i, tn, tt):     # 純日曆@目標時段
    return svc.feats_at(tt - svc.WIN_CENTER)
def F_cal_lag(i, tn, tt):
    e = [ystep(i, 0), ystep(i, 1), yday(tt), rmean(i, 3), slope(i, 3)]
    if any(x is None for x in e): return None
    return svc.feats_at(tt - svc.WIN_CENTER) + e
def F_cal_lagslim(i, tn, tt):
    e = [ystep(i, 0), yday(tt)]
    if any(x is None for x in e): return None
    return svc.feats_at(tt - svc.WIN_CENTER) + e
def F_ar_only(i, tn, tt):
    e = [1.0, ystep(i, 0), ystep(i, 1), yday(tt), rmean(i, 3), slope(i, 3)]
    if any(x is None for x in e): return None
    return e

MODELS = {"CAL(部署思路)": F_cal, "CAL+精簡AR": F_cal_lagslim,
          "CAL+完整AR": F_cal_lag, "純AR": F_ar_only}
CUTS = (0.55, 0.65, 0.75, 0.85)
def cv(h, feats):
    X, Y = make(h, feats); n = len(X); folds = []
    for c in CUTS:
        ntr = int(n * c); nte = max(1, int(n * 0.10))
        Xtr, Ytr = X[:ntr], Y[:ntr]; Xte, Yte = X[ntr:ntr + nte], Y[ntr:ntr + nte]
        if len(Xte) < 3: continue
        w, _ = fit_best(Xtr, Ytr); folds.append(mae(w, Xte, Yte))
    return folds, n
def cv_naive(h, mode):
    folds = []
    X, Y = make(h, F_cal_lagslim)  # 對齊可用列
    # 重建對齊索引
    rows = []
    for i in range(len(data) - h):
        e = [ystep(i, 0), yday(data[i + h][0])]
        if any(x is None for x in e): continue
        rows.append((ystep(i, 0), yday(data[i + h][0]), data[i + h][1]))
    n = len(rows)
    for c in CUTS:
        ntr = int(n * c); nte = max(1, int(n * 0.10))
        te = rows[ntr:ntr + nte]
        if len(te) < 3: continue
        if mode == "persist": folds.append(sum(abs(p - y) for p, _, y in te) / len(te))
        else: folds.append(sum(abs(pd - y) for _, pd, y in te) / len(te))
    return folds
def avg(xs): xs = [x for x in xs if x == x]; return sum(xs) / len(xs) if xs else float("nan")

for h, lbl in [(1, "h=1 (30分後)"), (2, "h=2 (60分後)")]:
    print(f"\n═══ 前瞻預測 {lbl}  ═══")
    base_folds, _ = cv(h, F_cal); base_avg = avg(base_folds)
    for name, fn in MODELS.items():
        folds, n = cv(h, fn); a = avg(folds)
        wins = sum(1 for bf, cf in zip(base_folds, folds) if cf < bf - 1e-9)
        v = "—(基準)" if name.startswith("CAL(") else ("★判優★" if wins >= 3 and a < base_avg - 1e-9 else "未判優")
        print(f"  {name:14s} 折=[{', '.join(f'{x:.2f}' for x in folds)}] 平均={a:.3f} 勝{wins}/4 {v} (n={n})")
    for mode, ml in [("persist", "naive持平 y_t"), ("day", "前日同時刻")]:
        bf = cv_naive(h, mode); print(f"  {ml:14s} 折=[{', '.join(f'{x:.2f}' for x in bf)}] 平均={avg(bf):.3f}")
