# -*- coding: utf-8 -*-
"""
線上學習服務（cloud_dash/ai_online_learning.py）自檢。

不碰網路、不碰 InfluxDB——純本地單元驗證：
  1. 特徵同構：服務端 feats() 必須與 PI5/pi_fsm.py 的 ShadowAdvisor._feats
     逐點一致（改其一沒改另一 → 部署模型直接失效，這是最危險的靜默錯誤）
  2. 農曆近似常數同步（SYN / EPOCH）
  3. 純 stdlib 紀律：服務檔不得 import 第三方套件（部署端免裝套件）
  4. ridge 閉式解正確性（可回收已知線性關係）
  5. 守門條款：樣本不足拒換模型；勝過基線才可部署
  6. 異常偵測：正常資料不誤報；注入溫度偏差跳變／資料中斷必須觸發
  7. 誠實標註：模型與輸出必須帶誠實邊界字串

    python 驗證線上學習.py
"""
import importlib.util
import math
import os
import random
import sys
import types
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAIL.append(name)


def load_by_path(name, path, stubs=()):
    for s in stubs:
        if s not in sys.modules:
            sys.modules[s] = types.ModuleType(s)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


print("== 1/2. 特徵同構（服務 vs Pi 部署端）==")
svc = load_by_path("ai_online", os.path.join(ROOT, "cloud_dash",
                                             "ai_online_learning.py"))
# pi_fsm 頂層 import serial / paho —— 筆電端以空模組替身載入
paho = types.ModuleType("paho")
paho_mqtt = types.ModuleType("paho.mqtt")
paho_client = types.ModuleType("paho.mqtt.client")
paho_client.Client = object
paho.mqtt = paho_mqtt
paho_mqtt.client = paho_client
sys.modules.setdefault("paho", paho)
sys.modules.setdefault("paho.mqtt", paho_mqtt)
sys.modules.setdefault("paho.mqtt.client", paho_client)
pi = load_by_path("pi_fsm", os.path.join(ROOT, "PI5", "pi_fsm.py"),
                  stubs=("serial",))

rng = random.Random(42)
worst = 0.0
for _ in range(500):
    h = rng.uniform(0, 24)
    ld = rng.uniform(0, 29.53)
    dow = rng.randrange(7)
    io = float(rng.randrange(2))
    a = svc.feats(h, ld, dow, io)
    b = pi.ShadowAdvisor._feats(h, ld, dow, io)
    worst = max(worst, max(abs(x - y) for x, y in zip(a, b)))
check("feats() 與 ShadowAdvisor._feats 逐點一致（500 隨機點）",
      worst < 1e-12, f"最大差 {worst:.1e}")
check("農曆常數 SYN 同步", abs(svc.SYN - pi.ShadowAdvisor._SYN) < 1e-9)
check("農曆常數 EPOCH 同步",
      abs(svc.LUNAR_EPOCH - pi.ShadowAdvisor._EPOCH) < 1e-9)

print("== 3. 純 stdlib 紀律 ==")
import ast
tree = ast.parse(open(os.path.join(ROOT, "cloud_dash", "ai_online_learning.py"),
                      encoding="utf-8").read())
