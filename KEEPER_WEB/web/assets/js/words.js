// words.js — 介面文字（中文為主，公開頁可切英文）與「機器人正在做什麼」的敘述

const T = {
  zh: {
    title: "廟公機器人",
    sub: "WRO 2026 未來創新組，守護香火的巡廟機器人",
    air: "空氣", fanL: "集煙",
    eyeTable: "供桌之眼", eyeTableSrc: "M-Vision，車尾",
    eyeAsh: "香灰之眼", eyeAshSrc: "HuskyLens，看香爐色條",
    ashTitle: "香灰高度",
    co2Title: "空氣中的 CO2，近 30 分鐘",
    co2Hint: "虛線是背景值：沒有人時空氣的底",
    storyTitle: "今日紀事",
    storyEmpty: "機器人還沒出任務，出發後這裡會記下每一站",
    live: "即時", stale: "{s} 秒前", down: "連線中斷，重新連線中", waiting: "等待機器人上線",
    offline: "機器人離線，最後更新 {t}",
    mvEmpty: "供桌相機沒有送資料", hlEmpty: "香灰相機沒有送資料",
    plate: "供盤", target: "要夾回的供品", onPlate: "盤上", outside: "盤外", noPlate: "沒看到供盤",
    strip: "色條", ashLine: "灰面", blocks: "色塊", photo: "畫面", photoAge: "{s} 秒前",
    ashUnknown: "還沒校正，或看不到色條",
    ashCool: "香灰已冷，可以整平", ashHot: "香灰溫度未確認，不挖灰",
    mapNote: "位置依路線表推算",
    foot1: "背景香煙的濃淡代表目前 CO2 高於背景的程度；風扇轉得越快，煙越往集煙塔飄。",
    foot2: "資料每秒更新：R4 經 WiFi 傳到筆電中繼，再經 Tailscale 送到這台伺服器。",
    co2Fresh: "清新", co2Busy: "香火正旺", co2High: "煙太濃，全速排煙",
    st: { S0: "待機", S1: "常態換氣", S2: "高峰排煙", S3: "安全停機" },
    stNote: { S0: "沒有人，風扇休息", S1: "溫和換氣", S2: "人多香旺，加大抽風", S3: "安全檢查未通過，風扇停止" },
    stn: { DOCK: "充電座", TABLE: "供桌", BURNER: "香爐", ASH: "倒灰區", NONE: "" },
    stnEn: { DOCK: "Dock", TABLE: "Offering table", BURNER: "Incense burner", ASH: "Ash bin" },
    mission: { MORNING: "早上任務", EVENING: "晚上任務" },
    purpose: { TABLE: "整理掉落的供品", BURNER: "收集香煙、查看香灰", ASH: "倒掉多的香灰", DOCK: "回去充電" },
    nowIdle: "在{s}待命", nowIdleHome: "在充電座待命",
    nowGo: "正在前往{d}，{p}", nowSpin: "原地迴轉，準備出發", nowFind: "尋找黑線",
    nowCal: "正在校正循線感測器", nowView: "正在檢查循線感測器",
    nowTable: "停在供桌前：盤外有 {n} 個供品要夾回", nowTableClear: "停在供桌前：供品都在盤上",
    nowTableNoCam: "停在供桌前，整理供品",
    nowBurner: "停在香爐旁收集香煙，香灰 {a}", nowAsh: "停在倒灰區", nowDock: "回到充電座",
    nowFail: "任務暫停，團隊正在處理", nowOffline: "機器人目前離線",
    subMission: "{m}，第 {i} 段：{leg}",
  },
  en: {
    title: "Temple Keeper",
    sub: "WRO 2026 Future Innovators: a robot that looks after a temple's incense burner",
    air: "Air", fanL: "Smoke fan",
    eyeTable: "Offering table camera", eyeTableSrc: "M-Vision, rear",
    eyeAsh: "Ash camera", eyeAshSrc: "HuskyLens, reads a colour strip",
    ashTitle: "Ash level",
    co2Title: "CO2 in the air, last 30 minutes",
    co2Hint: "Dashed line: background level when nobody is around",
    storyTitle: "Today's log",
    storyEmpty: "No mission yet. Each stop will be logged here.",
    live: "Live", stale: "{s} s ago", down: "Connection lost, reconnecting", waiting: "Waiting for the robot",
    offline: "Robot offline, last update {t}",
    mvEmpty: "Table camera is not sending data", hlEmpty: "Ash camera is not sending data",
    plate: "Plate", target: "Offering to pick up", onPlate: "On plate", outside: "Off plate", noPlate: "No plate in view",
    strip: "Strip", ashLine: "Ash surface", blocks: "Blocks", photo: "Photo", photoAge: "{s} s ago",
    ashUnknown: "Not calibrated, or the strip is not visible",
    ashCool: "Ash is cool, safe to level", ashHot: "Ash temperature unknown, not scooping",
    mapNote: "Position estimated from the route plan",
    foot1: "The background smoke thickens as CO2 rises above background, and drifts toward the filter when the fan speeds up.",
    foot2: "Updated every second: R4 over WiFi to a laptop relay, then over Tailscale to this server.",
    co2Fresh: "Fresh", co2Busy: "Busy with incense", co2High: "Too smoky, fan at full",
    st: { S0: "Standby", S1: "Ventilating", S2: "Peak extraction", S3: "Safety stop" },
    stNote: { S0: "Nobody around, fan resting", S1: "Gentle airflow", S2: "Crowded, extracting harder", S3: "Safety check failed, fan off" },
    stn: { DOCK: "Dock", TABLE: "Offering table", BURNER: "Incense burner", ASH: "Ash bin", NONE: "" },
    stnEn: {},
    mission: { MORNING: "Morning mission", EVENING: "Evening mission" },
    purpose: { TABLE: "to tidy fallen offerings", BURNER: "to capture smoke and check the ash", ASH: "to empty excess ash", DOCK: "to recharge" },
    nowIdle: "Waiting at the {s}", nowIdleHome: "Waiting at the dock",
    nowGo: "Heading to the {d} {p}", nowSpin: "Turning around to set off", nowFind: "Looking for the line",
    nowCal: "Calibrating the line sensor", nowView: "Checking the line sensor",
    nowTable: "At the offering table: {n} offerings to put back", nowTableClear: "At the offering table: all offerings are on the plate",
    nowTableNoCam: "At the offering table, tidying offerings",
    nowBurner: "Beside the burner capturing smoke, ash {a}", nowAsh: "At the ash bin", nowDock: "Back at the dock",
    nowFail: "Mission paused, the team is on it", nowOffline: "The robot is offline",
    subMission: "{m}, leg {i}: {leg}",
  },
};

