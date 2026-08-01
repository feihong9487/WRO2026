/*
 * ⚠️ 【原型階段方案・目前未使用】2026-08-02 起改採合併架構，
 *    改用 R4/matrix_mini_r4（MATRIX Mini R4 版，含感測）。
 *    本檔為 Arduino UNO R4 Minima 裸板版本，保留備查。
 *
 * 智慧香爐 P0 — 機構／安全層（Arduino UNO R4 Minima）
 * -------------------------------------------------------------
 * 職責（照交接文件：最單純可靠、當機率最低 → 守安全）：
 *   1. MAX6675 讀爐溫（每 500ms，晶片最短轉換 250ms）
 *   2. 安全聯鎖：爐溫 >= T_LOCK 觸發、<= T_RELEASE 解除（遲滯）
 *      熱電偶斷線（NaN）視為感測失效 → 一律進安全態（停止致動）
 *   3. 風扇 PWM（D9 → D4184 MOSFET → 12V 5015 風扇）
 *   4. S3 警報線輸入（A0 類比判位，外接 10kΩ 下拉）→ 強制風扇全速
 *      ★ 為何用類比腳而非數位腳 ★
 *        R4（RA4M1）數位輸入的 VIH = 0.8 x VCC = 4.0V，S3 只輸出 3.3V，
 *        規格上讀不到 HIGH（舊款 R3 的 ATmega328P 門檻 3.0V 才過得了）。
 *        類比腳量測範圍 0-5V：3.3V ≈ 675/1023、0V = 0，差距極大可靠分辨，
 *        因此不必外加 74HCT125 之類的電平轉換晶片。
 *   5. 與 Pi 的 USB 序列協定（115200）：
 *        Pi → R4：`FAN <0-255>\n` 或 `PING\n`
 *        R4 → Pi：每秒一行 JSON 狀態
 *   6. 看門狗：>5 秒沒收到 Pi 指令 → FALLBACK 後備轉速
 *
 * 優先權（由高到低）：
 *   熱電偶故障 / 超溫聯鎖（fan=0）＞ S3 警報（fan=255）＞ Pi 指令 ＞ 看門狗後備
 *
 * 程式庫：MAX6675 library（Adafruit）
 * 接線：MAX6675 SCK=D7, CS=D5, SO=D6, VCC=5V
 *       A0 ← S3 GPIO4（外接 10kΩ 下拉到 GND）
 *       ★絕不可對 A0 啟用內部上拉 —— 5V 會倒灌進不耐 5V 的 S3，且讀值失真★
 */

#include <max6675.h>

// ---- 腳位 ----
const int PIN_TC_SCK   = 7;
const int PIN_TC_CS    = 5;
const int PIN_TC_SO    = 6;
const int PIN_FAN      = 9;    // PWM → D4184 TRIG
const int PIN_ALARM_IN = A0;   // ← S3 警報線（類比判位）

// ---- 門檻（桌面測試值；燃燒艙階段再依實況調整） ----
const float    T_LOCK        = 80.0;   // °C 聯鎖觸發
const float    T_RELEASE     = 60.0;   // °C 聯鎖解除（遲滯）
const uint32_t PI_TIMEOUT_MS = 5000;   // 看門狗
const uint8_t  FALLBACK_DUTY = 80;     // Pi 失聯時的後備轉速

// 警報線 ADC 門檻（10-bit，參考電壓 5V）：S3 拉高 3.3V ≈ 675、放開 0V = 0
// 上下門檻不同 = 軟體遲滯，用來取代數位腳才有的施密特輸入，避免雜訊造成抖動
const int ALARM_HI = 500;   // > 此值判定警報中（約 2.44V）
const int ALARM_LO = 300;   // < 此值才解除（約 1.47V）

MAX6675 tc(PIN_TC_SCK, PIN_TC_CS, PIN_TC_SO);

