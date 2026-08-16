# -*- coding: utf-8 -*-
"""
方案 B 訓練：負載預測器（ridge 回歸，閉式解）。

資料：以隨機化的 VisitorModel 合成 1,200 天「日曆特徵 → 每小時同時
燃燒香支數」樣本（訓練 1,000 天／保留 200 天驗證 MAE）。
★合成資料訓練——aroma01 真實 CO2 歷史累積後應重訓並回報真實 MAE★

    python 訓練B.py
"""
import json
import math
import os
import random
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sim_config import SimConfig
from visitors import VisitorModel, lunar_day
from policies import PredictSchedule

rng = random.Random(777)
DAYS_PER_CFG = 30
N_CFG = 40
DT = 60.0

X, Y = [], []
for ci in range(N_CFG):
    cfg = SimConfig().randomize(rng)
    start_dow = rng.randrange(7)
    vm = VisitorModel(cfg, random.Random(rng.randrange(10 ** 9)),
                      start_weekday=start_dow)
    stick_ends = []
    for day in range(DAYS_PER_CFG):
        ld = lunar_day(cfg, day)
        dow = (start_dow + day) % 7
        for hour in range(24):
            acc, cnt = 0.0, 0
            for k in range(int(3600 / DT)):
                t = day * 86400 + hour * 3600 + k * DT
                _, new = vm.step(t, DT)
                for _ in range(new):
                    stick_ends.append(t + cfg.BURN_MIN * 60.0)
                stick_ends = [e for e in stick_ends if e > t]
                acc += len(stick_ends)
                cnt += 1
            is_open = 1.0 if cfg.OPEN_HOUR <= hour < cfg.CLOSE_HOUR else 0.0
            X.append(PredictSchedule.feats(hour, ld, dow, is_open))
            Y.append(acc / cnt)

X = np.array(X)
Y = np.array(Y)
n_tr = 1000 * 24
Xtr, Ytr, Xva, Yva = X[:n_tr], Y[:n_tr], X[n_tr:], Y[n_tr:]


def fit(Xt, Yt, lam):
    return np.linalg.solve(Xt.T @ Xt + lam * np.eye(X.shape[1]), Xt.T @ Yt)


def val_mae(w):
    return float(np.mean(np.abs(np.maximum(0.0, Xva @ w) - Yva)))


# v2 優化一：λ 以驗證集選擇（原固定 1.0）
lams = [0.1, 1.0, 10.0, 100.0]
maes = {l: val_mae(fit(Xtr, Ytr, l)) for l in lams}
lam = min(maes, key=maes.get)
w = fit(Xtr, Ytr, lam)
mae = maes[lam]
base_mae = float(np.mean(np.abs(Yva.mean() - Yva)))   # 常數預測基線

# v2 優化二：學習曲線（訓練天數 vs 驗證 MAE）→ B 的損失變化圖
curve = []
for days in (100, 250, 500, 750, 1000):
    wq = fit(Xtr[:days * 24], Ytr[:days * 24], lam)
    curve.append([days, val_mae(wq)])
with open(os.path.join(HERE, "models", "predictorB_history.json"), "w",
          encoding="utf-8") as f:
    json.dump({"learning_curve_days_mae": curve,
               "lambda_sweep": {str(k): round(v, 3) for k, v in maes.items()},
               "chosen_lambda": lam, "const_baseline_mae": round(base_mae, 3),
               "note": "★合成資料；MAE 單位＝同時燃燒香支數★"},
              f, ensure_ascii=False)

os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
out = os.path.join(HERE, "models", "predictorB.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"w": w.tolist(),
               "feat_names": ["bias", "hour_sin", "hour_cos", "morning",
                              "evening", "lunar_peak", "weekend", "is_open",
                              "open*morning*lunar", "open*evening*lunar",
                              "open*weekend", "open*lunar"],
               "train_days": 1000, "val_days": 200,
               "val_mae_sticks": round(mae, 3),
               "const_baseline_mae": round(base_mae, 3),
               "data": "synthetic-visitor-model（★模擬資料，待真實歷史重訓★)"},
              f, ensure_ascii=False, indent=1)
print(f"樣本 {len(Y)} 小時｜驗證 MAE = {mae:.2f} 支"
      f"（常數基線 {base_mae:.2f} 支）｜saved {out}")
