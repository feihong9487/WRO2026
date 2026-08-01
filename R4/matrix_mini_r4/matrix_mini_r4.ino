/*
 * 智慧香爐 — 合併版韌體（MATRIX Mini R4 Controller）
 * =============================================================================
 * 本檔取代原本的 s3_sensor_node.ino（感測層）＋ r4_actuator_node.ino（安全層），
 * 把「感測」與「安全致動」合併到同一顆控制器上。
 *
 * 職責：
 *   1. I2C 讀 SCD41（CO2/溫/濕，每 5 秒一筆）與 SHT31（溫/濕，1 Hz）
 *   2. 計算 CO2 斜率（ppm/min）＝ 前饋削峰指標 θ_ff 的輸入
 *   3. 雙溫度交叉驗證 → conf（1.0 / 0.5），呼應「雙感測冗餘」防線
 *   4. MAX6675 讀爐溫（每 500ms），安全聯鎖：>=T_LOCK 觸發、<=T_RELEASE 解除（遲滯）
 *      熱電偶斷線（NaN）視為感測失效 → 一律進安全態（停止致動）
 *   5. 風扇 PWM（D1左 → D4184 MOSFET → 12V 5015 風扇）
 *   6. 與 Pi 的 USB 序列協定（115200）：
 *        Pi → 本機：`FAN <0-255>\n` 或 `PING\n`
 *        本機 → Pi：每秒一行 JSON（含感測值＋安全狀態，Pi 據此跑主 FSM）
 *   7. 看門狗：>5 秒沒收到 Pi 指令 → 用「自己的 CO2 讀值」跑本地簡化 FSM
 *      ★這是合併後的升級★ 原設計 R4 沒有感測資料，Pi 一死只能吐固定 duty 80；
 *      現在能做真正的回饋控制。
 *
 * 控制優先權（由高到低）：
 *   熱電偶故障 / 超溫聯鎖（fan=0）
 *     ＞ CO2 硬警報（fan=255，即使 Pi 說別的也要換氣）
 *     ＞ Pi 指令
 *     ＞ 本地簡化 FSM（感測正常時）
 *     ＞ FALLBACK 後備轉速（感測也失效時）
 *
 * -----------------------------------------------------------------------------
 * 硬體與接線（★腳位經查證，避開 MATRIX 函式庫佔用的腳★）
 *
 *   MiniR4.begin() 內部會執行 PS2.config_gamepad(11, 4, 12, 5)，
 *   把 D2 埠(5,4) 與 D3 埠(12,11) 佔為手把介面，因此本專案只用 D1 與 D4：
 *
 *     SCD41        → I2C1 埠（Wire1 + PCA9548A 多工器 ch0，5V 直插）
 *     SHT31        → I2C2 埠（同上，ch1）
 *     MAX6675 SCK  → D4 埠左（腳 13）
 *     MAX6675 SO   → D4 埠右（腳 10）
 *     MAX6675 CS   → D1 埠右（腳 2）
 *     風扇 PWM     → D1 埠左（腳 3，支援 PWM）→ D4184 TRIG
 *     Pi           → USB-C（供電兼序列）
 *
 *   電源：12V 2A 同時餵 MATRIX 電源輸入（板子吃 6-24V）與 D4184 VIN，
 *         共地自動成立。★馬達埠是 5V，推不動 12V 風扇，D4184 必須保留★
 *
 * -----------------------------------------------------------------------------
 * 程式庫（程式庫管理員安裝）：
 *   - MatrixMiniR4          （GitHub: Matrix-Robotics/MatrixMiniR4）
 *   - SparkFun SCD4x Arduino Library
 *   - Adafruit SHT31 Library（含 Adafruit BusIO）
 *   - MAX6675 library（Adafruit）
 * 開發板：Arduino UNO R4 WiFi
 */

#include <Wire.h>
#include <max6675.h>

