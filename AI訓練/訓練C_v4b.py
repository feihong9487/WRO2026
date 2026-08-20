# -*- coding: utf-8 -*-
"""
方案 C 訓練 v4b：修正 v4 塌縮的重訓。

v4 驗屍（cemC_v4_history.json＋動作分布診斷）：
  - 兩架構選拔分數一模一樣、動作分布 {70:100%} ＝ 塌縮成定速
  - 成因：固定 4 個評估配置（可被記憶）＋常數解附近的扁平高原
    → 精英選擇被雜訊主導 → σ 收斂在高原上
v4b 三個修正：
  1. ★熱啟動★：從 v3 的可用策略（70/220 切換行為）出發，σ=0.3 細調
     ——「給更多算力」的正確姿勢是續煉可用解，不是從零重滾
  2. ★每代輪換評估 seed★（代內共用、跨代輪換）：防對固定配置過擬合，
     常數解無法在輪換下維持假優勢
  3. σ 下限 0.05（乘性），防高原塌縮
  訓練側選拔（8 個獨立 seed、3 天）與 v3 同場對決，勝者才進 mlpC.json；
  凍結評比 1001–1010 仍是最終裁判。

★模擬環境訓練，非實測★    python 訓練C_v4b.py
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
DIM, NA, HID = len(KEYS), len(ACTIONS), 16
POP, ITERS, N_ELITE = 48, 30, 12
SEEDS_PER_ITER, DAYS = 4, 3
SEED_POOL = list(range(3200, 3280))
SELECT_SEEDS = tuple(range(3300, 3308))
SCALE_VEC = np.array([_SCALES.get(k, 1.0) for k in KEYS])


def unpack(theta):
    i = 0
    W1 = theta[i:i + HID * DIM].reshape(HID, DIM); i += HID * DIM
    b1 = theta[i:i + HID]; i += HID
    W2 = theta[i:i + NA * HID].reshape(NA, HID); i += NA * HID
    b2 = theta[i:i + NA]
    return W1, b1, W2, b2


def rollout(args):
    theta, seed = args
    W1, b1, W2, b2 = unpack(np.asarray(theta))
    env = IncenseEnv(randomize=True, episode_days=DAYS)
    obs = env.reset(seed=seed)
    tot, done = 0.0, False
    while not done:
        x = np.array([float(obs[k]) for k in KEYS]) * SCALE_VEC
        q = W2 @ np.tanh(W1 @ x + b1) + b2
        obs, r, done, _ = env.step(ACTIONS[int(np.argmax(q))])
        tot += r
    return tot


def pack_v3():
    d = json.load(open(os.path.join(HERE, "models", "mlpC_v3.json"),
                       encoding="utf-8"))
    (W1, b1), (W2, b2) = d["layers"]
    return np.concatenate([np.array(W1).ravel(), np.array(b1),
                           np.array(W2).ravel(), np.array(b2)])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    nw = max(2, (os.cpu_count() or 4) - 2)
    mean = pack_v3()
    std = np.ones(len(mean)) * 0.3
    rng = np.random.default_rng(4242)
    print(f"v4b：熱啟動自 v3、POP={POP}×ITERS={ITERS}、每代輪換 "
          f"{SEEDS_PER_ITER} seeds、{nw} 進程", flush=True)
    with ProcessPoolExecutor(max_workers=nw) as pool:
        for it in range(ITERS):
            seeds = rng.choice(SEED_POOL, SEEDS_PER_ITER, replace=False)
            eps = rng.standard_normal((POP // 2 - 1, len(mean))) * std
            cands = np.concatenate([[mean], mean + eps, mean - eps])  # 含現任
            jobs = [(c.tolist(), int(s)) for c in cands for s in seeds]
            rews = np.array(list(pool.map(rollout, jobs, chunksize=4)))
            scores = rews.reshape(len(cands), len(seeds)).mean(axis=1)
            elite = cands[np.argsort(scores)[-N_ELITE:]]
            mean = 0.7 * elite.mean(axis=0) + 0.3 * mean
            std = np.maximum(0.7 * elite.std(axis=0) + 0.3 * std, 0.05)
            print(f"  iter {it + 1:2d}/{ITERS} best={scores.max():10.2f} "
                  f"現任={scores[0]:10.2f} mean={scores.mean():10.2f}", flush=True)

        # 訓練側選拔：v4b vs v3 同場（8 seeds × 3 天）
        v3 = pack_v3()
        j4 = [(mean.tolist(), s) for s in SELECT_SEEDS]
        j3 = [(v3.tolist(), s) for s in SELECT_SEEDS]
        s4 = np.array(list(pool.map(rollout, j4)))
        s3 = np.array(list(pool.map(rollout, j3)))
    wins = int((s4 > s3).sum())
    print(f"選拔：v4b 平均 {s4.mean():.1f} vs v3 {s3.mean():.1f}"
          f"（v4b 勝 {wins}/{len(SELECT_SEEDS)} seeds）  耗時 {time.time()-t0:.0f}s",
          flush=True)

    W1, b1, W2, b2 = unpack(mean)
    payload = {"layers": [[W1.tolist(), b1.tolist()], [W2.tolist(), b2.tolist()]],
               "obs_keys": list(KEYS),
               "train": {"algo": "CEM-MLP v4b（v3 熱啟動、每代輪換 seed、σ下限）",
                         "hidden": HID, "iters": ITERS, "pop": POP, "days": DAYS,
                         "select_vs_v3": {"v4b": round(float(s4.mean()), 1),
                                          "v3": round(float(s3.mean()), 1),
                                          "wins": f"{wins}/{len(SELECT_SEEDS)}"},
                         "data": "★模擬環境（域隨機化）訓練，非實測★"}}
    with open(os.path.join(HERE, "models", "mlpC_v4b.json"), "w",
              encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    if wins >= 6 and s4.mean() > s3.mean():
        shutil.copy(os.path.join(HERE, "models", "mlpC_v4b.json"),
                    os.path.join(HERE, "models", "mlpC.json"))
        print("v4b 判優 → 已寫入 mlpC.json（跑 評比.py 做最終裁決）", flush=True)
    else:
        print("v4b 未勝 v3 → mlpC.json 維持 v3（誠實條款）", flush=True)


if __name__ == "__main__":
    main()
