#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
產生「資料鏈端到端實測」海報圖（向量 SVG，純標準函式庫）
==========================================================
資料來源：AI訓練/data/aroma01_co2_hourly.csv（aroma01 真機，經 InfluxDB 匯出）

★誠實邊界★ 依 CLAUDE.md §7 與《研究日誌》§7g：
  本圖資料為 **居家環境 CO₂，非廟宇負載**，且裝置非全天開機。
  本圖只能用來證明「感測—決策—雲端鏈路實際運作」，
  **不得**用來表述廟宇場域之濃度水準，也不得當成減污成效。

為什麼不用 matplotlib：本機沒有裝，且不為了畫一張圖去動環境。
SVG 手寫即可，而且輸出天生是向量，正好符合海報規劃書 §3.1
「圖表一律向量」的要求。

版面規範對齊《海報規劃書_三張A1.md》：
  §3.4 系列 1 藍 #2a78d6（主系列）／格線 #e1e0d9／次文字 #52514e／註腳 #898781
  §3.5 直接標註取代圖例、格線 0.25 pt、資料線 2 pt、無 3D 無漸層
  §3.3 圖說／軸標 20 pt ≈ 7 mm、註腳 16 pt ≈ 5.6 mm

用法：
    python 產生_資料鏈實測圖.py            # 輸出到 簡報/圖_資料鏈實測_aroma01_CO2.svg
