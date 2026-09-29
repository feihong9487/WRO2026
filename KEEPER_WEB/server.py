#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py — 廟公機器人監控網站（架在桌機，和 Grafana 放在一起）

資料流：
  R4 → 筆電中繼 → 桌機 mosquitto ──訂閱──▶ 本程式 ──SSE 即時推送──▶ 瀏覽器
  團隊頁的操控按鈕 → 本程式 → mosquitto（incense/<裝置>/cmd）→ 筆電中繼 → R4

兩種頁面：
  /        公開展示頁，免登入，給評審與觀眾看。只送展示用的資料，沒有任何操控功能。
  /team    團隊內部頁，要登入。多了操控、事件紀錄、系統狀態。
  操控 API 在伺服器端檢查登入，不是只把按鈕藏起來。

只用 Python 標準函式庫，和桌機上的 ai-online 一樣可以直接用 python:3.12-alpine 執行。

設定（環境變數，或 data/keeper_web.json）：
  MQTT_HOST      預設 mosquitto（在同一個 docker compose 裡）
  MQTT_PORT      預設 1883
  MQTT_USER      預設 keeper-web
  MQTT_PASSWORD  或放在 data/keeper_web.json 的 mqtt_password
  DEVICE         預設 aroma01
  PORT           預設 8090
  PUBLIC_PHOTO   預設 1：公開頁也看得到 M-Vision 照片；設 0 只給團隊看

