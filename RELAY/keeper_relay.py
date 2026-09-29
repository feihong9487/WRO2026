#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
keeper_relay.py — 廟公機器人的筆電中繼程式（接替原本 Pi 5 的工作）

資料流：
  R4 ──WiFi TCP──▶ 筆電（本程式）──Tailscale MQTT──▶ 桌機 mosquitto → Telegraf → InfluxDB → Grafana

做四件事：
  1. 每秒用 UDP 廣播自己的位址，R4 自己找過來，不用寫死筆電的 IP。
  2. 接收 R4 的資料：{JSON} 每秒遙測、V{JSON} 相機結果、# 紀錄訊息。
  3. 跑原 pi_fsm.py 的風扇決策（S0/S1/S2/S3），每秒把 FAN 指令送回 R4。
     安全聯鎖仍由 R4 就地執行；筆電斷線 5 秒後，R4 自動改用它自己的本地 FSM。
  4. 轉成儀表板認得的格式，送上桌機：
       incense/<裝置>/sensor    與原 Pi 相同的感測欄位，加上原本漏送的 co2_base、fan_rpm、
                               tc_fault、sensor_fault，以及機器人的數值欄位（香灰、電池、訊號）
       incense/<裝置>/decision  與原 Pi 相同的決策紀錄
       incense/<裝置>/robot     機器人狀態文字（任務、路段、站點），給之後的自製面板用
       incense/<裝置>/vision    相機框框，每秒 5 筆，給監控網站用
       incense/<裝置>/event     R4 的紀錄訊息與連線事件，給監控網站的事件紀錄用
       incense/<裝置>/ack       遠端指令的處理結果
       incense/<裝置>/photo     M-Vision 照片（160 × 120 JPEG，靜止時約每 2 秒一張）
     桌機的 Telegraf 只收 sensor 與 decision，其餘主題不影響現有儀表板。
  5. 訂閱 incense/<裝置>/cmd，把監控網站的指令轉給 R4。只接受固定幾種指令，
     超過 30 秒才送到的指令不執行。R4 自己還會再檢查一次狀態與電池。

雲端斷線時只補送 10 秒內的資料。Telegraf 用「收到的時間」當資料時間，
補送太舊的資料會被畫在錯的時間點。完整紀錄都在 logs 資料夾裡。

使用前：
  把桌機 mosquitto 的 burner 帳號密碼填進同資料夾的 relay_secrets.json。
  這個檔案不要傳到 GitHub。沒填密碼時，只做本機中繼與風扇決策，不上雲。

用法：
  python keeper_relay.py                 一般使用
  python keeper_relay.py --no-cloud      不上雲
  python keeper_relay.py --no-fan        不送風扇指令，讓 R4 用自己的本地 FSM
  執行中可以直接打字送指令給 R4：
    STOP      中止任務並停車
    FAN 120   手動指定風扇（R4 的安全聯鎖與 CO2 警報仍然優先）
    AUTO      回到自動決策

