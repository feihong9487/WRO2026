# -*- coding: utf-8 -*-
"""
方案 C 訓練 v4：CEM-MLP 算力強化版——給挑戰者公平的算力。

v3 是筆電十幾分鐘的小預算（POP24×ITERS18×3seeds×1天 ≈ 1,296 回合）。
v4 的問題意識：C 輸給 B，是「RL/演化不適合這問題」還是「算力沒給夠」？
給足算力再輸，結論才硬。

v4 相對 v3 的改動（全在訓練側，凍結評估協定 1001–1010 不碰）：
  1. ★3 天回合★——凍結評比就是 3 天情境（跨日電量預算），v3 用 1 天
     訓練等於沒看過「昨天花太兇今天沒電」的後果
  2. 算力 ×24：POP 48 × ITERS 40 × 4 eval seeds × 3 天
  3. 鏡像抽樣（antithetic）：±ε 成對，降低梯度估計變異
  4. 雙架構 HID∈{16,24} 各訓一支，於★訓練側★獨立 seeds（3300–3305）
     選拔，勝者存 mlpC.json（v3 產物備份為 mlpC_v3.json）
  5. 多進程平行（ProcessPoolExecutor）

★模擬環境訓練，非實測★    python 訓練C_v4.py
"""
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from incense_env import IncenseEnv
from policies import ACTIONS, _SCALES

KEYS = IncenseEnv.OBS_KEYS
DIM, NA = len(KEYS), len(ACTIONS)
POP, ITERS, ELITE_FRAC = 48, 40, 0.25
EVAL_SEEDS = (3200, 3201, 3202, 3203)      # 候選比較用固定配置集
SELECT_SEEDS = (3300, 3301, 3302, 3303, 3304, 3305)  # 架構選拔（訓練側）
DAYS = 3
SCALE_VEC = np.array([_SCALES.get(k, 1.0) for k in KEYS])


def n_param(hid):
    return hid * DIM + hid + NA * hid + NA


def unpack(theta, hid):
    i = 0
    W1 = theta[i:i + hid * DIM].reshape(hid, DIM); i += hid * DIM
    b1 = theta[i:i + hid]; i += hid
    W2 = theta[i:i + NA * hid].reshape(NA, hid); i += NA * hid
    b2 = theta[i:i + NA]
    return W1, b1, W2, b2


def rollout(args):
    theta, hid, seed = args
    W1, b1, W2, b2 = unpack(np.asarray(theta), hid)
    env = IncenseEnv(randomize=True, episode_days=DAYS)
    obs = env.reset(seed=seed)
    tot, done = 0.0, False
    while not done:
        x = np.array([float(obs[k]) for k in KEYS]) * SCALE_VEC
        q = W2 @ np.tanh(W1 @ x + b1) + b2
        obs, r, done, _ = env.step(ACTIONS[int(np.argmax(q))])
        tot += r
    return tot


def cem_train(hid, pool, log):
    npar = n_param(hid)
    rng = np.random.default_rng(1000 + hid)
    mean = np.zeros(npar)
    std = np.ones(npar)
    n_elite = int(POP * ELITE_FRAC)
    hist = []
    for it in range(ITERS):
        eps = rng.standard_normal((POP // 2, npar)) * std
        cands = np.concatenate([mean + eps, mean - eps])   # 鏡像抽樣
        jobs = [(c.tolist(), hid, s) for c in cands for s in EVAL_SEEDS]
        rews = np.array(list(pool.map(rollout, jobs, chunksize=4)))
        scores = rews.reshape(len(cands), len(EVAL_SEEDS)).mean(axis=1)
        elite = cands[np.argsort(scores)[-n_elite:]]
        mean = 0.7 * elite.mean(axis=0) + 0.3 * mean
        std = 0.7 * elite.std(axis=0) + 0.3 * std + 0.02
        hist.append([it + 1, float(scores.max()), float(scores.mean())])
        log(f"  HID={hid} iter {it + 1:2d}/{ITERS} "
            f"best={scores.max():9.2f} mean={scores.mean():9.2f}")
    sel = [(mean.tolist(), hid, s) for s in SELECT_SEEDS]
    sel_score = float(np.mean(list(pool.map(rollout, sel))))
    return mean, sel_score, hist


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    nw = max(2, (os.cpu_count() or 4) - 2)
    print(f"v4 訓練啟動：POP={POP}×ITERS={ITERS}×{len(EVAL_SEEDS)}seeds×{DAYS}天"
          f"，{nw} 進程")
    results = {}
    with ProcessPoolExecutor(max_workers=nw) as pool:
        for hid in (16, 24):
            mean, sel, hist = cem_train(hid, pool, print)
            results[hid] = (mean, sel, hist)
            print(f"HID={hid} 訓練側選拔分數（6 獨立 seeds）= {sel:.2f}")
    best_hid = max(results, key=lambda h: results[h][1])
    mean, sel, hist = results[best_hid]
    print(f"勝者：HID={best_hid}（{sel:.2f}）  總耗時 {time.time()-t0:.0f}s")

    src = os.path.join(HERE, "models", "mlpC.json")
    if os.path.exists(src):
        shutil.copy(src, os.path.join(HERE, "models", "mlpC_v3.json"))
    W1, b1, W2, b2 = unpack(mean, best_hid)
    with open(src, "w", encoding="utf-8") as f:
        json.dump({"layers": [[W1.tolist(), b1.tolist()],
                              [W2.tolist(), b2.tolist()]],
                   "obs_keys": list(KEYS),
                   "train": {"algo": "CEM-MLP v4（算力×24、3天回合、鏡像抽樣、"
                                     "雙架構訓練側選拔）",
                             "hidden": best_hid, "iters": ITERS, "pop": POP,
                             "days": DAYS, "eval_seeds": list(EVAL_SEEDS),
                             "select_seeds": list(SELECT_SEEDS),
                             "select_score_3day": round(sel, 2),
                             "data": "★模擬環境（域隨機化）訓練，非實測★"}},
                  f, ensure_ascii=False)
    with open(os.path.join(HERE, "models", "cemC_v4_history.json"), "w",
              encoding="utf-8") as f:
        json.dump({"by_hid": {str(h): results[h][2] for h in results},
                   "winner": best_hid,
                   "note": "v4 各架構 CEM 歷程（分數越高越好＝報酬）"},
                  f, ensure_ascii=False)
    print("saved", src, "（v3 已備份 mlpC_v3.json）")


if __name__ == "__main__":
    main()