#include "MatrixMiniR4.h"
#include "SparkFun_SCD4x_Arduino_Library.h"
#include "Adafruit_SHT31.h"

// ═══════════════════════════════════════════════════════════════════════════
// 接線方案（二選一）
// ═══════════════════════════════════════════════════════════════════════════
//   WIRING_MUX  : SCD41→I2C1、SHT31→I2C2。走 Wire1 經 PCA9548A 多工器。
//                 兩顆各用一個 Grove 埠，接線乾淨；程式需切通道（已封裝）。
//   WIRING_I2C0 : 兩顆共用 Port A3（走 Wire，無多工器）。
//                 程式最單純，但需要一個 Grove 分接頭把兩顆併到同一埠。
#define WIRING_MUX   1
#define WIRING_I2C0  2

#define WIRING  WIRING_MUX        // ← 改這行切換接線方案

#if WIRING == WIRING_MUX
#    define SENSOR_WIRE Wire1
const uint8_t MUX_ADDR = 0x70;    // PCA9548A（MATRIX 函式庫用的位址）
const uint8_t CH_SCD41 = 0;       // I2C1 埠
const uint8_t CH_SHT31 = 1;       // I2C2 埠
// 切換多工器通道。第三方感測器函式庫不認得多工器，每次存取前要先切。
inline void muxSelect(uint8_t ch)
{
    SENSOR_WIRE.beginTransmission(MUX_ADDR);
    SENSOR_WIRE.write(1 << ch);
    SENSOR_WIRE.endTransmission();
    delayMicroseconds(800);       // 與 MATRIX 函式庫的 i2cMUXSelect() 一致
}
#else
#    define SENSOR_WIRE Wire
const uint8_t CH_SCD41 = 0;       // 無多工器，僅為介面一致而保留
const uint8_t CH_SHT31 = 0;
inline void muxSelect(uint8_t) {} // 空實作，編譯後不產生程式碼
#endif

// ---- 腳位（★避開 PS2 佔用的 11/12/4/5★）----
const int PIN_TC_SCK = 13;   // D4 埠左
const int PIN_TC_SO  = 10;   // D4 埠右
const int PIN_TC_CS  = 2;    // D1 埠右
const int PIN_FAN    = 3;    // D1 埠左（PWM）→ D4184 TRIG

// ---- 門檻（桌面測試值；燃燒艙階段再依實況調整）----
// 安全層
const float    T_LOCK        = 80.0;    // °C 聯鎖觸發
const float    T_RELEASE     = 60.0;    // °C 聯鎖解除（遲滯）
const uint32_t PI_TIMEOUT_MS = 5000;    // 看門狗：多久沒收到 Pi 指令視為失聯
const uint8_t  FALLBACK_DUTY = 80;      // Pi 與感測皆失效時的後備轉速
// 感測層
const uint16_t CO2_ALARM_PPM   = 1500;  // CO2 硬警報門檻（呼氣即可觸發，方便驗證）
const uint32_t SENSOR_STALE_MS = 15000; // SCD41 多久沒有效讀值視為感測失效（更新週期 5s）
// 本地簡化 FSM（與 pi_fsm.py 的門檻一致，確保降級前後行為連續）
const uint16_t CO2_IDLE    = 600;       // 低於此持續 IDLE_HOLD_MS → S0 待機
const uint16_t T1          = 900;       // 進 S2（暫由 CO2 代打 PM 門檻）
const uint16_t T1_EXIT     = 800;       // 退 S2（遲滯，T1' < T1）
const float    SLOPE_TH    = 120.0;     // ppm/min，CO2 前饋門檻 θ_ff
const uint32_t IDLE_HOLD_MS = 60000;

// ---- 週期 ----
const uint32_t TICK_MS    = 1000;       // 系統心跳與序列回報 1 Hz
const uint32_t TC_READ_MS = 500;        // MAX6675 轉換最長 220ms
const uint32_t SCD_POLL_MS = 1000;      // 輪詢 SCD41（它自己 5 秒才更新一筆）

