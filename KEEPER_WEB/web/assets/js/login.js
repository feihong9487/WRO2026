// login.js — 團隊台登入
import { startSmoke } from "./smoke.js";

startSmoke(document.querySelector("#smoke")).set(0.35, 0.1);

try { const th = localStorage.getItem("keeper-theme"); if (th) document.documentElement.dataset.theme = th; } catch (_) {}

const form = document.querySelector("#form");
const user = document.querySelector("#user"), pw = document.querySelector("#pw");
const userErr = document.querySelector("#user-err"), pwErr = document.querySelector("#pw-err");
const submit = document.querySelector("#submit");
const toggle = document.querySelector("#pw-toggle");

toggle.addEventListener("click", () => {
  const show = pw.type === "password";
  pw.type = show ? "text" : "password";
  toggle.textContent = show ? "隱藏" : "顯示";
  toggle.setAttribute("aria-pressed", String(show));
});

function setErr(input, el, msg) {
  el.textContent = msg;
  input.setAttribute("aria-invalid", msg ? "true" : "false");
}

// 已經登入就直接進團隊台
fetch("/api/me", { credentials: "same-origin" }).then((r) => { if (r.ok) location.replace("/team"); }).catch(() => {});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  setErr(user, userErr, ""); setErr(pw, pwErr, "");
  if (!user.value.trim()) { setErr(user, userErr, "請輸入帳號"); user.focus(); return; }
  if (!pw.value) { setErr(pw, pwErr, "請輸入密碼"); pw.focus(); return; }
  submit.setAttribute("aria-busy", "true"); submit.disabled = true;
  try {
    const r = await fetch("/api/login", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Keeper": "1" },
      body: JSON.stringify({ user: user.value.trim(), password: pw.value }),
    });
    const j = await r.json().catch(() => ({}));
    if (r.ok) { location.replace("/team"); return; }
    const target = j.field === "user" ? [user, userErr] : [pw, pwErr];
    setErr(target[0], target[1], j.error || "登入失敗，請再試一次");
    target[0].focus();
  } catch (_) {
    setErr(pw, pwErr, "連不上伺服器，請確認網路後再試");
  } finally {
    submit.removeAttribute("aria-busy"); submit.disabled = false;
  }
});
