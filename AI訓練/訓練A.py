# -*- coding: utf-8 -*-
"""
方案 A 訓練：線性策略（13 維 obs → 4 動作）＋交叉熵法（CEM）。
每代所有候選用同一組 seed（共同隨機數）評分，域隨機化開。

    python 訓練A.py
"""
import json
import os
import random
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from incense_env import IncenseEnv
from policies import LinearPolicy

KEYS = IncenseEnv.OBS_KEYS
DIM = len(KEYS)
N_ACT = 4
N_PARAM = N_ACT * DIM + N_ACT

POP, ELITE, ITERS = 18, 5, 18
# v2：★固定配置集★——跨代分數可比（F35 根治）。
# v3：擴到 5 配置＋★種子注入★——v2 收斂到「永遠 70」的常數解，
# 這代初始族群直接塞入該常數解與手工日曆型候選，並加大初始變異，
# 測試 CEM 能否從常數局部最優逃逸（逃不出＝線性天花板的再確認）。
EVAL_SEEDS = (3000, 3001, 3002, 3003, 3004)
INIT_STD = 2.0


def handcrafted():
    """兩個注入種子：常數 70（v2 的收斂解）與日曆型（開廟+有電→220）。"""
    k = {n: i for i, n in enumerate(KEYS)}
    th70 = np.zeros(N_PARAM)
    th70[N_ACT * DIM + 1] = 3.0                     # bias 偏向動作 1（70）
    thcal = np.zeros(N_PARAM)
    W = thcal[:N_ACT * DIM].reshape(N_ACT, DIM)
    b = thcal[N_ACT * DIM:]
    b[0] = 1.0                                      # 預設關機
    W[2, k["is_open"]] = 2.5                        # 開廟 → 傾向 220
    W[2, k["battery"]] = 1.5                        # 有電才開
    b[2] = -1.2
    return [th70, thcal]


def unpack(theta):
    W = theta[:N_ACT * DIM].reshape(N_ACT, DIM)
    b = theta[N_ACT * DIM:]
    return {"W": W.tolist(), "b": b.tolist(), "obs_keys": list(KEYS)}


def rollout(theta, seed):
    env = IncenseEnv(randomize=True, episode_days=1)
    pol = LinearPolicy(model=unpack(theta))
    obs = env.reset(seed=seed)
    tot, done = 0.0, False
    while not done:
        obs, r, done, _ = env.step(pol.act(obs, env.t))
        tot += r
    return tot


rng = np.random.default_rng(42)
mean = np.zeros(N_PARAM)
std = np.ones(N_PARAM) * INIT_STD

history = []
for it in range(ITERS):
    seeds = EVAL_SEEDS
    cands = mean + std * rng.standard_normal((POP, N_PARAM))
    if it == 0:
        for j, th in enumerate(handcrafted()):
            cands[j] = th                           # v3 種子注入
    scores = np.array([np.mean([rollout(c, s) for s in seeds])
                       for c in cands])
    elite = cands[np.argsort(scores)[-ELITE:]]
    mean = 0.7 * elite.mean(axis=0) + 0.3 * mean
    std = 0.7 * elite.std(axis=0) + 0.3 * std + 0.02
    history.append([it + 1, float(scores.max()), float(scores.mean())])
    print(f"iter {it + 1:2d}/{ITERS}  best={scores.max():.2f} "
          f"mean={scores.mean():.2f}", flush=True)

best_theta = mean
# 泛化檢查用「未參與訓練評分」的獨立 seed（防對固定配置集過擬合）
best_score = float(np.mean([rollout(mean, s) for s in (3100, 3101, 3102)]))
print(f"final mean policy 獨立3-seed score = {best_score:.2f}")

os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
out = os.path.join(HERE, "models", "linearA.json")
final = unpack(best_theta)
final["train"] = {"algo": "CEM-v3 固定配置集+種子注入", "iters": ITERS, "pop": POP,
                  "eval_seeds": list(EVAL_SEEDS),
                  "indep_score_1day": round(best_score, 2),
                  "data": "★模擬環境（域隨機化）訓練，非實測★"}
with open(out, "w", encoding="utf-8") as f:
    json.dump(final, f, ensure_ascii=False, indent=1)
with open(os.path.join(HERE, "models", "cemA_history.json"), "w",
          encoding="utf-8") as f:
    json.dump({"iters": history,
               "note": "v2：固定配置集評分，跨代分數可比（越低越好）"},
              f, ensure_ascii=False)
print("saved", out)
