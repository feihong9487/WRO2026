// team.js — 團隊頁：操控、系統狀態、完整事件紀錄
// 操控的安全由三層把關：伺服器檢查登入與指令格式、筆電中繼檢查指令是否過期、R4 檢查自己的狀態與電池。
// 這裡的按鈕停用只是讓人少按錯，不是安全機制。

import { connect, store, onUpdate, age, num, fmtClock } from "./live.js";
import { createBoard, robotNow } from "./board.js";
import { createChart } from "./chart.js";
import { ICON, legLabel, useLang } from "./words.js";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

useLang("zh");
createBoard({ isPublic: false, slips: false });

const tempChart = createChart($("#temp-chart"), {
  series: [
    { key: "t_scd", color: "--s1", label: "SCD41" },
    { key: "t_sht", color: "--s2", label: "SHT31" },
    { key: "t_ds", color: "--s3", label: "DS18B20" },
  ],
  unit: "°C", digits: 1, empty: "還沒有溫度資料",
});
$("#temp-legend").innerHTML = [["--s1", "SCD41"], ["--s2", "SHT31"], ["--s3", "DS18B20"]]
  .map(([c, n]) => `<span><i style="background:var(${c})"></i>${n}</span>`).join("");
const fanChart = createChart($("#fan-chart"), {
  series: [{ key: "fanp", color: "--gold-2", label: "風扇" }], unit: "%", empty: "還沒有風扇資料",
});
function renderCharts() {
  tempChart.set(store.hist);
  fanChart.set(store.hist.map((h) => (typeof h.fan === "number" ? { t: h.t, fanp: Math.round((h.fan / 255) * 100) } : { t: h.t })));
}

// ───────── 系統狀態 ─────────
function level(el, lv, text) { el.dataset.level = lv; el.innerHTML = ICON[lv] || ""; el.append(text); }
function renderHealth() {
  const s = robotNow() || {};
  const d = store.latest.decision || {};
  const v = store.latest.vision || {};
  const a = age("sensor");
  const rows = [
    ["監控網站 ↔ MQTT", store.mqtt && store.connected ? ["good", "已連線"] : ["crit", "斷線"]],
    ["機器人資料", a < 3 ? ["good", "即時"] : a < 30 ? ["warn", `${Math.round(a)} 秒前`] : ["crit", a === Infinity ? "還沒收到" : "離線"]],
    ["風扇決策", s.mode === "PI" ? ["good", "筆電中繼決策"] : s.mode ? ["warn", "R4 本地決策"] : ["warn", "未知"]],
    ["電池", (() => { const b = num(s.batt); return b == null ? ["warn", "未知"] : b >= 6.8 ? ["good", `${b.toFixed(2)} V`] : b >= 6 ? ["warn", `${b.toFixed(2)} V 偏低`] : ["crit", `${b.toFixed(2)} V，沒接或過低`]; })()],
    ["WiFi 訊號", (() => { const r = s.rssi; return typeof r !== "number" || r === 0 ? ["warn", "未知"] : r >= -67 ? ["good", `${r} dBm`] : r >= -80 ? ["warn", `${r} dBm 偏弱`] : ["crit", `${r} dBm 很弱`]; })()],
    ["熱電偶", s.tc_fault ? ["crit", "故障或沒接"] : num(d.t_furnace) != null ? ["good", `${d.t_furnace} °C`] : ["warn", "未知"]],
    ["空氣感測器", s.sensor_fault ? ["crit", "讀值異常"] : a < 30 ? ["good", "正常"] : ["warn", "未知"]],
    ["CO2 警報", s.alarm ? ["crit", "超過 1500 ppm"] : ["good", "正常"]],
    ["M-Vision", age("vision") < 2 && v.mv && v.mv.ok ? ["good", "有資料"] : ["warn", "沒有資料"]],
    ["HuskyLens", age("vision") < 2 && v.hl && v.hl.ok ? ["good", "有資料"] : ["warn", "沒有資料"]],
    ["WiFi 丟棄", !s.net_drop ? ["good", "0 行"] : ["warn", `${s.net_drop} 行`]],
  ];
  $("#health").replaceChildren(...rows.map(([k, [lv, txt]]) => {
    const div = document.createElement("div");
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); level(dd, lv, txt);
    div.append(dt, dd); return div;
  }));
}