// ═══════════════════════════════════════════════════════════════════════════
// 全域狀態
// ═══════════════════════════════════════════════════════════════════════════
SCD4x          scd41;
Adafruit_SHT31 sht31 = Adafruit_SHT31(&SENSOR_WIRE);
MAX6675        tc(PIN_TC_SCK, PIN_TC_CS, PIN_TC_SO);

// 感測值
uint16_t co2   = 0;
float    tScd = NAN, rhScd = NAN, tSht = NAN, rhSht = NAN;
float    slopePpmMin = 0.0f;
float    conf        = 0.5f;
bool     scdOk = false, shtOk = false;
bool     co2Alarm    = false;   // CO2 超過硬門檻
bool     sensorFault = false;   // SCD41 長時間無有效讀值

// 安全層狀態
float tempC     = NAN;
bool  tcFault   = false;
bool  interlock = false;

// 控制狀態
uint8_t piDuty  = 0;
uint8_t outDuty = 0;
bool    piSeen  = false;        // 開機後是否真的收過 Pi 指令（避免誤判「Pi 在線」）
char    mode[10] = "FALLBACK";  // PI / FALLBACK
char    localState[3] = "S1";   // 本地 FSM 狀態（Pi 在線時僅供參考）

// 計時
uint32_t lastPiCmd = 0, lastTick = 0, lastTcRead = 0, lastScdPoll = 0;
uint32_t lastScdOk = 0, idleSince = 0;

// CO2 斜率緩衝：SCD41 約每 5 秒更新一筆，12 筆 ≈ 60 秒視窗
struct Sample
{
    uint32_t ms;
    uint16_t co2;
};
const int BUF_N = 12;
Sample    buf[BUF_N];
int       bufCount = 0;

// 序列指令收集
char    lineBuf[32];
uint8_t lineLen = 0;

// NaN 會讓 JSON 解析失敗，用 -99.9 當「無資料」哨兵值
float j(float v) { return isnan(v) ? -99.9f : v; }

// ═══════════════════════════════════════════════════════════════════════════
// 感測
// ═══════════════════════════════════════════════════════════════════════════

// 與原 s3_sensor_node.ino 逐行相同——本專案的核心演算法，不隨硬體變動
void pushSample(uint16_t c)
{
    if (bufCount < BUF_N) {
        buf[bufCount++] = {millis(), c};
    } else {
        memmove(buf, buf + 1, sizeof(Sample) * (BUF_N - 1));
        buf[BUF_N - 1] = {millis(), c};
    }
    if (bufCount >= 2) {
        Sample& a    = buf[0];
        Sample& b    = buf[bufCount - 1];
        float   mins = (b.ms - a.ms) / 60000.0f;
        if (mins > 0.05f) slopePpmMin = ((float)b.co2 - (float)a.co2) / mins;
    }
}

void readSensors()
{
    // --- SCD41（約每 5 秒才有新資料）---
    if (scdOk && millis() - lastScdPoll >= SCD_POLL_MS) {
        lastScdPoll = millis();
        muxSelect(CH_SCD41);
        if (scd41.readMeasurement()) {
            co2   = scd41.getCO2();
            tScd  = scd41.getTemperature();
            rhScd = scd41.getHumidity();
            pushSample(co2);
            lastScdOk = millis();
        }
    }

    // --- SHT31（1 Hz）---
    if (shtOk) {
        muxSelect(CH_SHT31);
        float t = sht31.readTemperature();
        float h = sht31.readHumidity();
        if (!isnan(t)) tSht = t;
        if (!isnan(h)) rhSht = h;
    }

    // --- 感測失效判定 ---
    // SCD41 是 CO2 唯一來源，它沒讀值就無法做濃度決策
    sensorFault = !scdOk || (lastScdOk == 0) || (millis() - lastScdOk > SENSOR_STALE_MS);

    // --- 雙溫度交叉驗證 → 信賴度 ---
    conf = 0.5f;
    if (!isnan(tScd) && !isnan(tSht) && fabsf(tScd - tSht) < 2.0f) conf = 1.0f;

    // --- CO2 硬警報 ---
    // 註：原 S3 韌體此處還有「MQTT 斷線 >10 秒 → 判定 Pi 失效 → 拉警報」。
    //     合併後 Pi 失聯改由本地 FSM 接手（有真實 CO2 可用，比一律全速更精確），
    //     故這裡只保留 CO2 硬門檻這一條。
    co2Alarm = (co2 != 0 && co2 >= CO2_ALARM_PPM);
}

