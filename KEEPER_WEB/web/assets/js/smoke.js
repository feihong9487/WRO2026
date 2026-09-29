// smoke.js — 背景香煙
// density 0~1：CO2 高於背景越多，煙越濃。draft 0~1：風扇越快，煙越往右邊（集煙塔）飄。
// 30 fps 上限、分頁看不到時暫停、「減少動態效果」時只畫一張靜態畫面。

const reduce = matchMedia("(prefers-reduced-motion: reduce)");

export function startSmoke(canvas) {
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0, dpr = 1, sprite = null, running = false, last = 0, acc = 0;
  let density = 0.25, draft = 0.2, target = { density, draft };
  const parts = [];
  const MAX = 420;

  function smokeRGB() {
    return getComputedStyle(document.documentElement).getPropertyValue("--smoke").trim() || "222,210,190";
  }
  function makeSprite() {
    const s = document.createElement("canvas");
    s.width = s.height = 128;
    const g = s.getContext("2d");
    const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    const c = smokeRGB();
    grad.addColorStop(0, `rgba(${c},0.42)`);
    grad.addColorStop(0.4, `rgba(${c},0.14)`);
    grad.addColorStop(1, `rgba(${c},0)`);
    g.fillStyle = grad;
    g.fillRect(0, 0, 128, 128);
    sprite = s;
  }
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // 三炷香的位置（畫面底部），手機只留中間一炷
  function sources() {
    return W < 700 ? [0.5] : [0.22, 0.5, 0.78];
  }
  function spawn() {
    const src = sources();
    const x = src[(Math.random() * src.length) | 0] * W + (Math.random() - 0.5) * 16;
    parts.push({
      x, y: H + 10, r: 3 + Math.random() * 3,
      vx: (Math.random() - 0.5) * 0.08, vy: -(0.7 + Math.random() * 0.45),
      life: 0, max: 420 + Math.random() * 360, seed: Math.random() * 1000,
    });
  }
  function step(dt, time) {
    density += (target.density - density) * 0.02;
    draft += (target.draft - draft) * 0.02;
    acc += dt * (0.08 + density * 0.5);          // 每毫秒產生的煙量
    while (acc > 1 && parts.length < MAX) { spawn(); acc -= 1; }
    if (acc > 1) acc = 1;
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i];
      const k = dt / 16.7;
      const wob = Math.sin(p.y * 0.006 + time * 0.0006 + p.seed) + 0.5 * Math.sin(p.y * 0.013 + p.seed * 2);
      p.vx += (wob * 0.012 + draft * 0.018) * k;
      p.vx *= 0.985;
      p.x += p.vx * k; p.y += p.vy * k;
      p.r += (0.06 + p.life / p.max * 0.28) * k;     // 先細後散，像香煙往上擴散
      p.life += k;
      if (p.life > p.max || p.y < -120 || p.x > W + 150) parts.splice(i, 1);
    }
  }
  function draw() {
    ctx.clearRect(0, 0, W, H);
    for (const p of parts) {
      const f = p.life / p.max;
      const a = Math.min(1, f * 5) * (1 - f) * (1 - f) * (0.10 + density * 0.22);
      if (a <= 0.01) continue;
      ctx.globalAlpha = a;
      const s = p.r * 2;
      ctx.drawImage(sprite, p.x - p.r, p.y - p.r, s, s);
    }
    ctx.globalAlpha = 1;
  }
  function frame(time) {
    if (!running) return;
    const dt = Math.min(64, time - (last || time));
    if (dt >= 32 || !last) {                       // 約 30 fps
      last = time;
      step(dt || 16, time);
      draw();
    }
    requestAnimationFrame(frame);
  }
  function staticScene() {
    parts.length = 0;
    for (let i = 0; i < 90; i++) {
      spawn();
      const p = parts[parts.length - 1];
      p.life = Math.random() * p.max * 0.8;
      p.y = H - p.life * 0.8; p.r += p.life * 0.2;
      p.x += Math.sin(p.seed) * 40 + draft * p.life * 0.15;
    }
    draw();
  }
  function start() {
    if (reduce.matches) { running = false; staticScene(); return; }
    if (running) return;
    running = true; last = 0;
    requestAnimationFrame(frame);
  }

  resize(); makeSprite(); start();
  addEventListener("resize", () => { resize(); if (reduce.matches) staticScene(); });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) running = false; else start();
  });
  reduce.addEventListener("change", () => { running = false; start(); });
  matchMedia("(prefers-color-scheme: light)").addEventListener("change", makeSprite);

  return {
    set(d, f) {
      target.density = Math.max(0, Math.min(1, d));
      target.draft = Math.max(0, Math.min(1, f));
      if (reduce.matches) { density = target.density; draft = target.draft; staticScene(); }
    },
    retheme() { makeSprite(); if (reduce.matches) staticScene(); },
  };
}
