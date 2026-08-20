#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
產生兩張海報／簡報用向量圖（純標準函式庫，無外部套件）
======================================================
  1. 圖_商業模式九宮格.svg —— Business Model Canvas
  2. 圖_思維發散.svg       —— 解題路徑發散與否決紀錄

★誠實邊界★ 依 CLAUDE.md §7：
  九宮格中**未經市場驗證**的欄位一律加 ⚠ 前綴，不得表述為已成立的商業事實。
  所有數字皆引自海報既有內容（BOM < NT$4,200 為原型單機物料成本、非量產售價）。

內容來源（不自行發明）：
  《學術海報_三張A1_2.pdf》第 III 張 XIV–XVI 節、表 11、表 12
  《海報規劃書_三張A1.md》§4 P3、《研究日誌_全期完整版.md》

版面規範對齊《海報規劃書_三張A1.md》§3.3–§3.5：
  1 mm = 4 SVG 單位；內文 16 pt ≈ 5.6 mm ≈ 22 單位（規劃書的最小可讀字級）
  系列色僅用於強調，版面色為主；無 3D、無漸層、無陰影

用法：
    python 產生_商業與發散圖.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MM = 4

C_TEXT, C_SUB, C_NOTE = "#0b0b0b", "#52514e", "#898781"
C_GRID, C_PAPER = "#e1e0d9", "#ffffff"
C_INCENSE = "#7a3b2e"          # 深香色：僅用於標題與分隔線
C_OK, C_WARN, C_NO = "#0ca30c", "#fab219", "#d03b3b"
C_S1 = "#2a78d6"
FONT = "'Noto Sans TC','Source Han Sans TC','Microsoft JhengHei',sans-serif"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=22, fill=C_TEXT, weight="400", anchor="start"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{esc(s)}</text>')


def wrapped(x, y, lines, size=20, fill=C_SUB, lh=26):
    """逐行輸出——CJK 不自動斷行，行由呼叫端決定，避免估錯字寬。"""
    return [text(x, y + i * lh, ln, size=size, fill=fill) for i, ln in enumerate(lines)]


def box(x, y, w, h, stroke=C_GRID, fill=C_PAPER, sw=1.5):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="6" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def svg_open(w_mm, h_mm):
    w, h = w_mm * MM, h_mm * MM
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w_mm}mm" height="{h_mm}mm" '
            f'viewBox="0 0 {w} {h}" font-family="{FONT}">',
            f'<rect width="{w}" height="{h}" fill="{C_PAPER}"/>'], w, h


def save(parts, path):
    parts.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"輸出 {path}")


# ══════════════════════════════════════════════════════════════
# 1. 商業模式九宮格
# ══════════════════════════════════════════════════════════════
CANVAS = {
    "關鍵夥伴": ["廟方管委會（共同認定", "　h_min，非團隊自訂）", "感測器與風機供應商",
                 "⚠ 地方政府：設備補助", "　核銷通路（未驗證）"],
    "關鍵活動": ["罩體幾何設計與流體驗證", "特性曲線實測", "　η(u)／h(u)／SPL(u)", "雲端資料鏈維運",
                 "濾材配送與更換"],
    "關鍵資源": ["215 mm 罩口＋三面側裙", "雙控制器架構（Pi 5＋R4）", "歸一化 KPI 與雲端稽核鏈",
                 "四層驗證體系（L1–L4）"],
    "價值主張": ["**不改變焚香行為**的減污", "——爐口點源捕集", "",
                 "**可被證明的乾淨**：歸一化", "KPI 產出可歸因的減量數據", "",
                 "以 1/11.5 的風量達成", "3.22× 減量（設計值）"],
    "顧客關係": ["廟方可公開展示的", "即時空品看板（即文宣）", "濾材更換週期與農曆",
                 "維運節奏天然耦合"],
    "通路": ["公部門補助核銷", "——2017 宮廟聯盟主動", "　要求政府輔導添購設備",
             "⚠ 廟宇社群口碑（未驗證）"],
    "目標客群": ["B2B 單一決策者＝", "廟方管理委員會", "", "中小型宮廟——被現行",
                 "最佳方案（500 萬元）", "排除在外的絕大多數"],
    "成本結構": ["原型 BOM < NT$4,200（單機物料成本，非量產售價）",
                 "濾材耗材｜佈建與維運｜⚠ 量產成本結構未驗證"],
    "收益流": ["設備銷售（一次性）｜濾材耗材訂閱（經常性）",
               "空品數據服務：ESG 揭露／碳盤查／補助核銷（經常性）"],
}


