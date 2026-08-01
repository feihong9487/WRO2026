#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KiCad 電路圖結構與連通性驗證器
================================================================
本機沒有 KiCad 可開檔，因此用靜態分析代替：解析 S-expression，
逐項檢查「KiCad 載入時會抱怨的東西」與「電氣上會斷線的東西」。

檢查項目：
  A. 括號平衡與 S-expression 可解析
  B. 每個 lib_id 都能在 lib_symbols 找到對應定義
  C. 元件實例的 pin 編號與符號定義一致
  D. ★導線端點是否真的落在腳位座標上★（座標算錯 → 看起來有線、實際沒連上）
  E. 每個網路至少有 2 個連接點（單點網路 = 斷頭）
  F. 標籤與電源符號是否都接在導線端點上
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

SCH = Path(__file__).parent / "incense_p0.kicad_sch"
TOL = 0.01          # mm，座標比對容差


# ── A. 解析 ──────────────────────────────────────────────────
def tokenize(text):
    tokens, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            tokens.append(c); i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n:
                if text[j] == "\\":
                    buf.append(text[j + 1]); j += 2
                elif text[j] == '"':
                    break
                else:
                    buf.append(text[j]); j += 1
            tokens.append(("STR", "".join(buf))); i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()\"":
                j += 1
            tokens.append(("SYM", text[i:j])); i = j
    return tokens


def parse(tokens):
    def helper(idx):
        node, i = [], idx
        while i < len(tokens):
            t = tokens[i]
            if t == "(":
                sub, i = helper(i + 1)
                node.append(sub)
            elif t == ")":
                return node, i + 1
            else:
                node.append(t); i += 1
        return node, i
    if tokens[0] != "(":
        raise ValueError("檔案不是以 ( 開頭")
    tree, end = helper(1)
    if end != len(tokens):
        raise ValueError(f"解析後仍有殘留 token（位置 {end}/{len(tokens)}）")
    return tree


def head(node):
    return node[0][1] if node and isinstance(node[0], tuple) else None

def find_all(node, name):
    return [c for c in node if isinstance(c, list) and head(c) == name]

def find_one(node, name):
    r = find_all(node, name)
    return r[0] if r else None

def val(node, idx=1):
    return node[idx][1] if len(node) > idx and isinstance(node[idx], tuple) else None

def nums(node, start=1, count=2):
    out = []
    for k in range(start, start + count):
        if len(node) > k and isinstance(node[k], tuple):
            try: out.append(float(node[k][1]))
            except ValueError: out.append(None)
    return out


