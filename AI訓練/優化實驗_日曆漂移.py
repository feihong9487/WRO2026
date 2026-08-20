# -*- coding: utf-8 -*-
"""
AI-1 日曆輪廓模型優化 — 純日曆信息集內(不引入 lag，避免重複 nowcast 實測)，
看能否更好擬合「這個時刻平常多忙」。與現役同設定：feats_at(t-WIN_CENTER)→y_t，
全部 255 列，滾動起點 CV 公平比較。判優 ≥3/4 折勝且平均更低。
"""
import sys, os, json, math, importlib.util
from datetime import datetime, timedelta, timezone
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("svc", os.path.join(ROOT, "cloud_dash/ai_online_learning.py"))
svc = importlib.util.module_from_spec(spec); spec.loader.exec_module(svc)
TPE, UTC = svc.TPE, timezone.utc; PPM = svc.PPM_PER_STICK

raw = json.load(open(os.path.join(ROOT, "AI訓練/data/aroma01_co2_minutely.json"), encoding="utf-8"))
pts = sorted(((datetime.fromisoformat(k)), v) for k, v in raw.items())
pts = [(t if t.tzinfo else t.replace(tzinfo=UTC), v) for t, v in pts]
buck = {}
for t, v in pts:
    key = t.replace(minute=(t.minute // 30) * 30, second=0, microsecond=0)
    buck.setdefault(key, []).append(v)
series30 = sorted((k + timedelta(minutes=30), sum(v) / len(v)) for k, v in buck.items())
data = [(t, max(0.0, e / PPM)) for t, e in svc.daily_elevation(series30)]

def base_feats(t):  # 現役 12 維
    return svc.feats_at(t - svc.WIN_CENTER)

def harm_feats(t):  # 現役 + 二次/三次諧波(更細時段輪廓)
    tl = (t - svc.WIN_CENTER).astimezone(TPE)
    h = tl.hour + tl.minute / 60.0
    extra = [math.sin(4 * math.pi * h / 24), math.cos(4 * math.pi * h / 24),
             math.sin(6 * math.pi * h / 24), math.cos(6 * math.pi * h / 24)]
    return base_feats(t) + extra

def lunar_cont(t):  # 現役 + 農曆連續(sin/cos) 取代硬門檻
    tl = t - svc.WIN_CENTER
    ld = svc.lunar_day(tl.timestamp())
    extra = [math.sin(2 * math.pi * ld / svc.SYN), math.cos(2 * math.pi * ld / svc.SYN)]
    return base_feats(t) + extra

def hour_dow(t):    # 現役 + hour×weekend 諧波交互
    tl = (t - svc.WIN_CENTER).astimezone(TPE)
    h = tl.hour + tl.minute / 60.0; we = 1.0 if tl.weekday() >= 5 else 0.0
    extra = [we * math.sin(2 * math.pi * h / 24), we * math.cos(2 * math.pi * h / 24)]
    return base_feats(t) + extra

def full(t):        # 全部加法
    tl = (t - svc.WIN_CENTER).astimezone(TPE)
    h = tl.hour + tl.minute / 60.0; we = 1.0 if tl.weekday() >= 5 else 0.0
    ld = svc.lunar_day((t - svc.WIN_CENTER).timestamp())
    extra = [math.sin(4 * math.pi * h / 24), math.cos(4 * math.pi * h / 24),
             math.sin(6 * math.pi * h / 24), math.cos(6 * math.pi * h / 24),
             math.sin(2 * math.pi * ld / svc.SYN), math.cos(2 * math.pi * ld / svc.SYN),
             we * math.sin(2 * math.pi * h / 24), we * math.cos(2 * math.pi * h / 24)]
    return base_feats(t) + extra

MODELS = {"現役 CAL-12": base_feats, "+諧波2/3次(16)": harm_feats,
          "+農曆連續(14)": lunar_cont, "+hour×we諧波(14)": hour_dow, "+全部(20)": full}
LAMS = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0)
CUTS = (0.55, 0.65, 0.75, 0.85)
def mae(w, X, Y): return sum(abs(svc.predict(w, x) - y) for x, y in zip(X, Y)) / len(Y)
def fit_best(Xtr, Ytr):
    nv = int(len(Xtr) * 0.8); best = (1e18, 1.0)
    for lam in LAMS:
        try: w = svc.ridge_fit(Xtr[:nv], Ytr[:nv], lam)
        except ValueError: continue
        m = mae(w, Xtr[nv:], Ytr[nv:]) if nv < len(Xtr) else 1e18
        if m < best[0]: best = (m, lam)
    return svc.ridge_fit(Xtr, Ytr, best[1]), best[1]
def cv(feats):
    X = [feats(t) for t, _ in data]; Y = [y for _, y in data]; n = len(X); folds = []; lams = []
    for c in CUTS:
        ntr = int(n * c); nte = max(1, int(n * 0.10))
        w, lam = fit_best(X[:ntr], Y[:ntr]); lams.append(lam)
        Xte, Yte = X[ntr:ntr + nte], Y[ntr:ntr + nte]
        folds.append(mae(w, Xte, Yte))
    return folds, lams
def avg(xs): return sum(xs) / len(xs)

print("═══ 純日曆信息集內優化(全 255 列，公平比較) ═══")
bf, _ = cv(base_feats); ba = avg(bf)
for name, fn in MODELS.items():
    folds, lams = cv(fn); a = avg(folds)
    wins = sum(1 for x, y in zip(bf, folds) if y < x - 1e-9)
    v = "—(基準)" if name.startswith("現役") else ("★判優★" if wins >= 3 and a < ba - 1e-9 else "未判優")
    print(f"  {name:16s} 折=[{', '.join(f'{x:.2f}' for x in folds)}] 平均={a:.3f} 勝{wins}/4 {v}")

# ── 決定性穩健檢驗：9 個截點細粒度滾動 ──
print("\n═══ 穩健檢驗：9 截點(50%~90%)細粒度滾動 ═══")
CUTS9 = tuple(round(0.50 + 0.05 * i, 2) for i in range(9))
def cv9(feats):
    X = [feats(t) for t, _ in data]; Y = [y for _, y in data]; n = len(X); folds = []
    for c in CUTS9:
        ntr = int(n * c); nte = max(1, int(n * 0.08))
        w, _ = fit_best(X[:ntr], Y[:ntr])
        folds.append(mae(w, X[ntr:ntr + nte], Y[ntr:ntr + nte]))
    return folds
bf9 = cv9(base_feats)
for name, fn in [("+農曆連續(14)", lunar_cont), ("+全部(20)", full)]:
    f9 = cv9(fn)
    wins = sum(1 for x, y in zip(bf9, f9) if y < x - 1e-9)
    print(f"  {name:16s} 勝 {wins}/9 折  平均 {avg(f9):.3f} (vs 現役 {avg(bf9):.3f})")
    print(f"    現役折: [{', '.join(f'{x:.1f}' for x in bf9)}]")
    print(f"    挑戰折: [{', '.join(f'{x:.1f}' for x in f9)}]")

# ── 決定性對照：農曆勝利 = 真農曆效應 還是 吸收線性漂移? ──
print("\n═══ 決定性對照：農曆 vs 純線性趨勢(排除漂移伪影) ═══")
t0 = data[0][0].timestamp(); tspan = data[-1][0].timestamp() - t0
def trend_feats(t):   # 現役 + 純線性時間趨勢(標準化)
    tt = ((t - svc.WIN_CENTER).timestamp() - t0) / tspan
    return base_feats(t) + [tt]
def trend_quad(t):    # 現役 + 線性+二次趨勢
    tt = ((t - svc.WIN_CENTER).timestamp() - t0) / tspan
    return base_feats(t) + [tt, tt * tt]
def lunar_plus_trend(t):  # 農曆連續 + 趨勢(若農曆是真效應,加趨勢後農曆仍有增量)
    tt = ((t - svc.WIN_CENTER).timestamp() - t0) / tspan
    return lunar_cont(t) + [tt]
for name, fn in [("+純線性趨勢(13)", trend_feats), ("+線性+二次趨勢(14)", trend_quad),
                 ("+農曆連續(14)", lunar_cont), ("農曆+趨勢(15)", lunar_plus_trend)]:
    f9 = cv9(fn); wins = sum(1 for x, y in zip(bf9, f9) if y < x - 1e-9)
    print(f"  {name:18s} 勝 {wins}/9  平均 {avg(f9):.3f} (現役 {avg(bf9):.3f})")
