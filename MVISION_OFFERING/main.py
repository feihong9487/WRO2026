# main.py — M-Vision（OpenMV H7）供品與盤子辨識
#
# 場景：白色桌面、紅色圓盤（直徑約 15 公分）、綠色供品（像綠色乖乖）
# 任務：找出盤子位置，並找出「掉在盤子外面」的綠色供品，回報給 Mini R4
#
# ── 通訊 ────────────────────────────────────────────────────────
# UART3（P4 = TX、P5 = RX），鮑率 115200，接 Mini R4 的 UART 埠。
# 相機會每一幀主動送出一個封包，格式和 Matrix 程式庫 MiniR4.Vision 相同：
#   0xAA、數值個數 N、N 個 16 位元無號整數（低位元組在前）、XOR 檢查碼
#   檢查碼 = 0xAA ^ N ^ 所有資料位元組
#
# 封包內容（共 12 個數值）：
#   [0]  狀態旗標：bit0 = 有看到盤子，bit1 = 有要夾的供品
#   [1]  盤子中心 x      [2] 盤子中心 y
#   [3]  盤子寬          [4] 盤子高
#   [5]  目標供品中心 x  [6] 目標供品中心 y
#   [7]  目標供品寬      [8] 目標供品高
#   [9]  盤子外的供品數量
#   [10] 盤子上的供品數量
#   [11] 幀編號（每幀加一，Mini R4 可用來判斷資料有沒有在更新）
#   畫面是 320 x 240，座標原點在左上角。沒看到的欄位填 0。
#
# 拍照回傳（給監控網站看真的畫面）：
#   Mini R4 送一個字元 'S' 過來，相機就在下一幀拍一張 160 x 120 的 JPEG 回傳：
#   0xAB、0x4A、長度（16 位元，低位元組在前）、JPEG 資料、XOR 檢查碼（只算 JPEG 資料）
#   照片是在畫框框之前拍的，網站會自己疊上框框。
#   JPEG 分成 128 位元組一段送，中間停 15 ms，讓 R4 來得及收。
#
# ── 調整顏色門檻 ────────────────────────────────────────────────
# 在 OpenMV IDE 執行本腳本，用 Tools > Machine Vision > Threshold Editor
# 框選盤子和供品，把得到的 LAB 數值填進 RED_TH、GREEN_TH。
# 調好後用 Tools > Save open script to OpenMV Cam 存成 main.py，
# 相機接在 Mini R4 上時才會自己執行。

import sensor
import image
import time
import struct
from pyb import UART, LED

# ================= 通訊 =================
UART_BAUD = 115200
uart = UART(3, UART_BAUD, timeout_char=10)

# ================= 顏色門檻（LAB） =================
# 格式：(L 最小, L 最大, A 最小, A 最大, B 最小, B 最大)
# A 為正偏紅、為負偏綠；白色桌面的 A、B 都接近 0，所以不會被誤抓。
RED_TH   = (20, 90,  20, 127,   0, 127)   # 紅色盤子
GREEN_TH = (20, 90, -90, -15, -10,  70)   # 綠色乖乖

# ================= 大小門檻（像素數） =================
PLATE_MIN_PIXELS = 900    # 盤子最少要有這麼多紅色像素，太小的紅色（包裝上的字）會被忽略
GREEN_MIN_PIXELS = 120    # 供品最少像素，濾掉雜訊
PLATE_MARGIN     = 1.0    # 判斷「在盤子上」的半徑倍率，>1 放寬、<1 收緊

# ================= 鏡頭方向 =================
# 沿用舊腳本的設定。若在 IDE 裡看到畫面上下或左右顛倒，就改成 False。
FLIP_V = True
FLIP_H = True

DEBUG_PRINT = True

# ================= 拍照回傳 =================
SNAP_MAX_BYTES = 2900         # R4 的接收緩衝區是 3000 位元組，照片不能超過
SNAP_QUALITIES = (45, 30, 18) # 太大就降畫質重壓
SNAP_CHUNK = 128
SNAP_GAP_MS = 15
snap_req = False

# ================= 相機初始化 =================
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QVGA)          # 320 x 240
sensor.set_vflip(FLIP_V)
sensor.set_hmirror(FLIP_H)
sensor.skip_frames(time=2000)              # 等曝光穩定
sensor.set_auto_gain(False)                # 顏色追蹤一定要關自動增益
sensor.set_auto_whitebal(False)            # 和自動白平衡，否則顏色會飄

clock = time.clock()
led_green = LED(2)
frame = 0