def draw_canvas():
    W_MM, H_MM = 480, 175
    o, W, H = svg_open(W_MM, H_MM)
    pad, top = 12, 34
    cw = (W - pad * 6) / 5
    r1h, r2h = 440, 170            # 上排（含上下分割）、下排高度
    y0 = top

    o.append(text(pad, 24, "商業模式九宮格", 28, C_INCENSE, "700"))
    o.append(text(W - pad, 24, "⚠＝未經市場驗證之假設", 20, C_NOTE, anchor="end"))
    o.append(f'<line x1="{pad}" y1="{top - 8}" x2="{W - pad}" y2="{top - 8}" '
             f'stroke="{C_INCENSE}" stroke-width="2"/>')

    def cell(cx, cy, cw_, ch_, title, lines, accent=C_GRID):
        o.append(box(cx, cy, cw_, ch_, stroke=accent))
        o.append(text(cx + 12, cy + 30, title, 24, C_INCENSE, "700"))
        for i, ln in enumerate(lines):
            bold = ln.startswith("**")
            o.append(text(cx + 12, cy + 62 + i * 26,
                          ln.replace("**", ""), 20,
                          C_TEXT if bold else C_SUB, "700" if bold else "400"))

    xs = [pad + i * (cw + pad) for i in range(5)]
    # 第 1 欄：關鍵夥伴（滿高）
    cell(xs[0], y0, cw, r1h, "關鍵夥伴", CANVAS["關鍵夥伴"])
    # 第 2 欄：關鍵活動 / 關鍵資源（上下切）
    cell(xs[1], y0, cw, r1h / 2 - 6, "關鍵活動", CANVAS["關鍵活動"])
    cell(xs[1], y0 + r1h / 2 + 6, cw, r1h / 2 - 6, "關鍵資源", CANVAS["關鍵資源"])
    # 第 3 欄：價值主張（滿高，強調）
    cell(xs[2], y0, cw, r1h, "價值主張", CANVAS["價值主張"], accent=C_S1)
    # 第 4 欄：顧客關係 / 通路
    cell(xs[3], y0, cw, r1h / 2 - 6, "顧客關係", CANVAS["顧客關係"])
    cell(xs[3], y0 + r1h / 2 + 6, cw, r1h / 2 - 6, "通路", CANVAS["通路"])
    # 第 5 欄：目標客群（滿高）
    cell(xs[4], y0, cw, r1h, "目標客群", CANVAS["目標客群"])

    # 下排：成本結構（2 欄寬）／收益流（3 欄寬）
    y1 = y0 + r1h + pad
    w_cost = cw * 2 + pad
    cell(xs[0], y1, w_cost, r2h, "成本結構", CANVAS["成本結構"])
    cell(xs[2], y1, cw * 3 + pad * 2, r2h, "收益流", CANVAS["收益流"], accent=C_S1)

    o.append(text(pad, H - 10,
                  "數值引自第 III 張 XVI 節與表 12；BOM 為原型單機物料成本，非量產售價",
                  18, C_NOTE))
    o.append(text(W - pad, H - 10, "產生_商業與發散圖.py", 18, C_NOTE, anchor="end"))
    save(o, os.path.join(HERE, "圖_商業模式九宮格.svg"))


