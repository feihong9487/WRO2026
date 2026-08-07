#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧香爐 P0 — 元件佈局與佈線定義（★合併版・兩板架構★）
================================================================
2026-08-02 改版：拿掉獨立的 ESP32-S3 開發板，感測改由 MATRIX Mini R4
直接以 I2C 讀取。連帶消失的還有整條警報線與它的 10kΩ 下拉電阻——
感測與安全同在一顆 MCU 內，不需要跨板訊號。

與 產生電路圖.py 分離，方便單獨調整版面而不動產生邏輯。

佈線原則：
  * 訊號線實際畫出導線（含轉角），並在導線上標註網路名稱。
  * 電源網路（GND / +5V / +12V）用電源符號——GND 接點多，全部拉線會過於雜亂。
  * 元件由左至右擺放：感測器 → 控制器 → 致動器，訊號流向一致。

★腳位限制★
  MiniR4.begin() 內執行 PS2.config_gamepad(11, 4, 12, 5)，
  把 D2 埠(5,4) 與 D3 埠(12,11) 佔為手把介面，故本專案只用 D1 與 D4。
"""

# ── 電氣型別 ────────────────────────────────────────────────
PWR, POUT, BID, IN, OUT, PAS = (
    "power_in", "power_out", "bidirectional", "input", "output", "passive")

# ── 元件佈局 ────────────────────────────────────────────────
# 座標皆對齊 1.27mm 連接格點（產生器會檢查）
COMPONENTS = [
    # ── 感測層（左）──────────────────────────────────────
    # 以 Grove 線接控制器的 I2C 埠，一條線同時含 VCC/GND/SDA/SCL。
    # 圖上電源以符號表示，實體只有一條 4 芯線。
    dict(ref="U2", name="SCD41", value="SCD41 CO2 (0x62) - I2C1 埠",
         at=(57.15, 38.10), width=33.02,
         left=[("1", "VDD 5V", PWR, "+5V"), ("2", "GND", PWR, "GND")],
         right=[("3", "SDA", BID, "I2C1_SDA"), ("4", "SCL", BID, "I2C1_SCL")]),

    dict(ref="U3", name="SHT31", value="GY-SHT31-D (0x44) - I2C2 埠",
         at=(57.15, 71.12), width=33.02,
         left=[("1", "VIN 5V", PWR, "+5V"), ("2", "GND", PWR, "GND")],
         right=[("3", "SDA", BID, "I2C2_SDA"), ("4", "SCL", BID, "I2C2_SCL")]),

    # ── 控制器（中）：感測 ＋ 安全 ＋ 致動 ────────────────
    dict(ref="A1", name="MATRIX-Mini-R4", value="MATRIX Mini R4 控制器",
         at=(187.96, 60.96), width=55.88,
         left=[("1", "VIN 6-24V", PWR, "+12V"),
               ("2", "GND", PWR, "GND"),
               ("3", "I2C1 SDA", BID, "I2C1_SDA"),
               ("4", "I2C1 SCL", BID, "I2C1_SCL"),
               ("5", "I2C2 SDA", BID, "I2C2_SDA"),
               ("6", "I2C2 SCL", BID, "I2C2_SCL")],
         right=[("7", "5V OUT", POUT, "+5V"),
                ("8", "D4L p13 SCK", OUT, "TC_SCK"),
                ("9", "D4R p10 SO", IN, "TC_SO"),
                ("10", "D1R p2 CS", OUT, "TC_CS"),
                ("11", "D1L p3 PWM", OUT, "FAN_PWM"),
                ("12", "USB - Pi 5", BID, "USB_PI_R4")]),

    # ── 決策層（下）──────────────────────────────────────
    dict(ref="A2", name="RaspberryPi5", value="Raspberry Pi 5 決策層",
         at=(187.96, 138.43), width=48.26,
         left=[("1", "GND", PWR, "GND")],
         right=[("2", "USB - 控制器", BID, "USB_PI_R4")]),

    # ── 爐溫量測（右上）──────────────────────────────────
    dict(ref="U5", name="MAX6675", value="MAX6675 熱電偶介面",
         at=(325.12, 38.10), width=38.10,
         left=[("1", "VCC 5V", PWR, "+5V"),
               ("2", "GND", PWR, "GND"),
               ("3", "SCK", IN, "TC_SCK"),
               ("4", "CS", IN, "TC_CS"),
               ("5", "SO", OUT, "TC_SO")],
         right=[("6", "K+", PAS, "TC_KP"), ("7", "K-", PAS, "TC_KN")]),

    dict(ref="J1", name="Thermocouple-K", value="K型熱電偶",
         at=(400.05, 40.64), width=17.78,
         left=[("1", "K+", PAS, "TC_KP"), ("2", "K-", PAS, "TC_KN")],
         right=[]),

    # ── 風扇驅動（右下）──────────────────────────────────
    # 馬達埠是 5V，推不動 12V 風扇，故 D4184 必須保留
    dict(ref="U6", name="D4184-Module", value="D4184 MOSFET 模組",
         at=(325.12, 137.16), width=40.64,
         left=[("1", "TRIG (PWM)", IN, "FAN_PWM"),
               ("2", "訊號 GND", PWR, "GND"),
               ("3", "VIN+", PWR, "+12V"),
               ("4", "VIN-", PWR, "GND")],
         right=[("5", "OUT+", PAS, "FAN_P"), ("6", "OUT-", PAS, "FAN_N")]),

    dict(ref="M1", name="Fan-5015", value="5015 渦輪風扇 12V 0.2A",
         at=(400.05, 139.70), width=20.32,
         left=[("1", "紅線 +", PAS, "FAN_P"), ("2", "黑線 -", PAS, "FAN_N")],
         right=[]),

    # ── 理香機構與霧化（2026-08-07）────────────────────────
    # ★用 I²C 驅動板而不是 GPIO★ R4 的可用腳（D1/D4 共 4 腳）已全滿，
    #   D2/D3 被 MiniR4.begin() 的 PS2 佔走。而 0.5A 電磁鐵本來就要 MOSFET，
    #   驅動板無論如何都要買——選 I²C 版本同時解掉腳位，增量成本趨近於零。
    #   結構上還更好：互鎖變成「寫出去的位元組至多一個 bit 為 1」，
    #   單一地點可驗證；四支獨立 GPIO 反而可能不小心同時拉高兩支。
    dict(ref="U6", name="PCF8574-MOSFET", value="I2C 8路 MOSFET 驅動板",
         at=(325.12, 100.33), width=45.72,
         left=[("1", "VCC 5V", PWR, "+5V"), ("2", "GND", PWR, "GND"),
               ("3", "SDA", BID, "I2C1_SDA"), ("4", "SCL", BID, "I2C1_SCL"),
               ("5", "VIN+ 12V", PWR, "+12V")],
         right=[("6", "OUT1 電磁鐵1", OUT, "MAG1"), ("7", "OUT2 電磁鐵2", OUT, "MAG2"),
                ("8", "OUT3 電磁鐵3", OUT, "MAG3"), ("9", "OUT4 電磁鐵4", OUT, "MAG4"),
                ("10", "OUT5 霧化", OUT, "MIST"), ("11", "OUT6 罩內LED", OUT, "HOODLED")]),

    dict(ref="K1", name="Solenoid-Array", value="電磁鐵 ×4（理香，脈衝驅動）",
         at=(400.05, 95.25), width=30.48,
         left=[("1", "MAG1", IN, "MAG1"), ("2", "MAG2", IN, "MAG2"),
               ("3", "MAG3", IN, "MAG3"), ("4", "MAG4", IN, "MAG4")],
         right=[]),

    dict(ref="M2", name="Mist-Ultrasonic", value="超音波霧化模組 12V（冷霧，無明火）",
         at=(400.05, 121.92), width=30.48,
         left=[("1", "MIST", IN, "MIST"), ("2", "GND", PWR, "GND")],
         right=[]),

    # ── 電源（左下）：一顆 12V 同時餵控制器與風扇，共地自動成立 ──
    dict(ref="J2", name="PSU-12V", value="12V 3A 變壓器",
         at=(77.47, 138.43), width=30.48,
         left=[],
         right=[("1", "+12V", POUT, "+12V"), ("2", "0V", PWR, "GND")]),
]

# ── 電阻 ────────────────────────────────────────────────────
# 合併版不需要任何電阻：警報線消失，10kΩ 下拉隨之取消。
RESISTORS = []

# ── 佈線通道（避開元件本體的走線 x 座標；產生器會吸附到格點）──
CH = dict(
    i2c1_sda = 109.22,   # SCD41 → 控制器
    i2c1_scl = 116.84,
    i2c2_sda = 124.46,   # SHT31 → 控制器
    i2c2_scl = 132.08,
    fan_pwm  = 234.95,   # 控制器 → D4184
    usb      = 245.11,   # 控制器 → Pi 5
    tc_sck   = 257.81,   # 控制器 → MAX6675（三條 SPI 各走一條通道，避免交叉）
    tc_cs    = 269.24,
    tc_so    = 280.67,
    tc_kp    = 367.03,   # MAX6675 → 熱電偶
    tc_kn    = 372.11,
    fan_p    = 367.03,   # D4184 → 風扇
    fan_n    = 372.11,
)
