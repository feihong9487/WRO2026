# -*- coding: utf-8 -*-
"""
線香煙羽擴散模型（承研究日誌第 17／20 週的分析，程式化）。

三段物理，全部可溯源到日誌：
1. 上升速度  w(z,N) = W_PLUME_1 · N^(1/3) · (z/0.2)^(-1/3)
   （第 17 週 Zukoski/Heskestad；錨點 N=1,z=0.2m → 0.40 m/s，
     N=9 → 0.83、N=20 → 1.08，驗證環境.py 直接對表）
2. 半徑擴張  b(z) = DS/2 + DB_DZ · z
   （第 20 週擴張錐核算；DB_DZ=0.14 為 ⚠ 假設，§5.2 優先實驗第 2 項）
3. 橫流偏移  δ = u_cross_eff · t_rise，u_cross_eff = u_cross / SKIRT_ATTEN
   （B8：側裙衰減 3–10× 是全案最脆弱假設——所以放進域隨機化，
     訓練出的策略不得依賴側裙一定有效）

捕集率由此推導（取代純假設曲線）：
    η(duty, N, u_cross) = ETA_GEO × F_geo × F_vel
    F_geo：罩口圓（半徑 R_h）與偏移 δ 的煙羽圓（半徑 b）之面積重疊比
    F_vel：1 − exp(−ETA_A · u_face/w)——罩面風速與煙羽動量的競爭
橫流大→δ 大→F_geo 崩→η 崩：這正是 F29「裕度對橫流脆弱」的再現。

★仍是工程近似，不是 CFD（CFD 屬 L1，離線做幾何比選）。
  所有係數依附錄 C 為假設值，實測後回填。★
"""
import math


def w_plume(cfg, z, n):
    """煙羽中心線上升速度 m/s。z 下限取 2 cm 避免奇異點。"""
    if n <= 0:
        return 0.0
    z = max(z, 0.02)
    return cfg.W_PLUME_1 * n ** (1.0 / 3.0) * (z / 0.2) ** (-1.0 / 3.0)


def b_plume(cfg, z):
    """煙羽半徑 m（線性擴張錐）。"""
    return cfg.DS_M / 2.0 + cfg.DB_DZ * max(0.0, z)


def rise_time(cfg, z, n):
    """由爐面升到高度 z 的時間：∫dz/w = (3/4)·z^(4/3)/k，k=w1·N^(1/3)·0.2^(1/3)"""
    if n <= 0:
        return float("inf")
    k = cfg.W_PLUME_1 * n ** (1.0 / 3.0) * 0.2 ** (1.0 / 3.0)
    return 0.75 * z ** (4.0 / 3.0) / k


def _circle_overlap(r1, r2, d):
    """半徑 r1、r2、圓心距 d 之兩圓重疊面積（標準透鏡公式）。"""
    if d >= r1 + r2:
        return 0.0
    if d <= abs(r1 - r2):
        r = min(r1, r2)
        return math.pi * r * r
    a1 = r1 * r1 * math.acos((d * d + r1 * r1 - r2 * r2) / (2 * d * r1))
    a2 = r2 * r2 * math.acos((d * d + r2 * r2 - r1 * r1) / (2 * d * r2))
    a3 = 0.5 * math.sqrt(max(0.0, (-d + r1 + r2) * (d + r1 - r2)
                             * (d - r1 + r2) * (d + r1 + r2)))
    return a1 + a2 - a3


def capture(cfg, duty, n, u_cross):
    """
    回傳 (η, 診斷 dict)。
    η = ETA_GEO × F_geo（幾何重疊）× F_vel（速度競爭）
    """
    if n <= 0 or duty <= 0:
        return 0.0, {"f_geo": 0.0, "f_vel": 0.0, "delta_m": 0.0,
                     "b_m": b_plume(cfg, cfg.Z_HOOD_M), "w": 0.0}
    z = cfg.Z_HOOD_M
    w = w_plume(cfg, z, n)
    b = b_plume(cfg, z)
    r_h = cfg.HOOD_DIA_M / 2.0

    u_eff = u_cross / max(1.0, cfg.SKIRT_ATTEN)          # 側裙衰減（B8 假設）
    delta = u_eff * rise_time(cfg, z, n)                 # 橫流偏移

    f_geo = _circle_overlap(b, r_h, delta) / (math.pi * b * b)

    q = cfg.Q_MAX_M3H / 3600.0 * (min(255, max(0, duty)) / 255.0)
    u_face = q / (math.pi * r_h * r_h)
    r = u_face / w
    f_vel = 1.0 - math.exp(-cfg.ETA_A * r)

    eta = cfg.ETA_GEO * f_geo * f_vel
    return eta, {"f_geo": f_geo, "f_vel": f_vel, "delta_m": delta,
                 "b_m": b, "w": w, "u_face": u_face, "r": r}


def h_visible(cfg, duty, n):
    """可見煙柱高度：正常情況＝罩口高度（煙升到罩口被收走，柱高 Z_HOOD
    ≥ h_spec 0.18，即 D33 的幾何保證）；只有過度抽吸（u_face ≫ 煙羽速度）
    會把煙提早拉走、柱身變矮，違反文化約束。★假設關係★"""
    if n <= 0:
        return 0.0
    z = cfg.Z_HOOD_M
    w = w_plume(cfg, z, n)
    q = cfg.Q_MAX_M3H / 3600.0 * (min(255, max(0, duty)) / 255.0)
    u_face = q / (math.pi * (cfg.HOOD_DIA_M / 2.0) ** 2)
    over = max(0.0, u_face / w - 1.0)
    return z / (1.0 + over)
