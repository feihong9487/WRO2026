#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧香爐 P0 — KiCad 電路圖產生器
================================================================
產出：incense_p0.kicad_sch / .kicad_pro / incense.kicad_sym / sym-lib-table

設計決策：
  * ★訊號線實際畫出導線★（含轉角與接點），並在導線上標註網路名稱，圖面直觀可讀。
  * 電源網路（GND / +3V3 / +5V / +12V）用電源符號——GND 有 10 個接點，
    全部拉線會變成一團亂麻。這是電路圖的標準做法。
  * 符號定義內嵌 lib_symbols，並另存 incense.kicad_sym 供 KiCad 註冊。
  * 模組（開發板、breakout board）以方塊符號表示，這是慣例畫法。
  * 2026-08-02 起為兩板架構（Pi 5 ＋ MATRIX Mini R4）。

版面與佈線資料在 佈線定義.py，改版面不必動本檔。
重跑：python3 產生電路圖.py
"""

import uuid
from pathlib import Path

from 佈線定義 import COMPONENTS, RESISTORS, CH

OUT_DIR = Path(__file__).parent
PROJECT = "incense_p0"
PAPER = "A3"
PAPER_W, PAPER_H = 420.0, 297.0
STUB = 5.08          # 腳位長度
GRID = 1.27          # KiCad 連接格點（50 mil）；所有端點必須對齊，否則 ERC 報 endpoint_off_grid
PWR_NETS = {"GND", "+3V3", "+5V", "+12V"}

def U() -> str:
    return str(uuid.uuid4())

ROOT_UUID = U()
COMP_BY_REF = {c["ref"]: c for c in COMPONENTS}


def snap(v: float) -> float:
    """吸附到連接格點。"""
    return round(round(v / GRID) * GRID, 2)


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ────────────────────────────────────────────────────────────────
# 幾何：符號尺寸與腳位座標
# ────────────────────────────────────────────────────────────────

def geom(c):
    rows = max(len(c["left"]), len(c["right"]))
    h = max(rows + 1, 4) * 2.54
    return c["width"], h


def pin_local(c, side, i):
    """符號本地座標（+Y 朝上，KiCad 符號庫慣例）。"""
    w, h = geom(c)
    x = -(w / 2 + STUB) if side == "L" else (w / 2 + STUB)
    return x, h / 2 - 2.54 * (i + 1)


def pin_xy(ref, pin_name):
    """圖紙座標。符號放在 (X,Y) 時，本地 (px,py) 對應圖紙 (X+px, Y-py)。"""
    c = COMP_BY_REF[ref]
    X, Y = c["at"]
    for side, pins in (("L", c["left"]), ("R", c["right"])):
        for i, p in enumerate(pins):
            if p[1] == pin_name:
                px, py = pin_local(c, side, i)
                return round(X + px, 2), round(Y - py, 2)
    raise KeyError(f"{ref} 沒有腳位「{pin_name}」")


def bbox(c):
    X, Y = c["at"]
    w, h = geom(c)
    return X - w / 2, Y - h / 2, X + w / 2, Y + h / 2


# ────────────────────────────────────────────────────────────────
# 佈線：以通道座標產生正交路徑
# ────────────────────────────────────────────────────────────────

def hvh(a, b, xm):
    """水平 → 垂直 → 水平（Z 形）。轉角 x 吸附到格點。"""
    xm = snap(xm)
    return [a, (xm, a[1]), (xm, b[1]), b]


def put_label(poly, net, frac=0.45):
    """
    在折線的第一段夠長的水平線上插入一個頂點，並回傳標籤座標。
    標籤讓網表有可讀名稱（否則 KiCad 會自動命名成 Net-(A1-A0…)）。
    插入頂點是為了讓標籤落在導線端點上——共線的兩段導線共用端點會自動連通，
    不需要 junction。
    """
    best = None
    for i, (a, b) in enumerate(zip(poly, poly[1:])):
        if abs(a[1] - b[1]) < 1e-6:
            span = abs(b[0] - a[0])
            if span > 6.0 and (best is None or span > best[0]):
                best = (span, i, a, b)
    if best is None:
        return None
    _, i, a, b = best
    pt = (snap(a[0] + (b[0] - a[0]) * frac), a[1])
    if pt in (a, b):
        return None
    poly.insert(i + 1, pt)
    return (net, pt)


def build_routes():
    """
    回傳 (wires, junctions, labels)。

    合併版（兩板）的網路全部是「兩點」——每條 I2C 埠只掛一顆感測器
    （PCA9548A 多工器讓各埠彼此獨立），警報線與下拉電阻也已取消，
    因此不需要任何接點（junction）。
    """
    W, J, L = [], [], []

    def link(net, a, b, xm):
        poly = hvh(a, b, xm)
        W.append(poly)
        lb = put_label(poly, net)
        if lb: L.append(lb)

    # ── I2C1：SCD41 → 控制器（Grove 線，含 5V/GND 未畫）────────
    link("I2C1_SDA", pin_xy("U2", "SDA"), pin_xy("A1", "I2C1 SDA"), CH["i2c1_sda"])
    link("I2C1_SCL", pin_xy("U2", "SCL"), pin_xy("A1", "I2C1 SCL"), CH["i2c1_scl"])

    # ── I2C2：SHT31 → 控制器 ─────────────────────────────────
    link("I2C2_SDA", pin_xy("U3", "SDA"), pin_xy("A1", "I2C2 SDA"), CH["i2c2_sda"])
    link("I2C2_SCL", pin_xy("U3", "SCL"), pin_xy("A1", "I2C2 SCL"), CH["i2c2_scl"])

    # ── 熱電偶 SPI：控制器 D1/D4 埠 → MAX6675（軟體 SPI）──────
    link("TC_SCK", pin_xy("A1", "D4L p13 SCK"), pin_xy("U5", "SCK"), CH["tc_sck"])
    link("TC_CS",  pin_xy("A1", "D1R p2 CS"),   pin_xy("U5", "CS"),  CH["tc_cs"])
    link("TC_SO",  pin_xy("U5", "SO"), pin_xy("A1", "D4R p10 SO"),   CH["tc_so"])

    # ── 風扇 PWM：控制器 → D4184 ─────────────────────────────
    link("FAN_PWM", pin_xy("A1", "D1L p3 PWM"), pin_xy("U6", "TRIG (PWM)"), CH["fan_pwm"])

    # ── USB：控制器 ↔ Pi 5（供電、感測上傳、FAN 指令都走這條）──
    link("USB_PI_R4", pin_xy("A1", "USB - Pi 5"), pin_xy("A2", "USB - 控制器"), CH["usb"])

    # ── 熱電偶接線：MAX6675 → K 型熱電偶 ─────────────────────
    link("TC_KP", pin_xy("U5", "K+"), pin_xy("J1", "K+"), CH["tc_kp"])
    link("TC_KN", pin_xy("U5", "K-"), pin_xy("J1", "K-"), CH["tc_kn"])

    # ── 風扇線：D4184 → 風扇 ─────────────────────────────────
    link("FAN_P", pin_xy("U6", "OUT+"), pin_xy("M1", "紅線 +"), CH["fan_p"])
    link("FAN_N", pin_xy("U6", "OUT-"), pin_xy("M1", "黑線 -"), CH["fan_n"])

    # ── 霧化／照明致動：控制器 → PCF8574（I2C3 獨立埠）────────
    # （2026-08-16 理香機構移除：MAG1-4 四路與 K1 電磁鐵陣列自電路刪除）
    link("I2C3_SDA", pin_xy("A1", "I2C3 SDA"), pin_xy("U7", "SDA"), CH["i2c3_sda"])
    link("I2C3_SCL", pin_xy("A1", "I2C3 SCL"), pin_xy("U7", "SCL"), CH["i2c3_scl"])
    link("MIST", pin_xy("U7", "OUT5 霧化"), pin_xy("M2", "MIST"), CH["mist"])
    link("HOODLED", pin_xy("U7", "OUT6 罩內LED"), pin_xy("LED1", "HOODLED"), CH["hoodled"])

    return W, J, L


# ────────────────────────────────────────────────────────────────
# 版面自我檢查
# ────────────────────────────────────────────────────────────────

def seg_hits_box(p1, p2, box, pad=1.0):
    """線段（僅正交）是否穿過方框內部。"""
    x1, y1, x2, y2 = box
    x1, y1, x2, y2 = x1 + pad, y1 + pad, x2 - pad, y2 - pad
    ax, ay = p1
    bx, by = p2
    if abs(ay - by) < 1e-6:                      # 水平
        return y1 < ay < y2 and min(ax, bx) < x2 and max(ax, bx) > x1
    if abs(ax - bx) < 1e-6:                      # 垂直
        return x1 < ax < x2 and min(ay, by) < y2 and max(ay, by) > y1
    return False


def self_check(wires):
    errs = []

    # 元件不可超出圖紙、彼此不可重疊
    boxes = {}
    for c in COMPONENTS:
        b = bbox(c)
        boxes[c["ref"]] = b
        if b[0] < 5 or b[1] < 5 or b[2] > PAPER_W - 5 or b[3] > PAPER_H - 5:
            errs.append(f"版面：{c['ref']} 超出圖紙 {tuple(round(v,1) for v in b)}")
    # 元件中心與寬度必須對齊格點，否則腳位座標會落在格點外
    for c in COMPONENTS:
        X, Y = c["at"]
        for label, v in (("中心 x", X), ("中心 y", Y), ("寬度", c["width"])):
            if abs(v - snap(v)) > 1e-6:
                errs.append(f"格點：{c['ref']} 的{label} {v} 未對齊 {GRID} mm 格點")

    refs = list(boxes)
    for i, ra in enumerate(refs):
        for rb in refs[i + 1:]:
            a, b = boxes[ra], boxes[rb]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                errs.append(f"版面：{ra} 與 {rb} 重疊")

    # 導線不可穿過元件本體
    for poly in wires:
        for p1, p2 in zip(poly, poly[1:]):
            for ref, b in boxes.items():
                if seg_hits_box(p1, p2, b):
                    errs.append(f"佈線：導線 {p1}→{p2} 穿過元件 {ref}")

    # 所有導線端點必須對齊連接格點（否則 KiCad ERC 報 endpoint_off_grid）
    for poly in wires:
        for (x, y) in poly:
            if abs(x - snap(x)) > 1e-6 or abs(y - snap(y)) > 1e-6:
                errs.append(f"格點：導線端點 ({x}, {y}) 未對齊 {GRID} mm 格點")

    # 每支訊號腳都要在某條導線的端點上
    ends = set()
    for poly in wires:
        ends.add(poly[0]); ends.add(poly[-1])
    for c in COMPONENTS:
        for side, pins in (("L", c["left"]), ("R", c["right"])):
            for i, (num, pname, etype, net) in enumerate(pins):
                if net in PWR_NETS:
                    continue
                if pin_xy(c["ref"], pname) not in ends:
                    errs.append(f"佈線：{c['ref']}.{pname}（{net}）沒有導線連上")
    return errs


# ────────────────────────────────────────────────────────────────
# 符號定義
# ────────────────────────────────────────────────────────────────

def rect_symbol(c):
    name, w, h = c["name"], *geom(c)
    hw, hh = w / 2, h / 2
    out = [
        f'    (symbol "incense:{esc(name)}"',
        '      (pin_names (offset 1.016))',
        '      (exclude_from_sim no) (in_bom yes) (on_board yes)',
        f'      (property "Reference" "{esc(c["ref"].rstrip("0123456789"))}" '
        f'(at 0 {hh + 2.54:.2f} 0) (effects (font (size 1.27 1.27))))',
        f'      (property "Value" "{esc(c["value"])}" '
        f'(at 0 {-hh - 2.54:.2f} 0) (effects (font (size 1.27 1.27))))',
        '      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (property "Description" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        f'      (symbol "{esc(name)}_0_1"',
        f'        (rectangle (start {-hw:.2f} {hh:.2f}) (end {hw:.2f} {-hh:.2f})',
        '          (stroke (width 0.254) (type default)) (fill (type background)))',
        '      )',
        f'      (symbol "{esc(name)}_1_1"',
    ]
    for side, pins in (("L", c["left"]), ("R", c["right"])):
        rot = 0 if side == "L" else 180
        for i, (num, pname, etype, _net) in enumerate(pins):
            px, py = pin_local(c, side, i)
            out.append(
                f'        (pin {etype} line (at {px:.2f} {py:.2f} {rot}) (length {STUB:.2f})\n'
                f'          (name "{esc(pname)}" (effects (font (size 1.27 1.27))))\n'
                f'          (number "{esc(num)}" (effects (font (size 1.27 1.27)))))')
    out += ['      )', '    )']
    return "\n".join(out)


def power_symbol(name, shape):
    if shape == "gnd":
        art = ('        (polyline (pts (xy 0 0) (xy 0 -1.27) (xy 1.905 -1.27) '
               '(xy 0 -3.81) (xy -1.905 -1.27) (xy 0 -1.27))\n'
               '          (stroke (width 0.254) (type default)) (fill (type none)))')
        rot, vy = 270, -5.08
    else:
        art = ('        (polyline (pts (xy -1.27 1.27) (xy 0 2.54) (xy 1.27 1.27) (xy -1.27 1.27))\n'
               '          (stroke (width 0.254) (type default)) (fill (type outline)))\n'
               '        (polyline (pts (xy 0 0) (xy 0 2.54))\n'
               '          (stroke (width 0.254) (type default)) (fill (type none)))')
        rot, vy = 90, 4.318
    return "\n".join([
        f'    (symbol "incense:{esc(name)}"',
        '      (power) (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes))',
        '      (exclude_from_sim no) (in_bom no) (on_board yes)',
        '      (property "Reference" "#PWR" (at 0 -1.27 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        f'      (property "Value" "{esc(name)}" (at 0 {vy:.3f} 0) (effects (font (size 1.27 1.27))))',
        '      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (property "Description" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        f'      (symbol "{esc(name)}_0_1"', art, '      )',
        f'      (symbol "{esc(name)}_1_1"',
        f'        (pin power_in line (at 0 0 {rot}) (length 0)',
        f'          (name "{esc(name)}" (effects (font (size 1.27 1.27))))',
        '          (number "1" (effects (font (size 1.27 1.27)))))',
        '      )', '    )'])


def pwr_flag_symbol():
    return "\n".join([
        '    (symbol "incense:PWR_FLAG"',
        '      (power) (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes))',
        '      (exclude_from_sim no) (in_bom no) (on_board yes)',
        '      (property "Reference" "#FLG" (at 0 1.905 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (property "Value" "PWR_FLAG" (at 0 3.81 0) (effects (font (size 1.27 1.27))))',
        '      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (property "Description" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (symbol "PWR_FLAG_0_0"',
        '        (pin power_out line (at 0 0 90) (length 0)',
        '          (name "~" (effects (font (size 1.27 1.27))))',
        '          (number "1" (effects (font (size 1.27 1.27)))))',
        '      )',
        '      (symbol "PWR_FLAG_0_1"',
        '        (polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.016 1.905) (xy 0 2.54)'
        ' (xy 1.016 1.905) (xy 0 1.27))',
        '          (stroke (width 0.254) (type default)) (fill (type none)))',
        '      )', '    )'])


def resistor_symbol():
    return "\n".join([
        '    (symbol "incense:R"',
        '      (pin_numbers (hide yes)) (pin_names (offset 0))',
        '      (exclude_from_sim no) (in_bom yes) (on_board yes)',
        '      (property "Reference" "R" (at 2.54 0.635 0) (effects (font (size 1.27 1.27)) (justify left)))',
        '      (property "Value" "R" (at 2.54 -1.905 0) (effects (font (size 1.27 1.27)) (justify left)))',
        '      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (property "Description" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        '      (symbol "R_0_1"',
        '        (rectangle (start -1.016 2.54) (end 1.016 -2.54)',
        '          (stroke (width 0.254) (type default)) (fill (type none)))',
        '      )',
        '      (symbol "R_1_1"',
        f'        (pin passive line (at 0 {STUB:.2f} 270) (length 2.54)',
        '          (name "~" (effects (font (size 1.27 1.27))))',
        '          (number "1" (effects (font (size 1.27 1.27)))))',
        f'        (pin passive line (at 0 {-STUB:.2f} 90) (length 2.54)',
        '          (name "~" (effects (font (size 1.27 1.27))))',
        '          (number "2" (effects (font (size 1.27 1.27)))))',
        '      )', '    )'])


# ────────────────────────────────────────────────────────────────
# 組裝
# ────────────────────────────────────────────────────────────────

def build():
    wires, junctions, labels = build_routes()
    errs = self_check(wires)
    if errs:
        raise SystemExit("版面／佈線檢查失敗：\n  " + "\n  ".join(errs))

    lib = [rect_symbol(c) for c in COMPONENTS]
    lib += [resistor_symbol(), pwr_flag_symbol()]
    for n, s in (("GND", "gnd"), ("+3V3", "arrow"), ("+5V", "arrow"), ("+12V", "arrow")):
        lib.append(power_symbol(n, s))

    body, pwr_n = [], [0]

    def add_wire(pts):
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            body.append(
                f'  (wire (pts (xy {a[0]:.2f} {a[1]:.2f}) (xy {b[0]:.2f} {b[1]:.2f}))\n'
                f'    (stroke (width 0) (type default))\n    (uuid "{U()}"))')

    def add_junction(x, y):
        body.append(f'  (junction (at {x:.2f} {y:.2f}) (diameter 0) '
                    f'(color 0 0 0 0) (uuid "{U()}"))')

    def add_power(x, y, net):
        pwr_n[0] += 1
        ref = f"#PWR{pwr_n[0]:03d}"
        voff = 3.81 if net == "GND" else -3.81
        body.append("\n".join([
            '  (symbol', f'    (lib_id "incense:{esc(net)}")',
            f'    (at {x:.2f} {y:.2f} 0)',
            '    (unit 1) (exclude_from_sim no) (in_bom no) (on_board yes) (dnp no)',
            f'    (uuid "{U()}")',
            f'    (property "Reference" "{ref}" (at {x:.2f} {y - 1.27:.2f} 0)',
            '      (effects (font (size 1.27 1.27)) (hide yes)))',
            f'    (property "Value" "{esc(net)}" (at {x:.2f} {y + voff:.2f} 0)',
            '      (effects (font (size 1.27 1.27))))',
            f'    (property "Footprint" "" (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'    (property "Datasheet" "" (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'    (property "Description" "" (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'    (pin "1" (uuid "{U()}"))',
            '    (instances', f'      (project "{PROJECT}"',
            f'        (path "/{ROOT_UUID}" (reference "{ref}") (unit 1))))', '  )']))

    def add_instance(lib_id, ref, value, X, Y, pins, ref_y, val_y, hide_ref=False):
        hide = ' (hide yes)' if hide_ref else ''
        body.append("\n".join([
            '  (symbol', f'    (lib_id "incense:{esc(lib_id)}")',
            f'    (at {X:.2f} {Y:.2f} 0)',
            '    (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)',
            f'    (uuid "{U()}")',
            f'    (property "Reference" "{esc(ref)}" (at {X:.2f} {ref_y:.2f} 0)',
            f'      (effects (font (size 1.27 1.27)){hide}))',
            f'    (property "Value" "{esc(value)}" (at {X:.2f} {val_y:.2f} 0)',
            '      (effects (font (size 1.27 1.27))))',
            f'    (property "Footprint" "" (at {X:.2f} {Y:.2f} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'    (property "Datasheet" "" (at {X:.2f} {Y:.2f} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'    (property "Description" "" (at {X:.2f} {Y:.2f} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            "\n".join(f'    (pin "{esc(p)}" (uuid "{U()}"))' for p in pins),
            '    (instances', f'      (project "{PROJECT}"',
            f'        (path "/{ROOT_UUID}" (reference "{esc(ref)}") (unit 1))))', '  )']))

    # 訊號導線、接點與網路名稱標籤
    for poly in wires:
        add_wire(poly)
    for x, y in junctions:
        add_junction(x, y)
    for net, (x, y) in labels:
        body.append(
            f'  (label "{esc(net)}" (at {x:.2f} {y:.2f} 0)\n'
            f'    (effects (font (size 1.27 1.27)) (justify left bottom))\n'
            f'    (uuid "{U()}"))')

    # 元件本體＋電源腳的短線與電源符號
    for c in COMPONENTS:
        X, Y = c["at"]
        w, h = geom(c)
        for side, pins in (("L", c["left"]), ("R", c["right"])):
            for i, (num, pname, etype, net) in enumerate(pins):
                if net not in PWR_NETS:
                    continue
                sx, sy = pin_xy(c["ref"], pname)
                d = -3.81 if side == "L" else 3.81
                add_wire([(sx, sy), (sx + d, sy)])
                add_power(sx + d, sy, net)
        add_instance(c["name"], c["ref"], c["value"], X, Y,
                     [p[0] for p in c["left"] + c["right"]],
                     Y - h / 2 - 2.54, Y + h / 2 + 3.81)

    # 電阻
    for r in RESISTORS:
        X, Y = r["at"]
        add_wire([(X, Y + STUB), (X, Y + STUB + 3.81)])
        add_power(X, Y + STUB + 3.81, r["bot_net"])
        add_instance("R", r["ref"], r["value"], X, Y, ["1", "2"],
                     Y - 1.27, Y + 1.27)

    # GND 的 PWR_FLAG
    fx, fy = 96.52, 175.26
    add_wire([(fx, fy), (fx, fy + STUB)])
    add_power(fx, fy + STUB, "GND")
    add_instance("PWR_FLAG", "#FLG01", "PWR_FLAG", fx, fy, ["1"],
                 fy - 2.54, fy - 5.08, hide_ref=True)

    # 圖說
    for x, y, sz, txt in [
        (14.0, 20.0, 6.0, "智慧香爐 P0 — 兩板系統電路圖"),
        (14.0, 27.0, 2.2, "訊號以導線直接連接；電源網路（GND / +5V / +12V）採電源符號，"
                          "同名符號即同一網路（GND 接點多，拉線會過於雜亂）。"),
        (14.0, 172.0, 3.2, "★ 合併架構：感測 ＋ 安全 ＋ 致動 同在 MATRIX Mini R4 ★"),
        (14.0, 179.0, 2.2, "SCD41 與 SHT31 以 Grove 線直插 I2C1 / I2C2 埠（5V，兩顆晶片皆支援 2.4-5.5V，不需電平轉換）。"),
        (14.0, 185.0, 2.2, "各 I2C 埠經 PCA9548A 多工器（位址 0x70）彼此獨立，韌體存取前需切通道：寫入 (1 << 通道)。"),
        (14.0, 191.0, 2.2, "原三板架構的「S3 GPIO4 → R4 警報線」已取消——感測與安全同在一顆 MCU，不需跨板訊號，"),
        (14.0, 197.0, 2.2, "連帶不再需要 3.3V→5V 電平轉換與 10k 下拉電阻。"),
        (14.0, 207.0, 3.2, "★ 腳位限制：不可使用 D2、D3 埠 ★"),
        (14.0, 214.0, 2.2, "MiniR4.begin() 內執行 PS2.config_gamepad(11, 4, 12, 5)，把 D2 埠(5,4) 與 D3 埠(12,11) 佔為手把介面。"),
        (14.0, 220.0, 2.2, "本設計僅用 D1 埠(3,2) 與 D4 埠(13,10)；風扇 PWM 必須落在 3/5/10/11 其中之一。"),
        (14.0, 230.0, 3.2, "★ 電源與共地 ★"),
        (14.0, 237.0, 2.2, "一顆 12V 2A 同時餵控制器（板子吃 6-24V）與 D4184，共地自動成立——省去原設計最易翻車的地線母排。"),
        (14.0, 243.0, 2.2, "馬達埠是 5V（Port M1 DC 5V Motor），推不動 12V 風扇，故 D4184 MOSFET 模組必須保留。"),
        (14.0, 249.0, 2.2, "12V 僅進 D4184 VIN± 與控制器電源輸入，不可碰到 5V 排。"),
        (14.0, 259.0, 2.2, "感測器與 MAX6675 的 5V/GND 實體上隨埠線一同供給，圖上以電源符號表示。"),
        (14.0, 265.0, 2.2, "I2C 線長上限約 1-2 公尺（100kHz、模組內建 10k 上拉）；感測頭若需更遠，改回三板架構走 WiFi。"),
        (14.0, 275.0, 2.2, "完整驗算見《電路設計/電氣驗證計算.md》；韌體見 R4/matrix_mini_r4/。"),
    ]:
        body.append(f'  (text "{esc(txt)}" (at {x:.2f} {y:.2f} 0)\n'
                    f'    (effects (font (size {sz:.2f} {sz:.2f})) (justify left bottom))\n'
                    f'    (uuid "{U()}"))')

    doc = "\n".join([
        '(kicad_sch', '  (version 20231120)', '  (generator "incense_p0_generator")',
        '  (generator_version "8.0")', f'  (uuid "{ROOT_UUID}")', f'  (paper "{PAPER}")',
        '  (title_block',
        '    (title "智慧香爐 P0 — 兩板系統電路圖")',
        '    (date "2026-07-31")', '    (rev "E")',
        '    (company "WRO 2026 智慧香爐")',
        '    (comment 1 "E 版：合併架構——感測改由 MATRIX Mini R4 直接 I2C 讀取，取消 ESP32-S3 與警報線")',
        '    (comment 2 "腳位僅用 D1/D4 埠（D2/D3 被 MiniR4.begin() 的 PS2 介面佔用）")',
        '  )',
        '  (lib_symbols', "\n".join(lib), '  )',
        "\n".join(body),
        '  (sheet_instances', '    (path "/" (page "1"))', '  )', ')', ''])
    return doc, lib, len(wires), len(junctions), len(labels)


def build_symbol_lib(lib):
    return "\n".join([
        '(kicad_symbol_lib', '  (version 20231120)',
        '  (generator "incense_p0_generator")', '  (generator_version "8.0")',
        "\n".join(lib).replace('(symbol "incense:', '(symbol "'), ')', ''])


PRO = """{
  "board": {},
  "boards": [],
  "cvpcb": { "equivalence_files": [] },
  "libraries": { "pinned_footprint_libs": [], "pinned_symbol_libs": [] },
  "meta": { "filename": "%s.kicad_pro", "version": 1 },
  "net_settings": {
    "classes": [
      { "name": "Default", "clearance": 0.2, "track_width": 0.25,
        "via_diameter": 0.8, "via_drill": 0.4, "wire_width": 6, "bus_width": 12 },
      { "name": "Power12V", "clearance": 0.4, "track_width": 0.8,
        "via_diameter": 1.0, "via_drill": 0.5, "wire_width": 6, "bus_width": 12 }
    ],
    "meta": { "version": 3 }
  },
  "pcbnew": { "page_layout_descr_file": "" },
  "schematic": {
    "legacy_lib_dir": "", "legacy_lib_list": [],
    "meta": { "version": 1 }, "page_layout_descr_file": ""
  },
  "sheets": [],
  "text_variables": {}
}
""" % PROJECT

SYM_LIB_TABLE = """(sym_lib_table
  (version 7)
  (lib (name "incense")(type "KiCad")(uri "${KIPRJMOD}/incense.kicad_sym")(options "")(descr "智慧香爐 P0 專用符號庫"))
)
"""

if __name__ == "__main__":
    sch, lib, nw, nj, nl = build()
    (OUT_DIR / f"{PROJECT}.kicad_sch").write_text(sch, encoding="utf-8")
    (OUT_DIR / f"{PROJECT}.kicad_pro").write_text(PRO, encoding="utf-8")
    (OUT_DIR / "incense.kicad_sym").write_text(build_symbol_lib(lib), encoding="utf-8")
    (OUT_DIR / "sym-lib-table").write_text(SYM_LIB_TABLE, encoding="utf-8")
    print(f"版面／佈線自我檢查通過")
    print(f"已產生 {PROJECT}.kicad_sch（{len(sch):,} 位元組，"
          f"{nw} 條訊號路徑、{nj} 個接點、{nl} 個網路標籤）")
    print(f"已產生 {PROJECT}.kicad_pro / incense.kicad_sym / sym-lib-table")