let lang = "zh";
try { lang = localStorage.getItem("keeper-lang") === "en" ? "en" : "zh"; } catch (_) {}

export function getLang() { return lang; }
// 團隊頁固定用中文，不改公開頁記住的語言
export function useLang(l) { lang = l === "en" ? "en" : "zh"; }
export function setLang(l) {
  lang = l === "en" ? "en" : "zh";
  try { localStorage.setItem("keeper-lang", lang); } catch (_) {}
  document.documentElement.lang = lang === "en" ? "en" : "zh-Hant-TW";
  applyStatic();
}

export function t(key, vars) {
  const v = key.split(".").reduce((o, k) => (o ? o[k] : undefined), T[lang]);
  let s = v === undefined ? key : v;
  if (vars && typeof s === "string") for (const [k, x] of Object.entries(vars)) s = s.replace(`{${k}}`, x);
  return s;
}

export function applyStatic(root = document) {
  for (const el of root.querySelectorAll("[data-t]")) el.textContent = t(el.dataset.t);
}

// 路段代號 → 中文
const LEG_NAME = {
  "DOCK>TABLE": ["DOCK", "TABLE"], "TABLE>BURN": ["TABLE", "BURNER"], "BURN>TABLE": ["BURNER", "TABLE"],
  "TABLE>ASH": ["TABLE", "ASH"], "ASH>DOCK": ["ASH", "DOCK"],
};
export function legLabel(tag) {
  const p = LEG_NAME[tag];
  return p ? `${t("stn." + p[0])} → ${t("stn." + p[1])}` : tag || "";
}
export function legDest(tag) { const p = LEG_NAME[tag]; return p ? p[1] : null; }

const MOVING = new Set(["SPIN", "ACQUIRE", "FOLLOW", "CROSS", "AXLE", "ROLL"]);
export function isMoving(robot) { return MOVING.has(robot); }

// 一句話說明機器人正在做什麼（公開頁的主標）
export function narrate(s, vision, isPublic) {
  if (!s) return { main: t("nowOffline"), sub: "" };
  const robot = s.robot, stn = s.station, dest = legDest(s.leg);
  let main;
  if (robot === "FAIL") main = isPublic ? t("nowFail") : `${t("nowFail")}（${s.fail || "?"}）`;
  else if (robot === "LINECAL") main = t("nowCal");
  else if (robot === "LINEVIEW") main = t("nowView");
  else if (robot === "SPIN" && s.step <= 1 && !stn) main = t("nowSpin");
  else if (robot === "ACQUIRE") main = t("nowFind");
  else if (isMoving(robot) && dest) main = t("nowGo", { d: t("stn." + dest), p: t("purpose." + dest) });
  else if (robot === "STATION" || (robot === "IDLE" && stn && stn !== "NONE")) {
    if (stn === "TABLE") {
      const mv = vision && vision.mv;
      if (mv && mv.ok) main = mv.no > 0 ? t("nowTable", { n: mv.no }) : t("nowTableClear");
      else main = t("nowTableNoCam");
    } else if (stn === "BURNER") {
      const a = typeof s.ash_pct === "number" && s.ash_pct >= 0 ? `${s.ash_pct}%` : "--";
      main = t("nowBurner", { a });
    } else if (stn === "ASH") main = t("nowAsh");
    else if (stn === "DOCK") main = t("nowDock");
    else main = t("nowIdle", { s: t("stn." + stn) });
  } else main = t("nowIdleHome");

  let sub = "";
  if (s.mission && s.leg) {
    const m = T[lang].mission[s.mission] || s.mission;
    const legs = s.mission === "MORNING" ? ["DOCK>TABLE", "TABLE>BURN"]
      : s.mission === "EVENING" ? ["BURN>TABLE", "TABLE>ASH", "ASH>DOCK"] : [s.leg];
    sub = t("subMission", { m, i: legs.indexOf(s.leg) + 1 || 1, leg: legLabel(s.leg) });
  }
  return { main, sub };
}

// 狀態等級：good / warn / crit，一律搭配文字與圖示，不只靠顏色
export function co2Level(co2, base) {
  if (co2 == null) return null;
  if (co2 >= 1500) return { level: "crit", text: t("co2High") };
  if (base != null && co2 > base + 300) return { level: "warn", text: t("co2Busy") };
  return { level: "good", text: t("co2Fresh") };
}

export const ICON = {
  good: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M5 8.2l2 2 4-4.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  warn: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.8l6.6 12H1.4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M8 6.2v3.6M8 11.8v.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  crit: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5.2 1.5h5.6l3.7 3.7v5.6l-3.7 3.7H5.2l-3.7-3.7V5.2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M8 4.8v4M8 11.2v.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};
