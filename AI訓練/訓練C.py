# -*- coding: utf-8 -*-
"""
方案 C 訓練 v3：小型 MLP（13→16→4）＋ CEM 演化——換掉 DQN。

為什麼換演算法（v3 的核心假設）：
  DQN 連兩輪敗在跨日電量預算（v1 勝7/10、v2 勝1/10 且無電 18.3 h/日），
  診斷指向 bootstrap 信用分配撐不起日尺度的延遲代價。CEM 直接優化
  ★整回合報酬★，沒有 bootstrap——若 v3 顯著優於 v2，證明死因是訓練法；
  若仍輸給 B，則「顯式最佳化才是對的工具」的結論再添一組對照。
  同時與方案 A（線性×演化）構成 2×2：非線性是否帶來增量，一測便知。

DQN v1/v2 產物保留（dqnC_v1/v2.json）；本檔產出 mlpC.json。
★模擬環境訓練，非實測★    python 訓練C.py
"""
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from incense_env import IncenseEnv
from policies import ACTIONS, _SCALES

KEYS = IncenseEnv.OBS_KEYS
DIM, NA, HID = len(KEYS), len(ACTIONS), 16
N_PARAM = HID * DIM + HID + NA * HID + NA          # 292

POP, ELITE, ITERS = 24, 6, 18
EVAL_SEEDS = (3200, 3201, 3202)                    # 固定配置集（同 v2/A 紀律）
INIT_STD = 1.0

SCALE_VEC = np.array([_SCALES.get(k, 1.0) for k in KEYS])


def unpack(theta):
    i = 0
    W1 = theta[i:i + HID * DIM].reshape(HID, DIM); i += HID * DIM
    b1 = theta[i:i + HID]; i += HID
    W2 = theta[i:i + NA * HID].reshape(NA, HID); i += NA * HID
    b2 = theta[i:i + NA]
    return W1, b1, W2, b2


def rollout(theta, seed):
    W1, b1, W2, b2 = unpack(theta)
    env = IncenseEnv(randomize=True, episode_days=1)
    obs = env.reset(seed=seed)
    tot, done = 0.0, False
    while not done:
        x = np.array([float(obs[k]) for k in KEYS]) * SCALE_VEC
        q = W2 @ np.tanh(W1 @ x + b1) + b2
        obs, r, done, _ = env.step(ACTIONS[int(np.argmax(q))])
        tot += r
    return tot


rng = np.random.default_rng(99)
mean = np.zeros(N_PARAM)
std = np.ones(N_PARAM) * INIT_STD
history = []
for it in range(ITERS):
    cands = mean + std * rng.standard_normal((POP, N_PARAM))
    scores = np.array([np.mean([rollout(c, s) for s in EVAL_SEEDS])
                       for c in cands])
    elite = cands[np.argsort(scores)[-ELITE:]]
    mean = 0.7 * elite.mean(axis=0) + 0.3 * mean
    std = 0.7 * elite.std(axis=0) + 0.3 * std + 0.02
    history.append([it + 1, float(scores.max()), float(scores.mean())])
    print(f"iter {it + 1:2d}/{ITERS}  best={scores.max():.2f} "
          f"mean={scores.mean():.2f}", flush=True)

indep = float(np.mean([rollout(mean, s) for s in (3300, 3301, 3302)]))
print(f"final mean policy 獨立3-seed score = {indep:.2f}")

W1, b1, W2, b2 = unpack(mean)
os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
out = os.path.join(HERE, "models", "mlpC.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"layers": [[W1.tolist(), b1.tolist()],
                          [W2.tolist(), b2.tolist()]],
               "obs_keys": list(KEYS),
               "train": {"algo": "CEM-MLP v3（演化，無 bootstrap）",
                         "hidden": HID, "iters": ITERS, "pop": POP,
                         "eval_seeds": list(EVAL_SEEDS),
                         "indep_score_1day": round(indep, 2),
                         "data": "★模擬環境（域隨機化）訓練，非實測★"}},
              f, ensure_ascii=False)
with open(os.path.join(HERE, "models", "cemC_history.json"), "w",
          encoding="utf-8") as f:
    json.dump({"iters": history,
               "note": "v3：CEM-MLP 固定配置集，跨代分數可比（越低越好）"},
              f, ensure_ascii=False)
print("saved", out)
