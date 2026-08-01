/*
 * 智慧香爐 — R4 安全層「控制邏輯」Wokwi 模擬版
 * =============================================================
 * 目的：在沒有實體硬體的情況下，驗證 r4_actuator_node.ino 的
 *       ★安全優先權★與★看門狗★邏輯是否正確。
 *
 * ── 與正式韌體的差異（只有輸入來源，決策邏輯逐行相同）──────────
 *   正式版                          本模擬版
 *   MAX6675 熱電偶讀爐溫      →     電位器 A1（0–1024 °C 線性對應）
 *   S3 GPIO4 → R4 A0（類比判位） →     按鈕 A0（按住 = 警報中）
 *   D4184 → 12V 風扇           →     LED D9（亮度 = 風扇 duty）
 *   Pi 經 USB 序列下指令       →     序列監控手動輸入（同樣的 FAN/PING 指令）
 *
 * ⚠️ Wokwi 目前沒有 UNO R4 Minima，本專案用 UNO R3 當替身。
 *    這不影響邏輯驗證（兩者程式碼相同）。至於「為什麼警報線要接類比腳」，
 *    那是 R4 數位輸入 VIH = 4.0V 的規格問題，見《電氣驗證計算.md》§1——
 *    模擬器驗證不了電氣準位，只能靠規格書算。
 *
 * ── 怎麼用（貼到 wokwi.com 後）─────────────────────────────
 *   1. 按 ▶ 開始模擬，打開序列監控（115200）
 *   2. 觀察開機前 5 秒：應顯示 mode:"FALLBACK"、fan:80（★piSeen 修正的驗證點★）
 *   3. 序列監控輸入 `FAN 220` → mode 轉 PI、LED 變亮
 *   4. 停止輸入 5 秒 → 自動回 FALLBACK、fan 80（看門狗）
 *   5. 轉電位器讓爐溫 > 80 °C → interlock:1、fan 強制 0、LED 熄、板載 LED 快閃
 *   6. 降回 < 60 °C → interlock 自動解除（遲滯）
 *   7. 按住 A0 按鈕 → alarm:1、fan 跳 255（但若同時超溫，聯鎖優先，仍為 0）
 */

// ---- 腳位（對應正式版接線）----
const int PIN_TEMP_SIM = A1;  // 模擬用：取代 MAX6675
const int PIN_FAN      = 9;   // 正式版：PWM → D4184 TRIG
const int PIN_ALARM_IN = A0;  // 正式版：← S3 GPIO4（類比判位，不需電平轉換晶片）

// ---- 門檻（與正式韌體完全相同）----
const float    T_LOCK        = 80.0;   // °C 聯鎖觸發
const float    T_RELEASE     = 60.0;   // °C 聯鎖解除（遲滯）
const uint32_t PI_TIMEOUT_MS = 5000;   // 看門狗
const uint8_t  FALLBACK_DUTY = 80;     // Pi 失聯時的後備轉速

// 警報線 ADC 門檻（與正式韌體相同）。上下門檻不同 = 軟體遲滯。
// 註：真實 S3 拉高為 3.3V ≈ 675；本模擬的按鈕給 5V = 1023。
//     兩者都遠高於 ALARM_HI，判定邏輯完全一致。
const int ALARM_HI = 500;
const int ALARM_LO = 300;

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
    piDuty    = (uint8_t)v;
    lastPiCmd = millis();
    piSeen    = true;
  } else if (strcmp(s, "PING") == 0) {
    lastPiCmd = millis();
    piSeen    = true;
  }
}

// 模擬用：電位器 0–1023 → 爐溫 0–1024 °C（對應 MAX6675 的量測範圍）
float readTempSim() {
  return analogRead(PIN_TEMP_SIM) * (1024.0 / 1023.0);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_FAN, OUTPUT);
  pinMode(PIN_ALARM_IN, INPUT);   // 靠外部 10kΩ 下拉，不用內部上拉
  pinMode(LED_BUILTIN, OUTPUT);
  analogWrite(PIN_FAN, 0);
  delay(500);                     // 正式版：MAX6675 上電穩定
  Serial.println(F("=== R4 安全層模擬啟動 ==="));
  Serial.println(F("指令：FAN <0-255> / PING｜轉電位器改爐溫｜按 A0 按鈕觸發 S3 警報"));
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
    float t = readTempSim();
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

  // 4) 每秒回報狀態（格式與正式韌體完全相同）
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