// ───────── 按鈕可用狀態 ─────────
const MISSION_NAME = { "RUN MORNING": "早上任務", "RUN EVENING": "晚上任務" };
function cmdName(cmd) {
  if (MISSION_NAME[cmd]) return MISSION_NAME[cmd];
  const m = /^RUN ([A-E])$/.exec(cmd);
  if (m) return `單段 ${m[1]}`;
  return { GO: "繼續下一段", END: "結束任務", CLEAR: "清除失敗", STOP: "緊急停止", AUTO: "風扇自動" }[cmd] || cmd;
}
function renderButtons() {
  const s = robotNow();
  const online = !!s && age("sensor") < 5;
  const r = s && s.robot;
  let why = "";
  if (!online) why = "機器人離線，只有緊急停止可以按。";
  else if (r === "STATION") why = `已到${s.station ? "站" : ""}，可以繼續下一段或結束任務。`;
  else if (r === "FAIL") why = `任務失敗（${s.fail || "原因未知"}），檢查場地後按「清除失敗」或直接開始新任務。`;
  else if (r && r !== "IDLE") why = `機器人正在執行（${legLabel(s.leg) || r}），要中止請按緊急停止。`;
  const lowBatt = num(s && s.batt) == null || num(s.batt) < 6;
  if (online && (!r || r === "IDLE") && lowBatt) why = "電池電壓不足或沒接電池，不能開始任務（R4 也會拒絕）。";
  $("#why").textContent = why;
  for (const b of $$("[data-need]")) {
    if (b.getAttribute("aria-busy") === "true") continue;
    const need = b.dataset.need;
    b.disabled = !online || (need === "idle" && (!(r === "IDLE" || r === "FAIL") || lowBatt))
      || (need === "station" && r !== "STATION") || (need === "fail" && r !== "FAIL");
  }
}

// ───────── 送指令與回覆 ─────────
const pending = new Map();                  // 指令編號 → {cmd, btn, timer}
function toast(lv, text) {
  const el = document.createElement("div");
  el.className = `toast ${lv}`;
  el.innerHTML = ICON[lv] || "";
  el.append(text);
  $("#toasts").append(el);
  setTimeout(() => el.remove(), lv === "crit" ? 7000 : 4000);
}
function done(id) {
  const p = pending.get(id); if (!p) return;
  clearTimeout(p.timer);
  if (p.btn) { p.btn.removeAttribute("aria-busy"); }
  pending.delete(id);
  renderButtons();
}
async function send(cmd, btn) {
  if (btn) { btn.setAttribute("aria-busy", "true"); btn.disabled = true; }
  try {
    const r = await fetch("/api/team/cmd", {
      method: "POST", headers: { "Content-Type": "application/json", "X-Keeper": "1" },
      body: JSON.stringify({ cmd }), credentials: "same-origin",
    });
    if (r.status === 401) { location.href = "/login"; return; }
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { toast("crit", `${cmdName(cmd)}：${j.error || "送不出去"}`); if (btn) btn.removeAttribute("aria-busy"); renderButtons(); return; }
    const timer = setTimeout(() => {
      toast("warn", `${cmdName(cmd)}：8 秒內沒有收到 R4 回覆，請看事件紀錄`);
      done(j.id);
    }, 8000);
    pending.set(j.id, { cmd, btn, timer });
  } catch (e) {
    toast("crit", `${cmdName(cmd)}：網路錯誤，指令可能沒有送出`);
    if (btn) btn.removeAttribute("aria-busy");
    renderButtons();
  }
}
onUpdate((kind, o) => {
  if (kind !== "ack" || !o.id || !pending.has(o.id)) return;
  const p = pending.get(o.id);
  if (!o.ok) { toast("crit", `${cmdName(p.cmd)}：${o.why}`); done(o.id); return; }
  // 中繼層的「已轉給 R4」之後還要等 R4 自己回覆；風扇指令只到中繼為止
  if (o.stage === "r4" || p.cmd === "AUTO" || p.cmd.startsWith("FAN ")) { toast("good", `${cmdName(p.cmd)}：${o.why}`); done(o.id); }
});

