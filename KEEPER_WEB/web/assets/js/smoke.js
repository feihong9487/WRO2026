// smoke.js — 背景香煙：一縷一縷裊裊往上的煙絲
// 每炷香冒出幾縷煙絲：靠近香頭細而直，越往上越寬、越淡，波紋沿著煙絲往上爬。
// density 0~1：CO2 高於背景越多，煙絲越多越濃。draft 0~1：風扇越快，煙越往右邊（集煙塔）飄。
// 30 fps 上限、分頁看不到時暫停、「減少動態效果」時只畫一張靜態畫面。

const reduce = matchMedia("(prefers-reduced-motion: reduce)");

export function startSmoke(canvas) {
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0, dpr = 1, running = false, last = 0, t = 0;
  let density = 0.3, draft = 0.2;
  const target = { density, draft };
  let rgb = "222,210,190";
  let strands = [];

  function smokeRGB() {
    return getComputedStyle(document.documentElement).getPropertyValue("--smoke").trim() || "222,210,190";
  }

  // 香的位置在畫面底部。手機一炷、桌面三炷；每炷三縷煙絲，依 density 決定冒幾縷
  function layout() {
    const xs = W < 700 ? [0.5] : [0.16, 0.5, 0.84];
    strands = [];
    xs.forEach((fx) => {
      for (let k = 0; k < 3; k++) {
        strands.push({
          x0: fx * W + (k - 1) * 5,
          phase: Math.random() * 6.28 + k * 2.1,
          speed: 1.5 + Math.random() * 0.5 + k * 0.25,   // 每縷上升速度略不同，才不會疊成一條
          k, pts: [],
        });
      }
    });
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    layout();
  }

  // 高度 h 處的左右擺動：越高擺越大；(h·k − t·w) 讓波紋往上爬
  function sway(h, phase) {
    const f = Math.min(1, h / (H * 0.9));
    const amp = 3 + 75 * Math.pow(f, 1.6);
    return amp * (Math.sin(h * 0.011 - t * 0.0016 + phase) + 0.45 * Math.sin(h * 0.029 - t * 0.0027 + phase * 1.7));
  }
  const xAt = (s, h) => s.x0 + sway(h, s.phase) + draft * Math.pow(h, 1.25) * 0.09;

  function step(dt) {
    density += (target.density - density) * 0.03;
    draft += (target.draft - draft) * 0.03;
    const k = dt / 33;
    const active = 1 + Math.round(density * 2);   // 每炷 1~3 縷
    const top = H * (0.55 + density * 0.4);        // 煙越濃飄得越高
    for (const s of strands) {
      if (s.k < active) s.pts.push({ h: 0 });      // 每格冒一點，連起來就是一縷
      for (const p of s.pts) p.h += s.speed * k * (1 + p.h / H * 0.6);
      while (s.pts.length && s.pts[0].h > top) s.pts.shift();
    }
  }

  function drawStrand(s) {
    const n = s.pts.length;
    if (n < 3) return;
    const top = H * (0.55 + density * 0.4);
    const base = 0.10 + density * 0.22;
    const BAND = 10;
    // 從最高（最舊）往香頭畫，分段設定粗細與透明度
    for (let i = 0; i < n - 1; i += BAND) {
      const j = Math.min(n - 1, i + BAND);
      const hMid = s.pts[Math.floor((i + j) / 2)].h;
      const f = hMid / top;
      const fadeIn = Math.min(1, hMid / 40);
      const a = base * Math.pow(1 - f, 1.4) * fadeIn;
      if (a < 0.004) continue;
      const w = 1 + 9 * Math.pow(f, 1.3);
      ctx.beginPath();
      ctx.moveTo(xAt(s, s.pts[i].h), H - s.pts[i].h);
      for (let m = i + 1; m <= j; m++) ctx.lineTo(xAt(s, s.pts[m].h), H - s.pts[m].h);
      ctx.strokeStyle = `rgba(${rgb},${(a * 0.28).toFixed(3)})`;   // 外層柔光，越高散得越開
      ctx.lineWidth = w * (3 + 3 * f);
      ctx.stroke();
      ctx.strokeStyle = `rgba(${rgb},${a.toFixed(3)})`;            // 煙絲本體
      ctx.lineWidth = w;
      ctx.stroke();
    }
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.lineCap = "butt"; ctx.lineJoin = "round";   // 平頭：分段接點才不會疊出一顆顆亮點
    for (const s of strands) drawStrand(s);
  }

  function frame(time) {
    if (!running) return;
    const dt = Math.min(66, time - (last || time));
    if (dt >= 32 || !last) {                       // 約 30 fps
      last = time; t = time;
      step(dt || 33);
      draw();
    }
    requestAnimationFrame(frame);
  }

  // 減少動態效果：一次長滿煙絲，只畫一張
  function staticScene() {
    density = target.density; draft = target.draft;
    for (const s of strands) s.pts = [];
    for (let i = 0; i < 400; i++) step(33);
    draw();
  }

  function start() {
    if (reduce.matches) { running = false; staticScene(); return; }
    if (running) return;
    running = true; last = 0;
    requestAnimationFrame(frame);
  }

  rgb = smokeRGB(); resize();
  for (let i = 0; i < 260; i++) step(33);          // 一打開就有煙，不用等它長上來
  start();
  addEventListener("resize", () => { resize(); if (reduce.matches) staticScene(); });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) running = false; else start();
  });
  reduce.addEventListener("change", () => { running = false; start(); });
  matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => { rgb = smokeRGB(); });

  return {
    set(d, f) {
      target.density = Math.max(0, Math.min(1, d));
      target.draft = Math.max(0, Math.min(1, f));
      if (reduce.matches) staticScene();
    },
    retheme() { rgb = smokeRGB(); if (reduce.matches) staticScene(); },
  };
}