def find_plate(img):
    """回傳面積最大的紅色色塊，當作盤子。找不到回傳 None。"""
    blobs = img.find_blobs([RED_TH],
                           pixels_threshold=PLATE_MIN_PIXELS,
                           area_threshold=PLATE_MIN_PIXELS,
                           merge=True, margin=10)
    if not blobs:
        return None
    return max(blobs, key=lambda b: b.pixels())


def plate_radius(plate):
    return max(plate.w(), plate.h()) / 2 * PLATE_MARGIN


def is_on_plate(blob, plate):
    """供品中心落在盤子的圓內就算在盤子上。"""
    if plate is None:
        return False
    r = plate_radius(plate)
    dx = blob.cx() - plate.cx()
    dy = blob.cy() - plate.cy()
    return dx * dx + dy * dy <= r * r


def send_packet(values):
    """用 Matrix 的 0xAA 封包格式送出一串 16 位元數值。"""
    vals = [int(v) & 0xFFFF for v in values]
    payload = struct.pack("<%dH" % len(vals), *vals)
    chk = 0xAA ^ len(vals)
    for b in payload:
        chk ^= b
    uart.write(bytes([0xAA, len(vals)]) + payload + bytes([chk & 0xFF]))


def check_request():
    """R4 送 'S' 表示要一張照片。"""
    global snap_req
    n = uart.any()
    if n:
        data = uart.read(n)
        if data and b"S" in data:
            snap_req = True


def make_jpeg(img):
    """縮成 160 x 120 再壓成 JPEG，太大就降畫質。回傳 bytes 或 None。"""
    for q in SNAP_QUALITIES:
        small = img.copy(x_scale=0.5, y_scale=0.5)
        try:
            jpg = small.compress(quality=q)
        except AttributeError:            # 新版韌體改名
            jpg = small.to_jpeg(quality=q)
        data = bytes(jpg.bytearray())
        if len(data) <= SNAP_MAX_BYTES:
            return data
    return None


def send_jpeg(data):
    chk = 0
    for b in data:
        chk ^= b
    n = len(data)
    uart.write(bytes([0xAB, 0x4A, n & 0xFF, n >> 8]))
    for i in range(0, n, SNAP_CHUNK):
        uart.write(data[i:i + SNAP_CHUNK])
        time.sleep_ms(SNAP_GAP_MS)
    uart.write(bytes([chk & 0xFF]))


while True:
    clock.tick()
    img = sensor.snapshot()
    check_request()
    photo = None
    if snap_req:                          # 在畫框框之前先拍下來
        snap_req = False
        photo = make_jpeg(img)

    # ---- 盤子 ----
    plate = find_plate(img)

    # ---- 供品 ----
    greens = img.find_blobs([GREEN_TH],
                            pixels_threshold=GREEN_MIN_PIXELS,
                            area_threshold=GREEN_MIN_PIXELS,
                            merge=True, margin=5)

    outside = []
    n_on = 0
    for g in greens:
        if is_on_plate(g, plate):
            n_on += 1
            img.draw_rectangle(g.rect(), color=(0, 0, 255), thickness=2)   # 藍框：已在盤上
        else:
            outside.append(g)
            img.draw_rectangle(g.rect(), color=(0, 255, 0), thickness=2)   # 綠框：掉在外面

    # 盤子外面最大的那個，通常也是最靠近鏡頭的，就當作這次要夾的目標
    target = max(outside, key=lambda b: b.pixels()) if outside else None

    # ---- 組封包 ----
    flags = 0
    px = py = pw = ph = 0
    tx = ty = tw = th = 0

    if plate:
        flags |= 1
        px, py, pw, ph = plate.cx(), plate.cy(), plate.w(), plate.h()
        img.draw_circle(px, py, int(plate_radius(plate)), color=(255, 0, 0), thickness=2)

    if target:
        flags |= 2
        tx, ty, tw, th = target.cx(), target.cy(), target.w(), target.h()
        img.draw_cross(tx, ty, color=(255, 255, 0), size=10, thickness=2)
        led_green.on()
    else:
        led_green.off()

    send_packet([flags, px, py, pw, ph, tx, ty, tw, th, len(outside), n_on, frame])
    frame = (frame + 1) & 0xFFFF
    if photo:
        send_jpeg(photo)

    img.draw_string(4, 4, "out:%d on:%d" % (len(outside), n_on), color=(255, 0, 255), scale=2)

    if DEBUG_PRINT:
        print("plate:%s (%d,%d %dx%d)  target:%s (%d,%d %dx%d)  out:%d on:%d  fps:%.1f" % (
            "Y" if plate else "N", px, py, pw, ph,
            "Y" if target else "N", tx, ty, tw, th,
            len(outside), n_on, clock.fps()))