// 確認對話框：會讓車子動起來的指令一定要確認
const dlg = $("#confirm");
function confirmRun(cmd) {
  return new Promise((resolve) => {
    const name = cmdName(cmd);
    $("#confirm-title").textContent = `開始${name}？`;
    const m = /^RUN (MORNING|EVENING|[A-E])$/.exec(cmd);
    const route = { MORNING: "充電座 → 供桌 → 香爐", EVENING: "香爐 → 供桌 → 倒灰區 → 充電座", A: "充電座 → 供桌", B: "供桌 → 香爐", C: "香爐 → 供桌", D: "供桌 → 倒灰區", E: "倒灰區 → 充電座" }[m[1]];
    $("#confirm-text").textContent = `機器人會立刻開始移動，路線：${route}。請確認場地上沒有手或雜物，旁邊有人可以按實體鍵停車。`;
    $("#confirm-ok").textContent = `開始${name}`;
    dlg.returnValue = "";
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true });
    dlg.showModal();
    $("#confirm-ok").focus();
  });
}

for (const b of $$("[data-cmd]")) {
  b.addEventListener("click", async () => {
    const cmd = b.dataset.cmd;
    if (cmd.startsWith("RUN ") && !(await confirmRun(cmd))) return;
    send(cmd, b);
  });
}
for (const b of $$("[data-stop]")) b.addEventListener("click", () => send("STOP", null));
const range = $("#fan-range"), out = $("#fan-out");
range.addEventListener("input", () => { out.textContent = `${range.value}%`; });
$("#fan-apply").addEventListener("click", (e) => send(`FAN ${Math.round((range.value / 100) * 255)}`, e.currentTarget));

// ───────── 事件紀錄 ─────────
const SRC = { r4: "R4", relay: "中繼", web: "網站" };
function renderLog() {
  const list = store.events.slice(-120).reverse();
  const ol = $("#slips");
  if (!list.length) {
    const li = document.createElement("li"); li.className = "empty-slip"; li.textContent = "還沒有事件。R4 連上筆電中繼後，紀錄訊息會出現在這裡。";
    ol.replaceChildren(li); return;
  }
  ol.replaceChildren(...list.map((e) => {
    const li = document.createElement("li");
    const tm = document.createElement("time"); tm.textContent = fmtClock(e._t);
    const src = document.createElement("span"); src.className = "src";
    const msg = document.createElement("span");
    if (e._kind === "ack" || "cmd" in e) {
      src.textContent = e.stage === "r4" ? "R4 回覆" : "中繼回覆";
      msg.textContent = `${cmdName(e.cmd)}：${e.why}${e.by ? `（${e.by}）` : ""}`;
      li.className = e.ok ? "ok" : "bad";
    } else {
      src.textContent = SRC[e.src] || e.src || "";
      msg.textContent = e.msg;
      if (/失敗|中斷|錯誤|逾時/.test(e.msg || "")) li.className = "bad";
    }
    li.append(tm, src, msg); return li;
  }));
}

// ───────── 登入者與登出 ─────────
fetch("/api/me", { credentials: "same-origin" }).then((r) => r.ok ? r.json() : Promise.reject())
  .then((j) => { $("#who").textContent = j.user; })
  .catch(() => { location.href = "/login"; });
$("#logout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST", headers: { "X-Keeper": "1" }, credentials: "same-origin" }).catch(() => {});
  location.href = "/login";
});

let chartDue = 0;
onUpdate((kind) => {
  if (kind === "snapshot") { renderCharts(); renderHealth(); renderButtons(); renderLog(); return; }
  if (kind === "sensor" || kind === "robot") {
    renderHealth(); renderButtons();
    if (performance.now() > chartDue) { chartDue = performance.now() + 2000; renderCharts(); }
  }
  if (kind === "event" || kind === "ack") renderLog();
});
setInterval(() => { renderHealth(); renderButtons(); }, 1000);
renderHealth(); renderButtons(); renderLog();
connect("/api/team/stream");
