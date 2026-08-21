# -*- coding: utf-8 -*-
"""一頁 16:9：AI 如何自我學習 + 運作流程圖(SVG,純stdlib)。"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 960, 540
C_INK, C_SUB, C_NOTE = "#1a1a1a", "#52514e", "#8a8377"
C_RED, C_BLUE, C_GOLD, C_INCENSE, C_GREEN = "#9E3B2F", "#2a78d6", "#C9A227", "#7a3b2e", "#1baf7a"
C_PAPER, C_CARD, C_LINE = "#faf8f3", "#ffffff", "#e6e2d8"
FONT = "'Noto Sans TC','Source Han Sans TC','Microsoft JhengHei',sans-serif"

def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def T(x, y, s, sz=20, fill=C_INK, w="400", anc="start", ls="0"):
    return (f'<text x="{x}" y="{y}" font-size="{sz}" fill="{fill}" font-weight="{w}" '
            f'text-anchor="{anc}" letter-spacing="{ls}">{esc(s)}</text>')
def box(x, y, w, h, fill=C_CARD, stroke=C_LINE, sw=1.5, r=10):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'

o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">']
o.append(f'<rect width="{W}" height="{H}" fill="{C_PAPER}"/>')
# 箭頭定義
o.append(f'<defs><marker id="a" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto">'
         f'<path d="M0,0 L7,3 L0,6 Z" fill="{C_SUB}"/></marker>'
         f'<marker id="ag" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto">'
         f'<path d="M0,0 L7,3 L0,6 Z" fill="{C_GOLD}"/></marker></defs>')

# ── 標題帶 ──
o.append(f'<rect x="0" y="0" width="{W}" height="70" fill="{C_INCENSE}"/>')
o.append(T(40, 34, "INTELLIGENCE · AI 自我學習", 15, "#e8dcc8", "600", ls="2"))
o.append(T(40, 58, "AI 用真機資料不斷重訓自己 —— 但「證明不了更好，就不上線」", 24, "#ffffff", "800"))

# ── 運作流程圖(上半,循環) ──
fy = 92
o.append(T(40, fy + 14, "運作流程：資料飛輪", 17, C_INCENSE, "700"))
# 節點:  [真爐感測] → [MQTT 上雲] → [InfluxDB 實測庫] → [ai-online 學習]
nodes = [
    (40,  "真爐感測", "R4→Pi5·1Hz", C_INK),
    (255, "上雲", "MQTT→雲端", C_INK),
    (455, "實測資料庫", "InfluxDB", C_BLUE),
    (665, "AI 學習容器", "ai-online", C_GREEN),
]
nw, nh, ny = 165, 58, fy + 26
for i, (nx, t1, t2, col) in enumerate(nodes):
    o.append(box(nx, ny, nw, nh, stroke=col, sw=2))
    o.append(T(nx + nw/2, ny + 26, t1, 17, C_INK, "700", anc="middle"))
    o.append(T(nx + nw/2, ny + 46, t2, 13, C_NOTE, anc="middle"))
    if i < 3:
        x1 = nx + nw; x2 = nodes[i+1][0]
        o.append(f'<line x1="{x1}" y1="{ny+nh/2}" x2="{x2-4}" y2="{ny+nh/2}" stroke="{C_SUB}" stroke-width="2" marker-end="url(#a)"/>')
# 回環箭頭(學習容器 → 寫回 → 影響決策 → 回到真爐)，金色虛線繞下
o.append(f'<path d="M {665+nw/2} {ny+nh} L {665+nw/2} {ny+nh+22} L {40+nw/2} {ny+nh+22} L {40+nw/2} {ny+nh+4}" '
         f'fill="none" stroke="{C_GOLD}" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#ag)"/>')
o.append(T(W/2, ny + nh + 40, "每 6 小時用最新實測重訓 → 寫回 ai_status → 供決策層參考（影子模式：只建議、不致動）",
           13, C_GOLD, "600", anc="middle"))

# ── 下半:三張卡(如何學 + 守門 + 誠實) ──
cy, cw, ch = 300, 280, 178
gap = 20
cards = [
    (C_BLUE, "① 兩個 AI 各司其職",
     ["AI-1 負載預測：學「這個時刻", "平常多忙」，供前饋削峰",
      "AI-2 異常偵測：學感測老化、", "濾材狀態的正常範圍"]),
    (C_GREEN, "② 資料飛輪：越跑越準",
     ["每 6 小時用累積的真機資料", "重訓一次，模型版本遞增",
      "每 5 分鐘評分一次現況", "—— 系統常駐、持續自學"]),
    (C_RED, "③ 守門條款：安全剎車",
     ["新模型沒證明贏過基線", "→ 就不換，沿用舊版",
      "防止「越學越差」上線；", "這跟調出好數字就宣稱相反"]),
]
for i, (col, title, lines) in enumerate(cards):
    cx = 40 + i * (cw + gap)
    o.append(box(cx, cy, cw, ch))
    o.append(f'<rect x="{cx}" y="{cy}" width="6" height="{ch}" rx="3" fill="{col}"/>')
    o.append(T(cx + 22, cy + 34, title, 18, C_INK, "700"))
    for j, ln in enumerate(lines):
        o.append(T(cx + 22, cy + 62 + j * 26, ln, 14.5, C_SUB))
# 底部收束
o.append(T(W/2, H - 14, "★誠實邊界：目前為居家實測資料訓練，屬「預測機制」驗證，非廟宇負載成效★",
           13, C_NOTE, "600", anc="middle"))

o.append("</svg>")
open(os.path.join(HERE, "頁_AI自我學習.svg"), "w", encoding="utf-8").write("\n".join(o))
print("輸出 頁_AI自我學習.svg")
