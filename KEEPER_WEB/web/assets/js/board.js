// board.js — 公開頁與團隊頁共用的畫面：對聯、場地圖、雙眼、香灰、CO2 圖、紀事

import { store, onUpdate, age, num, fmtClock } from "./live.js";
import { t, applyStatic, narrate, co2Level, ICON, setLang, getLang } from "./words.js";
import { createField } from "./field.js";
import { createCams } from "./cams.js";
import { createChart } from "./chart.js";
import { startSmoke } from "./smoke.js";

const $ = (s) => document.querySelector(s);
const FRESH_S = 3, VISION_FRESH_S = 2;

// 機器人狀態：數值在 sensor 主題，任務文字在 robot 主題，合在一起用
export function robotNow() {
  if (age("sensor") >= 30 && age("robot") >= 30) return null;
  return { ...(store.latest.sensor || {}), ...(age("robot") < 30 ? store.latest.robot : {}) };
}

function status(el, level, text) {
  el.innerHTML = level ? ICON[level] : "";
  if (text) el.append(text);
}

export function createBoard({ isPublic, slips = true }) {
  const smoke = startSmoke($("#smoke"));
  const field = createField($("#field"));
  const cams = createCams({
    mvCanvas: $("#mv"), hlCanvas: $("#hl"), mvEmpty: $("#mv-empty"), hlEmpty: $("#hl-empty"),
    mvChips: $("#mv-chips"), hlChips: $("#hl-chips"),
  });
  const co2Chart = createChart($("#co2-chart"), {
    series: [{ key: "co2", color: "--gold-2", label: "CO2" }],
    unit: "ppm", ref: { key: "co2_base", label: getLang() === "en" ? "Background" : "背景值", minSpan: 120 },
    empty: getLang() === "en" ? "No readings yet" : "還沒有資料，機器人上線後開始記錄",
  });

  function renderAir() {
    const s = store.latest.sensor, fresh = age("sensor") < 30;
    const co2 = fresh && s ? num(s.co2) : null;
    $("#co2").textContent = co2 ?? "--";
    const lv = co2Level(co2, s && num(s.co2_base));
    status($("#co2-status"), lv && lv.level, lv ? lv.text : "");
    $("#c-air").dataset.level = lv ? lv.level : "";
    if (s && fresh) {
      const base = num(s.co2_base);
      $("#co2-note").textContent = base != null ? (getLang() === "en" ? `Background ${base}` : `背景值 ${base}`) : "";
    } else $("#co2-note").textContent = "";

    const d = store.latest.decision, dFresh = age("decision") < 30;
    const fan = d && dFresh && typeof d.fan_actual === "number" ? Math.round((d.fan_actual / 255) * 100) : null;
    $("#fan").textContent = fan ?? "--";
    const st = d && dFresh ? d.state : null;
    const lvl = st === "S3" ? "crit" : st === "S2" ? "warn" : st ? "good" : null;
    status($("#fan-status"), lvl, st ? t("st." + st) : "");
    $("#fan-note").textContent = st ? t("stNote." + st) : "";
    $("#c-fan").dataset.level = lvl || "";

    const base = s ? num(s.co2_base) : null;
    const dens = co2 != null ? Math.max(0.1, Math.min(1, (co2 - (base ?? 450)) / 450 + 0.2)) : 0.15;
    smoke.set(dens, fan != null ? fan / 100 : 0.15);
  }

  function renderNow() {
    const s = robotNow();
    const n = narrate(s, store.latest.vision, isPublic);
    $("#now").textContent = n.main;
    $("#now-sub").textContent = n.sub;
    field.update(s);
  }

  function renderAsh() {
    const s = store.latest.sensor, fresh = age("sensor") < 30;
    const p = fresh && s && typeof s.ash_pct === "number" && s.ash_pct >= 0 ? s.ash_pct : null;
    $("#ash-num").innerHTML = "";
    $("#ash-num").append(p == null ? "--" : String(p));
    const sm = document.createElement("small"); sm.textContent = "%"; $("#ash-num").append(sm);
    const top = 158 - 84 * ((p ?? 0) / 100);
    const r = $("#ash-fill");
    r.setAttribute("y", top.toFixed(1)); r.setAttribute("height", (158 - top).toFixed(1));
    const txt = [];
    if (p == null) txt.push(t("ashUnknown"));
    if (fresh && s) txt.push(s.ash_cool ? t("ashCool") : t("ashHot"));
    $("#ash-text").textContent = txt.join("。");
  }

  function renderSlips() {
    if (!slips) return;
    const list = store.events.filter((e) => e._kind !== "ack" && (!isPublic || e.src === "r4")).slice(-8).reverse();
    const ol = $("#slips");
    if (!ol) return;
    if (!list.length) {
      const li = document.createElement("li"); li.className = "empty-slip"; li.textContent = t("storyEmpty");
      ol.replaceChildren(li); return;
    }
    ol.replaceChildren(...list.map((e) => {
      const li = document.createElement("li");
      const tm = document.createElement("time"); tm.textContent = fmtClock(e._t);
      const m = document.createElement("span"); m.textContent = e.msg;
      li.append(tm, m); return li;
    }));
  }

  function renderLive() {
    const el = $("#live");
    const a = age("sensor");
    if (!store.connected) { el.dataset.state = "down"; el.textContent = t("down"); }
    else if (a < FRESH_S) { el.dataset.state = "live"; el.textContent = t("live"); }
    else if (a < 30) { el.dataset.state = "stale"; el.textContent = t("stale", { s: Math.round(a) }); }
    else if (a === Infinity) { el.dataset.state = "stale"; el.textContent = t("waiting"); }
    else { el.dataset.state = "down"; el.textContent = t("offline", { t: fmtClock(store.latest.sensor._t) }); }
  }

  function renderCams() {
    cams.update(store.latest.vision, age("vision") < VISION_FRESH_S);
  }

  function renderAll() {
    applyStatic();
    renderAir(); renderNow(); renderAsh(); renderSlips(); renderLive(); renderCams();
    co2Chart.set(store.hist);
  }

  let chartDue = 0;
  onUpdate((kind) => {
    if (kind === "snapshot") return renderAll();
    if (kind === "sensor") {
      renderAir(); renderNow(); renderAsh(); renderLive();
      const now = performance.now();
      if (now > chartDue) { chartDue = now + 2000; co2Chart.set(store.hist); }
    } else if (kind === "decision") renderAir();
    else if (kind === "robot") renderNow();
    else if (kind === "vision") { renderCams(); const r = robotNow(); if (r && r.station === "TABLE") renderNow(); }
    else if (kind === "event") renderSlips();
    else if (kind === "conn" || kind === "tick") renderLive();
  });
  setInterval(() => { renderLive(); renderCams(); }, 1000);

  // 深淺色切換：系統預設 → 手動切換後記住
  const root = document.documentElement;
  try { const th = localStorage.getItem("keeper-theme"); if (th) root.dataset.theme = th; } catch (_) {}
  $("#theme").addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("keeper-theme", root.dataset.theme); } catch (_) {}
    smoke.retheme(); co2Chart.redraw(); renderCams();
  });

  const langBtn = $("#lang");
  if (langBtn) {
    const syncLang = () => {
      langBtn.textContent = getLang() === "en" ? "中" : "EN";
      langBtn.setAttribute("aria-label", getLang() === "en" ? "切換成中文" : "Switch to English");
    };
    langBtn.addEventListener("click", () => { setLang(getLang() === "en" ? "zh" : "en"); syncLang(); field.labels(); renderAll(); });
    setLang(getLang()); syncLang(); field.labels();
  } else applyStatic();

  renderAll();
  return { renderAll, field, cams, co2Chart };
}
