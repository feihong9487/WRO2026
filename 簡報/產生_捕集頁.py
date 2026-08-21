# -*- coding: utf-8 -*-
"""產生一頁 16:9 投影片：捕集是「接」不是「吸」＋自我否證(SVG,純stdlib)。"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
MM = 4
W, H = 960, 540                      # 16:9 pt (Google Slides / PowerPoint 標準)
C_INK, C_SUB, C_NOTE = "#1a1a1a", "#52514e", "#8a8377"
C_RED, C_BLUE, C_GOLD, C_INCENSE = "#9E3B2F", "#2a78d6", "#C9A227", "#7a3b2e"
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

# ── 標題帶 ──
o.append(f'<rect x="0" y="0" width="{W}" height="70" fill="{C_INCENSE}"/>')
o.append(T(40, 34, "SOLUTION · 工程", 15, "#e8dcc8", "600", ls="2"))
o.append(T(40, 58, "捕集是「接」的問題，不是「吸」的問題", 27, "#ffffff", "800"))

# ── 左卡：反直覺洞察 + 誘導風速比 ──
lx, ly, lw = 40, 92, 430
o.append(box(lx, ly, lw, 210))
o.append(f'<rect x="{lx}" y="{ly}" width="6" height="210" rx="3" fill="{C_RED}"/>')
o.append(T(lx + 24, ly + 40, "煙羽不是被「吸」進去的", 21, C_INK, "700"))
o.append(T(lx + 24, ly + 70, "是靠自身浮力上升，被罩口「承接」。", 17, C_SUB))
o.append(T(lx + 24, ly + 95, "所以決定成敗的是罩體幾何，不是風量大小。", 17, C_SUB))
# 兩個比值方塊
for i, (ratio, dist) in enumerate([("1 : 8", "距罩口 100 mm"), ("1 : 22", "距罩口 200 mm")]):
    bx = lx + 24 + i * 200
    o.append(box(bx, ly + 118, 176, 72, fill=C_PAPER))
    o.append(T(bx + 88, ly + 158, ratio, 34, C_BLUE, "800", anc="middle"))
    o.append(T(bx + 88, ly + 180, dist, 14, C_NOTE, anc="middle"))
o.append(T(lx + 24, ly + 205, "誘導風速 : 煙羽上升速度（設計值）", 12, C_NOTE))

# ── 右卡：CAD retrofit ──
rx, ry, rw = 490, 92, 430
o.append(box(rx, ry, rw, 210, fill=C_CARD))
o.append(T(rx + 24, ry + 38, "不換爐，只加裝一個模組", 21, C_INK, "700"))
o.append(T(rx + 24, ry + 66, "retrofit —— 香客插香動作完全不變，", 16, C_SUB))
o.append(T(rx + 24, ry + 88, "廟方導入零儀式衝擊。", 16, C_SUB))
# 簡化的漏斗罩示意(梯形+爐)
cx = rx + rw / 2
o.append(f'<polygon points="{cx-120},{ry+120} {cx+120},{ry+120} {cx+70},{ry+165} {cx-70},{ry+165}" '
         f'fill="none" stroke="{C_INCENSE}" stroke-width="3"/>')
o.append(f'<rect x="{cx-55}" y="{ry+165}" width="110" height="28" fill="none" stroke="{C_INCENSE}" stroke-width="3"/>')
o.append(f'<line x1="{cx}" y1="{ry+120}" x2="{cx}" y2="{ry+95}" stroke="{C_RED}" stroke-width="3"/>')
# 煙羽箭頭(浮力上升)
for dx in (-18, 0, 18):
    o.append(f'<path d="M {cx+dx} {ry+118} q {dx*0.3} -18 {dx*0.5} -30" fill="none" stroke="{C_GOLD}" stroke-width="2" stroke-linecap="round"/>')
o.append(T(cx, ry + 150, "煙羽↑浮力", 13, C_GOLD, "600", anc="middle"))
o.append(T(rx + 24, ry + 205, "集煙罩 · 爐盆 · 電子艙（參數化 CAD）", 12, C_NOTE))

# ── 底部條：自我否證(最強的誠實賣點) ──
by = 318
o.append(box(40, by, W - 80, 194, fill="#2b211c", stroke="#2b211c"))
o.append(f'<rect x="40" y="{by}" width="6" height="194" rx="3" fill="{C_GOLD}"/>')
o.append(T(66, by + 40, "我們被自己的判準推翻過", 24, "#ffffff", "800"))
o.append(T(66, by + 70, "三項獨立判準（煙羽幾何・橫流漂移・ACGIH 面風速）同時指出：原訂罩口接不住煙羽。", 16, "#d9cfc0"))
o.append(T(66, by + 94, "這不是把失敗藏起來，而是用幾何判準把設計推到能承接煙羽的位置。", 16, "#d9cfc0"))
# 175 → 215 大字
o.append(T(150, by + 165, "175 mm", 46, "#c9857a", "800", anc="middle"))
o.append(T(150, by + 186, "原訂罩口 ✗", 15, "#a89684", anc="middle"))
o.append(T(W/2, by + 158, "→", 40, C_GOLD, "400", anc="middle"))
o.append(T(W - 200, by + 165, "215 mm", 46, "#7bc49a", "800", anc="middle"))
o.append(T(W - 200, by + 186, "定案罩口＋三面側裙 ✓", 15, "#a89684", anc="middle"))
# 收束一句
o.append(T(W/2, by + 116, "多數團隊只寫成功；我們把「被自己推翻」也寫出來 —— 這才像 IEEE。", 14, C_GOLD, "600", anc="middle"))

o.append("</svg>")
open(os.path.join(HERE, "頁_捕集是接不是吸.svg"), "w", encoding="utf-8").write("\n".join(o))
print("輸出 頁_捕集是接不是吸.svg")
