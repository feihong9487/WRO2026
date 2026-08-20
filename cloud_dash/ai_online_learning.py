#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧香爐 — 兩個 AI 的線上自我學習服務（未來計畫第五章落地）
================================================================
AI-1 負載預測（B 案 ridge，12 維日曆特徵，與 PI5/pi_fsm.py 的
     ShadowAdvisor 完全同構——重訓產物可直接當 ai_predictor.json 部署）
AI-2 異常偵測（drift 偵測：感測器老化、跨感測偏差、資料中斷、
     風扇指令/實際不匹配——濾材「按狀態換」的技術基礎）

兩者皆以 aroma01 真爐上線後的實測資料訓練，並以滾動視窗持續重訓
（資料飛輪）。狀態每輪寫入 InfluxDB measurement=ai_status，
由 Grafana 儀表板 grafana_dashboard_ai.json 呈現。

★誠實邊界★
- aroma01 目前放在居家環境：AI-1 學到的是「此爐所在環境的人員作息」，
  不是廟宇香客負載；報告用語限「預測機制之真實資料遷移」。
- 「香支負載」由 CO₂ 高程以穩態換算 N≈高程/26 推得（模擬推導近似，
  見 AI訓練/policies.py PredictSchedule v3 nowcast）——是代理量非實測香支。
- InfluxDB 中 aroma01 於 2026-08-08 01:15（台北）之前為模擬資料，
  本服務抓取起點固定晚於此界線。
- AI-1 僅產生影子模型；★是否換上 Pi 致動，由人拍板★（模型檔部署
  仍走人工 scp，本服務絕不碰 Pi 與 R4）。

零相依：純 Python 標準函式庫（部署端 WSL / Pi 免裝套件）。

用法：
  python3 ai_online_learning.py                 # 單次：抓資料→重訓→評分→報告
  python3 ai_online_learning.py --serve         # 常駐：持續評分＋定期重訓
  python3 ai_online_learning.py --no-write      # 乾跑（不寫 InfluxDB）
  python3 ai_online_learning.py --source grafana  # 強制走公開儀表板 API

資料來源自動偵測：
  1) InfluxDB 直連（雲端主機本地）：INFLUX_URL（預設 http://localhost:8086）
     ＋固定本地 token（非機密，與 cloud-telegraf.conf 同值）
  2) Grafana 公開儀表板查詢 API（唯讀、免帳密，任何機器可跑）
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")

