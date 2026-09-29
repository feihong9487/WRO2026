// live.js — 即時資料連線（Server-Sent Events）與共用狀態
// 伺服器先送 snapshot（最新值＋30 分鐘歷史＋事件），之後逐筆推送。
// 時間一律用伺服器時鐘計算「幾秒前」，看的人手機時間不準也不影響。

export const store = {
  latest: {},          // sensor / decision / robot / vision 最新一筆（含 _t 伺服器時間）
  hist: [],            // {t, co2, co2_base, t_scd, t_sht, rh_sht, ash_pct, fan}
  events: [],          // 事件與指令回覆，新的在後
  offset: 0,           // 伺服器時間 − 本機時間（秒）
  connected: false,
  mqtt: true,
  team: false,
  user: null,
};

const listeners = new Set();
export function onUpdate(fn) { listeners.add(fn); }
function emit(kind, obj) { for (const fn of listeners) fn(kind, obj); }

export function serverNow() { return Date.now() / 1000 + store.offset; }
export function age(kind) {
  const o = store.latest[kind];
  return o && o._t ? serverNow() - o._t : Infinity;
}

const HIST_MAX_S = 1800;

export function connect(url) {
  const es = new EventSource(url);
  es.addEventListener("snapshot", (e) => {
    const s = JSON.parse(e.data);
    store.offset = s.now - Date.now() / 1000;
    store.latest = s.latest || {};
    store.hist = s.hist || [];
    store.events = s.events || [];
    store.team = !!s.team;
    store.user = s.user || null;
    store.mqtt = s.mqtt !== false;
    store.connected = true;
    emit("snapshot", s);
  });
  for (const kind of ["sensor", "decision", "robot", "vision", "photo"]) {
    es.addEventListener(kind, (e) => {
      const o = JSON.parse(e.data);
      store.latest[kind] = o;
      if (kind === "sensor") pushHist(o);
      emit(kind, o);
    });
  }
  for (const kind of ["event", "ack"]) {
    es.addEventListener(kind, (e) => {
      const o = JSON.parse(e.data);
      o._kind = kind;
      store.events.push(o);
      if (store.events.length > 200) store.events.shift();
      emit(kind, o);
    });
  }
  es.addEventListener("tick", (e) => {
    const t = JSON.parse(e.data);
    store.offset = t.now - Date.now() / 1000;
    store.mqtt = t.mqtt !== false;
    emit("tick", t);
  });
  es.onopen = () => { store.connected = true; emit("conn", true); };
  es.onerror = () => { store.connected = false; emit("conn", false); };
  return es;
}

function pushHist(o) {
  const last = store.hist[store.hist.length - 1];
  if (last && o._t - last.t < 1) return;
  const row = { t: o._t };
  for (const k of ["co2", "co2_base", "t_scd", "t_sht", "rh_sht", "ash_pct"]) {
    const v = o[k];
    if (typeof v === "number" && v > -99 && !(k === "ash_pct" && v < 0)) row[k] = v;
  }
  const d = store.latest.decision;
  if (d && typeof d.fan_actual === "number") row.fan = d.fan_actual;
  store.hist.push(row);
  const cutoff = o._t - HIST_MAX_S;
  while (store.hist.length && store.hist[0].t < cutoff) store.hist.shift();
}

// 有效數值：R4 用 -99.9 代表沒有資料
export function num(v) { return typeof v === "number" && v > -99 ? v : null; }

export function fmtClock(t) {
  const d = new Date((t - store.offset) * 1000);
  return d.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });
}