float    tempC     = NAN;
bool     tcFault   = false;
bool     interlock = false;
bool     alarmIn   = false;
uint8_t  piDuty    = 0;
uint8_t  outDuty   = 0;
uint32_t lastPiCmd = 0, lastTcRead = 0, lastStatus = 0, lastBlink = 0;
bool     piSeen    = false;     // 開機後是否真的收過 Pi 指令（避免誤判「Pi 在線」）
bool     ledState  = false;
char     mode[10]  = "FALLBACK";

char    lineBuf[32];
uint8_t lineLen = 0;

void handleLine(char* s) {
  if (strncmp(s, "FAN ", 4) == 0) {
    int v = atoi(s + 4);
    if (v < 0)   v = 0;
    if (v > 255) v = 255;
    piDuty   = (uint8_t)v;
    lastPiCmd = millis();
    piSeen    = true;
  } else if (strcmp(s, "PING") == 0) {
    lastPiCmd = millis();
    piSeen    = true;
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_FAN, OUTPUT);
  pinMode(PIN_ALARM_IN, INPUT);   // ★靠外部 10kΩ 下拉，絕不可用內部上拉★
  pinMode(LED_BUILTIN, OUTPUT);
  analogWrite(PIN_FAN, 0);
  delay(500);                     // MAX6675 上電穩定
}

void loop() {
  // 1) 收 Pi 序列指令（非阻塞逐字元）
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineLen) { lineBuf[lineLen] = 0; handleLine(lineBuf); lineLen = 0; }
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    }
  }

  // 2) 每 500ms 讀爐溫 + 聯鎖判斷（遲滯）
  if (millis() - lastTcRead >= 500) {
    lastTcRead = millis();
    float t = tc.readCelsius();
    if (isnan(t)) {
      tcFault = true;             // 熱電偶斷線/未接 → 安全態
    } else {
      tcFault = false;
      tempC   = t;
      if      (t >= T_LOCK)    interlock = true;
      else if (t <= T_RELEASE) interlock = false;
    }
  }

  // 3) 控制解算（優先權：聯鎖/故障 > S3 警報 > Pi > 後備）
  //    警報線用類比判位＋軟體遲滯；介於上下門檻之間時維持原狀
  int alarmRaw = analogRead(PIN_ALARM_IN);
  if      (alarmRaw > ALARM_HI) alarmIn = true;
  else if (alarmRaw < ALARM_LO) alarmIn = false;

  uint8_t duty;
  if (piSeen && millis() - lastPiCmd < PI_TIMEOUT_MS) {
    duty = piDuty;
    strcpy(mode, "PI");
  } else {
    duty = FALLBACK_DUTY;         // Pi 尚未上線或已失聯 → 後備低速
    strcpy(mode, "FALLBACK");
  }
  if (alarmIn)              duty = 255;  // S3 警報 → 基本抽排全速
  if (tcFault || interlock) duty = 0;    // 安全聯鎖優先於一切 → 停止致動

  outDuty = duty;
  analogWrite(PIN_FAN, outDuty);

  // 4) 每秒回報狀態給 Pi（也可在序列監控直接看）
  if (millis() - lastStatus >= 1000) {
    lastStatus = millis();
    Serial.print("{\"t_furnace\":");
    if (tcFault) Serial.print("-99.9");
    else         Serial.print(tempC, 2);
    Serial.print(",\"fan\":");       Serial.print(outDuty);
    Serial.print(",\"alarm\":");     Serial.print(alarmIn   ? 1 : 0);
    Serial.print(",\"interlock\":"); Serial.print(interlock ? 1 : 0);
    Serial.print(",\"tc_fault\":");  Serial.print(tcFault   ? 1 : 0);
    Serial.print(",\"mode\":\"");    Serial.print(mode);
    Serial.println("\"}");
  }

  // 5) 板上 LED：正常慢閃（1s）、聯鎖/故障快閃（120ms）
  uint32_t period = (tcFault || interlock) ? 120 : 1000;
  if (millis() - lastBlink >= period) {
    lastBlink = millis();
    ledState = !ledState;
    digitalWrite(LED_BUILTIN, ledState);
  }
}