# ── 設定 ─────────────────────────────────────────────────────
DEVICE = os.environ.get("AI_DEVICE", "aroma01")
INFLUX_URL = os.environ.get("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "incense-local-token")  # 本地固定 token（部署紀錄§3）
INFLUX_ORG = "incense"
INFLUX_BUCKET = "incense"
GRAFANA_BASE = os.environ.get(
    "GRAFANA_PUBLIC_BASE", "https://desktop-c8l8ri6-1.tail7920c6.ts.net")
GRAFANA_PUBTOKEN = os.environ.get(
    "GRAFANA_PUBTOKEN", "cc9acc908b144cc98e9563b09e089e34")  # aroma01 詳細面板（公開唯讀）

TPE = timezone(timedelta(hours=8))
REAL_DATA_START = "2026-08-08T01:15:00+08:00"   # 誠實邊界：此前為模擬資料
TRAIN_WINDOW_DAYS = 60          # AI-1 重訓資料視窗
ANOM_WINDOW_DAYS = 14           # AI-2 穩健統計視窗
# 訓練聚合粒度：30 分鐘。2026-08-20《加速實驗》A/B：同測試段下 30 分鐘
# 粒度訓練比小時粒度 MAE 低 7.7%（樣本×2、模型不變）。
AGG_EVERY = "30m"
AGG_STEP_MIN = 30
MIN_TRAIN_ROWS = 144            # ＝72 小時；低於此不換模型（防過擬合上線）
PPM_PER_STICK = 26.0            # ★模擬推導之穩態換算（policies.py v3）★
SCORE_EVERY_S = 300             # --serve：每 5 分鐘評分一次
RETRAIN_EVERY_S = 6 * 3600      # --serve：每 6 小時重訓一次
Z_ALARM = 4.5                   # 異常旗標門檻（穩健 z 分數）
DROPOUT_ALARM = 0.6             # 最近一小時缺資料比例警戒
DUTY_MISMATCH_ALARM = 20.0      # 指令/實際 duty 平均差（cmd>0 時）

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.environ.get("AI_MODELS_DIR", os.path.join(HERE, "ai_models"))

HONESTY = ("aroma01 真實資料（居家環境作息，2026-08-08 01:15 後）；"
           "負載＝CO₂高程/26 之模擬換算代理量；影子模型，未致動")


# ── 與 pi_fsm.ShadowAdvisor 完全同構的特徵（改動即需雙邊同步＋重訓）──
SYN = 29.530588
LUNAR_EPOCH = 947182440.0       # 2000-01-06 18:14 UTC（朔）近似


def lunar_day(ts_utc: float) -> float:
    return ((ts_utc - LUNAR_EPOCH) / 86400.0) % SYN


def feats(hour, ld, dow, is_open):
    morning = math.exp(-((hour - 8.0) ** 2) / 8.0)
    evening = math.exp(-((hour - 17.0) ** 2) / 12.5)
    lp = 1.0 if (ld < 1.0 or 14.0 <= ld < 15.5) else 0.0
    we = 1.0 if dow >= 5 else 0.0
    return [1.0, math.sin(2 * math.pi * hour / 24.0),
            math.cos(2 * math.pi * hour / 24.0),
            morning, evening, lp, we, is_open,
            is_open * morning * lp, is_open * evening * lp,
            is_open * we, is_open * lp]


def feats_at(t: datetime):
    """t 需帶時區；hour/dow 取台北、農曆日取 UTC 時戳。"""
    tl = t.astimezone(TPE)
    hour = tl.hour + tl.minute / 60.0
    is_open = 1.0 if 6 <= tl.hour < 21 else 0.0
    return feats(hour, lunar_day(t.timestamp()), tl.weekday(), is_open)


# ── 純 stdlib 線性代數（12×12 足矣）──────────────────────────
def mat_solve(A, b):
    """高斯消去＋部分樞軸。A: n×n list、b: n list → x。"""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            raise ValueError("奇異矩陣")
        M[c], M[p] = M[p], M[c]
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            for k in range(c, n + 1):
                M[r][k] -= f * M[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (M[r][n] - sum(M[r][k] * x[k] for k in range(r + 1, n))) / M[r][r]
    return x


def ridge_fit(X, Y, lam):
    n_f = len(X[0])
    XtX = [[sum(x[i] * x[j] for x in X) for j in range(n_f)] for i in range(n_f)]
    for i in range(n_f):
        XtX[i][i] += lam
    XtY = [sum(x[i] * y for x, y in zip(X, Y)) for i in range(n_f)]
    return mat_solve(XtX, XtY)


def predict(w, x):
    return max(0.0, sum(a * b for a, b in zip(w, x)))


def median(v):
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def mad(v, med=None):
    if med is None:
        med = median(v)
    return median([abs(x - med) for x in v]) * 1.4826 or 1e-9


def lsq_slope(pairs):
    """pairs: [(x, y)] → 最小平方斜率。"""
    n = len(pairs)
    if n < 2:
        return 0.0
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    den = sum((p[0] - mx) ** 2 for p in pairs)
    return sum((p[0] - mx) * (p[1] - my) for p in pairs) / den if den else 0.0


# ── 資料來源 ─────────────────────────────────────────────────
def _http_json(url, data=None, headers=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class InfluxSource:
    """雲端主機本地直連（Flux over HTTP）。"""
    name = "influxdb"

    def ok(self):
        try:
            req = urllib.request.Request(INFLUX_URL + "/health")
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read()).get("status") == "pass"
        except Exception:
            return False

    def _flux(self, q):
        req = urllib.request.Request(
            f"{INFLUX_URL}/api/v2/query?org={INFLUX_ORG}",
            data=q.encode("utf-8"),
            headers={"Authorization": f"Token {INFLUX_TOKEN}",
                     "Content-Type": "application/vnd.flux",
                     "Accept": "application/csv"})
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8")
        out = []
        cols = None
        for line in text.splitlines():
            if not line or line.startswith("#"):
                cols = None
                continue
            parts = line.split(",")
            if cols is None:
                cols = {c: i for i, c in enumerate(parts)}
                continue
            try:
                t = datetime.fromisoformat(
                    parts[cols["_time"]].replace("Z", "+00:00"))
                v = float(parts[cols["_value"]])
                f = parts[cols["_field"]] if "_field" in cols else ""
                out.append((t, f, v))
            except (KeyError, ValueError, IndexError):
                continue
        return out

    def series(self, measurement, fields, start_iso, every="1h", fn="mean"):
        flist = " or ".join(f'r._field == "{f}"' for f in fields)
        q = (f'from(bucket: "{INFLUX_BUCKET}") |> range(start: {start_iso})'
             f' |> filter(fn: (r) => r._measurement == "{measurement}"'
             f' and ({flist}))'
             f' |> filter(fn: (r) => r.device == "{DEVICE}")'
             f' |> filter(fn: (r) => r._value > -900.0)'
             f' |> aggregateWindow(every: {every}, fn: {fn}, createEmpty: false)')
        rows = self._flux(q)
        out = {f: [] for f in fields}
        for t, f, v in rows:
            if f in out:
                out[f].append((t, v))
        for f in out:
            out[f].sort()
        return out


class GrafanaPublicSource:
    """公開儀表板查詢 API（唯讀免帳密）。面板編號對照 aroma01 詳細面板。"""
    name = "grafana-public"
    PANEL = {"co2": 7, "t_scd": 9, "t_sht": 9, "rh_scd": 9, "rh_sht": 9,
             "t_ds": 10, "fan_duty": 11, "fan_actual": 11, "ai_duty": 102}

    def ok(self):
        try:
            _http_json(GRAFANA_BASE + "/api/health", timeout=8)
            return True
        except Exception:
            return False

    def _panel(self, pid, start, stop, interval_ms, max_pts):
        body = json.dumps({
            "intervalMs": int(interval_ms), "maxDataPoints": int(max_pts),
            "timeRange": {   # API 不接受微秒 → 固定截到秒
                "from": start.isoformat(timespec="seconds"),
                "to": stop.isoformat(timespec="seconds")},
        }).encode()
        url = (f"{GRAFANA_BASE}/api/public/dashboards/{GRAFANA_PUBTOKEN}"
               f"/panels/{pid}/query")
        d = _http_json(url, data=body,
                       headers={"Content-Type": "application/json"}, timeout=60)
        out = {}
        for res in d.get("results", {}).values():
            for fr in res.get("frames", []):
                fields = fr["schema"]["fields"]
                vals = fr["data"]["values"]
                if len(fields) < 2 or not vals or not vals[0]:
                    continue
                fname = fields[1].get("name") or \
                    (fields[1].get("labels") or {}).get("_field", "")
                ser = [(datetime.fromtimestamp(ts / 1000, tz=timezone.utc), v)
                       for ts, v in zip(vals[0], vals[1]) if v is not None]
                out.setdefault(fname, []).extend(ser)
        for f in out:
            out[f].sort()
        return out

    def series(self, measurement, fields, start_iso, every="1h", fn="mean"):
        start = datetime.fromisoformat(start_iso)
        stop = datetime.now(timezone.utc)
        step_ms = {"1h": 3600000, "30m": 1800000, "1m": 60000,
                   "5m": 300000}[every]
        max_pts = int((stop - start).total_seconds() * 1000 / step_ms) + 2
        out = {f: [] for f in fields}
        for pid in {self.PANEL[f] for f in fields if f in self.PANEL}:
            got = self._panel(pid, start, stop, step_ms, max_pts)
            for f in fields:
                if f in got:
                    out[f] = got[f]
        return out


def pick_source(prefer):
    if prefer in ("influx", "auto"):
        s = InfluxSource()
        if s.ok():
            return s
        if prefer == "influx":
            raise SystemExit("InfluxDB 連不上（--source influx 指定失敗）")
    s = GrafanaPublicSource()
    if s.ok():
        return s
    raise SystemExit("兩個資料來源都連不上（InfluxDB 直連與 Grafana 公開 API）")


# ── 資料飛輪快取：小時 CO₂ 併入本地檔，歷史不因保留策略而流失 ──
def cache_merge(series, path):
    old = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = {k: v for k, v in json.load(f).items()}
    for t, v in series:
        old[t.astimezone(timezone.utc).isoformat(timespec="seconds")] = round(v, 2)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False)
    os.replace(tmp, path)
    return sorted((datetime.fromisoformat(k), v) for k, v in old.items())


# ── AI-1：負載預測重訓 ───────────────────────────────────────
def daily_elevation(hourly):
    """[(t,co2)] → [(t, 高程)]；基線＝當日（台北）最小值。日覆蓋<6h 不採。"""
    min_rows = max(1, 6 * 60 // AGG_STEP_MIN)
    bydate = {}
    for t, v in hourly:
        bydate.setdefault(t.astimezone(TPE).date(), []).append((t, v))
    out = []
    for d, rows in sorted(bydate.items()):
        if len(rows) < min_rows:
            continue
        base = min(v for _, v in rows)
        out.extend((t, v - base) for t, v in rows)
    out.sort()
    return out


WIN_CENTER = timedelta(minutes=AGG_STEP_MIN // 2)   # 窗尾時戳 → 移回窗中心


def retrain_predictor(hourly, state):
    data = [(t, max(0.0, e / PPM_PER_STICK)) for t, e in daily_elevation(hourly)]
    n = len(data)
    if n < MIN_TRAIN_ROWS:
        return None, {"skip": f"樣本不足（{n} < {MIN_TRAIN_ROWS} 列）",
                      "n_hours": round(n * AGG_STEP_MIN / 60, 1)}
    X = [feats_at(t - WIN_CENTER) for t, _ in data]
    Y = [y for _, y in data]
    n_tr = int(n * 0.7)
    Xtr, Ytr, Xte, Yte = X[:n_tr], Y[:n_tr], X[n_tr:], Y[n_tr:]

    n_v = int(n_tr * 0.8)
    best = (1e18, 1.0)
    for lam in (0.1, 1.0, 10.0, 100.0):
        try:
            w = ridge_fit(Xtr[:n_v], Ytr[:n_v], lam)
        except ValueError:
            continue
        m = sum(abs(predict(w, x) - y)
                for x, y in zip(Xtr[n_v:], Ytr[n_v:])) / max(1, n_tr - n_v)
        if m < best[0]:
            best = (m, lam)
    lam = best[1]
    w = ridge_fit(Xtr, Ytr, lam)
    mae = sum(abs(predict(w, x) - y) for x, y in zip(Xte, Yte)) / len(Yte)

    ym = sum(Ytr) / len(Ytr)
    mae_const = sum(abs(ym - y) for y in Yte) / len(Yte)
    lookup = {(t.astimezone(TPE).date(), t.astimezone(TPE).hour,
               t.astimezone(TPE).minute // 30): y for t, y in data}
    pairs = [(lookup.get((t.astimezone(TPE).date() - timedelta(days=1),
                          t.astimezone(TPE).hour,
                          t.astimezone(TPE).minute // 30)), y)
             for t, y in data[n_tr:]]
    pairs = [(p, y) for p, y in pairs if p is not None]
    mae_pers = (sum(abs(p - y) for p, y in pairs) / len(pairs)) if pairs else None

    sane = all(math.isfinite(x) and abs(x) < 1e3 for x in w)
    beats = sane and mae <= mae_const and (mae_pers is None or mae <= mae_pers * 1.1)
    meta = {"n_hours": round(n * AGG_STEP_MIN / 60, 1), "n_rows": n,
            "lambda": lam,
            "test_mae_sticks": round(mae, 3),
            "const_mae_sticks": round(mae_const, 3),
            "persistence_mae_sticks": (round(mae_pers, 3)
                                       if mae_pers is not None else None),
            "deployable": bool(beats),
            "trained_at": datetime.now(TPE).isoformat(timespec="seconds"),
            "data_span": [data[0][0].astimezone(TPE).isoformat(timespec="seconds"),
                          data[-1][0].astimezone(TPE).isoformat(timespec="seconds")],
            "honesty": HONESTY}
    if not beats:
        meta["skip"] = "未優於基線或權重異常——沿用舊模型（守門條款）"
        return None, meta
    state["ai1_version"] = state.get("ai1_version", 0) + 1
    meta["version"] = state["ai1_version"]
    return {"w": w, "feat_names": [
        "bias", "sin_h", "cos_h", "morning", "evening", "lunar_peak",
        "weekend", "is_open", "open*morning*lp", "open*evening*lp",
        "open*weekend", "open*lp"], "meta": meta}, meta


# ── AI-2：異常偵測（穩健統計，滾動重訓＝持續自我學習）─────────
def retrain_anomaly(hourly, minutely, state):
    elev = daily_elevation(hourly)
    cutoff = datetime.now(timezone.utc) - timedelta(days=ANOM_WINDOW_DAYS)
    elev = [(t, e) for t, e in elev if t >= cutoff]
    byhour = {}
    for t, e in elev:
        byhour.setdefault((t - WIN_CENTER).astimezone(TPE).hour, []).append(e)
    hour_stats = {h: {"med": round(median(v), 1), "mad": round(mad(v), 1)}
                  for h, v in byhour.items() if len(v) >= 3}

    def daily_median_bias(a, b):
        bmap = {t: v for t, v in minutely.get(b, [])}
        byd = {}
        for t, v in minutely.get(a, []):
            if t in bmap:
                byd.setdefault(t.astimezone(TPE).date(), []).append(v - bmap[t])
        return {d.isoformat(): round(median(v), 3) for d, v in sorted(byd.items())
                if len(v) >= 60}

    t_bias_daily = daily_median_bias("t_scd", "t_sht")
    rh_bias_daily = daily_median_bias("rh_scd", "rh_sht")
    co2_daily_min = {}
    for t, v in hourly:
        d = t.astimezone(TPE).date()
        if t >= cutoff:
            co2_daily_min[d] = min(co2_daily_min.get(d, 1e9), v)

    model = {
        "hour_stats": hour_stats,
        "t_bias": {"med": round(median(list(t_bias_daily.values()) or [0.0]), 3),
                   "mad": round(mad(list(t_bias_daily.values()) or [0.0]), 3)},
        "rh_bias": {"med": round(median(list(rh_bias_daily.values()) or [0.0]), 3),
                    "mad": round(mad(list(rh_bias_daily.values()) or [0.0]), 3)},
        "co2_min_slope_ppm_day": round(lsq_slope(
            [(i, v) for i, (d, v) in enumerate(sorted(co2_daily_min.items()))]), 2),
        "window_days": ANOM_WINDOW_DAYS,
        "n_hours": len(elev),
        "trained_at": datetime.now(TPE).isoformat(timespec="seconds"),
        "honesty": "無標註異常樣本之非監督統計模型；分數為漂移指標非故障判定",
    }
    state["ai2_version"] = state.get("ai2_version", 0) + 1
    model["version"] = state["ai2_version"]
    return model


def score_anomaly(model, minutely, now=None):
    now = now or datetime.now(timezone.utc)
    h1 = now - timedelta(hours=1)
    h24 = now - timedelta(hours=24)

    def recent(f, since):
        return [(t, v) for t, v in minutely.get(f, []) if t >= since]

    out = {}
    co2_1h = recent("co2", h1)
    out["dropout"] = round(1.0 - min(1.0, len(co2_1h) / 60.0), 3)

    co2_24 = recent("co2", h24)
    z_co2 = 0.0
    if co2_24 and model.get("hour_stats"):
        base = min(v for _, v in co2_24)
        if co2_1h:
            elev_now = median([v for _, v in co2_1h]) - base
            hs = model["hour_stats"].get(str(now.astimezone(TPE).hour)) or \
                model["hour_stats"].get(now.astimezone(TPE).hour)
            if hs:
                z_co2 = (elev_now - hs["med"]) / max(hs["mad"], 5.0)  # 5 ppm 下限
    out["co2_z"] = round(z_co2, 2)

    def bias_z(a, b, key):
        pa, pb = recent(a, h24), recent(b, h24)
        if len(pa) < 30 or len(pb) < 30:
            return 0.0, None
        cur = median([v for _, v in pa]) - median([v for _, v in pb])
        st = model[key]
        floor = 0.1 if key == "t_bias" else 0.5     # °C / %RH 的 MAD 下限
        return (cur - st["med"]) / max(st["mad"], floor), cur

    z_t, t_cur = bias_z("t_scd", "t_sht", "t_bias")
    z_rh, rh_cur = bias_z("rh_scd", "rh_sht", "rh_bias")
    out["t_bias"] = round(t_cur, 2) if t_cur is not None else None
    out["t_bias_z"] = round(z_t, 2)
    out["rh_bias"] = round(rh_cur, 2) if rh_cur is not None else None
    out["rh_bias_z"] = round(z_rh, 2)

    # 實際 < 指令＝風扇失效代理；實際 > 指令＝R4 安全接管（CO₂ 硬警報
    # 全速等），是預期行為 → 只回報比例、不當異常。
    duty = recent("fan_duty", h1)
    act = recent("fan_actual", h1)
    mism, override = None, None
    if duty and act:
        amap = {t.replace(second=0, microsecond=0): v for t, v in act}
        pairs = [(v, amap[t.replace(second=0, microsecond=0)])
                 for t, v in duty
                 if v is not None and t.replace(second=0, microsecond=0) in amap]
        under = [max(0.0, c - a) for c, a in pairs if c > 0]
        mism = round(sum(under) / len(under), 1) if under else 0.0
        override = round(sum(1 for c, a in pairs if a > c) / len(pairs), 3) \
            if pairs else 0.0
    out["duty_mismatch"] = mism
    out["safety_override"] = override

    out["co2_drift_ppm_day"] = model.get("co2_min_slope_ppm_day", 0.0)
    zs = [abs(z_co2), abs(z_t), abs(z_rh)]
    out["score"] = round(max(zs), 2)
    out["flag"] = int(out["score"] >= Z_ALARM
                      or out["dropout"] >= DROPOUT_ALARM
                      or (mism is not None and mism >= DUTY_MISMATCH_ALARM))
    return out


# ── 狀態寫入 InfluxDB（line protocol；僅直連模式可寫）─────────
def esc(s):
    return str(s).replace(" ", "\\ ").replace(",", "\\,")


def write_status(fields):
    clean = {k: v for k, v in fields.items()
             if v is not None and isinstance(v, (int, float))}
    if not clean:
        return False
    line = (f"ai_status,device={esc(DEVICE)},source=ai_online "
            + ",".join(f"{k}={float(v)}" for k, v in clean.items())
            + f" {int(time.time())}")
    try:
        req = urllib.request.Request(
            f"{INFLUX_URL}/api/v2/write?org={INFLUX_ORG}"
            f"&bucket={INFLUX_BUCKET}&precision=s",
            data=line.encode("utf-8"),
            headers={"Authorization": f"Token {INFLUX_TOKEN}"})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as e:
        print(f"  寫入 InfluxDB 失敗：{e}")
        return False


# ── 檔案存取 ────────────────────────────────────────────────
def save_json(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ── 主流程 ──────────────────────────────────────────────────
def cycle(src, state, do_retrain, no_write):
    now = datetime.now(timezone.utc)
    t0 = max(datetime.fromisoformat(REAL_DATA_START),
             now - timedelta(days=TRAIN_WINDOW_DAYS))
    start_iso = t0.astimezone(timezone.utc).isoformat(timespec="seconds")

    print(f"[{datetime.now(TPE):%m-%d %H:%M}] 資料來源={src.name}  抓取自 {start_iso}")
    hourly_new = src.series("sensor", ["co2"], start_iso, every=AGG_EVERY)["co2"]
    hourly = cache_merge(hourly_new, os.path.join(
        MODELS_DIR, f"co2_{AGG_EVERY}_cache.json"))
    hourly = [(t, v) for t, v in hourly if v and v > 0]
    m_start = (now - timedelta(hours=26)).isoformat(timespec="seconds")
    minutely = src.series(
        "sensor", ["co2", "t_scd", "t_sht", "rh_scd", "rh_sht", "t_ds"],
        m_start, every="1m")
    minutely.update(src.series(
        "decision", ["fan_duty", "fan_actual", "ai_duty"], m_start, every="1m"))
    print(f"  {AGG_EVERY} 粒度 CO₂ {len(hourly)} 列（快取合併後）；"
          f"近 26h 分鐘級：" + " ".join(f"{k}={len(v)}" for k, v in minutely.items()))

    status = {"svc_heartbeat": 1}

    # AI-1 重訓
    ai1_meta = state.get("ai1_meta", {})
    if do_retrain:
        model, meta = retrain_predictor(hourly, state)
        if model:
            save_json(model, os.path.join(MODELS_DIR, "ai_predictor_real.json"))
            hist = load_json(os.path.join(MODELS_DIR, "ai1_history.json"), [])
            hist.append(meta)
            save_json(hist, os.path.join(MODELS_DIR, "ai1_history.json"))
            state["ai1_meta"] = ai1_meta = meta
            print(f"  AI-1 重訓完成 v{meta['version']}：test MAE={meta['test_mae_sticks']}"
                  f"（常數 {meta['const_mae_sticks']}／前日 {meta['persistence_mae_sticks']}）"
                  f" n={meta['n_hours']}h")
        else:
            print(f"  AI-1 未換模型：{meta.get('skip')}")
            state.setdefault("ai1_meta", {}).update(
                {k: meta[k] for k in ("n_hours",) if k in meta})
        state["ai1_last_retrain"] = datetime.now(TPE).isoformat(timespec="seconds")

        # AI-2 重訓（滾動統計）
        am = retrain_anomaly(hourly, minutely, state)
        save_json(am, os.path.join(MODELS_DIR, "anomaly_model.json"))
        state["ai2_trained_at"] = am["trained_at"]
        print(f"  AI-2 重訓完成 v{am['version']}：{len(am['hour_stats'])} 個時段統計、"
              f"t偏差 {am['t_bias']['med']}±{am['t_bias']['mad']}°C、"
              f"CO₂基線漂移 {am['co2_min_slope_ppm_day']} ppm/day")

    # AI-1 即時狀態
    pm = load_json(os.path.join(MODELS_DIR, "ai_predictor_real.json"))
    if pm:
        meta = pm.get("meta", ai1_meta)
        status["ai1_version"] = meta.get("version", 0)
        status["ai1_test_mae"] = meta.get("test_mae_sticks")
        status["ai1_const_mae"] = meta.get("const_mae_sticks")
        status["ai1_persist_mae"] = meta.get("persistence_mae_sticks")
        status["ai1_n_hours"] = meta.get("n_hours")
        try:
            tr = datetime.fromisoformat(meta["trained_at"])
            status["ai1_age_h"] = round((datetime.now(TPE) - tr).total_seconds() / 3600, 1)
        except Exception:
            pass
        status["ai1_pred_now"] = round(predict(pm["w"], feats_at(now)), 2)
        co2_1h = [(t, v) for t, v in minutely.get("co2", [])
                  if t >= now - timedelta(hours=1)]
        co2_24 = [(t, v) for t, v in minutely.get("co2", [])
                  if t >= now - timedelta(hours=24)]
        if co2_1h and co2_24:
            elev = median([v for _, v in co2_1h]) - min(v for _, v in co2_24)
            status["ai1_nowcast"] = round(max(0.0, elev / PPM_PER_STICK), 2)

    # AI-2 即時評分
    am = load_json(os.path.join(MODELS_DIR, "anomaly_model.json"))
    if am:
        sc = score_anomaly(am, minutely, now)
        status["ai2_version"] = am.get("version", 0)
        status["ai2_score"] = sc["score"]
        status["ai2_flag"] = sc["flag"]
        status["ai2_co2_z"] = sc["co2_z"]
        status["ai2_t_bias"] = sc["t_bias"]
        status["ai2_t_bias_z"] = sc["t_bias_z"]
        status["ai2_rh_bias"] = sc["rh_bias"]
        status["ai2_rh_bias_z"] = sc["rh_bias_z"]
        status["ai2_dropout"] = sc["dropout"]
        status["ai2_duty_mismatch"] = sc["duty_mismatch"]
        status["ai2_safety_override"] = sc["safety_override"]
        status["ai2_co2_drift"] = sc["co2_drift_ppm_day"]
        print(f"  AI-2 評分：score={sc['score']} flag={sc['flag']} "
              f"(co2_z={sc['co2_z']} t_z={sc['t_bias_z']} rh_z={sc['rh_bias_z']} "
              f"缺料率={sc['dropout']:.0%} 失效差={sc['duty_mismatch']} "
              f"安全接管={sc['safety_override']})")

    save_json(state, os.path.join(MODELS_DIR, "state.json"))
    if not no_write and isinstance(src, InfluxSource):
        if write_status(status):
            print("  狀態已寫入 InfluxDB（measurement=ai_status）")
    elif not no_write:
        print("  ※ 非直連模式無法寫 ai_status（唯讀 API）——僅本地報告")
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--serve", action="store_true", help="常駐服務模式")
    ap.add_argument("--no-write", action="store_true", help="不寫 InfluxDB")
    ap.add_argument("--source", choices=["auto", "influx", "grafana"],
                    default="auto")
    args = ap.parse_args()

    src = pick_source({"grafana": "grafana"}.get(args.source, args.source))
    state = load_json(os.path.join(MODELS_DIR, "state.json"), {})

    if not args.serve:
        st = cycle(src, state, do_retrain=True, no_write=args.no_write)
        print("\n── 單次執行摘要 ──")
        for k in sorted(st):
            print(f"  {k} = {st[k]}")
        print(f"\n★{HONESTY}★")
        return

    last_retrain = 0.0
    while True:
        try:
            retrain = (time.time() - last_retrain) >= RETRAIN_EVERY_S
            cycle(src, state, do_retrain=retrain, no_write=args.no_write)
            if retrain:
                last_retrain = time.time()
        except Exception as e:
            print(f"[cycle 失敗，{SCORE_EVERY_S}s 後重試] {e}")
        time.sleep(SCORE_EVERY_S)


if __name__ == "__main__":
    main()