"""
import csv
import os
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "..", "AI訓練", "data", "aroma01_co2_hourly.csv")
OUT_PATH = os.path.join(HERE, "圖_資料鏈實測_aroma01_CO2.svg")

TPE = timezone(timedelta(hours=8))
GAP_HOURS = 1.5          # 超過此間隔就斷線，不連過去——裝置沒開機的時段不可假裝連續

# ── 版面（1 mm = 4 SVG 單位；成品 165 × 95 mm，約一欄寬）─────────
MM = 4
W_MM, H_MM = 165, 95
W, H = W_MM * MM, H_MM * MM
M_L, M_R, M_T, M_B = 104, 28, 34, 80
PX0, PX1 = M_L, W - M_R
PY0, PY1 = M_T, H - M_B

C_SERIES = "#2a78d6"     # 系列 1 藍
C_GRID = "#e1e0d9"
C_TEXT = "#0b0b0b"
C_SUB = "#52514e"
C_NOTE = "#898781"
FONT = "'Noto Sans TC','Source Han Sans TC','Microsoft JhengHei',sans-serif"

Y_MIN, Y_MAX = 300, 2200
Y_TICKS = [500, 1000, 1500, 2000]


def load():
    """回傳 [(台北時間, ppm)]，略過空值列。"""
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            t, v = r.get("_time"), r.get("_value")
            if not t or not v:
                continue
            s = t.replace("Z", "+00:00")
            if "." in s:                       # 去掉奈秒，fromisoformat 只吃到微秒
                head, rest = s.split(".", 1)
                frac, tz = rest[:6], rest[len(rest) - 6:]
                s = f"{head}.{frac}{tz}"
            rows.append((datetime.fromisoformat(s).astimezone(TPE), float(v)))
    rows.sort(key=lambda x: x[0])
    return rows


def segments(rows):
    """依 GAP_HOURS 切段——裝置沒開機的空窗不可連線。"""
    segs, cur = [], [rows[0]]
    for prev, nxt in zip(rows, rows[1:]):
        if (nxt[0] - prev[0]).total_seconds() > GAP_HOURS * 3600:
            segs.append(cur)
            cur = []
        cur.append(nxt)
    segs.append(cur)
    return [s for s in segs if s]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    rows = load()
    segs = segments(rows)
    t0, t1 = rows[0][0], rows[-1][0]
    span = (t1 - t0).total_seconds()
    vals = [v for _, v in rows]
    vmin, vmax = min(vals), max(vals)

    def sx(t):
        return PX0 + (t - t0).total_seconds() / span * (PX1 - PX0)

    def sy(v):
        return PY1 - (v - Y_MIN) / (Y_MAX - Y_MIN) * (PY1 - PY0)

    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W_MM}mm" height="{H_MM}mm" '
      f'viewBox="0 0 {W} {H}" font-family="{FONT}">')
    a(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')

    # 水平格線與 y 軸刻度
    for v in Y_TICKS:
        y = sy(v)
        a(f'<line x1="{PX0}" y1="{y:.1f}" x2="{PX1}" y2="{y:.1f}" '
          f'stroke="{C_GRID}" stroke-width="1"/>')
        a(f'<text x="{PX0 - 8}" y="{y + 8:.1f}" font-size="24" fill="{C_SUB}" '
          f'text-anchor="end">{v:,}</text>')

    # x 軸日界線與日期標籤（台北時間）
    day = t0.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    while day < t1:
        x = sx(day)
        a(f'<line x1="{x:.1f}" y1="{PY0}" x2="{x:.1f}" y2="{PY1}" '
          f'stroke="{C_GRID}" stroke-width="1"/>')
        a(f'<text x="{x:.1f}" y="{PY1 + 30}" font-size="24" fill="{C_SUB}" '
          f'text-anchor="middle">{day.month}/{day.day}</text>')
        day += timedelta(days=1)

    # 基線
    a(f'<line x1="{PX0}" y1="{PY1}" x2="{PX1}" y2="{PY1}" stroke="{C_SUB}" stroke-width="1.5"/>')

    # 資料線（分段，空窗不連）
    for seg in segs:
        pts = " ".join(f"{sx(t):.1f},{sy(v):.1f}" for t, v in seg)
        a(f'<polyline points="{pts}" fill="none" stroke="{C_SERIES}" '
          f'stroke-width="8" stroke-linejoin="round" stroke-linecap="round"/>')

    # 直接標註（取代圖例，§3.5 規則 3）——放在左上空白處，避開資料線與軸
    a(f'<text x="{PX0 + 14}" y="{sy(2090):.1f}" font-size="26" '
      f'font-weight="600" fill="{C_SERIES}">aroma01 實測 CO₂</text>')

    # 極值標註——證明感測器有反應，不是卡住的定值
    tmax, vmax_ = max(rows, key=lambda r: r[1])
    tmin, vmin_ = min(rows, key=lambda r: r[1])
    # 峰值：標在點上方；靠近右緣時改為靠右對齊，避免溢出畫布
    anchor = "end" if sx(tmax) > PX1 - 70 else "middle"
    ax = PX1 if anchor == "end" else sx(tmax)
    a(f'<circle cx="{sx(tmax):.1f}" cy="{sy(vmax_):.1f}" r="5" fill="{C_SERIES}"/>')
    a(f'<text x="{ax:.1f}" y="{sy(vmax_) - 14:.1f}" font-size="24" '
      f'fill="{C_TEXT}" text-anchor="{anchor}">{vmax_:,.0f}</text>')
    # 谷值：標在點右下，避免壓到資料線
    a(f'<circle cx="{sx(tmin):.1f}" cy="{sy(vmin_):.1f}" r="5" fill="{C_SERIES}"/>')
    a(f'<text x="{sx(tmin) + 14:.1f}" y="{sy(vmin_) + 26:.1f}" font-size="24" '
      f'fill="{C_TEXT}" text-anchor="start">{vmin_:,.0f}</text>')

    # y 軸標題（x 軸不另設標題——日期刻度已表明是時間軸，時區寫進註腳，省一行避免碰撞）
    yc = (PY0 + PY1) / 2
    a(f'<text x="{PX0 - 74}" y="{yc:.1f}" font-size="26" fill="{C_SUB}" '
      f'text-anchor="middle" transform="rotate(-90 {PX0 - 74} {yc:.1f})">CO₂（ppm）</text>')

    # 誠實標示與來源（§3.5 規則 6：右下角標資料來源）——兩行，避免互相壓到
    a(f'<text x="{PX0}" y="{H - 32}" font-size="18" fill="{C_NOTE}">'
      f'{esc(f"台北時間｜n = {len(rows)} 小時樣本｜{len(segs)} 個開機區間（空窗＝未開機）")}</text>')
    a(f'<text x="{PX0}" y="{H - 8}" font-size="20" font-weight="600" fill="{C_TEXT}">'
      f'★居家環境 CO₂，非廟宇負載★</text>')
    a(f'<text x="{PX1}" y="{H - 8}" font-size="18" fill="{C_NOTE}" '
      f'text-anchor="end">產生_資料鏈實測圖.py</text>')
    a("</svg>")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(o))

    print(f"輸出 {OUT_PATH}")
    print(f"  樣本 {len(rows)} 筆｜開機區間 {len(segs)} 段｜"
          f"{t0:%Y-%m-%d %H:%M} – {t1:%Y-%m-%d %H:%M}（台北）")
    print(f"  CO₂ {vmin:,.0f} – {vmax:,.0f} ppm（平均 {sum(vals) / len(vals):,.0f}）")
    for i, s in enumerate(segs, 1):
        print(f"    區間 {i}: {s[0][0]:%m-%d %H:%M} – {s[-1][0]:%m-%d %H:%M}（{len(s)} 筆）")


if __name__ == "__main__":
    main()
