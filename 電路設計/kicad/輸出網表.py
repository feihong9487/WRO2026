#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
從 incense_p0.kicad_sch 反推網表（netlist），用來與接線表交叉核對。

作法：把每個腳位的圖紙座標算出來 → 沿導線傳遞 → 併入同名標籤／電源符號的網路。
輸出 網表.md。
"""

from collections import defaultdict
from pathlib import Path

import 驗證電路圖 as V   # 重用解析器

HERE = Path(__file__).parent
SCH = HERE / "incense_p0.kicad_sch"
OUT = HERE / "網表.md"

PWR_NETS = {"GND", "+3V3", "+5V", "+12V"}


def main():
    tree = V.parse(V.tokenize(SCH.read_text(encoding="utf-8")))

    # 符號定義的腳位本地座標與名稱
    libs = V.find_one(tree, "lib_symbols")
    lib_pin = {}
    for s in V.find_all(libs, "symbol"):
        name = V.val(s)
        d = {}
        for sub in V.find_all(s, "symbol"):
            for p in V.find_all(sub, "pin"):
                at, pn, nm = (V.find_one(p, "at"), V.find_one(p, "number"), V.find_one(p, "name"))
                if at and pn:
                    x, y = V.nums(at, 1, 2)
                    d[V.val(pn)] = (x, y, V.val(nm) if nm else "", p[1][1])
        lib_pin[name] = d

    # 元件實例 → 腳位圖紙座標
    pin_at = {}        # (x,y) -> [ "U1.GPIO4", ... ]
    pwr_at = {}        # (x,y) -> 電源網路名
    comp_rows = []
    for inst in [c for c in tree if isinstance(c, list) and V.head(c) == "symbol"]:
        lid = V.find_one(inst, "lib_id")
        lib_id = V.val(lid) if lid else ""
        short = lib_id.split(":")[-1]
        at = V.find_one(inst, "at")
        X, Y = V.nums(at, 1, 2)
        ref = value = None
        for pr in V.find_all(inst, "property"):
            if V.val(pr) == "Reference": ref = V.val(pr, 2)
            if V.val(pr) == "Value":     value = V.val(pr, 2)

        if short == "PWR_FLAG":
            continue
        if short in PWR_NETS:
            pwr_at[(round(X, 2), round(Y, 2))] = short
            continue

        comp_rows.append((ref, value, short))
        have = {V.val(p) for p in V.find_all(inst, "pin")}
        for pnum, (px, py, pname, etype) in lib_pin.get(lib_id, {}).items():
            if pnum not in have:
                continue
            key = (round(X + px, 2), round(Y - py, 2))
            pin_at.setdefault(key, []).append((ref, pnum, pname, etype))

    # 標籤座標
    label_at = defaultdict(list)
    for lb in V.find_all(tree, "label"):
        at = V.find_one(lb, "at")
        x, y = (round(v, 2) for v in V.nums(at, 1, 2))
        label_at[(x, y)].append(V.val(lb))

    # 用導線做 union-find，把兩端點併成同一節點
    parent = {}
    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb

    for w in V.find_all(tree, "wire"):
        pts = V.find_one(w, "pts")
        cs = [tuple(round(v, 2) for v in V.nums(x, 1, 2)) for x in V.find_all(pts, "xy")]
        for a, b in zip(cs, cs[1:]):
            union(a, b)

    for k in list(pin_at) + list(pwr_at) + list(label_at):
        find(k)

    # 把每個連通塊指派網路名（標籤名或電源名優先）
    group_name, group_pins = {}, defaultdict(list)
    for pt, names in label_at.items():
        group_name[find(pt)] = names[0]
    for pt, net in pwr_at.items():
        group_name[find(pt)] = net
    for pt, pins in pin_at.items():
        group_pins[find(pt)].extend(pins)

    # no-connect 旗標的位置：這些腳位是刻意空接，不算網路
    nc_groups = set()
    for nc in V.find_all(tree, "no_connect"):
        at = V.find_one(nc, "at")
        nc_groups.add(find(tuple(round(v, 2) for v in V.nums(at, 1, 2))))

    nets, no_connects = defaultdict(list), []
    for g, pins in group_pins.items():
        if g in nc_groups:
            no_connects.extend(pins)
        else:
            nets[group_name.get(g, f"(未命名-{g})")].extend(pins)

    # 輸出
    lines = [
        "# 智慧香爐 P0 — 網表（由 incense_p0.kicad_sch 反推）",
        "",
        "本檔由 `輸出網表.py` 自動產生（兩板合併架構），用途是與接線表交叉核對。",
        "**若兩邊對不上，代表電路圖或接線表其中一份錯了。**",
        "",
        f"元件 {len(comp_rows)} 個、網路 {len(nets)} 條。",
        "",
        "## 元件清單",
        "",
        "| 參考編號 | 品名 |",
        "|---|---|",
    ]
    for ref, value, _ in sorted(comp_rows, key=lambda r: (r[0][0], r[0])):
        lines.append(f"| `{ref}` | {value} |")

    lines += ["", "## 網路連線", "",
              "| 網路 | 連接點數 | 連到哪些腳位 |", "|---|---|---|"]
    for net in sorted(nets, key=lambda n: (-len(nets[n]), n)):
        pins = nets[net]
        desc = "、".join(f"`{r}` {nm}(pin {p})" for r, p, nm, _ in
                         sorted(pins, key=lambda x: (x[0], x[1])))
        flag = "" if len(pins) >= 2 else " ⚠️ 單點"
        lines.append(f"| **{net}** | {len(pins)}{flag} | {desc} |")

    if no_connects:
        lines += ["", "## 刻意空接（已標 no-connect 旗標，ERC 不會報錯）", "",
                  "| 腳位 | 說明 |", "|---|---|"]
        for r, p, nm, _ in sorted(no_connects, key=lambda x: (x[0], x[1])):
            lines.append(f"| `{r}` {nm}(pin {p}) | 74HCT125 未使用通道的輸出，"
                         f"其輸入已接 GND、致能已接 5V 除能 |")

    lines += [
        "", "## 關鍵路徑核對", "",
        "合併架構（兩板）的三條主幹，路徑必須完整無斷點：",
        "",
        "```",
        "感測  U2 SCD41 ──I2C1──┐",
        "      U3 SHT31 ──I2C2──┤── A1 MATRIX Mini R4（感測＋安全＋致動）",
        "                        │",
        "決策  A2 Pi 5 ──USB 序列┘   感測上傳 ＋ FAN 指令走同一條",
        "",
        "致動  A1 ──D4L p13/D4R p10/D1R p2──> U5 MAX6675 ──> J1 熱電偶",
        "      A1 ──D1L p3 PWM──> U6 D4184 ──> M1 風扇（12V）",
        "",
        "電源  J2 12V 2A ──┬──> A1 VIN（板子吃 6-24V）",
        "                  └──> U6 VIN+（風扇動力）      共地自動成立",
        "```",
        "",
        "對照上表：`+12V` 應為 **3 點**（J2、A1、U6），這是「一顆電源餵兩者」的證據；",
        "`I2C1_*` 與 `I2C2_*` 各 2 點——兩個 I2C 埠經 PCA9548A 多工器彼此獨立，不共匯流排。",
        "",
        "> 原三板架構的 `ALARM` 網路已不存在：感測與安全同在一顆 MCU，",
        "> 不需要跨板警報線，連帶取消 3.3V→5V 電平轉換與 10k 下拉電阻。",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"已輸出 {OUT.name}：元件 {len(comp_rows)} 個、網路 {len(nets)} 條")
    for net in ("I2C1_SDA", "TC_SCK", "FAN_PWM", "+12V"):
        pins = nets.get(net, [])
        print(f"  {net:12s} {len(pins)} 點  " +
              "、".join(f"{r}.{nm}" for r, p, nm, _ in sorted(pins)))


if __name__ == "__main__":
    main()
