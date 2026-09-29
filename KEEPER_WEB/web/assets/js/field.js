// field.js — 工字形場地圖（A0 1189 × 841 mm，座標單位就是 mm）
// R4 沒有里程計，只回報路段與第幾步，所以位置是依路線表與時間推算的，畫面上會註明。

import { t, isMoving } from "./words.js";

const NS = "http://www.w3.org/2000/svg";
const END = { DOCK: [275, 680], TABLE: [914, 210], BURNER: [275, 210], ASH: [914, 680] };
// 站點圖示畫在線尾外側（實際站點約在線尾外 90 mm），往外多挪一點，停車時才不會和機器人疊在一起
const STN = { BURNER: [160, 210], TABLE: [1029, 210], DOCK: [160, 680], ASH: [1029, 680] };
// 每一段的路點。第 k 步（從 1 算）是從路點 k-1 走到路點 k
const LEGS = {
  "DOCK>TABLE": { pts: [[275, 680], [594, 680], [594, 210], [914, 210]], turn180: true },
  "TABLE>BURN": { pts: [[914, 210], [594, 210], [275, 210]], turn180: false },
  "BURN>TABLE": { pts: [[275, 210], [594, 210], [914, 210]], turn180: true },
  "TABLE>ASH":  { pts: [[914, 210], [594, 210], [594, 680], [914, 680]], turn180: false },
  "ASH>DOCK":   { pts: [[914, 680], [594, 680], [275, 680]], turn180: false },
};
const SPEED_MM_S = 170;           // 估計的循線速度，只影響動畫

const ICONS = {
  DOCK: '<path class="ic" d="M6 -26 L-12 4 H2 L-6 26 L14 -6 H0 Z"/>',
  TABLE: '<path class="ic" d="M-26 -4 H26 M-20 -4 V22 M20 -4 V22"/><ellipse class="ic" cx="0" cy="-14" rx="16" ry="5"/>',
  BURNER: '<path class="ic" d="M-22 -6 H22 Q20 16 0 18 Q-20 16 -22 -6 Z M-22 -2 Q-30 -2 -28 -10 M22 -2 Q30 -2 28 -10 M-12 17 L-15 26 M12 17 L15 26 M-6 -8 L-9 -26 M0 -8 V-28 M6 -8 L9 -26"/>',
  ASH: '<path class="ic" d="M-18 -10 H18 L14 24 H-14 Z M-24 -16 H24 M-6 -22 H6"/>',
};

function el(name, attrs = {}, parent) {
  const e = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
const pathOf = (pts) => "M" + pts.map((p) => p.join(" ")).join(" L");
const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);
const lerp = (a, b, f) => [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
const angle = (a, b) => (Math.atan2(b[1] - a[1], b[0] - a[0]) * 180) / Math.PI;

export function createField(svg) {
  svg.setAttribute("viewBox", "0 0 1189 841");
  svg.setAttribute("role", "img");
  el("rect", { x: 8, y: 8, width: 1173, height: 825, rx: 18, fill: "none", stroke: "var(--gold-line)", "stroke-width": 2 }, svg);
  el("path", { class: "trk trk-draw", d: "M275 210 H914 M594 210 V680 M275 680 H914" }, svg);
  const legPath = el("path", { class: "leg-path", d: "" }, svg);
  const donePath = el("path", { class: "leg-done", d: "" }, svg);

  const stnEls = {};
  for (const [k, [x, y]] of Object.entries(STN)) {
    const g = el("g", { class: "stn", transform: `translate(${x} ${y})` }, svg);
    el("circle", { class: "pad", r: 56 }, g);
    g.insertAdjacentHTML("beforeend", ICONS[k]);
    const ly = y < 400 ? 106 : -112;
    const zh = el("text", { y: ly }, g);
    const en = el("text", { class: "en", y: ly + 30 }, g);
    stnEls[k] = { g, zh, en };
  }

  const bot = el("g", { class: "bot" }, svg);
  el("circle", { class: "bot-halo", r: 78 }, bot);
  const body = el("g", {}, bot);
  el("rect", { class: "bot-body", x: -50, y: -38, width: 100, height: 76, rx: 16 }, body);
  el("path", { class: "bot-nose", d: "M28 -17 L52 0 L28 17 Z" }, body);

  let pos = END.DOCK.slice(), heading = 0;
  let key = "", t0 = 0, raf = 0, cur = null;

  function labels() {
    for (const [k, o] of Object.entries(stnEls)) {
      o.zh.textContent = t("stn." + k);
      const en = t("stnEn." + k);
      o.en.textContent = en.startsWith("stnEn.") ? "" : en;
    }
  }
  labels();

  function place() {
    bot.setAttribute("transform", `translate(${pos[0].toFixed(1)} ${pos[1].toFixed(1)})`);
    body.setAttribute("transform", `rotate(${heading.toFixed(1)})`);
  }

  function frame() {
    raf = 0;
    if (!cur) return;
    const { leg, k } = cur;
    const a = leg.pts[k - 1], b = leg.pts[k];
    const len = dist(a, b);
    const f = Math.min(0.94, ((performance.now() - t0) / 1000) * SPEED_MM_S / len);
    pos = lerp(a, b, f);
    heading = angle(a, b);
    donePath.setAttribute("d", pathOf([...leg.pts.slice(0, k), pos]));
    place();
    if (f < 0.94) raf = requestAnimationFrame(frame);
  }

  function update(s) {
    cancelAnimationFrame(raf); raf = 0;
    for (const [k, o] of Object.entries(stnEls)) o.g.classList.toggle("active", !!s && s.station === k);
    const legInfo = s && LEGS[s.leg];
    const moving = !!s && isMoving(s.robot);
    bot.classList.toggle("moving", moving);
    bot.classList.toggle("fail", !!s && s.robot === "FAIL");
    legPath.classList.toggle("moving", moving);
    if (!s) { cur = null; return; }

    if (legInfo && s.mission) legPath.setAttribute("d", pathOf(legInfo.pts));
    else { legPath.setAttribute("d", ""); donePath.setAttribute("d", ""); }

    const k = Math.max(1, Math.min(s.step || 1, legInfo ? legInfo.pts.length - 1 : 1));
    const newKey = `${s.leg}/${k}`;
    if (legInfo && moving && !(s.robot === "SPIN" && k === 1 && key !== newKey)) {
      if (newKey !== key) { key = newKey; t0 = performance.now(); }
      cur = { leg: legInfo, k };
      frame();
      return;
    }
    cur = null;
    if (legInfo && s.robot === "SPIN") {                 // 出發前原地迴轉
      pos = legInfo.pts[0].slice();
      key = "";
    } else if (s.station && END[s.station]) {
      const arrived = legInfo && legInfo.pts[legInfo.pts.length - 1];
      pos = END[s.station].slice();
      if (arrived && key.startsWith(s.leg + "/")) {
        const p = legInfo.pts;
        heading = angle(p[p.length - 2], p[p.length - 1]) + (legInfo.turn180 ? 180 : 0);
        donePath.setAttribute("d", pathOf(p));
      }
      key = s.leg ? `${s.leg}/done` : "";
    }
    place();
  }

  place();
  return { update, labels };
}