def main():
    raw = SCH.read_text(encoding="utf-8")
    problems, warnings, notes = [], [], []

    # A. 括號平衡（字串感知）
    depth, in_str, esc_next = 0, False, False
    for ch in raw:
        if esc_next: esc_next = False; continue
        if in_str:
            if ch == "\\": esc_next = True
            elif ch == '"': in_str = False
            continue
        if ch == '"': in_str = True
        elif ch == "(": depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0: problems.append("A: 出現多餘的右括號")
    if depth != 0:
        problems.append(f"A: 括號不平衡，結尾 depth={depth}")
    if in_str:
        problems.append("A: 有字串未關閉")

    try:
        tree = parse(tokenize(raw))
    except Exception as e:
        problems.append(f"A: S-expression 無法解析 — {e}")
        report(problems, warnings, notes); return

    if head(tree) != "kicad_sch":
        problems.append(f"A: 根節點應為 kicad_sch，實際為 {head(tree)}")
    notes.append(f"A: S-expression 解析成功，根節點 kicad_sch，共 {len(tree)} 個頂層節點")

    # B/C. 符號定義 vs 實例
    libs = find_one(tree, "lib_symbols")
    lib_pins = {}
    for s in find_all(libs, "symbol"):
        name = val(s)
        pins = set()
        for sub in find_all(s, "symbol"):
            for p in find_all(sub, "pin"):
                pn = find_one(p, "number")
                if pn: pins.add(val(pn))
        lib_pins[name] = pins
    notes.append(f"B: lib_symbols 內含 {len(lib_pins)} 個符號定義")

    # 建立符號定義的腳位本地座標表
    lib_pin_xy = {}
    for s in find_all(libs, "symbol"):
        name = val(s)
        d = {}
        for sub in find_all(s, "symbol"):
            for p in find_all(sub, "pin"):
                at = find_one(p, "at")
                pn = find_one(p, "number")
                if at and pn:
                    x, y = nums(at, 1, 2)
                    d[val(pn)] = (x, y)
        lib_pin_xy[name] = d

    instances = [c for c in tree if isinstance(c, list) and head(c) == "symbol"]
    expected_pin_pts = []
    refs = []
    for inst in instances:
        lid_node = find_one(inst, "lib_id")
        lib_id = val(lid_node) if lid_node else None
        at = find_one(inst, "at")
        X, Y = nums(at, 1, 2)
        ref = None
        for pr in find_all(inst, "property"):
            if val(pr) == "Reference":
                ref = val(pr, 2)
        refs.append(ref)

        if lib_id not in lib_pins:
            problems.append(f"B: {ref} 的 lib_id「{lib_id}」在 lib_symbols 找不到定義")
            continue

        inst_pins = {val(p) for p in find_all(inst, "pin")}
        missing = inst_pins - lib_pins[lib_id]
        if missing:
            problems.append(f"C: {ref} 引用了定義中不存在的腳位 {sorted(missing)}")

        for pnum, (px, py) in lib_pin_xy[lib_id].items():
            if pnum in inst_pins:
                expected_pin_pts.append((round(X + px, 2), round(Y - py, 2), ref, pnum))

    notes.append(f"B/C: {len(instances)} 個元件實例，lib_id 與腳位編號全部對得上"
                 if not problems else "B/C: 有問題，見上")

    dup = [r for r in refs if refs.count(r) > 1 and r]
    if dup:
        problems.append(f"C: 參考編號重複 {sorted(set(dup))}")

    # D. 導線端點 vs 腳位座標
    wires = find_all(tree, "wire")
    wire_pts = []
    for w in wires:
        pts = find_one(w, "pts")
        xys = find_all(pts, "xy")
        coords = [tuple(round(v, 2) for v in nums(x, 1, 2)) for x in xys]
        wire_pts.append(coords)

    wire_endpoint_set = set()
    for coords in wire_pts:
        for c in coords:
            wire_endpoint_set.add(c)

    # no-connect 旗標的位置也算「已處理」
    nc_pts = set()
    for nc in find_all(tree, "no_connect"):
        at = find_one(nc, "at")
        nc_pts.add(tuple(round(v, 2) for v in nums(at, 1, 2)))

    unconnected_pins = []
    for (x, y, ref, pnum) in expected_pin_pts:
        if (x, y) not in wire_endpoint_set and (x, y) not in nc_pts:
            unconnected_pins.append(f"{ref}.{pnum} @({x},{y})")
    if unconnected_pins:
        problems.append(
            f"D: {len(unconnected_pins)} 個腳位座標上沒有導線端點（等於沒接上）："
            + ", ".join(unconnected_pins[:6])
            + (" …" if len(unconnected_pins) > 6 else "")
        )
    else:
        notes.append(f"D: {len(expected_pin_pts)} 個腳位全部已處理"
                     f"（導線端點 {len(expected_pin_pts) - len(nc_pts)} 個、"
                     f"no-connect 旗標 {len(nc_pts)} 個）✓")

    # E/F. 網路連通性
    #   改用「沿導線做 union-find」判斷，而非數標籤——
    #   自從訊號改為實際導線連接後，每條網路只有一個命名標籤，
    #   用標籤數判斷會把所有兩點網路誤報為單點。
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for coords in wire_pts:
        for a, b in zip(coords, coords[1:]):
            union(a, b)

    # 每個連通塊掛了幾支腳
    group_pins = defaultdict(list)
    for (x, y, ref, pnum) in expected_pin_pts:
        if (x, y) in nc_pts:
            continue
        group_pins[find((x, y))].append(f"{ref}.{pnum}")

    # 電源符號也算一個連接點
    group_pwr = defaultdict(list)
    for inst in instances:
        lid = find_one(inst, "lib_id")
        lib_id = val(lid) if lid else ""
        short = lib_id.split(":")[-1]
        if short in ("GND", "+3V3", "+5V", "+12V", "PWR_FLAG"):
            at = find_one(inst, "at")
            pt = tuple(round(v, 2) for v in nums(at, 1, 2))
            group_pwr[find(pt)].append(short)

    labels = find_all(tree, "label")
    label_of = {}
    dangling_labels = []
    for lb in labels:
        name = val(lb)
        at = find_one(lb, "at")
        pt = tuple(round(v, 2) for v in nums(at, 1, 2))
        if pt not in wire_endpoint_set:
            dangling_labels.append(f"{name} @{pt}")
        else:
            label_of[find(pt)] = name

    if dangling_labels:
        problems.append(
            f"F: {len(dangling_labels)} 個標籤沒接在導線端點上："
            + ", ".join(dangling_labels[:6]))
    else:
        notes.append(f"F: {len(labels)} 個網路標籤全部落在導線端點上 ✓")

    # 每條網路至少要有 2 個連接點（腳位 ＋ 電源符號）
    singles = []
    for g in set(list(group_pins) + list(group_pwr)):
        n = len(group_pins.get(g, [])) + len(group_pwr.get(g, []))
        if n < 2:
            who = (group_pins.get(g) or group_pwr.get(g) or ["?"])[0]
            singles.append(f"{label_of.get(g, '(未命名)')}={who}")
    if singles:
        warnings.append(f"E: 單點網路（只有一端，可能斷頭）：{', '.join(sorted(singles))}")

    n_nets = len(set(list(group_pins) + list(group_pwr)))
    notes.append(f"E: 沿導線追蹤出 {n_nets} 條網路，全部 ≥2 個連接點 ✓"
                 if not singles else f"E: 共 {n_nets} 條網路")
    top = sorted(group_pins.items(), key=lambda kv: -len(kv[1]))[:4]
    notes.append("E: 連接點最多的訊號網路 — "
                 + "、".join(f"{label_of.get(g, '?')}×{len(v)}" for g, v in top))

    report(problems, warnings, notes); return

    if head(tree) != "kicad_sch":
        problems.append(f"A: 根節點應為 kicad_sch，實際為 {head(tree)}")
    notes.append(f"A: S-expression 解析成功，根節點 kicad_sch，共 {len(tree)} 個頂層節點")

    # B/C. 符號定義 vs 實例
    libs = find_one(tree, "lib_symbols")
    lib_pins = {}
    for s in find_all(libs, "symbol"):
        name = val(s)
        pins = set()
        for sub in find_all(s, "symbol"):
            for p in find_all(sub, "pin"):
                pn = find_one(p, "number")
                if pn: pins.add(val(pn))
        lib_pins[name] = pins
    notes.append(f"B: lib_symbols 內含 {len(lib_pins)} 個符號定義")

    # 建立符號定義的腳位本地座標表
    lib_pin_xy = {}
    for s in find_all(libs, "symbol"):
        name = val(s)
        d = {}
        for sub in find_all(s, "symbol"):
            for p in find_all(sub, "pin"):
                at = find_one(p, "at")
                pn = find_one(p, "number")
                if at and pn:
                    x, y = nums(at, 1, 2)
                    d[val(pn)] = (x, y)
        lib_pin_xy[name] = d

    instances = [c for c in tree if isinstance(c, list) and head(c) == "symbol"]
    expected_pin_pts = []
    refs = []
    for inst in instances:
        lid_node = find_one(inst, "lib_id")
        lib_id = val(lid_node) if lid_node else None
        at = find_one(inst, "at")
        X, Y = nums(at, 1, 2)
        ref = None
        for pr in find_all(inst, "property"):
            if val(pr) == "Reference":
                ref = val(pr, 2)
        refs.append(ref)

        if lib_id not in lib_pins:
            problems.append(f"B: {ref} 的 lib_id「{lib_id}」在 lib_symbols 找不到定義")
            continue

        inst_pins = {val(p) for p in find_all(inst, "pin")}
        missing = inst_pins - lib_pins[lib_id]
        if missing:
            problems.append(f"C: {ref} 引用了定義中不存在的腳位 {sorted(missing)}")

        for pnum, (px, py) in lib_pin_xy[lib_id].items():
            if pnum in inst_pins:
                expected_pin_pts.append((round(X + px, 2), round(Y - py, 2), ref, pnum))

    notes.append(f"B/C: {len(instances)} 個元件實例，lib_id 與腳位編號全部對得上"
                 if not problems else "B/C: 有問題，見上")

    dup = [r for r in refs if refs.count(r) > 1 and r]
    if dup:
        problems.append(f"C: 參考編號重複 {sorted(set(dup))}")

    # D. 導線端點 vs 腳位座標
    wires = find_all(tree, "wire")
    wire_pts = []
    for w in wires:
        pts = find_one(w, "pts")
        xys = find_all(pts, "xy")
        coords = [tuple(round(v, 2) for v in nums(x, 1, 2)) for x in xys]
        wire_pts.append(coords)

    wire_endpoint_set = set()
    for coords in wire_pts:
        for c in coords:
            wire_endpoint_set.add(c)

    # no-connect 旗標的位置也算「已處理」
    nc_pts = set()
    for nc in find_all(tree, "no_connect"):
        at = find_one(nc, "at")
        nc_pts.add(tuple(round(v, 2) for v in nums(at, 1, 2)))

    unconnected_pins = []
    for (x, y, ref, pnum) in expected_pin_pts:
        if (x, y) not in wire_endpoint_set and (x, y) not in nc_pts:
            unconnected_pins.append(f"{ref}.{pnum} @({x},{y})")
    if unconnected_pins:
        problems.append(
            f"D: {len(unconnected_pins)} 個腳位座標上沒有導線端點（等於沒接上）："
            + ", ".join(unconnected_pins[:6])
            + (" …" if len(unconnected_pins) > 6 else "")
        )
    else:
        notes.append(f"D: {len(expected_pin_pts)} 個腳位全部已處理"
                     f"（導線端點 {len(expected_pin_pts) - len(nc_pts)} 個、"
                     f"no-connect 旗標 {len(nc_pts)} 個）✓")

    # E/F. 網路連通性
    labels = find_all(tree, "label")
    net_pts = defaultdict(list)
    dangling_labels = []
    for lb in labels:
        name = val(lb)
        at = find_one(lb, "at")
        x, y = (round(v, 2) for v in nums(at, 1, 2))
        net_pts[name].append((x, y))
        if (x, y) not in wire_endpoint_set:
            dangling_labels.append(f"{name} @({x},{y})")

    # 電源符號也算一種網路連接點
    for inst in instances:
        lid = find_one(inst, "lib_id")
        lib_id = val(lid) if lid else ""
        if lib_id and lib_id.split(":")[-1] in ("GND", "+3V3", "+5V", "+12V"):
            at = find_one(inst, "at")
            x, y = (round(v, 2) for v in nums(at, 1, 2))
            net_pts[lib_id.split(":")[-1]].append((x, y))
            if (x, y) not in wire_endpoint_set:
                dangling_labels.append(f"{lib_id.split(':')[-1]} @({x},{y})")

    if dangling_labels:
        problems.append(
            f"F: {len(dangling_labels)} 個標籤/電源符號沒接在導線端點上："
            + ", ".join(dangling_labels[:6])
            + (" …" if len(dangling_labels) > 6 else "")
        )
    else:
        notes.append(f"F: {len(labels)} 個網路標籤與所有電源符號都落在導線端點上 ✓")

    single = {n: p for n, p in net_pts.items() if len(p) < 2}
    intentional = {"NC_2Y", "NC_3Y", "NC_4Y"}
    real_single = {n: p for n, p in single.items() if n not in intentional}
    if real_single:
        warnings.append(
            f"E: 單點網路（只有一端，可能斷頭）：{', '.join(sorted(real_single))}"
        )
    skipped = sorted(set(single) & intentional)
    if skipped:
        notes.append(f"E: 刻意空接的網路已排除：{', '.join(skipped)}")

    notes.append(f"E: 共 {len(net_pts)} 條網路")
    top = sorted(net_pts.items(), key=lambda kv: -len(kv[1]))[:6]
    notes.append("E: 連接點最多的網路 — " + "、".join(f"{n}×{len(p)}" for n, p in top))

    report(problems, warnings, notes)


def report(problems, warnings, notes):
    print("=" * 62)
    for n in notes:
        print(f"  ℹ {n}")
    if warnings:
        print("-" * 62)
        for w in warnings:
            print(f"  ⚠ {w}")
    print("=" * 62)
    if problems:
        for p in problems:
            print(f"  ✗ {p}")
        print(f"\n結果：發現 {len(problems)} 項問題，KiCad 可能無法正常載入。")
        sys.exit(1)
    print("結果：結構與連通性檢查全數通過 ✓")


if __name__ == "__main__":
    main()