只用 Python 標準函式庫，不需要安裝任何套件。按 Ctrl+C 結束。
第一次執行時如果 Windows 防火牆詢問，要允許 Python 在「公用網路」連線，否則 R4 連不進來。
"""

import argparse
import base64
import json
import os
import re
import select
import socket
import struct
import sys
import threading
import time
from collections import deque
from datetime import datetime

BEACON_TAG = "WRO2026-RELAY"
DEFAULT_MQTT_HOST = "100.73.36.75"     # 桌機的 Tailscale IP
DEFAULT_DEVICE = "aroma01"

# ---- 決策門檻：與 pi_fsm.py、R4 韌體同一套，改門檻要三處一起改 ----
CO2_IDLE_DELTA = 50
T1_DELTA = 300
T1_EXIT_DELTA = 200
BASELINE_WINDOW_MIN = 10
CO2_BASELINE_INIT = 450
SLOPE_TH = 120.0
IDLE_HOLD_S = 60
SENSOR_STALE_S = 10
DUTY = {"S0": 0, "S1": 70, "S2": 220, "S3": 0}   # 0-255

R4_SILENT_S = 10          # R4 這麼久沒送任何資料就斷開，讓它重新找筆電
CMD_MAX_AGE_S = 30        # 監控網站送來的指令超過這麼久才收到就不執行，避免延遲的「開始任務」突然讓車子動起來
# 監控網站可以送的指令。其他一律拒絕
CMD_PATTERN = re.compile(r"^(STOP|GO|END|CLEAR|AUTO|RUN (MORNING|EVENING|[A-E])|FAN \d{1,3})$")
CLOUD_MAX_AGE_S = 10      # 雲端斷線時暫存的資料，超過這麼久就不補送
VISION_MAX_AGE_S = 1

# 原 Pi 轉發的感測欄位
SENSOR_KEYS = ("ts", "co2", "slope", "t_scd", "rh_scd", "t_sht", "rh_sht", "t_ds", "conf", "alarm")
# 原 Pi 漏送、這版補上的 R4 欄位
EXTRA_KEYS = ("co2_base", "fan_rpm", "tc_fault", "sensor_fault")
# 機器人的數值欄位。ash_pct = -1、batt = -99.9 表示沒有資料，就不送
ROBOT_NUM_KEYS = ("ash_pct", "ash_cool", "batt", "rssi", "net_drop", "step")
ROBOT_STR_KEYS = ("robot", "mission", "leg", "station", "fail")

HERE = os.path.dirname(os.path.abspath(__file__))


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def say(msg):
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════
# UDP 廣播位址（與 WIFI_SPEED_TEST/speed_server.py 相同）
# ═══════════════════════════════════════════════════════════════════
def local_ipv4():
    """列出本機可用的 IPv4 位址，排除本機迴路、自動私有位址與 Tailscale。"""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        # 對外連 UDP 不會真的送出封包，只是讓系統告訴我們預設網卡的位址
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith(("127.", "169.254.", "100.")))


def beacon(tcp_port, beacon_port, stop):
    """在每張網卡上各自廣播。每 5 秒重新偵測網卡，換熱點、IP 變了也會自動跟上。"""
    msg = f"{BEACON_TAG} {tcp_port}".encode()
    socks = {}
    last_scan = 0.0
    while not stop.is_set():
        if time.monotonic() - last_scan > 5:
            last_scan = time.monotonic()
            now = set(local_ipv4())
            for ip in list(socks):
                if ip not in now:
                    socks.pop(ip).close()
                    say(f"網卡 {ip} 已消失，停止在它上面廣播")
            for ip in now - set(socks):
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    s.bind((ip, 0))
                    socks[ip] = s
                    say(f"開始在 {ip} 上廣播位址")
                except OSError as e:
                    say(f"無法在 {ip} 上廣播：{e}")
        for s in list(socks.values()):
            try:
                s.sendto(msg, ("255.255.255.255", beacon_port))
            except OSError:
                pass
        stop.wait(1.0)


# ═══════════════════════════════════════════════════════════════════
# 極簡 MQTT 3.1.1 發布端（QoS 0）
# ═══════════════════════════════════════════════════════════════════
CONNACK_RC = {
    1: "伺服器不支援這個 MQTT 版本",
    2: "用戶端代號被拒絕",
    3: "伺服器暫時無法服務",
    4: "帳號或密碼錯誤",
    5: "沒有權限（通常是沒填帳號密碼）",
}


def _varlen(n):
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n:
            b |= 0x80
        out.append(b)
        if not n:
            return bytes(out)


def _str(s):
    b = s.encode("utf-8")
    return struct.pack("!H", len(b)) + b


def _packet(ptype, body):
    return bytes([ptype]) + _varlen(len(body)) + body


def _recv_exact(s, n):
    buf = b""
    while len(buf) < n:
        d = s.recv(n - len(buf))
        if not d:
            raise ConnectionError("伺服器關閉連線")
        buf += d
    return buf


class Cloud:
    """斷線自動重連。斷線期間的訊息先暫存，超過期限的就不補送。
    subscribe_fn() 回傳要訂閱的主題清單，收到訊息時呼叫 on_message(主題, 位元組, 是否為保留訊息)。"""

    def __init__(self, host, port, user, password, client_id, keepalive=30,
                 subscribe_fn=None, on_message=None):
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.client_id = client_id
        self.keepalive = keepalive
        self.subscribe_fn = subscribe_fn
        self.on_message = on_message
        self.q = deque(maxlen=400)
        self.cv = threading.Condition()
        self.state = "連線中"
        self.sent = 0
        self.expired = 0
        threading.Thread(target=self._run, daemon=True).start()

    def publish(self, topic, obj, max_age=CLOUD_MAX_AGE_S):
        payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with self.cv:
            self.q.append((time.monotonic() + max_age, topic, payload))
            self.cv.notify()

    def _set_state(self, st):
        if st != self.state:
            self.state = st
            say("雲端：" + st)

    def _connect(self):
        s = socket.create_connection((self.host, self.port), timeout=5)
        try:
            flags = 0x02                       # clean session
            tail = _str(self.client_id)
            if self.user:
                flags |= 0x80
                tail += _str(self.user)
            if self.password:
                flags |= 0x40
                tail += _str(self.password)
            body = _str("MQTT") + bytes([4, flags]) + struct.pack("!H", self.keepalive) + tail
            s.sendall(_packet(0x10, body))
            ack = _recv_exact(s, 4)
            if ack[0] != 0x20:
                raise ConnectionError("伺服器回應的格式不對")
            if ack[3]:
                raise PermissionError(CONNACK_RC.get(ack[3], f"代碼 {ack[3]}"))
            s.settimeout(5)
            return s
        except BaseException:
            s.close()
            raise

    def _run(self):
        backoff = 2
        while True:
            try:
                s = self._connect()
            except PermissionError as e:
                self._set_state(f"登入被拒絕：{e}，30 秒後重試")
                time.sleep(30)
                continue
            except OSError as e:
                self._set_state(f"連不上 {self.host}:{self.port}（{e}），重試中")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            backoff = 2
            self._set_state(f"已連上 {self.host}:{self.port}")
            try:
                self._serve(s)
            except (OSError, ConnectionError) as e:
                self._set_state(f"斷線（{e}），重連中")
            finally:
                s.close()

    def _subscribe(self, s):
        topics = self.subscribe_fn() if self.subscribe_fn else []
        if not topics:
            return
        body = struct.pack("!H", 1) + b"".join(_str(t) + b"\x00" for t in topics)   # QoS 0
        s.sendall(_packet(0x82, body))

    def _parse(self, buf):
        """從收到的位元組切出完整封包，處理 PUBLISH，其餘（心跳回應、訂閱確認）略過。"""
        while len(buf) >= 2:
            mult, n, i = 1, 0, 1
            while True:
                if i >= len(buf):
                    return
                b = buf[i]
                n += (b & 0x7F) * mult
                mult *= 128
                i += 1
                if not b & 0x80:
                    break
            if len(buf) < i + n:
                return
            ptype, body = buf[0], bytes(buf[i:i + n])
            del buf[:i + n]
            if ptype >> 4 == 3 and self.on_message:
                qos = (ptype >> 1) & 3
                tl = struct.unpack("!H", body[:2])[0]
                topic = body[2:2 + tl].decode("utf-8", "replace")
                payload = body[2 + tl + (2 if qos else 0):]
                try:
                    self.on_message(topic, payload, bool(ptype & 1))
                except Exception as e:
                    say(f"處理雲端訊息出錯：{e}")

    def _serve(self, s):
        self._subscribe(s)
        rx = bytearray()
        last_ping = time.monotonic()
        ping_wait = None                        # 送出心跳、還沒等到回應的時間
        while True:
            with self.cv:
                if not self.q:
                    self.cv.wait(0.1)           # 短一點，雲端送來的 STOP 才不會被延遲
                item = self.q.popleft() if self.q else None
            now = time.monotonic()
            if item:
                deadline, topic, payload = item
                if now > deadline:
                    self.expired += 1
                else:
                    try:
                        s.sendall(_packet(0x30, _str(topic) + payload))
                    except OSError:
                        with self.cv:
                            self.q.appendleft(item)
                        raise
                    self.sent += 1
            # QoS 0 發布時伺服器不回任何東西，所以固定送心跳，靠回應判斷線路是否還活著
            if now - last_ping > self.keepalive / 2:
                s.sendall(b"\xc0\x00")
                last_ping = now
                if ping_wait is None:
                    ping_wait = now
            r, _, _ = select.select([s], [], [], 0)
            if r:
                data = s.recv(4096)
                if not data:
                    raise ConnectionError("伺服器關閉連線")
                ping_wait = None
                rx += data
                self._parse(rx)
            if ping_wait is not None and now - ping_wait > 10:
                raise ConnectionError("伺服器沒有回應心跳")


class NoCloud:
    state = "未啟用"
    sent = 0

    def publish(self, *a, **k):
        pass


# ═══════════════════════════════════════════════════════════════════
# AI 影子建議：原 pi_fsm.py 的 ShadowAdvisor，程式逐行沿用
# B 案（日曆負載預測＋電量預算 DP 排程）。只算「AI 會建議多少 duty」寫進決策紀錄的 ai_duty，
# 完全不影響送給 R4 的實際風扇指令。模型檔 ai_predictor.json 與 PI5/ai_predictor.json 相同，
# 檔案不存在或壞掉時自動停用（ai_duty 不送）。
# ═══════════════════════════════════════════════════════════════════
import math as _math
import os as _os

AI_ACTIONS = (0, 70, 220, 255)
AI_BUDGET_WH = 4.0          # 與訓練情境一致（D40；耗盡假設見 AI訓練/README）
AI_FAN_P_MAX = 1.0          # SUNON 4020 家族典型（EST）


class ShadowAdvisor:
    _SYN = 29.530588
    _EPOCH = 947182440.0    # 2000-01-06 18:14 UTC（朔）近似

    def __init__(self, path):
        self.w = None
        try:
            with open(path, encoding="utf-8") as f:
                self.w = json.load(f)["w"]
        except Exception:
            return                       # 無模型 → 停用
        self._sched, self._slot = None, -1
        self._spent_wh, self._spent_day = 0.0, None

    @staticmethod
    def _feats(hour, ld, dow, is_open):
        morning = _math.exp(-((hour - 8.0) ** 2) / 8.0)
        evening = _math.exp(-((hour - 17.0) ** 2) / 12.5)
        lp = 1.0 if (ld < 1.0 or 14.0 <= ld < 15.5) else 0.0
        we = 1.0 if dow >= 5 else 0.0
        return [1.0, _math.sin(2 * _math.pi * hour / 24.0),
                _math.cos(2 * _math.pi * hour / 24.0),
                morning, evening, lp, we, is_open,
                is_open * morning * lp, is_open * evening * lp,
                is_open * we, is_open * lp]

    def _load_hat(self, hour, ld, dow):
        is_open = 1.0 if 6 <= hour < 21 else 0.0
        f = self._feats(hour, ld, dow, is_open)
        return max(0.0, sum(a * b for a, b in zip(self.w, f)))

    def suggest(self, co2, now, base=480.0):
        """base＝FSM 的滾動 CO2 基線（2026-08-21 修正：nowcast 原用固定
        480，在背景漂移的場域會把「持續偏高的背景」誤讀成負載——與
        FSM 門檻同尺（相對基線）後，影子建議與 FSM 的分歧只剩真實的
        決策差異。模擬端 policies.py 與凍結評比不動。"""
        if self.w is None:
            return None
        if self._spent_day != now.date():
            self._spent_day, self._spent_wh = now.date(), 0.0
        ld = ((now.timestamp() - self._EPOCH) / 86400.0) % self._SYN
        dow = now.weekday()
        hour = now.hour
        slot = (now.hour * 2) + (1 if now.minute >= 30 else 0)
        if self._sched is None or slot != self._slot:
            budget = max(0.0, AI_BUDGET_WH - self._spent_wh)
            nb = int(budget / 0.05) + 1
            dp = [(0.0, [])] * nb
            for h in range(23, hour - 1, -1):
                nhat = self._load_hat(h, ld, dow)
                if h == hour and co2:            # nowcast 混入當前時段
                    nhat = max(nhat, (co2 - base) / 26.0)
                if nhat < 0.3:
                    nhat = 0.0           # 微弱預測視為無負載（防雜訊倒預算）
                opts = [(d, int(round(AI_FAN_P_MAX * (d / 255.0) ** 3 / 0.05)),
                         (d / 255.0) * nhat) for d in AI_ACTIONS]
                ndp = [None] * nb
                for b in range(nb):
                    best = (-1.0, 0, [])
                    for d, c, ben in opts:
                        if c <= b:
                            v, ch = dp[b - c]
                            if ben + v > best[0]:
                                best = (ben + v, d, ch)
                    ndp[b] = (best[0], [best[1]] + best[2])
                dp = ndp
            self._sched = {h: d for h, d in
                           zip(range(hour, 24), dp[nb - 1][1])}
            self._slot = slot
        d = self._sched.get(hour, 0)
        self._spent_wh += AI_FAN_P_MAX * (d / 255.0) ** 3 / 3600.0
        return d




# ═══════════════════════════════════════════════════════════════════
# 風扇決策：原 pi_fsm.py 的狀態機，邏輯逐行沿用
# ═══════════════════════════════════════════════════════════════════
class Fsm:
    def __init__(self):
        self.state = "S1"
        self.idle_since = None
        self.buckets = [None] * BASELINE_WINDOW_MIN
        self.idx = 0
        self.bmin = None
        self.bstart = time.monotonic()

    def _baseline_update(self, v):
        """每分鐘記一個「該分鐘的最小值」，滾動保留 BASELINE_WINDOW_MIN 個。"""
        if not v:
            return
        self.bmin = v if self.bmin is None else min(self.bmin, v)
        if time.monotonic() - self.bstart >= 60:
            self.buckets[self.idx] = self.bmin
            self.idx = (self.idx + 1) % BASELINE_WINDOW_MIN
            self.bmin = None
            self.bstart = time.monotonic()

    def baseline(self):
        vals = [b for b in self.buckets if b is not None]
        if vals:
            return min(vals)
        return self.bmin if self.bmin is not None else CO2_BASELINE_INIT

    def step(self, s):
        co2 = s.get("co2", 0) or 0
        self._baseline_update(co2)
        slope = s.get("slope", 0.0) or 0.0
        action = ""
        # 資料新舊由呼叫端把關（太舊就不會呼叫），這裡只看 R4 自己回報的感測故障
        stale = bool(s.get("sensor_fault"))
        anomaly = bool(s.get("interlock") or s.get("tc_fault"))

        prev = self.state
        if anomaly:
            self.state = "S3"                   # 安全事件 R4 已就地處置，這裡記錄狀態
        elif self.state == "S3":
            self.state = "S1"
            action = "ANOMALY_CLEARED"
        elif stale:
            self.state = "S1"
            action = "SENSOR_STALE"
        else:
            base = self.baseline()
            th_s2, th_s2ex = base + T1_DELTA, base + T1_EXIT_DELTA
            th_idle = base + CO2_IDLE_DELTA
            if self.state in ("S0", "S1") and (co2 > th_s2 or slope > SLOPE_TH):
                self.state = "S2"
            elif self.state == "S2" and co2 < th_s2ex and slope < SLOPE_TH / 2:
                self.state = "S1"
            elif self.state == "S1" and co2 and co2 < th_idle:
                if self.idle_since is None:
                    self.idle_since = time.monotonic()
                elif time.monotonic() - self.idle_since > IDLE_HOLD_S:
                    self.state = "S0"
            if co2 >= th_idle:
                self.idle_since = None
                if self.state == "S0":
                    self.state = "S1"

        if self.state != prev and not action:
            action = f"{prev}->{self.state}"
        return co2, slope, action


# ═══════════════════════════════════════════════════════════════════
# R4 連線（TCP 伺服端，一次只接一台，新連線會取代舊的）
# ═══════════════════════════════════════════════════════════════════
class R4Link:
    def __init__(self, on_line, on_event=None):
        self.on_line = on_line
        self.on_event = on_event
        self.sock = None
        self.addr = None
        self.lock = threading.Lock()

    def connected(self):
        return self.sock is not None

    def send(self, text):
        with self.lock:
            s = self.sock
        if s is None:
            return False
        try:
            s.sendall((text + "\n").encode())
            return True
        except OSError as e:
            self._close(s, f"送出失敗：{e}")
            return False

    def serve(self, host, port, stop):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(2)
        srv.settimeout(1.0)
        while not stop.is_set():
            try:
                s, addr = srv.accept()
            except socket.timeout:
                continue
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self._handle, args=(s, addr), daemon=True).start()
        srv.close()

    def _handle(self, s, addr):
        with self.lock:
            old, self.sock, self.addr = self.sock, s, addr
        if old is not None:
            say("新的 R4 連線取代舊的連線")
            try:
                old.close()
            except OSError:
                pass
        say(f"R4 已連線：{addr[0]}")
        s.settimeout(R4_SILENT_S)
        buf = bytearray()
        why = "未知原因"
        try:
            while True:
                data = s.recv(4096)
                if not data:
                    raise ConnectionError("R4 關閉連線")
                buf += data
                while b"\n" in buf:
                    i = buf.index(b"\n")
                    line = bytes(buf[:i]).decode("utf-8", "replace").strip()
                    del buf[: i + 1]
                    if line:
                        try:
                            self.on_line(line)
                        except Exception as e:           # 一行壞掉不影響連線
                            say(f"處理資料出錯：{e}：{line[:80]}")
                if len(buf) > 8192:                      # 沒有換行的垃圾資料
                    buf.clear()
        except socket.timeout:
            why = f"R4 超過 {R4_SILENT_S} 秒沒送資料"
        except (ConnectionError, OSError) as e:
            why = str(e)
        self._close(s, why)

    def _close(self, s, why):
        with self.lock:
            mine = self.sock is s
            if mine:
                self.sock = None
        try:
            s.close()
        except OSError:
            pass
        if mine:
            say(f"R4 斷線：{why}")
            if self.on_event:
                self.on_event(f"R4 與筆電中繼斷線：{why}")


# ═══════════════════════════════════════════════════════════════════
# 中繼本體
# ═══════════════════════════════════════════════════════════════════
class Relay:
    def __init__(self, args, cloud):
        self.args = args
        self.cloud = cloud
        self.fsm = Fsm()
        self.advisor = ShadowAdvisor(os.path.join(HERE, "ai_predictor.json"))
        say("AI 影子建議：" + ("已載入模型" if self.advisor.w is not None else "找不到 ai_predictor.json，停用"))
        self.r4 = R4Link(self.on_line, lambda m: self.event(m, "relay"))
        self.lock = threading.Lock()
        self.tele, self.tele_t = {}, 0.0
        self.vis, self.vis_t = {}, 0.0
        self.device = args.device or DEFAULT_DEVICE
        self.device_fixed = bool(args.device)
        self.manual = None                 # 手動風扇值，None = 自動
        self.last_wait_msg = 0.0
        self.pending = {}                  # 已轉給 R4、等它回覆的指令：指令 → (編號, 送出者)
        self.photo_seq, self.photo_parts, self.photo_n = None, {}, 0
        self.photos = 0

        os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.dec_log = open(os.path.join(HERE, "logs", f"decision_{stamp}.jsonl"), "a",
                            encoding="utf-8", buffering=1)
        self.raw_log = open(os.path.join(HERE, "logs", f"raw_{stamp}.jsonl"), "a",
                            encoding="utf-8", buffering=1)

    def topic(self, kind):
        return f"incense/{self.device}/{kind}"

    def _set_device(self, dev):
        if dev and not self.device_fixed and dev != self.device:
            say(f"裝置代號改為 R4 回報的 {dev}")
            self.device = dev

    def _raw(self, line):
        self.raw_log.write(json.dumps({"t": now_iso(), "line": line}, ensure_ascii=False) + "\n")

    # ---- 收到 R4 的一行 ----
    def on_line(self, line):
        if line.startswith("{"):
            d = json.loads(line)
            with self.lock:
                self.tele, self.tele_t = d, time.monotonic()
            self._raw(line)
            self._set_device(d.get("dev"))
            self.publish_telemetry(d)
        elif line.startswith("V{"):
            v = json.loads(line[1:])
            with self.lock:
                self.vis, self.vis_t = v, time.monotonic()
            if self.args.log_vision:
                self._raw(line)
            self.cloud.publish(self.topic("vision"), v, max_age=VISION_MAX_AGE_S)
        elif line.startswith("#"):
            msg = line[1:].strip()
            self._raw(line)
            if msg.startswith("HELLO"):
                parts = msg.split()
                if len(parts) > 1:
                    self._set_device(parts[1])
                say(f"R4 報到：{msg}")
                self.event("R4 連上筆電中繼", "relay")
            else:
                say("R4> " + msg)
                self.event(msg, "r4")
        elif line.startswith("J"):
            self.on_photo_part(line)
        elif line.startswith("A{"):
            a = json.loads(line[1:])
            self._raw(line)
            cmd = a.get("cmd", "")
            with self.lock:
                cid, by = self.pending.pop(cmd, (None, None))
            say(f"R4 回覆 {cmd}：{'成功' if a.get('ok') else '拒絕'}，{a.get('why', '')}")
            self.ack(cid, cmd, bool(a.get("ok")), a.get("why", ""), "r4", by)
        else:
            say("收到無法辨識的內容：" + line[:80])

    # ---- M-Vision 照片：R4 分段送來 J<序號>,<第幾段>,<總段數>,<base64>，收齊再上傳 ----
    def on_photo_part(self, line):
        parts = line[1:].split(",", 3)
        if len(parts) != 4:
            return
        try:
            seq, i, n = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return
        if seq != self.photo_seq:                 # 新的一張：丟掉沒收齊的上一張
            self.photo_seq, self.photo_parts, self.photo_n = seq, {}, n
        self.photo_parts[i] = parts[3]
        if len(self.photo_parts) < self.photo_n or not all(k in self.photo_parts for k in range(self.photo_n)):
            return
        try:
            jpg = base64.b64decode("".join(self.photo_parts[k] for k in range(self.photo_n)))
        except ValueError:
            jpg = b""
        self.photo_parts = {}
        if jpg[:2] != bytes((0xFF, 0xD8)):          # JPEG 開頭
            say("收到壞掉的照片，略過")
            return
        self.photos += 1
        self.cloud.publish(self.topic("photo"), {"ts": now_iso(), "seq": seq, "w": 160, "h": 120,
                                                 "jpg": base64.b64encode(jpg).decode("ascii")}, max_age=3)
        try:
            with open(os.path.join(HERE, "logs", "photo_latest.jpg"), "wb") as f:
                f.write(jpg)                      # 最新一張留在本機，除錯用
        except OSError:
            pass

    # ---- 送給監控網站的事件與指令回覆 ----
    def event(self, msg, src):
        self.cloud.publish(self.topic("event"), {"ts": now_iso(), "src": src, "msg": msg})

    def ack(self, cid, cmd, ok, why, stage, by=None):
        self.cloud.publish(self.topic("ack"), {"ts": now_iso(), "id": cid, "cmd": cmd, "ok": ok,
                                               "why": why, "stage": stage, "by": by})

    # ---- 監控網站送來的指令（MQTT incense/<裝置>/cmd）----
    def subscriptions(self):
        return ["incense/+/cmd"]

    def on_cloud_message(self, topic, payload, retained):
        parts = topic.split("/")
        if len(parts) != 3 or parts[2] != "cmd" or parts[1] != self.device:
            return
        if retained:
            return                                   # 保留訊息是舊的指令，不執行
        try:
            d = json.loads(payload.decode("utf-8"))
            cmd = str(d.get("cmd", "")).strip().upper()
            cid, by, t = d.get("id"), d.get("by"), float(d.get("t", 0))
        except (ValueError, AttributeError, TypeError):
            say("收到格式錯誤的遠端指令，略過")
            return
        if not CMD_PATTERN.match(cmd):
            self.ack(cid, cmd, False, "中繼不接受這個指令", "relay", by)
            return
        if abs(time.time() - t) > CMD_MAX_AGE_S:
            self.ack(cid, cmd, False, f"指令超過 {CMD_MAX_AGE_S} 秒才送到，不執行", "relay", by)
            say(f"遠端指令 {cmd} 已過期，不執行")
            return
        say(f"遠端指令（{by or '?'}）：{cmd}")
        self.event(f"{by or '團隊'} 送出遠端指令 {cmd}", "web")
        if cmd == "AUTO":
            self.manual = None
            self.ack(cid, cmd, True, "風扇回到自動決策", "relay", by)
            return
        if cmd.startswith("FAN "):
            self.manual = max(0, min(255, int(cmd[4:])))
            self.ack(cid, cmd, True, f"風扇手動 {self.manual}", "relay", by)
            return
        with self.lock:
            self.pending[cmd] = (cid, by)
        if self.r4.send(cmd):
            self.ack(cid, cmd, True, "已轉給 R4", "relay", by)
        else:
            with self.lock:
                self.pending.pop(cmd, None)
            self.ack(cid, cmd, False, "R4 沒有連上筆電中繼", "relay", by)

    def publish_telemetry(self, d):
        sensor = {k: d[k] for k in SENSOR_KEYS + EXTRA_KEYS if k in d}
        for k in ROBOT_NUM_KEYS:
            v = d.get(k)
            if not isinstance(v, (int, float)) or v <= -99 or (k == "ash_pct" and v < 0):
                continue
            sensor[k] = v
        self.cloud.publish(self.topic("sensor"), sensor)
        robot = {k: d.get(k, "") for k in ROBOT_STR_KEYS}
        robot.update({k: d[k] for k in ("step", "ash_pct", "ash_cool", "batt", "mode", "local_state") if k in d})
        robot["ts"] = now_iso()
        self.cloud.publish(self.topic("robot"), robot)

    # ---- 每秒一次：決策、送風扇指令、上雲、印狀態 ----
    def tick(self):
        with self.lock:
            s = dict(self.tele)
            age = time.monotonic() - self.tele_t if self.tele_t else 1e9
            v = dict(self.vis)
            vage = time.monotonic() - self.vis_t if self.vis_t else 1e9

        if not self.r4.connected() or age > SENSOR_STALE_S:
            if time.monotonic() - self.last_wait_msg > 10:
                self.last_wait_msg = time.monotonic()
                ips = "、".join(local_ipv4()) or "找不到網卡"
                say(f"等待 R4 連線（筆電 {ips}，TCP {self.args.port}）｜雲端：{self.cloud.state}")
            return

        co2, slope, action = self.fsm.step(s)
        state = self.fsm.state
        duty = DUTY[state]
        if self.manual is not None:
            duty = self.manual
            action = (action + " MANUAL").strip()
        if not self.args.no_fan:
            if not self.r4.send(f"FAN {duty}"):
                action = (action + " SEND_ERR").strip()

        # AI 影子建議（只記錄、絕不影響上面已送出的實際 duty）
        try:
            ai_duty = self.advisor.suggest(co2, datetime.now(), base=float(self.fsm.baseline()))
        except Exception:
            ai_duty = None

        rec = {
            "ts": now_iso(),
            "co2": co2,
            "slope": round(slope, 1),
            "t_sht": s.get("t_sht"),
            "rh_sht": s.get("rh_sht"),
            "conf": s.get("conf"),
            "s3_alarm": s.get("alarm"),
            "t_furnace": s.get("t_furnace"),
            "fan_actual": s.get("fan"),
            "r4_mode": s.get("mode"),
            "interlock": s.get("interlock"),
            "state": state,
            "fan_duty": duty,
            "action": action,
        }
        if ai_duty is not None:
            rec["ai_duty"] = ai_duty              # 影子模式：AI 的建議值（未致動）
        self.dec_log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.cloud.publish(self.topic("decision"), rec)

        tf = "故障" if s.get("tc_fault") else f"{s.get('t_furnace', '--')}°C"
        ash = s.get("ash_pct", -1)
        batt = s.get("batt", -99.9)
        say(f"[{state}] CO2={co2:4d}ppm 斜率={slope:+6.1f}/min 爐溫={tf} "
            f"fan={s.get('fan', '?')}({s.get('mode', '?')}) ｜ "
            f"{s.get('robot', '?')} {s.get('leg', '') or ''} 站={s.get('station', '?')} "
            f"香灰={'--' if ash is None or ash < 0 else f'{ash}%'} "
            f"電池={'--' if batt is None or batt <= -99 else f'{batt:.2f}V'} "
            f"WiFi={s.get('rssi', '?')}dBm ｜ {self.vision_text(v, vage)} 照片{self.photos}張 ｜ "
            f"{'' if ai_duty is None else f'AI影子={ai_duty} '}雲端：{self.cloud.state} 已送 {self.cloud.sent} {action}")

    @staticmethod
    def vision_text(v, vage):
        if vage > 2:
            return "相機：無資料"
        mv, hl = v.get("mv", {}), v.get("hl", {})
        if mv.get("ok"):
            f = mv.get("f", 0)
            mvt = f"MV 盤{'有' if f & 1 else '無'} 盤外{mv.get('no', 0)} 盤上{mv.get('ni', 0)}"
        else:
            mvt = "MV 無"
        if hl.get("ok"):
            a = hl.get("ash", -1)
            hlt = f"HL {hl.get('n', 0)}塊" + (f" 香灰{a}%" if a is not None and a >= 0 else "")
        else:
            hlt = "HL 無"
        return f"{mvt} {hlt}"

    # ---- 鍵盤指令 ----
    def console(self):
        for raw in sys.stdin:
            cmd = raw.strip().upper()
            if not cmd:
                continue
            if cmd == "AUTO":
                self.manual = None
                say("風扇回到自動決策")
            elif cmd.startswith("FAN "):
                try:
                    self.manual = max(0, min(255, int(cmd[4:])))
                    say(f"風扇手動 {self.manual}（輸入 AUTO 回到自動）")
                except ValueError:
                    say("用法：FAN 0~255")
            else:
                ok = self.r4.send(cmd)
                say(f"送給 R4：{cmd}" if ok else "R4 沒有連線，送不出去")


def load_secrets(path):
    """回傳 (帳號, 密碼)。檔案不存在或密碼空白時，密碼為空字串。密碼不會被印出來。"""
    user, pw = "burner", ""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        user = d.get("mqtt_user") or user
        pw = d.get("mqtt_password") or ""
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        say(f"讀不到 {os.path.basename(path)}：{e}")
    pw = os.environ.get("MQTT_PASSWORD", pw)
    return user, pw


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass

    ap = argparse.ArgumentParser(description="廟公機器人筆電中繼")
    ap.add_argument("--port", type=int, default=5005, help="接收 R4 的 TCP 埠")
    ap.add_argument("--beacon-port", type=int, default=5006, help="廣播位址用的 UDP 埠")
    ap.add_argument("--host", default="0.0.0.0", help="綁定的位址；本機自我測試用 127.0.0.1")
    ap.add_argument("--no-beacon", action="store_true", help="不廣播位址（自我測試用）")
    ap.add_argument("--mqtt-host", default=DEFAULT_MQTT_HOST, help="桌機 MQTT 位址")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--device", help=f"雲端裝置代號；預設用 R4 回報的，沒有就用 {DEFAULT_DEVICE}")
    ap.add_argument("--no-cloud", action="store_true", help="不上雲")
    ap.add_argument("--no-fan", action="store_true", help="不送風扇指令，R4 用自己的本地 FSM")
    ap.add_argument("--log-vision", action="store_true", help="相機結果也寫進 logs（每小時約 4 MB）")
    ap.add_argument("--secrets", default=os.path.join(HERE, "relay_secrets.json"))
    a = ap.parse_args()

    say("=== 廟公機器人筆電中繼 ===")
    relay = Relay(a, NoCloud())
    if not a.no_cloud:
        user, pw = load_secrets(a.secrets)
        if not pw:
            say(f"{os.path.basename(a.secrets)} 裡沒有 MQTT 密碼，這次不上雲（填好後重開本程式）")
            relay.cloud.state = "沒填密碼，未啟用"
        else:
            # 代號要唯一：同名的連線會被 mosquitto 互相踢掉（例如同時開測試用的第二個中繼）
            cid = f"keeper-relay-{socket.gethostname()[:12]}-{os.getpid()}"
            relay.cloud = Cloud(a.mqtt_host, a.mqtt_port, user, pw, cid,
                                subscribe_fn=relay.subscriptions, on_message=relay.on_cloud_message)
    say(f"雲端主題 incense/{relay.device}/...；風扇決策："
        + ("不送指令（R4 本地 FSM）" if a.no_fan else "由筆電送 FAN 指令"))
    say("可以直接打字送指令：STOP、FAN 120、AUTO")

    stop = threading.Event()
    if not a.no_beacon:
        threading.Thread(target=beacon, args=(a.port, a.beacon_port, stop), daemon=True).start()
    threading.Thread(target=relay.r4.serve, args=(a.host, a.port, stop), daemon=True).start()
    threading.Thread(target=relay.console, daemon=True).start()

    nxt = time.monotonic()
    try:
        while True:
            nxt += 1.0
            time.sleep(max(0.0, nxt - time.monotonic()))
            relay.tick()
    except KeyboardInterrupt:
        say("結束")
    finally:
        stop.set()


if __name__ == "__main__":
    main()