// ═══════════════════════════════════════════════════════════════════════════
// 本地簡化 FSM（Pi 失聯時接手；門檻與 pi_fsm.py 一致）
// ═══════════════════════════════════════════════════════════════════════════
uint8_t localFSM()
{
    // 安全事件優先——對應 pi_fsm.py 的 anomaly 分支
    if (tcFault || interlock) {
        strcpy(localState, "S3");
        idleSince = 0;
        return 0;
    }
    // 異常解除 → 回 S1（對應 pi_fsm.py 的 ANOMALY_CLEARED）
    if (strcmp(localState, "S3") == 0) {
        strcpy(localState, "S1");
        idleSince = 0;
    }
    // 感測失效 → 無法做濃度決策，退回後備轉速
    // （對應原三板設計的「S3 感測層失效 → R4 回 FALLBACK」）
    if (sensorFault) {
        strcpy(localState, "S1");
        idleSince = 0;
        return FALLBACK_DUTY;
    }

    // 以下逐條對應 pi_fsm.py 的狀態轉移，確保降級前後行為連續
    bool isS0 = (strcmp(localState, "S0") == 0);
    bool isS1 = (strcmp(localState, "S1") == 0);
    bool isS2 = (strcmp(localState, "S2") == 0);

    if ((isS0 || isS1) && (co2 > T1 || slopePpmMin > SLOPE_TH)) {
        strcpy(localState, "S2");          // 前饋削峰：人潮（CO2 斜率）先行
    } else if (isS2 && co2 < T1_EXIT && slopePpmMin < SLOPE_TH / 2) {
        strcpy(localState, "S1");          // 遲滯退場，避免抖動
    } else if (isS1 && co2 != 0 && co2 < CO2_IDLE) {
        if (idleSince == 0) {
            idleSince = millis();
        } else if (millis() - idleSince > IDLE_HOLD_MS) {
            strcpy(localState, "S0");
        }
    }
    if (co2 >= CO2_IDLE) {
        idleSince = 0;
        if (strcmp(localState, "S0") == 0) strcpy(localState, "S1");
    }

    if (strcmp(localState, "S0") == 0) return 0;
    if (strcmp(localState, "S2") == 0) return 220;
    return 70;                              // S1
}