帳號：用 manage_users.py 新增（密碼只存雜湊值）。
"""

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import queue
import re
import secrets
import select
import socket
import struct
import sys
import threading
import time
from collections import deque
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
DATA = os.environ.get("DATA_DIR", os.path.join(HERE, "data"))

SESSION_HOURS = 12
COOKIE = "keeper_session"
HISTORY_S = 3600                 # 保留一小時的感測歷史
SNAPSHOT_HISTORY_S = 1800        # 新連線先送 30 分鐘
MAX_CLIENTS = 150
CMD_PATTERN = re.compile(r"^(STOP|GO|END|CLEAR|AUTO|RUN (MORNING|EVENING|[A-E])|FAN \d{1,3})$")
# 公開頁只顯示這些開頭的機器人紀錄（到站、任務進度），其餘除錯訊息只給團隊看
PUBLIC_EVENT_PREFIX = ("開始任務", "遠端開始任務", "已到站", "任務完成", "香爐站", "供桌站", "倒灰站",
                       "充電座", "任務失敗", "任務由")
SENSOR_HIST_KEYS = ("co2", "co2_base", "t_scd", "t_sht", "rh_sht", "ash_pct")


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def load_config():
    cfg = {"mqtt_host": "mosquitto", "mqtt_port": 1883, "mqtt_user": "keeper-web",
           "mqtt_password": "", "device": "aroma01", "port": 8090, "public_photo": True}
    path = os.path.join(DATA, "keeper_web.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if v not in (None, "")})
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        log(f"讀不到 {path}：{e}")
    env = {"MQTT_HOST": "mqtt_host", "MQTT_PORT": "mqtt_port", "MQTT_USER": "mqtt_user",
           "MQTT_PASSWORD": "mqtt_password", "DEVICE": "device", "PORT": "port", "PUBLIC_PHOTO": "public_photo"}
    for e, k in env.items():
        if os.environ.get(e):
            cfg[k] = os.environ[e]
    # 也可以指向另一個放帳密的 JSON（例如筆電上測試時沿用中繼程式的 relay_secrets.json），不必複製密碼
    sf = os.environ.get("SECRETS_FILE") or cfg.get("secrets_file")
    if sf:
        sf = sf if os.path.isabs(sf) else os.path.join(DATA, sf)
        try:
            with open(sf, encoding="utf-8") as f:
                sec = json.load(f)
            cfg["mqtt_user"] = sec.get("mqtt_user") or cfg["mqtt_user"]
            cfg["mqtt_password"] = sec.get("mqtt_password") or cfg["mqtt_password"]
        except (OSError, ValueError) as e:
            log(f"讀不到帳密檔 {sf}：{e}")
    cfg["mqtt_port"] = int(cfg["mqtt_port"])
    cfg["port"] = int(cfg["port"])
    cfg["public_photo"] = str(cfg["public_photo"]).lower() not in ("0", "false", "no")
    return cfg


# ═══════════════════════════════════════════════════════════════════
# 極簡 MQTT 3.1.1 用戶端（QoS 0，訂閱＋發布）
# ═══════════════════════════════════════════════════════════════════
def _varlen(n):
    out = bytearray()
    while True:
        b, n = n % 128, n // 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _str(s):
    b = s.encode("utf-8")
    return struct.pack("!H", len(b)) + b


def _packet(ptype, body):
    return bytes([ptype]) + _varlen(len(body)) + body


CONNACK_RC = {1: "不支援的協定版本", 2: "用戶端代號被拒絕", 3: "伺服器暫時無法服務",
              4: "帳號或密碼錯誤", 5: "沒有權限"}


class Mqtt:
    def __init__(self, host, port, user, password, topics, on_message):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.topics = topics
        self.on_message = on_message
        self.sock = None
        self.wlock = threading.Lock()
        self.state = "連線中"
        threading.Thread(target=self._run, daemon=True).start()

    @property
    def connected(self):
        return self.sock is not None

    def publish(self, topic, obj):
        payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with self.wlock:
            s = self.sock
            if s is None:
                return False
            try:
                s.sendall(_packet(0x30, _str(topic) + payload))
                return True
            except OSError:
                return False

    def _connect(self):
        s = socket.create_connection((self.host, self.port), timeout=5)
        try:
            flags, tail = 0x02, _str(f"keeper-web-{secrets.token_hex(3)}")
            if self.user:
                flags |= 0x80
                tail += _str(self.user)
            if self.password:
                flags |= 0x40
                tail += _str(self.password)
            s.sendall(_packet(0x10, _str("MQTT") + bytes([4, flags]) + struct.pack("!H", 30) + tail))
            ack = b""
            while len(ack) < 4:
                d = s.recv(4 - len(ack))
                if not d:
                    raise ConnectionError("伺服器關閉連線")
                ack += d
            if ack[0] != 0x20:
                raise ConnectionError("伺服器回應的格式不對")
            if ack[3]:
                raise PermissionError(CONNACK_RC.get(ack[3], f"代碼 {ack[3]}"))
            body = struct.pack("!H", 1) + b"".join(_str(t) + b"\x00" for t in self.topics)
            s.sendall(_packet(0x82, body))
            return s
        except BaseException:
            s.close()
            raise

    def _set_state(self, st):
        if st != self.state:
            self.state = st
            log("MQTT：" + st)

    def _run(self):
        backoff = 2
        while True:
            try:
                s = self._connect()
            except PermissionError as e:
                self._set_state(f"登入被拒絕：{e}")
                time.sleep(30)
                continue
            except OSError as e:
                self._set_state(f"連不上 {self.host}:{self.port}（{e}）")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            backoff = 2
            self.sock = s
            self._set_state(f"已連上 {self.host}:{self.port}")
            try:
                self._loop(s)
            except (OSError, ConnectionError) as e:
                self._set_state(f"斷線（{e}），重連中")
            finally:
                with self.wlock:
                    self.sock = None
                s.close()

    def _loop(self, s):
        buf = bytearray()
        last_ping, ping_wait = time.monotonic(), None
        while True:
            r, _, _ = select.select([s], [], [], 1.0)
            now = time.monotonic()
            if r:
                d = s.recv(65536)
                if not d:
                    raise ConnectionError("伺服器關閉連線")
                buf += d
                ping_wait = None
                self._parse(buf)
            if now - last_ping > 15:
                with self.wlock:
                    s.sendall(b"\xc0\x00")
                last_ping = now
                if ping_wait is None:
                    ping_wait = now
            if ping_wait is not None and now - ping_wait > 10:
                raise ConnectionError("伺服器沒有回應心跳")

    def _parse(self, buf):
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
            if ptype >> 4 == 3:
                qos = (ptype >> 1) & 3
                tl = struct.unpack("!H", body[:2])[0]
                topic = body[2:2 + tl].decode("utf-8", "replace")
                payload = body[2 + tl + (2 if qos else 0):]
                try:
                    self.on_message(topic, payload)
                except Exception as e:
                    log(f"處理 MQTT 訊息出錯：{e}")


# ═══════════════════════════════════════════════════════════════════
# 資料中樞：最新狀態、歷史、事件，並推送給所有瀏覽器
# ═══════════════════════════════════════════════════════════════════
class Hub:
    KINDS = ("sensor", "decision", "robot", "vision", "photo", "event", "ack")

    def __init__(self, device, public_photo=True):
        self.device = device
        self.PUBLIC_KINDS = ("sensor", "decision", "robot", "vision", "event") + (("photo",) if public_photo else ())
        self.lock = threading.Lock()
        self.latest = {}
        self.hist = deque(maxlen=HISTORY_S)
        self.events = deque(maxlen=300)
        self.clients = []                       # [queue, 是否為團隊]
        self.last_hist = 0.0
        self.fan = None

    def on_mqtt(self, topic, payload):
        parts = topic.split("/")
        if len(parts) != 3 or parts[1] != self.device or parts[2] not in self.KINDS:
            return
        kind = parts[2]
        try:
            obj = json.loads(payload.decode("utf-8"))
        except ValueError:
            return
        if not isinstance(obj, dict):
            return
        obj["_t"] = time.time()
        self.ingest(kind, obj)

    def ingest(self, kind, obj):
        with self.lock:
            if kind in ("event", "ack"):
                obj["public"] = kind == "event" and self._public_event(obj)
                self.events.append((kind, obj))
            else:
                self.latest[kind] = obj
            if kind == "decision":
                self.fan = obj.get("fan_actual")
            if kind == "sensor" and obj["_t"] - self.last_hist >= 1.0:
                self.last_hist = obj["_t"]
                row = {"t": round(obj["_t"], 1)}
                for k in SENSOR_HIST_KEYS:
                    v = obj.get(k)
                    if isinstance(v, (int, float)) and v > -99 and not (k == "ash_pct" and v < 0):
                        row[k] = v
                if self.fan is not None:
                    row["fan"] = self.fan
                self.hist.append(row)
            clients = list(self.clients)
        public_ok = kind in self.PUBLIC_KINDS and (kind != "event" or obj.get("public"))
        msg = self._sse(kind, obj)
        for c in clients:
            q, team = c
            if team or public_ok:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass                        # 慢的瀏覽器跳過這筆，不拖累別人

    @staticmethod
    def _public_event(obj):
        return obj.get("src") == "r4" and str(obj.get("msg", "")).startswith(PUBLIC_EVENT_PREFIX)

    @staticmethod
    def _sse(kind, obj):
        return f"event: {kind}\ndata: {json.dumps(obj, ensure_ascii=False, separators=(',', ':'))}\n\n"

    def snapshot(self, team):
        with self.lock:
            cutoff = time.time() - SNAPSHOT_HISTORY_S
            hist = [h for h in self.hist if h["t"] >= cutoff]
            hist = hist[::5] if len(hist) > 400 else hist
            events = [(k, e) for k, e in self.events if team or (k == "event" and e.get("public"))]
            latest = dict(self.latest)
            if not team and "photo" not in self.PUBLIC_KINDS:
                latest.pop("photo", None)
            return {"now": time.time(), "device": self.device, "team": team,
                    "latest": latest, "hist": hist, "events": [e for _, e in events][-60:]}

    def add_client(self, team):
        q = queue.Queue(maxsize=200)
        c = [q, team]
        with self.lock:
            if len(self.clients) >= MAX_CLIENTS:
                return None
            self.clients.append(c)
        return c

    def remove_client(self, c):
        with self.lock:
            if c in self.clients:
                self.clients.remove(c)


# ═══════════════════════════════════════════════════════════════════
# 帳號與登入
# ═══════════════════════════════════════════════════════════════════
class Auth:
    def __init__(self, path):
        self.path = path
        self.sessions = {}                      # token → (帳號, 到期時間)
        self.fails = {}                         # 帳號 → [失敗時間]
        self.global_fails = deque(maxlen=100)
        self.lock = threading.Lock()

    def _users(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f).get("users", {})
        except (OSError, ValueError):
            return {}

    def has_users(self):
        return bool(self._users())

    def login(self, user, password):
        """回傳 (token 或 None, 錯誤訊息)。"""
        now = time.time()
        with self.lock:
            recent = [t for t in self.fails.get(user, []) if now - t < 300]
            self.fails[user] = recent
            if len(recent) >= 5:
                return None, "這個帳號錯誤次數太多，請 5 分鐘後再試"
            if sum(1 for t in self.global_fails if now - t < 300) >= 30:
                return None, "登入失敗次數太多，請 5 分鐘後再試"
        rec = self._users().get(user)
        ok = False
        if rec:
            h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                    bytes.fromhex(rec["salt"]), int(rec["iter"]))
            ok = hmac.compare_digest(h.hex(), rec["hash"])
        else:
            hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), b"x" * 16, 200_000)   # 讓回應時間一致
        with self.lock:
            if not ok:
                self.fails.setdefault(user, []).append(now)
                self.global_fails.append(now)
                return None, "帳號或密碼不對"
            self.fails.pop(user, None)
            token = secrets.token_urlsafe(32)
            self.sessions[token] = (user, now + SESSION_HOURS * 3600)
            return token, ""

    def user_of(self, token):
        if not token:
            return None
        with self.lock:
            s = self.sessions.get(token)
            if not s:
                return None
            if s[1] < time.time():
                self.sessions.pop(token, None)
                return None
            return s[0]

    def logout(self, token):
        with self.lock:
            self.sessions.pop(token, None)


# ═══════════════════════════════════════════════════════════════════
# HTTP
# ═══════════════════════════════════════════════════════════════════
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


class Handler(BaseHTTPRequestHandler):
    server_version = "KeeperWeb/1.0"
    hub: Hub = None
    auth: Auth = None
    mqtt: Mqtt = None
    cmd_log = None
    last_cmd = {}

    def log_message(self, fmt, *args):
        pass                                    # 不逐筆印存取紀錄

    # ---- 工具 ----
    def _headers(self, status, ctype, extra=None, length=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", CSP)
        if length is not None:
            self.send_header("Content-Length", str(length))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, status, obj, extra=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", extra, len(body))
        self.wfile.write(body)

    def _token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE:
                return v
        return None

    def _user(self):
        return self.auth.user_of(self._token())

    def _secure(self):
        host = self.headers.get("Host", "")
        return self.headers.get("X-Forwarded-Proto") == "https" or host.split(":")[0].endswith(".ts.net")

    def _cookie(self, value, max_age):
        c = f"{COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
        return c + ("; Secure" if self._secure() else "")

    def _same_origin(self):
        """寫入類請求要帶自訂標頭，且來源要是本站，擋掉跨站偽造請求。"""
        if self.headers.get("X-Keeper") != "1":
            return False
        origin = self.headers.get("Origin")
        if origin:
            return urlparse(origin).netloc == self.headers.get("Host", "")
        return True

    def _body(self, limit=4096):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > limit:
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return None

    def _file(self, rel):
        path = os.path.realpath(os.path.join(WEB, rel))
        if not path.startswith(os.path.realpath(WEB) + os.sep) or not os.path.isfile(path):
            self._json(404, {"error": "找不到這個頁面"})
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(path, "rb") as f:
            data = f.read()
        self._headers(200, ctype, length=len(data))
        self.wfile.write(data)

    # ---- 路由 ----
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p in ("/", "/index.html"):
            return self._file("index.html")
        if p == "/team":
            if not self._user():
                self.send_response(303)
                self.send_header("Location", "/login")
                self.end_headers()
                return
            return self._file("team.html")
        if p == "/login":
            return self._file("login.html")
        if p.startswith("/assets/"):
            return self._file(p[1:])
        if p == "/api/public/stream":
            return self._stream(False)
        if p == "/api/team/stream":
            if not self._user():
                return self._json(401, {"error": "請先登入"})
            return self._stream(True)
        if p == "/api/me":
            user = self._user()
            return self._json(200 if user else 401, {"user": user})
        if p == "/healthz":
            return self._json(200, {"ok": True, "mqtt": self.mqtt.state})
        self._json(404, {"error": "找不到這個頁面"})

    def do_POST(self):
        p = urlparse(self.path).path
        if not self._same_origin():
            return self._json(403, {"error": "請從監控網站本身操作"})
        if p == "/api/login":
            d = self._body() or {}
            user, pw = str(d.get("user", "")).strip(), str(d.get("password", ""))
            if not user or not pw:
                return self._json(400, {"error": "請輸入帳號和密碼", "field": "user" if not user else "password"})
            if not self.auth.has_users():
                return self._json(503, {"error": "還沒有建立任何帳號，請在桌機執行 manage_users.py add 帳號"})
            token, err = self.auth.login(user, pw)
            if not token:
                log(f"登入失敗：{user}")
                return self._json(401, {"error": err})
            log(f"登入：{user}")
            return self._json(200, {"user": user}, {"Set-Cookie": self._cookie(token, SESSION_HOURS * 3600)})
        if p == "/api/logout":
            self.auth.logout(self._token())
            return self._json(200, {"ok": True}, {"Set-Cookie": self._cookie("", 0)})
        if p == "/api/team/cmd":
            user = self._user()
            if not user:
                return self._json(401, {"error": "請先登入"})
            d = self._body() or {}
            cmd = str(d.get("cmd", "")).strip().upper()
            if not CMD_PATTERN.match(cmd):
                return self._json(400, {"error": "不支援這個指令"})
            now = time.time()
            if cmd != "STOP" and now - self.last_cmd.get(user, 0) < 0.8:
                return self._json(429, {"error": "指令送太快了，請稍等一下"})
            self.last_cmd[user] = now
            cid = secrets.token_hex(6)
            ok = self.mqtt.publish(f"incense/{self.hub.device}/cmd",
                                   {"id": cid, "cmd": cmd, "by": user, "t": now})
            self.cmd_log.write(json.dumps({"ts": now_iso(), "user": user, "cmd": cmd, "id": cid,
                                           "sent": ok}, ensure_ascii=False) + "\n")
            self.cmd_log.flush()
            log(f"指令 {cmd}（{user}）{'已送出' if ok else '送不出去：MQTT 沒連線'}")
            if not ok:
                return self._json(503, {"error": "伺服器沒有連上 MQTT，指令送不出去"})
            return self._json(200, {"id": cid, "cmd": cmd})
        self._json(404, {"error": "找不到這個頁面"})

    def _stream(self, team):
        c = self.hub.add_client(team)
        if c is None:
            return self._json(503, {"error": "觀看人數已滿，請稍後再試"})
        try:
            self._headers(200, "text/event-stream; charset=utf-8", {"X-Accel-Buffering": "no"})
            snap = self.hub.snapshot(team)
            snap["mqtt"] = self.mqtt.connected
            if team:
                snap["user"] = self._user()
            self.wfile.write(Hub._sse("snapshot", snap).encode("utf-8"))
            self.wfile.flush()
            last_tick = time.monotonic()
            while True:
                try:
                    msg = c[0].get(timeout=5)
                    self.wfile.write(msg.encode("utf-8"))
                except queue.Empty:
                    pass
                if time.monotonic() - last_tick >= 5:
                    last_tick = time.monotonic()
                    tick = {"now": time.time(), "mqtt": self.mqtt.connected}
                    self.wfile.write(Hub._sse("tick", tick).encode("utf-8"))
                    if team and not self._user():
                        break                       # 登出或登入過期就中斷
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            self.hub.remove_client(c)


def main():
    ap = argparse.ArgumentParser(description="廟公機器人監控網站")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int)
    ap.add_argument("--device", help="覆蓋設定檔的裝置代號（測試用）")
    a = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("image/svg+xml", ".svg")
    mimetypes.add_type("application/manifest+json", ".webmanifest")
    os.makedirs(DATA, exist_ok=True)

    cfg = load_config()
    port = a.port or cfg["port"]
    if a.device:
        cfg["device"] = a.device
    hub = Hub(cfg["device"], cfg["public_photo"])
    auth = Auth(os.path.join(DATA, "users.json"))
    dev = cfg["device"]
    mqtt = Mqtt(cfg["mqtt_host"], cfg["mqtt_port"], cfg["mqtt_user"], cfg["mqtt_password"],
                [f"incense/{dev}/{k}" for k in Hub.KINDS], hub.on_mqtt)

    Handler.hub, Handler.auth, Handler.mqtt = hub, auth, mqtt
    Handler.cmd_log = open(os.path.join(DATA, "commands.log"), "a", encoding="utf-8")

    log(f"廟公機器人監控網站：http://{a.host}:{port}/（裝置 {dev}）")
    if not auth.has_users():
        log("還沒有任何團隊帳號。用 python manage_users.py add <帳號> 建立")
    if not cfg["mqtt_password"]:
        log("沒有設定 MQTT 密碼，mosquitto 會拒絕連線")
    srv = ThreadingHTTPServer((a.host, port), Handler)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("結束")


if __name__ == "__main__":
    main()
