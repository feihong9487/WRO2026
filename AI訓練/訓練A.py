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

POP, ELITE, ITERS, EPS_PER = 24, 6, 15, 2


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
std = np.ones(N_PARAM)
best_theta, best_score = None, -1e18

for it in range(ITERS):
    seeds = [3000 + it * EPS_PER + k for k in range(EPS_PER)]
    cands = mean + std * rng.standard_normal((POP, N_PARAM))
    scores = np.array([np.mean([rollout(c, s) for s in seeds])
                       for c in cands])
    elite = cands[np.argsort(scores)[-ELITE:]]
    mean = 0.7 * elite.mean(axis=0) + 0.3 * mean
    std = 0.7 * elite.std(axis=0) + 0.3 * std + 0.02
    if scores.max() > best_score:
        best_score = float(scores.max())
        best_theta = cands[int(np.argmax(scores))].copy()
    print(f"iter {it + 1:2d}/{ITERS}  best={scores.max():.2f} "
          f"mean={scores.mean():.2f}")

os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
out = os.path.join(HERE, "models", "linearA.json")
final = unpack(best_theta)
final["train"] = {"algo": "CEM", "iters": ITERS, "pop": POP,
                  "best_score_1day": round(best_score, 2),
                  "data": "★模擬環境（域隨機化）訓練，非實測★"}
with open(out, "w", encoding="utf-8") as f:
    json.dump(final, f, ensure_ascii=False, indent=1)
print("saved", out)
