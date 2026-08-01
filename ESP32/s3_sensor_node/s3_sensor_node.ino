/*
 * ⚠️ 【原型階段方案・目前未使用】2026-08-02 起改採合併架構，
 *    感測改由 R4/matrix_mini_r4 直接以 I2C 讀取。
 *    本檔保留作為三板架構的參考與備援（若感測頭需遠離控制盒 >2m 則回頭用它）。
 *
 * 智慧香爐 P0 — 感測層節點（ESP32-S3）
 * -------------------------------------------------------------
 * 感測器：SCD41（CO2/溫/濕，I2C 0x62）＋ GY-SHT31-D（溫/濕，I2C 0x44）
 * 功能：
 *   1. 每秒發布一筆 JSON 到 MQTT 主題 incense/sensor（Pi 5 上的 mosquitto）
 *   2. 計算 CO2 斜率（ppm/min）＝ 前饋削峰指標 θ_ff 的輸入
 *   3. 雙溫度交叉驗證 → conf（1.0 / 0.5），呼應「雙感測冗餘」防線
 *   4. 警報線 GPIO4 → R4 D2：CO2 >= 硬門檻，或 MQTT 斷線 >10 秒（Pi 失效）
 *      → 拉 HIGH，R4 收到後強制風扇全速（不經 Pi 的降級階梯）
 *
 * 程式庫（程式庫管理員安裝）：
 *   - SparkFun SCD4x Arduino Library
 *   - Adafruit SHT31 Library（含 Adafruit BusIO）
 *   - PubSubClient
 * 開發板：ESP32S3 Dev Module｜Tools → USB CDC On Boot: Enabled
 * 接線：SDA=GPIO8, SCL=GPIO9（兩顆感測器並聯同一匯流排，皆接 3V3）
 *       GPIO4 → R4 D2（務必與 R4 共地）
 */

#include <WiFi.h>
#include <Wire.h>
#include <PubSubClient.h>
#include "SparkFun_SCD4x_Arduino_Library.h"
#include "Adafruit_SHT31.h"

// ====== 依環境修改 ======
const char* WIFI_SSID = "YOUR_WIFI";
const char* WIFI_PASS = "YOUR_PASS";
const char* MQTT_HOST = "192.168.1.100";   // ← Pi 5 的 IP（在 Pi 上跑 hostname -I）
// ========================

// ---- 腳位 ----
const int PIN_SDA   = 8;
const int PIN_SCL   = 9;
const int PIN_ALARM = 4;              // → R4 D2

// ---- 門檻（之後燃燒艙實驗再調） ----
const uint16_t CO2_ALARM_PPM = 1500;  // CO2 硬警報門檻（呼氣即可觸發，方便驗證）
const uint32_t MQTT_DEAD_MS  = 10000; // 斷線多久判定 Pi 失效
const uint32_t TICK_MS       = 1000;  // 系統心跳 1 Hz

SCD4x          scd41;
Adafruit_SHT31 sht31 = Adafruit_SHT31();
WiFiClient     wifiClient;
PubSubClient   mqtt(wifiClient);

// CO2 斜率緩衝：SCD41 約每 5 秒更新一筆，12 筆 ≈ 60 秒視窗
struct Sample { uint32_t ms; uint16_t co2; };
const int BUF_N = 12;
Sample buf[BUF_N];
int    bufCount = 0;

uint16_t co2 = 0;
float tScd = NAN, rhScd = NAN, tSht = NAN, rhSht = NAN;
float slopePpmMin = 0.0f;
bool  alarmOn = false;
bool  scdOk = false, shtOk = false;
uint32_t lastMqttOk = 0, lastTick = 0, lastWifiTry = 0, lastMqttTry = 0;

// NaN 會讓 JSON 解析失敗，用 -99.9 當「無資料」哨兵值
float j(float v) { return isnan(v) ? -99.9f : v; }

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

bool mqttEnsure() {
  if (mqtt.connected()) return true;
  if (WiFi.status() != WL_CONNECTED) return false;
  if (millis() - lastMqttTry < 5000) return false;   // 每 5 秒最多重連一次
  lastMqttTry = millis();
  String cid = "s3-sensor-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  return mqtt.connect(cid.c_str());
}

void setup() {
  Serial.begin(115200);
  delay(300);

  pinMode(PIN_ALARM, OUTPUT);
  digitalWrite(PIN_ALARM, LOW);

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(100000);

  shtOk = sht31.begin(0x44);
  scdOk = scd41.begin(Wire);          // 內含 startPeriodicMeasurement
  Serial.printf("SHT31:%s  SCD41:%s\n", shtOk ? "OK" : "FAIL", scdOk ? "OK" : "FAIL");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) delay(200);
  Serial.printf("WiFi:%s  IP:%s\n",
                WiFi.status() == WL_CONNECTED ? "OK" : "FAIL",
                WiFi.localIP().toString().c_str());

  mqtt.setServer(MQTT_HOST, 1883);
  mqtt.setBufferSize(512);
  lastMqttOk = millis();              // 開機給 10 秒緩衝再判 Pi 失效
}

void loop() {
  // WiFi 斷線自動重試
  if (WiFi.status() != WL_CONNECTED && millis() - lastWifiTry > 5000) {
    lastWifiTry = millis();
    WiFi.reconnect();
  }
  mqtt.loop();

  if (millis() - lastTick < TICK_MS) return;   // 1 Hz 心跳
  lastTick = millis();

  // --- 讀感測器 ---
  if (shtOk) {
    tSht  = sht31.readTemperature();
    rhSht = sht31.readHumidity();
  }
  if (scdOk && scd41.readMeasurement()) {      // 約每 5 秒才有新資料
    co2   = scd41.getCO2();
    tScd  = scd41.getTemperature();
    rhScd = scd41.getHumidity();
    pushSample(co2);
  }

  // --- 警報邏輯（降級階梯的第二層） ---
  bool hardCo2 = (co2 != 0 && co2 >= CO2_ALARM_PPM);
  bool piDead  = (millis() - lastMqttOk > MQTT_DEAD_MS);
  alarmOn = hardCo2 || piDead;
  digitalWrite(PIN_ALARM, alarmOn ? HIGH : LOW);

  // --- 雙溫度交叉驗證 → 信賴度 ---
  float conf = 0.5f;
  if (!isnan(tScd) && !isnan(tSht) && fabsf(tScd - tSht) < 2.0f) conf = 1.0f;

  // --- 組 JSON、發布、同步印到序列（單板驗證用） ---
  char msg[256];
  snprintf(msg, sizeof(msg),
           "{\"ts\":%lu,\"co2\":%u,\"slope\":%.1f,"
           "\"t_scd\":%.2f,\"rh_scd\":%.1f,\"t_sht\":%.2f,\"rh_sht\":%.1f,"
           "\"conf\":%.1f,\"alarm\":%d}",
           (unsigned long)millis(), co2, slopePpmMin,
           j(tScd), j(rhScd), j(tSht), j(rhSht),
           conf, alarmOn ? 1 : 0);

  if (mqttEnsure() && mqtt.publish("incense/sensor", msg)) {
    lastMqttOk = millis();
  }
  Serial.println(msg);
}