// ═══════════════════════════════════════════════════════════════════════════
// 序列指令（與原 r4_actuator_node.ino 相同協定，Pi 端不必改）
// ═══════════════════════════════════════════════════════════════════════════
void handleLine(char* s)
{
    if (strncmp(s, "FAN ", 4) == 0) {
        int v = atoi(s + 4);
        if (v < 0) v = 0;
        if (v > 255) v = 255;
        piDuty    = (uint8_t)v;
        lastPiCmd = millis();
        piSeen    = true;
    } else if (strcmp(s, "PING") == 0) {
        lastPiCmd = millis();
        piSeen    = true;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// 顯示（板載 OLED 128x32 ＋ RGB LED）
// ═══════════════════════════════════════════════════════════════════════════
void updateDisplay()
{
    MiniR4.OLED.clearDisplay();
    MiniR4.OLED.setTextSize(1);

    MiniR4.OLED.setCursor(0, 0);
    MiniR4.OLED.print(localState);
    MiniR4.OLED.print(F("  "));
    MiniR4.OLED.print(mode);
    if (interlock || tcFault) MiniR4.OLED.print(F(" LOCK"));
    else if (sensorFault)     MiniR4.OLED.print(F(" NOSNS"));

    MiniR4.OLED.setCursor(0, 11);
    MiniR4.OLED.print(F("CO2 "));
    MiniR4.OLED.print(co2);
    MiniR4.OLED.print(F("ppm "));
    MiniR4.OLED.print(slopePpmMin, 0);

    MiniR4.OLED.setCursor(0, 22);
    MiniR4.OLED.print(F("T "));
    if (tcFault) MiniR4.OLED.print(F("--"));
    else         MiniR4.OLED.print(tempC, 1);
    MiniR4.OLED.print(F("C  FAN "));
    MiniR4.OLED.print(outDuty);
    MiniR4.OLED.display();

    // RGB LED：綠=常態、橙=高峰、紅=異常
    if (tcFault || interlock)               MiniR4.LED.setColor(1, 255, 0, 0);
    else if (strcmp(localState, "S2") == 0) MiniR4.LED.setColor(1, 255, 120, 0);
    else                                    MiniR4.LED.setColor(1, 0, 255, 0);
}

// ═══════════════════════════════════════════════════════════════════════════
void setup()
{
    Serial.begin(115200);

    pinMode(PIN_FAN, OUTPUT);
    analogWrite(PIN_FAN, 0);      // 上電先確保風扇停止

    // MATRIX 板級初始化（STM32、OLED、LED、蜂鳴器、馬達/伺服預備）
    // 註：內部有 while(!Mn.begin()) 迴圈，STM32 未就緒會停在這裡——
    //     若板子完全沒反應，先確認 MATRIX 韌體版本與電源。
    MiniR4.begin();

    MiniR4.OLED.clearDisplay();
    MiniR4.OLED.setTextSize(1);
    MiniR4.OLED.setCursor(0, 0);
    MiniR4.OLED.print(F("Incense P0 init..."));
    MiniR4.OLED.display();

    SENSOR_WIRE.begin();
    SENSOR_WIRE.setClock(100000);   // I2C 標準模式，與電氣驗證計算一致

    muxSelect(CH_SCD41);
    scdOk = scd41.begin(SENSOR_WIRE);   // 內含 startPeriodicMeasurement

    muxSelect(CH_SHT31);
    shtOk = sht31.begin(0x44);

    Serial.print(F("# SCD41:"));
    Serial.print(scdOk ? F("OK") : F("FAIL"));
    Serial.print(F("  SHT31:"));
    Serial.println(shtOk ? F("OK") : F("FAIL"));

    delay(500);                      // MAX6675 上電穩定
    lastTick = lastScdPoll = millis();
}

void loop()
{
    // 1) 收 Pi 序列指令（非阻塞逐字元）
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (lineLen) {
                lineBuf[lineLen] = 0;
                handleLine(lineBuf);
                lineLen = 0;
            }
        } else if (lineLen < sizeof(lineBuf) - 1) {
            lineBuf[lineLen++] = c;
        }
    }

    // 2) 每 500ms 讀爐溫 + 聯鎖判斷（遲滯）
    if (millis() - lastTcRead >= TC_READ_MS) {
        lastTcRead = millis();
        float t    = tc.readCelsius();
        if (isnan(t)) {
            tcFault = true;              // 熱電偶斷線/未接 → 安全態
        } else {
            tcFault = false;
            tempC   = t;
            if (t >= T_LOCK)         interlock = true;
            else if (t <= T_RELEASE) interlock = false;
        }
    }

    // 3) 讀感測器
    readSensors();

    // 4) 控制解算
    //    優先權：聯鎖/故障 > CO2 硬警報 > Pi 指令 > 本地 FSM > 後備
    uint8_t localDuty = localFSM();      // 每輪都算，讓 localState 保持最新

    uint8_t duty;
    if (piSeen && millis() - lastPiCmd < PI_TIMEOUT_MS) {
        duty = piDuty;
        strcpy(mode, "PI");
    } else {
        duty = localDuty;                // Pi 尚未上線或已失聯 → 本地 FSM 接手
        strcpy(mode, "FALLBACK");
    }
    if (co2Alarm)             duty = 255;   // CO2 硬警報 → 基本抽排全速
    if (tcFault || interlock) duty = 0;     // 安全聯鎖優先於一切 → 停止致動

    outDuty = duty;
    analogWrite(PIN_FAN, outDuty);

    // 5) 每秒回報狀態給 Pi ＋ 更新顯示
    if (millis() - lastTick >= TICK_MS) {
        lastTick = millis();

        // 一行 JSON 同時涵蓋「感測值」與「安全狀態」，Pi 據此跑主 FSM。
        // 欄位名稱刻意與原 sensor / decision 主題一致，雲端儀表板不必改。
        //
        // ★用 Serial.print 而非 snprintf("%f") 組字串★
        //   UNO R4 的 C 函式庫預設不保證支援 printf 系列的浮點格式化，
        //   原 r4_actuator_node.ino 也是用 Serial.print(x, 2) 迴避此問題。
        Serial.print(F("{\"ts\":"));            Serial.print(millis());
        Serial.print(F(",\"co2\":"));           Serial.print(co2);
        Serial.print(F(",\"slope\":"));         Serial.print(slopePpmMin, 1);
        Serial.print(F(",\"t_scd\":"));         Serial.print(j(tScd), 2);
        Serial.print(F(",\"rh_scd\":"));        Serial.print(j(rhScd), 1);
        Serial.print(F(",\"t_sht\":"));         Serial.print(j(tSht), 2);
        Serial.print(F(",\"rh_sht\":"));        Serial.print(j(rhSht), 1);
        Serial.print(F(",\"conf\":"));          Serial.print(conf, 1);
        Serial.print(F(",\"alarm\":"));         Serial.print(co2Alarm ? 1 : 0);
        Serial.print(F(",\"t_furnace\":"));      Serial.print(tcFault ? -99.9f : j(tempC), 2);
        Serial.print(F(",\"fan\":"));           Serial.print(outDuty);
        Serial.print(F(",\"interlock\":"));     Serial.print(interlock ? 1 : 0);
        Serial.print(F(",\"tc_fault\":"));      Serial.print(tcFault ? 1 : 0);
        Serial.print(F(",\"sensor_fault\":"));  Serial.print(sensorFault ? 1 : 0);
        Serial.print(F(",\"mode\":\""));        Serial.print(mode);
        Serial.print(F("\",\"local_state\":\"")); Serial.print(localState);
        Serial.println(F("\"}"));

        updateDisplay();
    }
}

/*
 * -----------------------------------------------------------------------------
 * 【待實作・Phase 2】WiFi 備援上雲路徑
 * -----------------------------------------------------------------------------
 * MATRIX Mini R4 基於 UNO R4 WiFi，內建 ESP32-S3 網路協處理器，
 * 可在「Pi 失效」時由本機直接把上面那行 JSON 發布到雲端 MQTT，
 * 讓手機端仍看得到現場 CO2 與風扇狀態（原三板設計做不到）。
 *
 * 作法：用 WiFiS3.h + ArduinoMqttClient，在 §5 回報區塊後追加一次 publish，
 *       主題 incense/<爐號>/sensor，僅在 mode == "FALLBACK" 時發送以省頻寬。
 *
 * ★ 尚未實作的理由：核心安全邏輯必須先在實機驗證通過，
 *   未經測試的網路程式碼混進安全韌體風險大於效益。硬體到位後再加。
 */
