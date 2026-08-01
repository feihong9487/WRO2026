/*
 * 智慧香爐 — S3 感測層「訊號處理邏輯」Wokwi 模擬版
 * =============================================================
 * 目的：在沒有實體感測器的情況下，驗證 s3_sensor_node.ino 的
 *       ★CO2 斜率計算★、★雙感測交叉驗證★與★警報判定★是否正確。
 *
 * ── 與正式韌體的差異（只有輸入來源，運算邏輯逐行相同）──────────
 *   正式版                          本模擬版
 *   SCD41 讀 CO2（每 5 秒一筆）  →   電位器 GPIO1（400–3000 ppm），同樣 5 秒取樣
 *   SHT31 讀溫濕度                →   由 CO2 推算的擬真室溫（26 °C 基準）
 *   GPIO4 → 74HCT125 → R4 D2      →   GPIO4 → LED（亮 = 警報中）
 *   WiFi/MQTT 上傳                 →   序列輸出（格式完全相同的 JSON）
 *
 * ── 怎麼用（貼到 wokwi.com 後）─────────────────────────────
 *   1. 按 ▶ 開始模擬，打開序列監控（115200）
 *   2. 慢慢轉電位器 → 觀察 slope 為小正值；快速轉大 → slope 衝上數百 ppm/min
 *      （這就是 FSM 前饋削峰的觸發訊號 θ_ff = 120）
 *   3. 轉到 co2 >= 1500 → alarm 變 1、LED 亮（不經 Pi 的硬體警報路徑）
 *   4. 轉回低值 → alarm 歸 0、LED 熄
 *   5. 對照《P0接線與驗證指南》§5 第 1 關的預期輸出逐項核對
 *
 * ⚠️ 模擬器驗證得了「訊號處理」，驗證不了「電氣準位」。
 *    GPIO4 輸出 3.3V 能不能被真實 R4 讀成 HIGH，見《電氣驗證計算.md》§1（答案是不能，要加 74HCT125）。
 */

// ---- 腳位 ----
const int PIN_CO2_SIM = 1;            // 模擬用：取代 SCD41
const int PIN_ALARM   = 4;            // 正式版：→ 74HCT125 → R4 D2

// ---- 門檻（與正式韌體完全相同）----
const uint16_t CO2_ALARM_PPM = 1500;  // CO2 硬警報門檻
const uint32_t TICK_MS       = 1000;  // 系統心跳 1 Hz
const uint32_t SCD_PERIOD_MS = 5000;  // SCD41 實際更新週期（5 秒，硬體特性）

// CO2 斜率緩衝：SCD41 約每 5 秒更新一筆，12 筆 ≈ 60 秒視窗
struct Sample { uint32_t ms; uint16_t co2; };
const int BUF_N = 12;
Sample buf[BUF_N];
int    bufCount = 0;

uint16_t co2 = 0;
float tScd = NAN, rhScd = NAN, tSht = NAN, rhSht = NAN;
float slopePpmMin = 0.0f;
bool  alarmOn = false;
uint32_t lastTick = 0, lastScdRead = 0;

// NaN 會讓 JSON 解析失敗，用 -99.9 當「無資料」哨兵值
float j(float v) { return isnan(v) ? -99.9f : v; }

// ★這個函式與正式韌體逐行相同——本模擬的核心驗證對象★
void pushSample(uint16_t c) {
  if (bufCount < BUF_N) {
    buf[bufCount++] = { millis(), c };
  } else {
    memmove(buf, buf + 1, sizeof(Sample) * (BUF_N - 1));
    buf[BUF_N - 1] = { millis(), c };
  }
  if (bufCount >= 2) {
    Sample &a = buf[0];
    Sample &b = buf[bufCount - 1];
    float mins = (b.ms - a.ms) / 60000.0f;
    if (mins > 0.05f) slopePpmMin = ((float)b.co2 - (float)a.co2) / mins;
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);

  pinMode(PIN_ALARM, OUTPUT);
  digitalWrite(PIN_ALARM, LOW);

  Serial.println("=== S3 感測層模擬啟動 ===");
  Serial.println("轉電位器改變 CO2（400-3000 ppm）｜>=1500 觸發警報｜每 5 秒取樣一次");
}

void loop() {
  if (millis() - lastTick < TICK_MS) return;   // 1 Hz 心跳
  lastTick = millis();

  // --- 模擬 SCD41：每 5 秒才有新資料（重現真實硬體的取樣率限制）---
  if (millis() - lastScdRead >= SCD_PERIOD_MS) {
    lastScdRead = millis();
    // 電位器 0-4095（ESP32 為 12-bit ADC）→ 400-3000 ppm
    co2   = 400 + (uint16_t)(analogRead(PIN_CO2_SIM) * (2600.0 / 4095.0));
    // 擬真溫濕度：CO2 越高代表人越多，室溫略升、濕度略降
    float rise = (co2 - 400) / 2600.0;
    tScd  = 26.5 + 1.2 * rise;
    rhScd = 62.0 - 3.0 * rise;
    tSht  = tScd - 0.4;               // 兩顆感測器的正常差異
    rhSht = rhScd - 1.0;
    pushSample(co2);
  }

  // --- 警報邏輯（降級階梯的第二層）---
  // 註：正式版還有「MQTT 斷線 >10 秒 → 判定 Pi 失效」這一條，
  //     模擬版無 MQTT，故只保留 CO2 硬門檻這一條。
  bool hardCo2 = (co2 != 0 && co2 >= CO2_ALARM_PPM);
  alarmOn = hardCo2;
  digitalWrite(PIN_ALARM, alarmOn ? HIGH : LOW);

  // --- 雙溫度交叉驗證 → 信賴度 ---
  float conf = 0.5f;
  if (!isnan(tScd) && !isnan(tSht) && fabsf(tScd - tSht) < 2.0f) conf = 1.0f;

  // --- 組 JSON、輸出（格式與正式韌體完全相同）---
  char msg[256];
  snprintf(msg, sizeof(msg),
           "{\"ts\":%lu,\"co2\":%u,\"slope\":%.1f,"
           "\"t_scd\":%.2f,\"rh_scd\":%.1f,\"t_sht\":%.2f,\"rh_sht\":%.1f,"
           "\"conf\":%.1f,\"alarm\":%d}",
           (unsigned long)millis(), co2, slopePpmMin,
           j(tScd), j(rhScd), j(tSht), j(rhSht),
           conf, alarmOn ? 1 : 0);

  Serial.println(msg);
}