tops = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        tops.update(n.name.split(".")[0] for n in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        tops.add(node.module.split(".")[0])
bad = tops - set(sys.stdlib_module_names)
check("服務檔僅用標準函式庫", not bad, f"違規：{bad}" if bad else "")

print("== 4. ridge 閉式解 ==")
rng = random.Random(7)
true_w = [2.0, -1.5, 0.5]
Xs = [[1.0, rng.uniform(-1, 1), rng.uniform(-1, 1)] for _ in range(300)]
Ys = [sum(a * b for a, b in zip(true_w, x)) + rng.gauss(0, 0.01) for x in Xs]
w = svc.ridge_fit(Xs, Ys, 1e-6)
check("已知線性關係可回收", max(abs(a - b) for a, b in zip(w, true_w)) < 0.05,
      f"w={['%.3f' % v for v in w]}")

print("== 5. 守門條款 ==")
UTC = timezone.utc
t0 = datetime(2026, 8, 1, tzinfo=UTC)
tiny = [(t0 + timedelta(hours=i), 500.0) for i in range(30)]
m, meta = svc.retrain_predictor(tiny, {})
check("樣本不足 → 拒換模型", m is None and "樣本不足" in meta.get("skip", ""))

rng = random.Random(3)
hourly = []
for d in range(14):
    for h in range(24):
        t = t0 + timedelta(days=d, hours=h, minutes=59)
        morning = math.exp(-((h - 8.0) ** 2) / 8.0)
        evening = math.exp(-((h - 17.0) ** 2) / 12.5)
        we = 2.0 if t.astimezone(svc.TPE).weekday() >= 5 else 0.0
        load = 5 * morning + 8 * evening + we + rng.gauss(0, 1.5)
        hourly.append((t, 450.0 + max(0.0, load) * svc.PPM_PER_STICK))
state = {}
m, meta = svc.retrain_predictor(hourly, state)
check("日曆結構資料 → 訓練成功且勝過基線",
      m is not None and meta["deployable"],
      f"MAE={meta.get('test_mae_sticks')} vs 常數 {meta.get('const_mae_sticks')}"
      f"／前日 {meta.get('persistence_mae_sticks')}")
check("版本計數遞增", state.get("ai1_version") == 1)

print("== 6. 異常偵測 ==")
now = t0 + timedelta(days=14)


def synth_minutely(t_bias_jump=0.0, drop_last_hour=False):
    out = {k: [] for k in ("co2", "t_scd", "t_sht", "rh_scd", "rh_sht",
                           "fan_duty", "fan_actual")}
    r = random.Random(11)
    for i in range(26 * 60):
        t = now - timedelta(hours=26) + timedelta(minutes=i)
        last_h = (now - t) <= timedelta(hours=1)
        if drop_last_hour and last_h:
            continue
        jump = t_bias_jump if (now - t) <= timedelta(hours=24) else 0.0
        out["co2"].append((t, 480.0 + r.gauss(0, 5)))
        out["t_scd"].append((t, 25.0 + jump + r.gauss(0, 0.05)))
        out["t_sht"].append((t, 25.5 + r.gauss(0, 0.05)))
        out["rh_scd"].append((t, 50.0 + r.gauss(0, 0.2)))
        out["rh_sht"].append((t, 52.0 + r.gauss(0, 0.2)))
        out["fan_duty"].append((t, 70.0))
        out["fan_actual"].append((t, 70.0))
    return out


normal = synth_minutely()
am = svc.retrain_anomaly(hourly, normal, {})
sc = svc.score_anomaly(am, normal, now)
check("正常資料不誤報", sc["flag"] == 0, f"score={sc['score']}")
sc2 = svc.score_anomaly(am, synth_minutely(t_bias_jump=3.0), now)
check("溫度偏差跳變 +3°C → 偏差 z 觸發", abs(sc2["t_bias_z"]) >= svc.Z_ALARM,
      f"t_bias_z={sc2['t_bias_z']}")
sc3 = svc.score_anomaly(am, synth_minutely(drop_last_hour=True), now)
check("最近一小時斷流 → 缺料旗標", sc3["dropout"] >= svc.DROPOUT_ALARM
      and sc3["flag"] == 1, f"dropout={sc3['dropout']}")

print("== 7. 誠實標註 ==")
check("預測模型帶誠實邊界字串", "代理量" in m["meta"]["honesty"]
      and "影子" in m["meta"]["honesty"])
check("異常模型標明非故障判定", "非故障判定" in am["honesty"])
check("R4 安全接管不計入異常", sc["safety_override"] is not None
      and sc["flag"] == 0)

print()
if FAIL:
    print(f"共 {len(FAIL)} 項失敗：{FAIL}")
    sys.exit(1)
print("全部通過 ✔")
