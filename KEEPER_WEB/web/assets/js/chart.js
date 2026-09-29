// chart.js — 小型折線圖（Canvas）
// 單一 Y 軸、2px 線、淡格線；滑過或點一下顯示十字線與數值；可加一條虛線參考線（例如 CO2 背景值）。

import { fmtClock } from "./live.js";

function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

export function createChart(box, { series, unit, ref, span = 1800, digits = 0, empty }) {
  const canvas = box.querySelector("canvas");
  const tip = box.querySelector(".tip");
  const emptyEl = box.querySelector(".chart-empty");
  const ctx = canvas.getContext("2d");
  let data = [], hover = null, W = 0, H = 0;
  const pad = { l: 46, r: 12, t: 12, b: 26 };

  function fit() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function draw() {
    if (!W) fit();
    ctx.clearRect(0, 0, W, H);
    const pts = data.filter((d) => series.some((s) => typeof d[s.key] === "number"));
    const has = pts.length >= 2;
    if (emptyEl) emptyEl.hidden = has;
    canvas.style.visibility = has ? "visible" : "hidden";
    if (!has) return;

    const t1 = pts[pts.length - 1].t, t0 = t1 - span;
    let lo = Infinity, hi = -Infinity;
    for (const d of pts) for (const s of series) {
      const v = d[s.key]; if (typeof v === "number") { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    }
    if (ref) for (const d of pts) { const v = d[ref.key]; if (typeof v === "number") { lo = Math.min(lo, v); hi = Math.max(hi, v); } }
    const padV = Math.max((hi - lo) * 0.15, ref && ref.minSpan ? ref.minSpan / 2 : 1);
    lo -= padV; hi += padV;
    const x = (tt) => pad.l + ((tt - t0) / span) * (W - pad.l - pad.r);
    const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);

    // 格線與刻度
    ctx.font = '12px "Noto Sans TC", sans-serif';
    ctx.fillStyle = css("--ink-3");
    ctx.strokeStyle = css("--gold-faint"); ctx.lineWidth = 1;
    for (let i = 0; i <= 3; i++) {
      const v = lo + ((hi - lo) * i) / 3, yy = y(v);
      ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(W - pad.r, yy); ctx.stroke();
      ctx.textAlign = "right"; ctx.fillText(v.toFixed(digits), pad.l - 8, yy + 4);
    }
    ctx.textAlign = "center";
    const step = 300;
    for (let tt = Math.ceil(t0 / step) * step; tt <= t1; tt += step) ctx.fillText(fmtClock(tt), x(tt), H - 6);

    // 參考線（虛線）
    if (ref) {
      ctx.setLineDash([5, 5]); ctx.strokeStyle = css("--ink-3"); ctx.lineWidth = 1.5;
      ctx.beginPath(); let started = false;
      for (const d of pts) {
        const v = d[ref.key]; if (typeof v !== "number" || d.t < t0) continue;
        if (!started) { ctx.moveTo(x(d.t), y(v)); started = true; } else ctx.lineTo(x(d.t), y(v));
      }
      ctx.stroke(); ctx.setLineDash([]);
    }
    // 資料線：中斷超過 10 秒就斷開，不把沒資料的時間連起來
    for (const s of series) {
      ctx.strokeStyle = css(s.color) || s.color; ctx.lineWidth = 2; ctx.lineJoin = "round";
      ctx.beginPath(); let prev = null;
      for (const d of pts) {
        const v = d[s.key]; if (typeof v !== "number" || d.t < t0) { prev = null; continue; }
        if (prev && d.t - prev.t < 10) ctx.lineTo(x(d.t), y(v)); else ctx.moveTo(x(d.t), y(v));
        prev = d;
      }
      ctx.stroke();
    }
    // 十字線與數值
    if (hover != null) {
      const tt = t0 + ((hover - pad.l) / (W - pad.l - pad.r)) * span;
      let best = null;
      for (const d of pts) if (!best || Math.abs(d.t - tt) < Math.abs(best.t - tt)) best = d;
      if (best) {
        const xx = x(best.t);
        ctx.strokeStyle = css("--gold-line"); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(xx, pad.t); ctx.lineTo(xx, H - pad.b); ctx.stroke();
        const lines = [fmtClock(best.t)];
        for (const s of series) {
          const v = best[s.key]; if (typeof v !== "number") continue;
          ctx.fillStyle = css(s.color) || s.color;
          ctx.beginPath(); ctx.arc(xx, y(v), 4.5, 0, Math.PI * 2); ctx.fill();
          ctx.strokeStyle = css("--bg-2"); ctx.lineWidth = 2; ctx.stroke();
          lines.push(`${s.label} ${v.toFixed(digits)} ${unit}`);
        }
        if (ref && typeof best[ref.key] === "number") lines.push(`${ref.label} ${best[ref.key].toFixed(digits)} ${unit}`);
        tip.textContent = lines.join("　");
        tip.style.left = `${Math.max(80, Math.min(W - 80, xx))}px`;
        tip.style.top = `${pad.t + 8}px`;
        tip.hidden = false;
      }
    } else tip.hidden = true;
  }

  function point(e) { const r = canvas.getBoundingClientRect(); hover = e.clientX - r.left; draw(); }
  canvas.addEventListener("pointermove", point);
  canvas.addEventListener("pointerdown", point);
  canvas.addEventListener("pointerleave", () => { hover = null; draw(); });
  addEventListener("resize", () => { fit(); draw(); });
  if (emptyEl && empty) emptyEl.textContent = empty;

  return {
    set(rows) { data = rows; draw(); },
    redraw() { draw(); },
  };
}
