// cams.js — 兩顆相機的示意畫面
// 相機本身不傳影像（WiFi 頻寬只夠傳辨識結果），這裡依回傳的框框座標在 320 × 240 的畫面上重畫。
// M-Vision 與 HuskyLens 回傳的都是「中心點 x、y ＋寬、高」。

import { t } from "./words.js";

const W = 320, H = 240;
const reduce = matchMedia("(prefers-reduced-motion: reduce)");

function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

function setup(canvas) {
  const ctx = canvas.getContext("2d");
  function fit() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth || W;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(w * 0.75 * dpr);
    ctx.setTransform(canvas.width / W, 0, 0, canvas.height / H, 0, 0);
  }
  fit();
  return { ctx, fit };
}

function label(ctx, text, x, y, color) {
  ctx.font = '600 11px "Noto Sans TC", sans-serif';
  const w = ctx.measureText(text).width + 10;
  const lx = Math.max(2, Math.min(W - w - 2, x - w / 2));
  const ly = Math.max(2, y);
  ctx.fillStyle = color;
  ctx.fillRect(lx, ly, w, 16);
  ctx.fillStyle = "#fff";
  ctx.fillText(text, lx + 5, ly + 12);
}

function brackets(ctx, x, y, w, h, color) {
  const l = Math.min(12, w / 3, h / 3);
  ctx.strokeStyle = color; ctx.lineWidth = 2.5;
  ctx.beginPath();
  for (const [cx, cy, dx, dy] of [[x, y, 1, 1], [x + w, y, -1, 1], [x, y + h, 1, -1], [x + w, y + h, -1, -1]]) {
    ctx.moveTo(cx + dx * l, cy); ctx.lineTo(cx, cy); ctx.lineTo(cx, cy + dy * l);
  }
  ctx.stroke();
}

export function createCams({ mvCanvas, hlCanvas, mvEmpty, hlEmpty, mvChips, hlChips }) {
  const mv = setup(mvCanvas), hl = setup(hlCanvas);
  let lastMv = null, lastHl = null, scan = 0, raf = 0;

  function drawTable(v, sweep) {
    const c = mv.ctx;
    c.clearRect(0, 0, W, H);
    c.fillStyle = css("--table"); c.fillRect(0, 0, W, H);
    c.strokeStyle = "rgba(120,90,60,.12)"; c.lineWidth = 1;
    for (let x = 40; x < W; x += 40) { c.beginPath(); c.moveTo(x, 0); c.lineTo(x, H); c.stroke(); }
    for (let y = 40; y < H; y += 40) { c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke(); }
    if (!v) return;
    const red = "#c0392b", green = "#1f8a5b";
    if (v.f & 1) {
      const [x, y, w, h] = v.p, r = Math.max(w, h) / 2;
      c.fillStyle = "rgba(192,57,43,.14)"; c.strokeStyle = red; c.lineWidth = 3;
      c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fill(); c.stroke();
      label(c, t("plate"), x, y - r - 18, red);
    }
    if (v.f & 2) {
      const [x, y, w, h] = v.t;
      c.fillStyle = "rgba(31,138,91,.18)"; c.fillRect(x - w / 2, y - h / 2, w, h);
      brackets(c, x - w / 2 - 4, y - h / 2 - 4, w + 8, h + 8, green);
      label(c, t("target"), x, y + h / 2 + 8, green);
    }
    if (sweep != null) {                         // 掃描線：代表相機正在即時辨識
      const g = c.createLinearGradient(0, sweep - 18, 0, sweep);
      g.addColorStop(0, "rgba(217,167,67,0)"); g.addColorStop(1, "rgba(217,167,67,.35)");
      c.fillStyle = g; c.fillRect(0, sweep - 18, W, 18);
    }
  }

  function drawStrip(v) {
    const c = hl.ctx;
    c.clearRect(0, 0, W, H);
    c.fillStyle = "#2a2522"; c.fillRect(0, 0, W, H);
    if (!v || !v.b) { c.fillStyle = "#6f6862"; c.fillRect(0, H * 0.78, W, H * 0.22); return; }
    const [x, y, w, h] = v.b;
    // 香灰：從灰面（色條下緣）往下都是灰
    c.fillStyle = "#6f6862"; c.fillRect(0, y + h / 2, W, H - (y + h / 2));
    const gold = css("--gold") || "#d9a743";
    c.fillStyle = "rgba(217,167,67,.30)"; c.fillRect(x - w / 2, y - h / 2, w, h);
    c.strokeStyle = gold; c.lineWidth = 2.5; c.strokeRect(x - w / 2, y - h / 2, w, h);
    label(c, `${t("strip")} ${h}px`, x, y - h / 2 - 20, "#8a6414");
    const surf = y + h / 2;                      // 色條下緣＝灰面
    c.setLineDash([6, 5]); c.strokeStyle = "#f3e7cf"; c.lineWidth = 2;
    c.beginPath(); c.moveTo(0, surf); c.lineTo(W, surf); c.stroke(); c.setLineDash([]);
    label(c, t("ashLine"), W - 40, surf + 6, "#5b524b");
  }

  function chips(elm, items) {
    elm.replaceChildren(...items.map(([sw, k, v]) => {
      const s = document.createElement("span");
      s.className = "chip";
      if (sw) { const i = document.createElement("i"); i.className = "swatch"; i.style.background = sw; s.append(i); }
      s.append(k + " ");
      const b = document.createElement("b"); b.textContent = v; s.append(b);
      return s;
    }));
  }

  function loop() {
    raf = 0;
    if (!lastMv || reduce.matches || document.hidden) return;
    scan = (scan + 2.2) % (H + 20);
    drawTable(lastMv, scan);
    raf = requestAnimationFrame(loop);
  }

  function update(vision, fresh) {
    const m = fresh && vision && vision.mv && vision.mv.ok ? vision.mv : null;
    const h = fresh && vision && vision.hl && vision.hl.ok ? vision.hl : null;
    mvEmpty.hidden = !!m; hlEmpty.hidden = !!h;
    lastMv = m; lastHl = h;
    if (m) {
      if (!raf) loop();
      if (reduce.matches) drawTable(m, null);
      chips(mvChips, [
        ["#c0392b", t("plate"), m.f & 1 ? "✓" : "—"],
        ["#1f8a5b", t("outside"), String(m.no ?? 0)],
        [null, t("onPlate"), String(m.ni ?? 0)],
      ]);
    } else { cancelAnimationFrame(raf); raf = 0; drawTable(null); mvChips.replaceChildren(); }
    drawStrip(h);
    if (h) chips(hlChips, [[null, t("strip"), h.b ? `${h.b[3]} px` : "—"], [null, t("blocks"), String(h.n ?? 0)]]);
    else hlChips.replaceChildren();
  }

  addEventListener("resize", () => { mv.fit(); hl.fit(); drawTable(lastMv); drawStrip(lastHl); });
  drawTable(null); drawStrip(null);
  return { update };
}
