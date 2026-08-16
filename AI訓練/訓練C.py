# -*- coding: utf-8 -*-
"""
方案 C 訓練 v2：n-step Double DQN（numpy 手寫，13→64→64→4 tanh MLP）。

v2 修正（針對 v1 評比暴露的弱點：日均 8.5 h 電量耗盡、僅平手區）：
1. **n-step return（n=32ステ≈160 s）**——把「現在花電、傍晚沒電」的代價
   壓縮進更少的 bootstrap 跳數，信用視野自約 2 h 拉長到半日尺度
2. **Double DQN**——online 選動作、target 估值，抑制 Q 高估
   （高估正是「敢花電」偏誤的放大器）
3. 訓練步數 250k→350k、ε 衰減放緩

訓練用 numpy；★部署權重輸出 JSON，Pi 上純 Python 前向★。
輸了仍照第 19 週承諾如實報告。

    python 訓練C.py
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
DIM, NA, H = len(KEYS), len(ACTIONS), 64
GAMMA, LR, BATCH, NSTEP = 0.9995, 1e-3, 64, 32
BUF, TOTAL, TARGET_SYNC, TRAIN_EVERY = 100_000, 350_000, 2_000, 4
EPS0, EPS1, EPS_DECAY_STEPS = 1.0, 0.05, 150_000

SCALE_VEC = np.array([_SCALES.get(k, 1.0) for k in KEYS])


def obs_np(env, obs):
    return np.array([float(obs[k]) for k in KEYS]) * SCALE_VEC


class Net:
    def __init__(self, rng):
        s1, s2 = (2.0 / (DIM + H)) ** 0.5, (2.0 / (H + H)) ** 0.5
        self.W1 = rng.normal(0, s1, (H, DIM)); self.b1 = np.zeros(H)
        self.W2 = rng.normal(0, s2, (H, H));   self.b2 = np.zeros(H)
        self.W3 = rng.normal(0, s2, (NA, H));  self.b3 = np.zeros(NA)

    def params(self):
        return [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3]

    def copy_from(self, o):
        for a, b in zip(self.params(), o.params()):
            a[...] = b

    def forward(self, X):
        h1 = np.tanh(X @ self.W1.T + self.b1)
        h2 = np.tanh(h1 @ self.W2.T + self.b2)
        return h1, h2, h2 @ self.W3.T + self.b3

    def grads(self, X, act_idx, td_err):
        n = len(X)
        h1, h2, _ = self.forward(X)
        dq = np.zeros((n, NA))
        dq[np.arange(n), act_idx] = td_err / n
        gW3 = dq.T @ h2; gb3 = dq.sum(0)
        dh2 = (dq @ self.W3) * (1 - h2 ** 2)
        gW2 = dh2.T @ h1; gb2 = dh2.sum(0)
        dh1 = (dh2 @ self.W2) * (1 - h1 ** 2)
        gW1 = dh1.T @ X; gb1 = dh1.sum(0)
        return [gW1, gb1, gW2, gb2, gW3, gb3]


class Adam:
    def __init__(self, params):
        self.m = [np.zeros_like(p) for p in params]
        self.v = [np.zeros_like(p) for p in params]
        self.t = 0

    def step(self, params, grads):
        self.t += 1
        b1c = 1 - 0.9 ** self.t
        b2c = 1 - 0.999 ** self.t
        for p, g, m, v in zip(params, grads, self.m, self.v):
            m[...] = 0.9 * m + 0.1 * g
            v[...] = 0.999 * v + 0.001 * g * g
            p -= LR * (m / b1c) / (np.sqrt(v / b2c) + 1e-8)


rng = np.random.default_rng(2026)
net, target = Net(rng), Net(rng)
target.copy_from(net)
opt = Adam(net.params())

# n-step replay：另存有效步數 K（回合尾端不足 n 步者 K<NSTEP）
S = np.zeros((BUF, DIM)); A = np.zeros(BUF, np.int64)
R = np.zeros(BUF); S2 = np.zeros((BUF, DIM))
D = np.zeros(BUF); K = np.zeros(BUF)
ptr, filled = 0, 0


def push(s, a, ret, s2, done, k):
    global ptr, filled
    S[ptr], A[ptr], R[ptr], S2[ptr], D[ptr], K[ptr] = s, a, ret, s2, done, k
    ptr = (ptr + 1) % BUF
    filled = min(filled + 1, BUF)


env = IncenseEnv(randomize=True, episode_days=1)
episode = 0
obs = env.reset(seed=20_000)
x = obs_np(env, obs)
window = []                        # [(s, a, r), ...] 長度 ≤ NSTEP
ep_ret, ep_rets = 0.0, []
td_hist = []
_td_acc, _td_n = 0.0, 0

for step in range(TOTAL):
    eps = max(EPS1, EPS0 - (EPS0 - EPS1) * step / EPS_DECAY_STEPS)
    if rng.random() < eps:
        a = int(rng.integers(NA))
    else:
        a = int(np.argmax(net.forward(x[None])[2][0]))
    obs, r, done, _ = env.step(ACTIONS[a])
    x2 = obs_np(env, obs)
    window.append((x, a, r))
    if len(window) == NSTEP:
        ret = sum(rw * GAMMA ** i for i, (_, _, rw) in enumerate(window))
        push(window[0][0], window[0][1], ret, x2, float(done), NSTEP)
        window.pop(0)
    ep_ret += r
    x = x2
    if done:
        # 回合結束：清空視窗（不足 n 步者以 done=1 存入，無 bootstrap）
        while window:
            ret = sum(rw * GAMMA ** i for i, (_, _, rw) in enumerate(window))
            push(window[0][0], window[0][1], ret, x2, 1.0, len(window))
            window.pop(0)
        ep_rets.append(ep_ret)
        episode += 1
        obs = env.reset(seed=20_000 + episode)
        x = obs_np(env, obs)
        ep_ret = 0.0
    if step % TRAIN_EVERY == 0 and filled >= 5_000:
        idx = rng.integers(filled, size=BATCH)
        # Double DQN：online 選動作、target 估值
        q_online_next = net.forward(S2[idx])[2]
        a_star = np.argmax(q_online_next, axis=1)
        q_next = target.forward(S2[idx])[2][np.arange(BATCH), a_star]
        y = R[idx] + (1 - D[idx]) * (GAMMA ** K[idx]) * q_next
        q = net.forward(S[idx])[2][np.arange(BATCH), A[idx]]
        td = q - y
        _td_acc += float(np.mean(np.abs(td)))
        _td_n += 1
        if _td_n >= 250:
            td_hist.append([step, _td_acc / _td_n])
            _td_acc, _td_n = 0.0, 0
        opt.step(net.params(), net.grads(S[idx], A[idx], td))
    if step % TARGET_SYNC == 0:
        target.copy_from(net)
    if step % 25_000 == 0 and ep_rets:
        print(f"step {step:>7,}  eps={eps:.2f}  "
              f"近5日均報酬={np.mean(ep_rets[-5:]):.2f}", flush=True)

os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
out = os.path.join(HERE, "models", "dqnC.json")
layers = [[net.W1.tolist(), net.b1.tolist()],
          [net.W2.tolist(), net.b2.tolist()],
          [net.W3.tolist(), net.b3.tolist()]]
with open(out, "w", encoding="utf-8") as f:
    json.dump({"layers": layers, "obs_keys": list(KEYS),
               "train": {"algo": "DoubleDQN-v2 nstep32", "steps": TOTAL,
                         "gamma": GAMMA, "nstep": NSTEP,
                         "episodes": episode,
                         "final_5day_mean_return":
                             round(float(np.mean(ep_rets[-5:])), 2),
                         "data": "★模擬環境（域隨機化）訓練，非實測★"}},
              f, ensure_ascii=False)
with open(os.path.join(HERE, "models", "dqnC_history.json"), "w",
          encoding="utf-8") as f:
    json.dump({"episode_returns": ep_rets, "td_history": td_hist,
               "note": "★模擬訓練歷程 v2（n-step Double DQN）；"
                       "各回合物理配置不同，回報跨回合震盪屬預期★"},
              f, ensure_ascii=False)
print(f"episodes={episode}  saved {out}")