# ══════════════════════════════════════════════════════════════
# 2. 思維發散圖
# ══════════════════════════════════════════════════════════════
def draw_diverge():
    W_MM, H_MM = 480, 270
    o, W, H = svg_open(W_MM, H_MM)
    pad = 12

    o.append(text(pad, 24, "解題路徑的發散與收斂", 28, C_INCENSE, "700"))
    o.append(text(W - pad, 24, "✗＝已否決並記錄理由　△＝保留為對照實驗　✓＝採用",
                  20, C_NOTE, anchor="end"))
    o.append(f'<line x1="{pad}" y1="26" x2="{W - pad}" y2="26" '
             f'stroke="{C_INCENSE}" stroke-width="2"/>')

    # 根節點
    rx, ry, rw, rh = pad, 445, 290, 160
    o.append(box(rx, ry, rw, rh, stroke=C_INCENSE, sw=3))
    o.extend(wrapped(rx + 14, ry + 34,
                     ["焚香污染", "不能禁、不能改變", "焚香行為"], size=24, fill=C_TEXT, lh=30))
    o.append(text(rx + 14, ry + 122, "＝設計前提，非妥協", 18, C_NOTE))

    # 四條一級路徑
    L1X, L1W, L1H = 370, 400, 180
    lanes = [
        (90,  "需求端", ["禁香／減香"], C_NO, "✗",
         ["社會總成本最高", "龍山寺客流一度 −30%，4 年才回升"]),
        (320, "配方端", ["低木質素／低精油"], C_WARN, "△",
         ["文獻示警：PM 降但 PAH 可能升", "保留為 2×2 因子對照實驗"]),
        (550, "空間端", ["全室稀釋／清淨機"], C_NO, "✗",
         ["治理層級錯配：為常溫低濃度設計", "稀釋所需換氣量破壞熱舒適"]),
        (780, "源頭端", ["爐口點源捕集"], C_OK, "✓",
         ["處理源強而非整室體積", "風量需求低一至兩個數量級"]),
    ]
    for y, name, sub, color, mark, why in lanes:
        o.append(box(L1X, y, L1W, L1H, stroke=color, sw=2.5))
        o.append(text(L1X + 14, y + 32, f"{mark} {name}", 24, color, "700"))
        o.append(text(L1X + 14, y + 62, sub[0], 22, C_TEXT))
        for i, w in enumerate(why):
            o.append(text(L1X + 14, y + 88 + i * 24, w, 18, C_SUB))
        # 連線：根 → 一級
        my = ry + rh / 2
        o.append(f'<path d="M {rx + rw} {my} C {rx + rw + 30} {my}, '
                 f'{L1X - 30} {y + L1H / 2}, {L1X} {y + L1H / 2}" '
                 f'fill="none" stroke="{C_GRID}" stroke-width="2.5"/>')

    # 二級：源頭端底下的四個設計決策（皆含被否決的前身）
    L2X, L2W, L2H = 830, 1078, 160
    subs = [
        (40,  "罩體幾何", "175 mm", "215 mm ＋三面側裙",
         "三項獨立判準同時否證原設計——本案最強的自我否證"),
        (230, "控制策略", "固定權重", "對偶上升（硬約束）",
         "固定權重下四種負載全數違反噪音／煙柱約束"),
        (420, "系統架構", "單板全包", "雙控制器分層",
         "單點故障；OS 排程抖動影響取樣與致動時序"),
        (610, "風扇位置", "推吹式", "抽拉式（濾後）",
         "扇葉先吃滿灰油，葉形與動平衡改變、風量衰減"),
        (800, "控制演算法", "規則式基線", "A／B／C 三案模擬對照",
         "B 案（預測＋DP）最佳；★模擬，實機未驗證★"),
    ]
    src_y = lanes[3][0] + L1H / 2
    for y, name, before, after, why in subs:
        o.append(box(L2X, y, L2W, L2H, stroke=C_GRID, sw=2))
        o.append(text(L2X + 14, y + 30, name, 22, C_INCENSE, "700"))
        o.append(text(L2X + 14, y + 60, before, 20, C_NO))
        o.append(text(L2X + 14 + 108, y + 60, "→", 20, C_NOTE))
        o.append(text(L2X + 14 + 140, y + 60, after, 20, C_OK, "700"))
        o.append(text(L2X + 14, y + 88, why, 17, C_SUB))
        o.append(f'<path d="M {L1X + L1W} {src_y} C {L1X + L1W + 30} {src_y}, '
                 f'{L2X - 30} {y + L2H / 2}, {L2X} {y + L2H / 2}" '
                 f'fill="none" stroke="{C_GRID}" stroke-width="2.5"/>')

    o.append(text(pad, H - 34,
                  "每一條被否決的路徑都保留了否決依據——工程貢獻不只在於所選的方案，",
                  20, C_TEXT, "600"))
    o.append(text(pad, H - 10, "也在於可被檢驗的否決理由（第 XII 節）。", 20, C_TEXT, "600"))
    o.append(text(W - pad, H - 10, "產生_商業與發散圖.py", 18, C_NOTE, anchor="end"))
    save(o, os.path.join(HERE, "圖_思維發散.svg"))


if __name__ == "__main__":
    draw_canvas()
    draw_diverge()
