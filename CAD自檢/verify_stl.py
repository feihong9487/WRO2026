#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧香爐 — STL 幾何驗證器（L2 迴路）
=============================================================
把 CAD 匯出的 STL 拿來，跟 mech_params.py 的設計參數對帳。
全過 exit 0，任一失敗 exit 1 —— 這是 CAD 層唯一機器可判定的訊號。

用法：
  python3 verify_stl.py <零件>.stl                # 通用幾何檢查

★ 見 .claude/commands/verify.md：不得為了讓輸出變綠而放寬容差或修改設計紅線。★

核心技巧：閉合曲面的虧格（genus）等於通孔數量。
  Euler 示性數 χ = V - E + F，genus g = (2 - χ) / 2。
  一塊有 N 個通孔的板子，g 應等於 N —— 少挖一孔或多挖一孔都會被抓到。

★ 2026-08-02：改為純標準函式庫實作 ★
  原版依賴 trimesh，但本機的系統 Python 受 PEP 668 保護裝不了。
  STL 格式本身很單純（三角形陣列），水密性、連通元件、體積、虧格
  都能自己算。若環境有 trimesh 會優先使用（三角化容差處理較完整）。
"""

import argparse
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mech_params as P

PASS = 0
FAIL = 0
TOL_PCT = 0.05          # 尺寸容差 5%（涵蓋 STL 三角化誤差與列印公差設定）
QUANT = 1e-4            # 頂點量化尺度，用於合併浮點誤差造成的重複點


def ok(msg):
    global PASS
    print(f"[PASS] {msg}")
    PASS += 1


def bad(msg, detail=""):
    global FAIL
    print(f"[FAIL] {msg}")
    if detail:
        print(f"       └─ {detail}")
    FAIL += 1


def warn(msg, detail=""):
    print(f"[WARN] {msg}")
    if detail:
        print(f"       └─ {detail}")


def close_enough(actual, expect, tol=TOL_PCT):
    if expect == 0:
        return abs(actual) < 1e-6
    return abs(actual - expect) / abs(expect) <= tol


# ═══════════════════════════════════════════════════════════════
# 純標準函式庫的 STL 解析與拓樸分析
# ═══════════════════════════════════════════════════════════════

class Mesh:
    """最小可用的三角網格：足以做水密、連通、體積、虧格分析。"""

    def __init__(self, tris):
        self.tris = tris                      # [((x,y,z)*3), ...]
        self._index()

    def _index(self):
        """把座標量化後建立頂點索引，合併浮點誤差造成的重複點。"""
        vmap, verts, faces = {}, [], []
        for tri in self.tris:
            idx = []
            for v in tri:
                key = tuple(round(c / QUANT) for c in v)
                if key not in vmap:
                    vmap[key] = len(verts)
                    verts.append(v)
                idx.append(vmap[key])
            faces.append(tuple(idx))
        self.vertices = verts
        self.faces = faces

        # 邊 → 使用它的面數；同時計數有向邊以判定纏繞方向
        self.edge_count = defaultdict(int)
        self.directed = defaultdict(int)
        for a, b, c in faces:
            for u, v in ((a, b), (b, c), (c, a)):
                self.edge_count[frozenset((u, v))] += 1
                self.directed[(u, v)] += 1

    @property
    def is_watertight(self):
        """每條邊恰好被兩個面共用。"""
        return bool(self.edge_count) and all(n == 2 for n in self.edge_count.values())

    @property
    def is_winding_consistent(self):
        """
        方向一致的閉合曲面：每條邊被兩個三角形以【相反方向】走過，
        因此每個有向邊 (u,v) 恰好出現一次。
        若某個 (u,v) 出現兩次，代表相鄰兩面同向 —— 法向量錯亂。
        """
        return all(n == 1 for n in self.directed.values())

    @property
    def body_count(self):
        """連通元件數（沿共用邊擴散）。"""
        adj = defaultdict(set)
        for i, (a, b, c) in enumerate(self.faces):
            for u, v in ((a, b), (b, c), (c, a)):
                adj[frozenset((u, v))].add(i)
        seen, groups = set(), 0
        for i in range(len(self.faces)):
            if i in seen:
                continue
            groups += 1
            stack = [i]
            seen.add(i)
            while stack:
                f = stack.pop()
                a, b, c = self.faces[f]
                for u, v in ((a, b), (b, c), (c, a)):
                    for nb in adj[frozenset((u, v))]:
                        if nb not in seen:
                            seen.add(nb)
                            stack.append(nb)
        return groups

    @property
    def extents(self):
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        zs = [v[2] for v in self.vertices]
        return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

    @property
    def volume(self):
        """散度定理：Σ 每個三角形與原點構成的四面體有號體積。"""
        total = 0.0
        for (a, b, c) in self.tris:
            total += (a[0] * (b[1] * c[2] - b[2] * c[1])
                      - a[1] * (b[0] * c[2] - b[2] * c[0])
                      + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
        return abs(total)

    @property
    def genus(self):
        """χ = V - E + F；g = (2 - χ)/2。僅對單一連通閉合曲面有意義。"""
        chi = len(self.vertices) - len(self.edge_count) + len(self.faces)
        return int(round((2 - chi) / 2))


def load_stl(path):
    """自動判別 ASCII / 二進位 STL。"""
    data = Path(path).read_bytes()
    tris = []
    # 二進位：檔頭 80 bytes ＋ 4 bytes 三角形數
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if len(data) == 84 + n * 50:
            for i in range(n):
                off = 84 + i * 50 + 12          # 跳過法向量
                v = struct.unpack_from("<9f", data, off)
                tris.append(((v[0], v[1], v[2]), (v[3], v[4], v[5]), (v[6], v[7], v[8])))
            return Mesh(tris)
    # ASCII
    cur = []
    for line in data.decode("utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith("vertex"):
            cur.append(tuple(float(x) for x in s.split()[1:4]))
            if len(cur) == 3:
                tris.append(tuple(cur))
                cur = []
    if not tris:
        raise ValueError("解析不到任何三角形，檔案可能不是有效的 STL")
    return Mesh(tris)


# ═══════════════════════════════════════════════════════════════
# 零件驗證
# ═══════════════════════════════════════════════════════════════

def verify_generic(mesh):
    """未指定零件類型時的通用檢查。"""
    if mesh.is_watertight:
        ok("模型水密（manifold）")
    else:
        bad("模型非水密")
    n = mesh.body_count
    if n == 1:
        ok("單一實體（1 個連通元件）")
    else:
        bad(f"含 {n} 個分離實體", "分離塊在切片時會變成印不出來的浮空件")
    ext = mesh.extents
    print(f"       外框尺寸：{ext[0]:.1f} × {ext[1]:.1f} × {ext[2]:.1f} mm")
    if mesh.is_winding_consistent:
        ok("面法向量方向一致")
    else:
        bad("面法向量方向不一致")
    if mesh.is_watertight:
        print(f"       體積：{mesh.volume/1000:.1f} cm³")
        if n == 1:
            print(f"       虧格（通孔數推估）：{mesh.genus}")


def main():
    ap = argparse.ArgumentParser(description="智慧香爐 STL 幾何驗證器")
    ap.add_argument("stl", help="STL 檔案路徑")
    ap.add_argument("--part", default="generic",
                    choices=["generic"],
                    help="零件類型（理香機構移除後僅剩通用檢查；"
                         "新零件的專屬驗證請在此登記）")
    args = ap.parse_args()

    print(f"=== STL 幾何驗證：{args.stl}（類型：{args.part}）===")
    try:
        mesh = load_stl(args.stl)
    except Exception as e:
        print(f"[FAIL] 無法讀取 STL：{e}")
        sys.exit(1)

    print(f"       三角形 {len(mesh.faces)}、頂點 {len(mesh.vertices)}")
    verify_generic(mesh)

    pending = P.unmeasured_items()
    if pending:
        print("\n【尚未實測，相關數值在報告中僅可稱設計目標】")
        for item in pending:
            print(f"  ・{item}")

    print("---------------------------------------------")
    print(f"通過 {PASS} 項，失敗 {FAIL} 項")
    if FAIL == 0:
        print("✅ 幾何驗證通過 —— 下一步是實體列印與人工檢驗（L3，無法自動化）")
        sys.exit(0)
    print("❌ 請修正模型或設計參數，不要放寬本驗證器的門檻")
    sys.exit(1)


if __name__ == "__main__":
    main()
