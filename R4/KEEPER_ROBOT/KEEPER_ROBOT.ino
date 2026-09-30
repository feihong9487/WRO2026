/*
  KEEPER_ROBOT.ino — 廟公機器人合併版韌體（MATRIX Mini R4 / Arduino UNO R4 WiFi）
  =============================================================================
  一塊 R4 控制全部：
    底盤循線（STM32 副處理器驅動 M3、M4）
    手臂與夾爪（RC1 夾爪上下、RC2 抹平香灰、RC3 灰盤、RC4 抽風；DC1/DC2 夾爪馬達）
    空氣感測（SCD41、SHT31）與熱電偶安全聯鎖、集煙風扇
    兩顆相機：HuskyLens 看香灰高度、M-Vision 看供品與供盤
    WiFi 把資料送到筆電中繼，再上雲到桌機儀表板

  來源與沿用：
    感測、安全聯鎖、風扇、本地 FSM：沿用 repo 的 R4/matrix_mini_r4.ino，門檻與優先權不變
    路線表與循線：沿用 ROUTE_FOLLOW.ino，改寫成不阻塞的狀態機
    香灰量測：沿用 ASH_LEVEL.ino，EEPROM 校正值格式相同，舊的校正可以直接用
    M-Vision 封包解析：沿用 CAM_TEST.ino
    WiFi 傳輸：依 WIFI_SPEED_TEST 實測，每次寫入 256 B 以內

  ── 設計原則 ──────────────────────────────────────────────────
  1. 主迴圈不阻塞。每個功能各自依時間表執行，車子行進時感測與安全檢查照常運作。
  2. 風扇控制優先權與原香爐韌體相同：
       熱電偶故障或超溫聯鎖（風扇 0）＞ CO2 硬警報（全速）＞ 外部指令 ＞ 本地 FSM ＞ 後備轉速
  3. 會阻塞的網路動作（連 WiFi、連中繼）只在車子靜止、且溫度離聯鎖門檻夠遠時才做。
  4. USB 序列協定與原 Pi 版完全相容，之後接回 Pi 5 也能直接用。

  ── 文化海報四條規則在程式裡的對應 ─────────────────────────
  絕不碰香爐       ：到香爐站只停在旁邊，不做任何接觸動作
  只整平不壓實     ：挖灰手臂尚未製作；先回報「香灰是否已冷」（ash_cool）作為挖灰前提
  不對香頭強吹     ：FAN_MAX_DUTY 風扇上限
  只捕集 hmin 以上 ：集煙手臂角度待手臂做好後設定

  ── 通訊協定（USB 與 WiFi 中繼相同）─────────────────────────
  R4 送出：
    {JSON}    每秒一行。欄位與原香爐韌體相同，另加機器人欄位
    V{JSON}   每 200 ms 一行相機結果。以 V 開頭，舊的 pi_fsm.py 會自動略過
    # ...     紀錄訊息（USB 與 WiFi 都送）
    A{JSON}   遠端指令的結果 {"cmd":"RUN MORNING","ok":1,"why":"已開始"}
    J...      M-Vision 照片分段（只走 WiFi）：J<序號>,<第幾段>,<總段數>,<base64 JPEG>
  R4 接收：
    FAN <0-255>  外部風扇指令（與原 Pi 協定相同）
    PING         外部心跳（與原 Pi 協定相同）
    STOP         立刻中止任務並停車（任何時候都接受）
    以下由監控網站經筆電中繼送來，config.h 的 REMOTE_CONTROL = 0 可以全部關掉：
    RUN <MORNING|EVENING|A|B|C|D|E>  開始任務。只在待命或失敗狀態、且電池電壓足夠時接受
    GO           到站後繼續下一段（等同下鍵）
    END          到站後結束任務（等同上鍵）
    CLEAR        從失敗狀態回到待命
    ARM <動作>   手臂測試（只在靜止時）：GRIP_UP、GRIP_DOWN、LEVEL、DUMP、HOOD_ON、HOOD_OFF、
                 GRIP_CLOSE、GRIP_OPEN、GRIP_STOP、HOME。角度與力道在 config.h
  ⚠ PING 會讓 R4 進入 PI 模式並採用最後一次的 FAN 值。
    中繼程式如果沒有在跑風扇決策，就不要送 PING，否則風扇會停在 0。

  ── 操作 ──────────────────────────────────────────────────────
  上鍵切換選單、下鍵執行。行進中按下鍵緊急停止。
  到站後：下鍵繼續下一段，上鍵結束任務。

  開發板：Arduino UNO R4 WiFi
  程式庫：MatrixMiniR4、SparkFun SCD4x、Adafruit SHT31、HUSKYLENS（DFRobot）
  MAX6675 改用本檔內建的讀取函式，避免電腦上兩套同名程式庫互相衝突。
*/

#define ENABLE_DRIVEDC_BRAKE_DELAY
#include <Wire.h>
#include <EEPROM.h>
#include <WiFiS3.h>
#include "MatrixMiniR4.h"
#include "SparkFun_SCD4x_Arduino_Library.h"
#include "Adafruit_SHT31.h"
#include "HUSKYLENS.h"

#include "config.h"
#include "types.h"
#include "route.h"
#include "arduino_secrets.h"

#if USE_PCF8574 && (HUSKY_I2C_PORT == 3)
#error "PCF8574 與 HuskyLens 都設在 I2C3。啟用 PCF8574 時，請把 HuskyLens 改接 I2C4，並把 HUSKY_I2C_PORT 改成 4"
#endif

// ═══════════════════════════════════════════════════════════════════════════
// 共用工具
// ═══════════════════════════════════════════════════════════════════════════

// 把 print() 的輸出收進記憶體，組好一整行再一次送出。
// 沿用 Print 的浮點格式化，因為 R4 的 printf 不保證支援 %f。
class LineBuf : public Print {
public:
  char   s[480];
  size_t n = 0;
  void clear() { n = 0; s[0] = 0; }
  size_t write(uint8_t c) override {
    if (n < sizeof(s) - 1) { s[n++] = (char)c; s[n] = 0; return 1; }
    return 0;
  }
  using Print::write;
};
LineBuf lb;

// NaN 會讓 JSON 解析失敗，用 -99.9 當「無資料」
float j(float v) { return isnan(v) ? -99.9f : v; }

void netEnqueue(const char* s, size_t n);

// 紀錄訊息同時送 USB 與 WiFi 中繼（中繼程式會轉給監控網站的事件紀錄）
void logMsg(const String& m) {
  Serial.print(F("# ")); Serial.println(m);
  String line = "# " + m;
  netEnqueue(line.c_str(), line.length());
}

// 切換 Wire1 上的 PCA9548A 通道。第三方程式庫不認得多工器，每次存取前都要先切。
void muxSelect(uint8_t ch) {
  Wire1.beginTransmission(MUX_ADDR);
  Wire1.write(1 << ch);
  Wire1.endTransmission();
  delayMicroseconds(800);    // 與原香爐韌體相同
}

// ═══════════════════════════════════════════════════════════════════════════
// 全域狀態
// ═══════════════════════════════════════════════════════════════════════════
// ---- 空氣感測 ----
SCD4x          scd41;
Adafruit_SHT31 sht31 = Adafruit_SHT31(&Wire1);
uint16_t co2 = 0;
float    tScd = NAN, rhScd = NAN, tSht = NAN, rhSht = NAN;
bool     scdOk = false, shtOk = false;
float    slopePpmMin = 0.0f, conf = 0.5f;
bool     co2Alarm = false, sensorFault = false;

// ---- 安全與風扇 ----
float    tempC = NAN;
bool     tcFault = false, interlock = false;
uint8_t  piDuty = 0, outDuty = 0;
bool     piSeen = false;
char     mode[10] = "FALLBACK";
char     localState[3] = "S1";
volatile uint32_t tachPulses = 0;
uint16_t fanRpm = 0;
float    battV = NAN;

// ---- 計時 ----
uint32_t lastPiCmd = 0, lastTick = 0, lastTcRead = 0, lastScdPoll = 0, lastShtPoll = 0;
uint32_t lastScdOk = 0, idleSince = 0, lastVisionSend = 0;

// ---- CO2 斜率緩衝（SCD41 約 5 秒一筆，12 筆 ≈ 60 秒）----
struct Sample { uint32_t ms; uint16_t co2; };
const int BUF_N = 12;
Sample cbuf[BUF_N];
int    cbufCount = 0;

// ---- CO2 背景基線 ----
uint16_t co2Buckets[BASELINE_WINDOW_MIN];
uint8_t  bucketIdx = 0;
uint16_t bucketMin = 0xFFFF;
uint32_t bucketStart = 0;

// ---- 相機 ----
HUSKYLENS husky;
bool      huskyOK = false;
uint8_t   huskyFails = 0;
unsigned long huskyNext = 0, huskyRetryAt = 0;
HuskyRes  hres = { false, 0, 0, 0, 0, 0, 0 };
int       ashHist[ASH_SAMPLES];
uint8_t   ashHistN = 0, ashHistI = 0;
AshCalib  ashCal = { 0, 0, 0 };
MVision   mv = { false, false, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 };
uint32_t  mvGood = 0, mvBad = 0;
#if USE_SNAPSHOT
uint8_t   snapBuf[SNAP_MAX_BYTES];
uint16_t  snapLen = 0, snapRx = 0, snapSent = 0;   // 照片長度、已收、已送
uint8_t   snapChk = 0, snapSeq = 0;
bool      snapReady = false, snapWaiting = false;
uint32_t  snapReqAt = 0, snapOk = 0, snapBad = 0;
#endif

// ---- 網路 ----
WiFiClient net;
WiFiUDP    udp;
NetState   netState = USE_WIFI ? NET_WIFI_DOWN : NET_DISABLED;
IPAddress  relayIP;
uint16_t   relayPort = RELAY_TCP_PORT;
unsigned long netNextTry = 0, netLastCheck = 0, netLastRx = 0, netLastBeacon = 0;
uint8_t    netWriteFails = 0, netConnFails = 0;
uint32_t   netDropped = 0, netSent = 0;
int32_t    wifiRssi = 0;
const size_t TXQ_SIZE = 2048;
uint8_t    txq[TXQ_SIZE];
size_t     txHead = 0, txTail = 0;

// ---- 指令列收集 ----
char    usbLine[40];  uint8_t usbLen = 0;
char    netLine[40];  uint8_t netLen = 0;

// ---- 運動狀態機 ----
MState  ms = MS_IDLE;
unsigned long msT0 = 0, segT0 = 0, blankUntil = 0, lostSince = 0, stationT0 = 0;
uint8_t jcnt = 0, okCnt = 0, snapFails = 0, calPhase = 0;
bool    seenL = false, seenR = false;
int     spinDir = -1, pendingDir = -1;
unsigned long spinMin = 0;
AfterSpin afterSpin = AS_LEG_START;
Act     pendingEnd = END_STOP;
float   fErr = 0, lastErr = 0;
const char* failCode = "";
const char* missionName = "";
struct {
  const Leg* const* legs;
  uint8_t nLegs, legIdx, stepIdx;
  bool active;
} mis = { nullptr, 0, 0, 0, false };
Station curStation = ST_NONE;

// ---- 介面 ----
enum MenuId : uint8_t {
  MENU_MORNING, MENU_EVENING, MENU_A, MENU_B, MENU_C, MENU_D, MENU_E,
  MENU_LINEVIEW, MENU_LINECAL, MENU_ASH_EMPTY, MENU_ASH_FULL, MENU_ARMTEST, MENU_NETINFO, MENU_COUNT
};
const char* const MENU_NAME[MENU_COUNT] = {
  "MORNING A+B", "EVENING C+D+E", "A dock>table", "B table>burner", "C burner>table",
  "D table>ash", "E ash>dock", "LINE VIEW", "LINE CAL", "ASH SET EMPTY", "ASH SET FULL", "ARM TEST", "NET INFO"
};
uint8_t menuSel = MENU_MORNING;
bool    upPrev = false, downPrev = false;
unsigned long lastBtn = 0, oledNext = 0, msgUntil = 0, lastLineView = 0;
bool    oledDirty = true;
String  msg1, msg2;

// ═══════════════════════════════════════════════════════════════════════════
// 空氣感測（沿用原香爐韌體）
// ═══════════════════════════════════════════════════════════════════════════
void pushSample(uint16_t c) {
  if (cbufCount < BUF_N) {
    cbuf[cbufCount++] = { millis(), c };
  } else {
    memmove(cbuf, cbuf + 1, sizeof(Sample) * (BUF_N - 1));
    cbuf[BUF_N - 1] = { millis(), c };
  }
  if (cbufCount >= 2) {
    Sample& a = cbuf[0];
    Sample& b = cbuf[cbufCount - 1];
    float mins = (b.ms - a.ms) / 60000.0f;
    if (mins > 0.05f) slopePpmMin = ((float)b.co2 - (float)a.co2) / mins;
  }
}

void baselineInit() {
  for (uint8_t i = 0; i < BASELINE_WINDOW_MIN; i++) co2Buckets[i] = 0xFFFF;
  bucketStart = millis();
}

// 每分鐘記一個最小值，基線 = 窗內所有分鐘的最小值。取最小不取平均，要的是「沒人時的底」。
void baselineUpdate(uint16_t v) {
  if (v == 0) return;
  if (v < bucketMin) bucketMin = v;
  if (millis() - bucketStart >= 60000UL) {
    co2Buckets[bucketIdx] = bucketMin;
    bucketIdx = (bucketIdx + 1) % BASELINE_WINDOW_MIN;
    bucketMin = 0xFFFF;
    bucketStart = millis();
  }
}

uint16_t co2Baseline() {
  uint16_t m = 0xFFFF;
  for (uint8_t i = 0; i < BASELINE_WINDOW_MIN; i++)
    if (co2Buckets[i] < m) m = co2Buckets[i];
  if (m == 0xFFFF) m = (bucketMin != 0xFFFF) ? bucketMin : CO2_BASELINE_INIT;
  return m;
}

void serviceAir() {
  uint32_t now = millis();

  if (scdOk && now - lastScdPoll >= SCD_POLL_MS) {
    lastScdPoll = now;
    muxSelect(CH_SCD41);
    if (scd41.readMeasurement()) {
      co2   = scd41.getCO2();
      baselineUpdate(co2);
      tScd  = scd41.getTemperature();
      rhScd = scd41.getHumidity();
      pushSample(co2);
      lastScdOk = millis();
    }
  }

  // 原韌體每圈都讀 SHT31；合併版主迴圈快很多，每次量測約卡 20 ms，所以改成 1 Hz 並一次讀兩個值
  if (shtOk && now - lastShtPoll >= SHT_POLL_MS) {
    lastShtPoll = now;
    muxSelect(CH_SHT31);
    float t = NAN, h = NAN;
    if (sht31.readBoth(&t, &h)) {
      if (!isnan(t)) tSht = t;
      if (!isnan(h)) rhSht = h;
    }
  }

  sensorFault = !scdOk || (lastScdOk == 0) || (millis() - lastScdOk > SENSOR_STALE_MS);
  conf = 0.5f;
  if (!isnan(tScd) && !isnan(tSht) && fabsf(tScd - tSht) < 2.0f) conf = 1.0f;
  co2Alarm = (co2 != 0 && co2 >= CO2_ALARM_PPM);
}

// ═══════════════════════════════════════════════════════════════════════════
// 熱電偶與安全聯鎖
// ═══════════════════════════════════════════════════════════════════════════
// MAX6675 讀取，時序與 Adafruit 程式庫相同。
// 另外多做兩項檢查：第 15 位與第 1 位固定為 0、整筆為 0 代表晶片沒接，都當作故障，
// 避免沒接模組時被誤讀成 0°C 而沒有觸發安全態。
float readThermocouple() {
  digitalWrite(PIN_TC_CS, LOW);
  delayMicroseconds(10);
  uint16_t v = 0;
  for (int i = 15; i >= 0; i--) {
    digitalWrite(PIN_TC_SCK, LOW);
    delayMicroseconds(10);
    if (digitalRead(PIN_TC_SO)) v |= (1 << i);
    digitalWrite(PIN_TC_SCK, HIGH);
    delayMicroseconds(10);
  }
  digitalWrite(PIN_TC_CS, HIGH);
  if (v == 0 || (v & 0x8002)) return NAN;   // 沒接晶片或資料格式不對
  if (v & 0x0004) return NAN;               // 熱電偶開路
  return (v >> 3) * 0.25f;
}

void serviceSafety() {
  if (millis() - lastTcRead < TC_READ_MS) return;
  lastTcRead = millis();
  float t = readThermocouple();
  if (isnan(t)) {
    tcFault = true;
  } else {
    tcFault = false;
    tempC = t;
    if (t >= T_LOCK)         interlock = true;
    else if (t <= T_RELEASE) interlock = false;
  }
}

bool ashCool() { return !tcFault && !isnan(tempC) && tempC < ASH_COOL_C; }

// 會阻塞好幾秒的網路動作期間，聯鎖無法反應。只有溫度離門檻夠遠，或已經在安全態時才允許。
bool safeToBlock() {
  if (tcFault || interlock || isnan(tempC)) return true;
  return tempC < T_LOCK - BLOCK_TEMP_MARGIN;
}

// ═══════════════════════════════════════════════════════════════════════════
// 風扇：本地 FSM 與優先權（沿用原香爐韌體）
// ═══════════════════════════════════════════════════════════════════════════
void tachISR() { tachPulses++; }
void fanWrite(uint8_t duty) { analogWrite(PIN_FAN, duty); }

uint8_t localFSM() {
  if (tcFault || interlock) { strcpy(localState, "S3"); idleSince = 0; return 0; }
  if (strcmp(localState, "S3") == 0) { strcpy(localState, "S1"); idleSince = 0; }
  if (sensorFault) { strcpy(localState, "S1"); idleSince = 0; return FALLBACK_DUTY; }

  bool isS0 = (strcmp(localState, "S0") == 0);
  bool isS1 = (strcmp(localState, "S1") == 0);
  bool isS2 = (strcmp(localState, "S2") == 0);
  uint16_t base   = co2Baseline();
  uint16_t thS2   = base + T1_DELTA;
  uint16_t thS2Ex = base + T1_EXIT_DELTA;
  uint16_t thIdle = base + CO2_IDLE_DELTA;

  if ((isS0 || isS1) && (co2 > thS2 || slopePpmMin > SLOPE_TH)) {
    strcpy(localState, "S2");
  } else if (isS2 && co2 < thS2Ex && slopePpmMin < SLOPE_TH / 2) {
    strcpy(localState, "S1");
  } else if (isS1 && co2 != 0 && co2 < thIdle) {
    if (idleSince == 0) idleSince = millis();
    else if (millis() - idleSince > IDLE_HOLD_MS) strcpy(localState, "S0");
  }
  if (co2 >= thIdle) {
    idleSince = 0;
    if (strcmp(localState, "S0") == 0) strcpy(localState, "S1");
  }
  if (strcmp(localState, "S0") == 0) return 0;
  if (strcmp(localState, "S2") == 0) return 220;
  return 70;
}

void serviceFan() {
  uint8_t localDuty = localFSM();
  uint8_t duty;
  if (piSeen && millis() - lastPiCmd < PI_TIMEOUT_MS) { duty = piDuty;    strcpy(mode, "PI"); }
  else                                                 { duty = localDuty; strcpy(mode, "FALLBACK"); }
  if (co2Alarm) duty = 255;
  if (duty > FAN_MAX_DUTY) duty = FAN_MAX_DUTY;   // 溫和捕集上限
  if (tcFault || interlock) duty = 0;             // 安全聯鎖優先於一切
  if (duty != outDuty) oledDirty = true;
  outDuty = duty;
  fanWrite(outDuty);
}

#if USE_PCF8574
// 舊香爐罩的霧化與罩內 LED（PCF8574 在 I2C3）。廟公機器人預設不用
const uint8_t PCF8574_ADDR = 0x20;
uint8_t pcfOut = 0;
void pcfWrite(uint8_t v) {
  pcfOut = v;
  muxSelect(CH_PCF);
  Wire1.beginTransmission(PCF8574_ADDR);
  Wire1.write(pcfOut);
  Wire1.endTransmission();
}
#endif

// ═══════════════════════════════════════════════════════════════════════════
// HuskyLens：香灰高度（沿用 ASH_LEVEL）
// ═══════════════════════════════════════════════════════════════════════════
void huskySelect() { muxSelect(HUSKY_I2C_PORT - 1); }

void ashLoad() {
  EEPROM.get(ASH_EEPROM_ADDR, ashCal);
  if (ashCal.magic != ASH_EEPROM_MAGIC) { ashCal.magic = 0; ashCal.hEmpty = 0; ashCal.hFull = 0; }
}

void ashSave() {
  ashCal.magic = ASH_EEPROM_MAGIC;
  EEPROM.put(ASH_EEPROM_ADDR, ashCal);
}

// 最近幾筆量測值（ASH_MEASURE 選的框高度或中心 y）的去頭去尾平均（×10，保留一位小數）：排序後丟掉最高、最低各 1/4，剩下的取平均。
// 比中位數細（可以算出 144.4），又不會被偶爾跳一下的框拉走。樣本不足一半回傳 -1
int ashAvg10() {
  if (ashHistN < (ASH_SAMPLES + 1) / 2) return -1;
  int tmp[ASH_SAMPLES];
  for (uint8_t i = 0; i < ashHistN; i++) tmp[i] = ashHist[i];
  for (uint8_t i = 1; i < ashHistN; i++) {
    int k = tmp[i]; int j2 = i - 1;
    while (j2 >= 0 && tmp[j2] > k) { tmp[j2 + 1] = tmp[j2]; j2--; }
    tmp[j2 + 1] = k;
  }
  uint8_t cut = ashHistN / 4;
  long sum = 0;
  for (uint8_t i = cut; i < ashHistN - cut; i++) sum += tmp[i];
  uint8_t m = ashHistN - 2 * cut;
  return (int)((sum * 10 + m / 2) / m);
}

// 四捨五入成整數像素，給校正存檔與遙測用
int ashMedian() {
  int a = ashAvg10();
  return (a < 0) ? -1 : (a + 5) / 10;
}

// 換算成香灰百分比。span 可正可負，貼色條與直接學灰色兩種作法都適用。用小數像素算，% 才不會一格一格跳
int ashPercent() {
  int a = ashAvg10();
  if (ashCal.magic != ASH_EEPROM_MAGIC || a < 0) return -1;
  int span = ashCal.hEmpty - ashCal.hFull;
  if (span == 0) return -1;
  long p = ((long)ashCal.hEmpty * 10 - a) * 100 / ((long)span * 10);
  return (int)constrain(p, 0L, 100L);
}

bool motionBusy();

void serviceHusky() {
#if USE_HUSKY
  unsigned long now = millis();
  if (!huskyOK) {
    // 連線嘗試會等回應，只在車子靜止時做
    if (!motionBusy() && now >= huskyRetryAt) {
      huskyRetryAt = now + 5000;
      huskySelect();
      husky.setTimeOutDuration(HUSKY_TIMEOUT_MS);
      huskyOK = husky.begin(Wire1);
      if (huskyOK) {
        husky.writeAlgorithm(ALGORITHM_COLOR_RECOGNITION);
        huskyFails = 0;
        logMsg("HuskyLens 已連線（I2C" + String(HUSKY_I2C_PORT) + "），切到顏色辨識");
      }
    }
    return;
  }
  if (now < huskyNext) return;
  huskyNext = now + HUSKY_PERIOD_MS;

  huskySelect();
  if (!husky.requestBlocks(ASH_COLOR_ID)) {
    if (++huskyFails >= 10) {
      huskyOK = false;
      huskyRetryAt = now + 2000;
      logMsg(F("HuskyLens 連續沒有回應，稍後重連"));
    }
    return;
  }
  huskyFails = 0;
  int n = husky.countBlocks(ASH_COLOR_ID);
  hres.n = (n > 0) ? n : 0;
  hres.ms = now;
  if (n <= 0) { hres.seen = false; return; }

  long bestArea = -1;
  for (int i = 0; i < n; i++) {
    HUSKYLENSResult r = husky.getBlock(ASH_COLOR_ID, i);
    long area = (long)r.width * r.height;
    if (area > bestArea) {
      bestArea = area;
      hres.x = r.xCenter; hres.y = r.yCenter; hres.w = r.width; hres.h = r.height;
    }
  }
  hres.seen = true;
#if ASH_MEASURE == 2
  ashHist[ashHistI] = hres.y - hres.h / 2;   // 香灰框的上緣
#elif ASH_MEASURE == 1
  ashHist[ashHistI] = hres.y;   // 香灰表面在畫面裡的位置
#else
  ashHist[ashHistI] = hres.h;   // 色條露出來的高度
#endif
  ashHistI = (ashHistI + 1) % ASH_SAMPLES;
  if (ashHistN < ASH_SAMPLES) ashHistN++;
#endif
}

// ═══════════════════════════════════════════════════════════════════════════
// M-Vision：供品與供盤（沿用 CAM_TEST 的封包解析）
// ═══════════════════════════════════════════════════════════════════════════
// 封包：0xAA、N、N 個 16 位元數值（低位元組在前）、XOR 檢查碼。邊收邊找開頭，掉位元組會自己對齊
// 照片：0xAB、0x4A、長度（低位元組在前）、JPEG、XOR 檢查碼（只算 JPEG）
void serviceMVision() {
#if USE_MVISION
  static uint8_t state = 0, len = 0, idx = 0, chk = 0;
  static uint8_t buf[40];
  uint16_t guard = 0;
  // 收照片時一次多讀一些，避免 UART 接收緩衝區滿了掉資料
  uint16_t limit = (state >= 10) ? 600 : 96;
  while (Serial1.available() && guard++ < limit) {
    uint8_t b = Serial1.read();
    switch (state) {
      case 0:
        if (b == 0xAA) { chk = 0xAA; state = 1; }
#if USE_SNAPSHOT
        else if (b == 0xAB) state = 10;
#endif
        break;
#if USE_SNAPSHOT
      case 10: state = (b == 0x4A) ? 11 : 0; break;
      case 11: snapLen = b; state = 12; break;
      case 12:
        snapLen |= (uint16_t)b << 8;
        // 上一張還沒送完、或長度不合理，就不收這一張。後面的 JPEG 位元組會在狀態 0 被當成雜訊略過，
        // 就算裡面剛好有 0xAA，也會被檢查碼和座標範圍擋掉
        if (snapLen == 0 || snapLen > SNAP_MAX_BYTES || snapReady) { state = 0; snapBad++; break; }
        snapRx = 0; snapChk = 0; state = 13; limit = 600;
        break;
      case 13:
        snapBuf[snapRx++] = b; snapChk ^= b;
        if (snapRx >= snapLen) state = 14;
        break;
      case 14:
        if (b == snapChk && snapBuf[0] == 0xFF && snapBuf[1] == 0xD8) {
          snapReady = true; snapSent = 0; snapSeq++; snapOk++;
        } else {
          snapBad++;
        }
        snapWaiting = false;
        state = 0;
        break;
#endif
      case 1:
        if (b == 0 || b > 20) { state = 0; break; }
        len = b; chk ^= b; idx = 0; state = 2;
        break;
      case 2:
        buf[idx++] = b; chk ^= b;
        if (idx >= len * 2) state = 3;
        break;
      case 3:
        if (b == chk && len >= 12) {
          uint16_t v[12];
          for (uint8_t i = 0; i < 12; i++) v[i] = buf[2 * i] | ((uint16_t)buf[2 * i + 1] << 8);
          // 座標超出 320 x 240 就是誤把照片裡的 0xAA 當成開頭，丟掉
          if (v[1] > 320 || v[2] > 240 || v[5] > 320 || v[6] > 240) { mvBad++; state = 0; break; }
          mv.plate = v[0] & 1;  mv.target = v[0] & 2;
          mv.px = v[1]; mv.py = v[2]; mv.pw = v[3]; mv.ph = v[4];
          mv.tx = v[5]; mv.ty = v[6]; mv.tw = v[7]; mv.th = v[8];
          mv.nOut = v[9]; mv.nOn = v[10]; mv.frame = v[11];
          mv.ms = millis();
          mvGood++;
        } else {
          mvBad++;
        }
        state = 0;
        break;
    }
  }
#endif
}

bool mvFresh() { return mv.ms != 0 && millis() - mv.ms < MVISION_STALE_MS; }

// ═══════════════════════════════════════════════════════════════════════════
// 網路：WiFi → 筆電中繼（TCP 一行一筆）
// ═══════════════════════════════════════════════════════════════════════════
size_t txUsed() { return (txHead + TXQ_SIZE - txTail) % TXQ_SIZE; }

// 整行放進佇列；放不下就整行丟掉，避免送出半行
void netEnqueue(const char* s, size_t n) {
  if (netState != NET_ONLINE) return;
  if (n + 1 > TXQ_SIZE - 1 - txUsed()) { netDropped++; return; }
  for (size_t i = 0; i < n; i++) { txq[txHead] = s[i]; txHead = (txHead + 1) % TXQ_SIZE; }
  txq[txHead] = '\n'; txHead = (txHead + 1) % TXQ_SIZE;
}

void netStartDiscovery() {
  if (strlen(SERVER_IP) > 0 && relayIP.fromString(SERVER_IP)) {
    netState = NET_CONNECTING;
    netNextTry = 0;
    return;
  }
  udp.begin(BEACON_PORT);
  netState = NET_DISCOVER;
}

void netDrop(const char* why) {
  net.stop();
  txHead = txTail = 0;               // 丟掉沒送完的半行
  logMsg(String("中繼連線中斷：") + why);
  oledDirty = true;
  if (WiFi.status() == WL_CONNECTED) netStartDiscovery();
  else { netState = NET_WIFI_DOWN; netNextTry = millis() + 2000; }
}

// 會阻塞最多十幾秒，只在車子靜止時呼叫
void netWifiConnect() {
  logMsg(String("WiFi 連線到 ") + SECRET_SSID);
  MiniR4.OLED.clearDisplay(); MiniR4.OLED.setTextSize(1);
  MiniR4.OLED.setCursor(0, 0); MiniR4.OLED.print(F("WiFi connecting..."));
  MiniR4.OLED.display();

  unsigned long t0 = millis();
  WiFi.begin(SECRET_SSID, SECRET_PASS);
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_CONNECT_TIMEOUT_MS) delay(100);
  if (WiFi.status() == WL_CONNECTED) {
    while (WiFi.localIP() == IPAddress(0, 0, 0, 0) && millis() - t0 < WIFI_CONNECT_TIMEOUT_MS + 5000) delay(100);
    wifiRssi = WiFi.RSSI();
    IPAddress ip = WiFi.localIP();
    logMsg("WiFi 已連線，IP " + String(ip[0]) + "." + ip[1] + "." + ip[2] + "." + ip[3] +
           "，訊號 " + String(wifiRssi) + " dBm");
    netStartDiscovery();
  } else {
    logMsg(F("WiFi 連線失敗：檢查帳密、iPhone 熱點要開「最大化相容性」（R4 只支援 2.4 GHz）"));
    netState = NET_WIFI_DOWN;
    netNextTry = millis() + WIFI_RETRY_MS;
  }
  oledDirty = true;
}

void handleLine(char* s);

void netPollRx() {
  uint8_t guard = 0;
  while (net.available() && guard++ < 64) {
    char c = net.read();
    if (c == '\n' || c == '\r') {
      if (netLen) { netLine[netLen] = 0; handleLine(netLine); netLen = 0; }
    } else if (netLen < sizeof(netLine) - 1) {
      netLine[netLen++] = c;
    }
  }
}

void netPumpTx(size_t maxBytes) {
  size_t used = txUsed();
  if (!used) return;
  size_t n = used < maxBytes ? used : maxBytes;
  size_t contig = TXQ_SIZE - txTail;
  if (n > contig) n = contig;
  size_t w = net.write(txq + txTail, n);
  if (w == 0) {
    if (++netWriteFails >= 5) netDrop("寫入失敗");
    return;
  }
  netWriteFails = 0;
  txTail = (txTail + w) % TXQ_SIZE;
  netSent += w;
}

void serviceNet() {
  if (netState == NET_DISABLED) return;
  unsigned long now = millis();
  switch (netState) {
    case NET_WIFI_DOWN:
      if (now >= netNextTry && !motionBusy() && safeToBlock()) netWifiConnect();
      break;

    case NET_DISCOVER:
      if (now - netLastBeacon >= 200) {
        netLastBeacon = now;
        int n = udp.parsePacket();
        if (n > 0) {
          char b[48];
          int k = udp.read(b, sizeof(b) - 1);
          if (k < 0) k = 0;
          b[k] = 0;
          size_t tl = strlen(BEACON_TAG);
          if (strncmp(b, BEACON_TAG, tl) == 0) {
            relayIP = udp.remoteIP();
            int p = atoi(b + tl + 1);
            if (p > 0) relayPort = p;
            udp.stop();
            netState = NET_CONNECTING;
            netNextTry = 0;
            logMsg("找到筆電中繼 " + String(relayIP[0]) + "." + relayIP[1] + "." + relayIP[2] + "." +
                   relayIP[3] + ":" + String(relayPort));
          }
        }
      }
      if (now - netLastCheck >= 2000) {
        netLastCheck = now;
        if (WiFi.status() != WL_CONNECTED) { udp.stop(); netState = NET_WIFI_DOWN; netNextTry = now; }
      }
      break;

    case NET_CONNECTING:
      if (now >= netNextTry && !motionBusy() && safeToBlock()) {
        if (net.connect(relayIP, relayPort)) {
          netState = NET_ONLINE;
          netWriteFails = 0; netConnFails = 0;
          txHead = txTail = 0;
          const char* hello = "# HELLO " DEVICE_ID;
          netEnqueue(hello, strlen(hello));
          logMsg(F("已連上筆電中繼"));
          oledDirty = true;
        } else {
          netNextTry = now + 3000;
          if (++netConnFails >= 3) { netConnFails = 0; netStartDiscovery(); }   // 筆電可能換了 IP，重新找
        }
      }
      break;

    case NET_ONLINE:
      netPumpTx(motionBusy() ? TX_CHUNK_MOVING : TX_CHUNK_IDLE);
      if (now - netLastRx >= NET_RX_POLL_MS) { netLastRx = now; netPollRx(); }
      if (now - netLastCheck >= 1000) {
        netLastCheck = now;
        if (!net.connected()) netDrop("中繼已關閉");
      }
      break;

    default: break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// M-Vision 拍照回傳：向相機要照片，收到後切成 base64 小段經 WiFi 送給筆電中繼
// 每行：J<序號>,<第幾段>,<總段數>,<base64>。中繼收齊後轉成 JPEG 上傳，網站拿來當相機畫面
// ═══════════════════════════════════════════════════════════════════════════
#if USE_SNAPSHOT
const uint16_t SNAP_RAW_PER_LINE = 180;       // 每行 180 位元組，base64 後 240 字，整行約 255 B
static const char B64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

size_t b64enc(const uint8_t* in, size_t n, char* out) {
  size_t o = 0;
  for (size_t i = 0; i < n; i += 3) {
    uint32_t v = (uint32_t)in[i] << 16;
    if (i + 1 < n) v |= (uint32_t)in[i + 1] << 8;
    if (i + 2 < n) v |= in[i + 2];
    out[o++] = B64[(v >> 18) & 63];
    out[o++] = B64[(v >> 12) & 63];
    out[o++] = (i + 1 < n) ? B64[(v >> 6) & 63] : '=';
    out[o++] = (i + 2 < n) ? B64[v & 63] : '=';
  }
  return o;
}

void serviceSnapshot() {
  unsigned long now = millis();
  if (snapWaiting && now - snapReqAt > SNAP_TIMEOUT_MS) snapWaiting = false;   // 相機沒回，下次再要
  if (netState != NET_ONLINE) { snapReady = false; return; }

  if (!snapReady) {
    // 只在靜止、相機有資料時要照片；行進中不拍，把迴圈時間留給循線
    if (!snapWaiting && !motionBusy() && mvFresh() && now - snapReqAt >= SNAP_PERIOD_MS) {
      Serial1.write('S');
      snapReqAt = now;
      snapWaiting = true;
    }
    return;
  }

  // 送出：傳送佇列有空間才放一行，每圈最多兩行，不擠掉遙測
  uint16_t total = (snapLen + SNAP_RAW_PER_LINE - 1) / SNAP_RAW_PER_LINE;
  for (uint8_t k = 0; k < 2 && snapReady; k++) {
    if (TXQ_SIZE - 1 - txUsed() < 300) return;
    uint16_t part = snapSent / SNAP_RAW_PER_LINE;
    uint16_t m = snapLen - snapSent;
    if (m > SNAP_RAW_PER_LINE) m = SNAP_RAW_PER_LINE;
    char line[272];
    int h = snprintf(line, sizeof(line), "J%u,%u,%u,", snapSeq, part, total);
    h += b64enc(snapBuf + snapSent, m, line + h);
    netEnqueue(line, h);
    snapSent += m;
    if (snapSent >= snapLen) snapReady = false;
  }
}
#else
void serviceSnapshot() {}
#endif

// ═══════════════════════════════════════════════════════════════════════════
// 手臂、夾爪、抽風（RC1 夾爪上下、RC2 抹平香灰、RC3 灰盤、RC4 抽風；DC1/DC2 夾爪）
// 角度都在 config.h。動作只在車子靜止時接受；等伺服轉到位時安全檢查與風扇照常運作
// ═══════════════════════════════════════════════════════════════════════════
int  servoNow[4] = { -1, -1, -1, -1 };
bool armBusy = false, armAbort = false;
unsigned long hoodManualUntil = 0;

void setServo(uint8_t i, int angle) {
  if (i > 3 || angle < 0 || angle > 180 || servoNow[i] == angle) return;
  switch (i) {
    case 0: MiniR4.RC1.setAngle(angle); break;
    case 1: MiniR4.RC2.setAngle(angle); break;
    case 2: MiniR4.RC3.setAngle(angle); break;
    case 3: MiniR4.RC4.setAngle(angle); break;
  }
  servoNow[i] = angle;
}

// 夾爪：正值夾緊、負值放開、0 停止
void gripPower(int p) {
  MiniR4.M1.setPower(GRIP_R_REVERSE ? -p : p);   // DC1 夾爪右
  MiniR4.M2.setPower(GRIP_L_REVERSE ? -p : p);   // DC2 夾爪左
}

void serviceSafety();
void serviceAir();
void serviceFan();
void serviceMVision();
void serviceNet();
void serviceUsbRx();

// 等待期間照常跑安全、空氣、風扇、相機與網路，不讓整台機器停下來。回傳 false = 被 STOP 中止
bool armWait(uint16_t ms) {
  unsigned long t0 = millis();
  while (millis() - t0 < ms) {
    serviceUsbRx(); serviceSafety(); serviceAir(); serviceFan(); serviceMVision(); serviceNet();
    if (armAbort) return false;          // 手臂動作中收到的 ARM 指令會因 armBusy 被拒，只有 STOP 會生效
    delay(5);
  }
  return true;
}

void armHome() {
  gripPower(0);
  for (uint8_t i = 0; i < 4; i++) if (SERVO_HOME[i] >= 0) setServo(i, SERVO_HOME[i]);
}

// 執行一個手臂動作。回傳 nullptr = 成功，否則是失敗原因
const char* armAction(const char* name) {
  if (motionBusy()) return "車子在移動，手臂動作只在靜止時執行";
  if (armBusy)      return "上一個手臂動作還沒做完";
  armBusy = true; armAbort = false;
  const char* why = nullptr;
  if      (!strcmp(name, "GRIP_UP"))    setServo(0, RC_GRIP_UP);
  else if (!strcmp(name, "GRIP_DOWN"))  setServo(0, RC_GRIP_DOWN);
  else if (!strcmp(name, "LEVEL")) {                     // 抹一次就收回
    setServo(1, RC_LEVEL_SWEEP);
    if (armWait(SERVO_SETTLE_MS)) setServo(1, RC_LEVEL_HOME);
  }
  else if (!strcmp(name, "DUMP")) {                      // 倒灰後放平
    setServo(2, RC_TRAY_DUMP);
    if (armWait(SERVO_SETTLE_MS * 2)) setServo(2, RC_TRAY_HOME);
  }
  else if (!strcmp(name, "HOOD_ON"))  { setServo(3, RC_HOOD_ON);  hoodManualUntil = millis() + 10000; }
  else if (!strcmp(name, "HOOD_OFF")) { setServo(3, RC_HOOD_OFF); hoodManualUntil = millis() + 10000; }
  else if (!strcmp(name, "GRIP_CLOSE")) {
    gripPower(GRIP_POWER);
    if (armWait(GRIP_MOVE_MS)) gripPower(GRIP_HOLD_POWER); else gripPower(0);
  }
  else if (!strcmp(name, "GRIP_OPEN")) {
    gripPower(-GRIP_POWER);
    armWait(GRIP_MOVE_MS);
    gripPower(0);
  }
  else if (!strcmp(name, "GRIP_STOP")) gripPower(0);
  else if (!strcmp(name, "HOME"))      armHome();
  else why = "沒有這個手臂動作";
  if (armAbort) { gripPower(0); why = "被 STOP 中止"; }
  armBusy = false;
  return why;
}

// 選單「ARM TEST」：每個動作做一次，方便確認角度與方向
void armTest() {
  static const char* const SEQ[] = { "GRIP_DOWN", "GRIP_UP", "LEVEL", "DUMP", "HOOD_ON", "HOOD_OFF",
                                     "GRIP_CLOSE", "GRIP_OPEN", "HOME" };
  logMsg(F("手臂測試開始：夾爪下、上，抹平，倒灰，抽風開、關，夾爪夾、放"));
  for (uint8_t i = 0; i < sizeof(SEQ) / sizeof(SEQ[0]); i++) {
    const char* why = armAction(SEQ[i]);
    logMsg(String("手臂 ") + SEQ[i] + (why ? String("：") + why : String("")));
    if (why || !armWait(SERVO_SETTLE_MS)) break;
  }
  armHome();
  logMsg(F("手臂測試結束"));
}

// RC4 抽風跟著風扇：風扇在轉而且車子靜止就打開；手動指令後 10 秒內不自動改
void serviceHood() {
#if HOOD_FOLLOWS_FAN
  if (armBusy || millis() < hoodManualUntil) return;
  setServo(3, (!motionBusy() && outDuty > 0) ? RC_HOOD_ON : RC_HOOD_OFF);
#endif
}

// ═══════════════════════════════════════════════════════════════════════════
// 指令（USB 與 WiFi 共用，與原 Pi 協定相容）
// ═══════════════════════════════════════════════════════════════════════════
void abortMission(const char* why);
void runMenu(uint8_t i);
void stationContinue();
void enterState(MState s);
void stopMotors();

// 回報遠端指令的結果：A{"cmd":"RUN MORNING","ok":1,"why":"..."}
void sendAck(const char* cmd, bool ok, const char* why) {
  lb.clear();
  lb.print(F("A{\"cmd\":\"")); lb.print(cmd);
  lb.print(F("\",\"ok\":"));   lb.print(ok ? 1 : 0);
  lb.print(F(",\"why\":\""));  lb.print(why);
  lb.print(F("\"}"));
  Serial.write(lb.s, lb.n); Serial.write('\n');
  netEnqueue(lb.s, lb.n);
}

#if REMOTE_CONTROL
void remoteRun(const char* cmd, const char* name) {
  static const char* const NAMES[] = { "MORNING", "EVENING", "A", "B", "C", "D", "E" };
  static const uint8_t MENUS[] = { MENU_MORNING, MENU_EVENING, MENU_A, MENU_B, MENU_C, MENU_D, MENU_E };
  int idx = -1;
  for (uint8_t i = 0; i < sizeof(MENUS); i++) if (strcmp(name, NAMES[i]) == 0) idx = i;
  if (idx < 0)                      { sendAck(cmd, false, "沒有這個任務"); return; }
  if (ms != MS_IDLE && ms != MS_FAIL) { sendAck(cmd, false, "機器人不是待命狀態"); return; }
  if (isnan(battV) || battV < REMOTE_MIN_BATT_V) { sendAck(cmd, false, "電池電壓太低或沒接電池"); return; }
  if (ms == MS_FAIL) enterState(MS_IDLE);
  logMsg(String("遠端開始任務 ") + name);
  runMenu(MENUS[idx]);
  sendAck(cmd, true, "已開始");
}
#endif

void handleLine(char* s) {
  if (strncmp(s, "FAN ", 4) == 0) {
    int v = constrain(atoi(s + 4), 0, 255);
    piDuty = (uint8_t)v; lastPiCmd = millis(); piSeen = true;
  } else if (strcmp(s, "PING") == 0) {
    lastPiCmd = millis(); piSeen = true;
  } else if (strcmp(s, "STOP") == 0) {
    armAbort = true; gripPower(0);
    abortMission("收到遠端 STOP");
    sendAck(s, true, "已停車");
  } else if (strncmp(s, "ARM ", 4) == 0) {
    const char* why = armAction(s + 4);
    sendAck(s, why == nullptr, why ? why : "完成");
#if REMOTE_CONTROL
  } else if (strncmp(s, "RUN ", 4) == 0) {
    remoteRun(s, s + 4);
  } else if (strcmp(s, "GO") == 0) {
    if (ms != MS_STATION) { sendAck(s, false, "不在站點，沒有下一段可以走"); return; }
    logMsg(F("遠端指令：繼續下一段"));
    stationContinue();
    sendAck(s, true, "繼續下一段");
  } else if (strcmp(s, "END") == 0) {
    if (ms != MS_STATION) { sendAck(s, false, "不在站點"); return; }
    stopMotors(); mis.active = false;
    logMsg(F("任務由遠端結束"));
    enterState(MS_IDLE);
    sendAck(s, true, "任務已結束");
  } else if (strcmp(s, "CLEAR") == 0) {
    if (ms != MS_FAIL) { sendAck(s, false, "目前沒有失敗狀態"); return; }
    enterState(MS_IDLE);
    sendAck(s, true, "已回到待命");
#endif
  }
}

void serviceUsbRx() {
  uint8_t guard = 0;
  while (Serial.available() && guard++ < 64) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (usbLen) { usbLine[usbLen] = 0; handleLine(usbLine); usbLen = 0; }
    } else if (usbLen < sizeof(usbLine) - 1) {
      usbLine[usbLen++] = c;
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 遙測
// ═══════════════════════════════════════════════════════════════════════════
const char* motionName() {
  switch (ms) {
    case MS_IDLE: return "IDLE";       case MS_SPIN: return "SPIN";
    case MS_ACQUIRE: return "ACQUIRE"; case MS_FOLLOW: return "FOLLOW";
    case MS_CROSS: return "CROSS";     case MS_AXLE: return "AXLE";
    case MS_ROLL: return "ROLL";       case MS_STATION: return "STATION";
    case MS_CAL: return "LINECAL";     case MS_LINEVIEW: return "LINEVIEW";
    case MS_FAIL: return "FAIL";
  }
  return "?";
}

const char* stationName(Station s) {
  switch (s) {
    case ST_TABLE: return "TABLE"; case ST_BURNER: return "BURNER";
    case ST_ASH: return "ASH";     case ST_DOCK: return "DOCK";
    default: return "NONE";
  }
}

// 每秒一行。前半段欄位與原香爐韌體完全相同，Pi 與儀表板不必改
void sendTelemetry() {
  lb.clear();
  lb.print(F("{\"ts\":"));            lb.print(millis());
  lb.print(F(",\"co2\":"));           lb.print(co2);
  lb.print(F(",\"co2_base\":"));      lb.print(co2Baseline());
  lb.print(F(",\"slope\":"));         lb.print(slopePpmMin, 1);
  lb.print(F(",\"t_scd\":"));         lb.print(j(tScd), 2);
  lb.print(F(",\"rh_scd\":"));        lb.print(j(rhScd), 1);
  lb.print(F(",\"t_sht\":"));         lb.print(j(tSht), 2);
  lb.print(F(",\"rh_sht\":"));        lb.print(j(rhSht), 1);
  lb.print(F(",\"conf\":"));          lb.print(conf, 1);
  lb.print(F(",\"alarm\":"));         lb.print(co2Alarm ? 1 : 0);
  lb.print(F(",\"t_furnace\":"));     lb.print(tcFault ? -99.9f : j(tempC), 2);
  lb.print(F(",\"fan\":"));           lb.print(outDuty);
  lb.print(F(",\"fan_rpm\":"));       lb.print(fanRpm);
  lb.print(F(",\"interlock\":"));     lb.print(interlock ? 1 : 0);
  lb.print(F(",\"tc_fault\":"));      lb.print(tcFault ? 1 : 0);
  lb.print(F(",\"sensor_fault\":"));  lb.print(sensorFault ? 1 : 0);
  lb.print(F(",\"mode\":\""));        lb.print(mode);
  lb.print(F("\",\"local_state\":\"")); lb.print(localState);
  // ---- 以下為廟公機器人新增 ----
  lb.print(F("\",\"dev\":\""));       lb.print(DEVICE_ID);
  lb.print(F("\",\"robot\":\""));     lb.print(motionName());
  lb.print(F("\",\"mission\":\""));   lb.print(mis.active ? missionName : "");
  lb.print(F("\",\"leg\":\""));
  if (mis.active && mis.legs) lb.print(mis.legs[mis.legIdx]->tag);
  lb.print(F("\",\"step\":"));        lb.print(mis.active ? mis.stepIdx + 1 : 0);
  lb.print(F(",\"station\":\""));     lb.print(stationName(curStation));
  lb.print(F("\",\"fail\":\""));      lb.print(ms == MS_FAIL ? failCode : "");
  lb.print(F("\",\"ash_pct\":"));     lb.print(ashPercent());
  lb.print(F(",\"ash_cool\":"));      lb.print(ashCool() ? 1 : 0);
  lb.print(F(",\"batt\":"));          lb.print(j(battV), 2);
  lb.print(F(",\"rssi\":"));          lb.print(netState == NET_ONLINE || netState == NET_DISCOVER || netState == NET_CONNECTING ? wifiRssi : 0);
  lb.print(F(",\"net_drop\":"));      lb.print(netDropped);
  lb.print(F("}"));

  Serial.write(lb.s, lb.n); Serial.write('\n');
  netEnqueue(lb.s, lb.n);
}

// 每 200 ms 一行相機結果，以 V 開頭
void sendVision() {
  lb.clear();
  lb.print(F("V{\"ts\":")); lb.print(millis());
  lb.print(F(",\"mv\":{\"ok\":")); lb.print(mvFresh() ? 1 : 0);
  if (mvFresh()) {
    lb.print(F(",\"f\":")); lb.print((mv.plate ? 1 : 0) | (mv.target ? 2 : 0));
    lb.print(F(",\"p\":[")); lb.print(mv.px); lb.print(','); lb.print(mv.py); lb.print(',');
    lb.print(mv.pw); lb.print(','); lb.print(mv.ph); lb.print(']');
    lb.print(F(",\"t\":[")); lb.print(mv.tx); lb.print(','); lb.print(mv.ty); lb.print(',');
    lb.print(mv.tw); lb.print(','); lb.print(mv.th); lb.print(']');
    lb.print(F(",\"no\":")); lb.print(mv.nOut);
    lb.print(F(",\"ni\":")); lb.print(mv.nOn);
    lb.print(F(",\"fr\":")); lb.print(mv.frame);
  }
  lb.print(F("},\"hl\":{\"ok\":")); lb.print(huskyOK ? 1 : 0);
  if (huskyOK) {
    lb.print(F(",\"n\":")); lb.print(hres.n);
    if (hres.seen) {
      lb.print(F(",\"b\":[")); lb.print(hres.x); lb.print(','); lb.print(hres.y); lb.print(',');
      lb.print(hres.w); lb.print(','); lb.print(hres.h); lb.print(']');
    }
    lb.print(F(",\"h\":"));   lb.print(ashMedian());
    lb.print(F(",\"ash\":")); lb.print(ashPercent());
  }
  lb.print(F("}}"));

  netEnqueue(lb.s, lb.n);
#if VISION_TO_USB
  Serial.write(lb.s, lb.n); Serial.write('\n');
#endif
}

// 每秒：風扇轉速、電池、遙測
void serviceTick() {
  uint32_t now = millis();
  if (now - lastTick < TICK_MS) return;
  uint32_t dt = now - lastTick;
  lastTick = now;

  noInterrupts();
  uint32_t pulses = tachPulses;
  tachPulses = 0;
  interrupts();
  fanRpm = (dt > 0) ? (uint16_t)((uint32_t)pulses * 30000UL / dt) : 0;


  battV = MiniR4.PWR.getBattVoltage();
  if (netState == NET_ONLINE) wifiRssi = WiFi.RSSI();

  sendTelemetry();
  if (!motionBusy()) oledDirty = true;
}

void serviceVisionSend() {
  if (millis() - lastVisionSend < VISION_SEND_MS) return;
  lastVisionSend = millis();
  if (netState == NET_ONLINE || VISION_TO_USB) sendVision();
}

// ═══════════════════════════════════════════════════════════════════════════
// 循線感測器與 PD
// ═══════════════════════════════════════════════════════════════════════════
const float W[10] = { -4.5, -3.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 3.5, 4.5 };

bool readSnap(Snap& s) {
  uint8_t d[10];
  if (!MiniR4.I2C0.MXLineTracer.getAllSensors(d)) return false;
  float sum = 0, total = 0;
  s.count = 0;
  for (int i = 0; i < 10; i++) {
    s.raw[i] = REVERSE_STEER ? d[9 - i] : d[i];
    int intensity = 100 - (int)s.raw[i];
    s.blk[i] = intensity > LINE_TH;
    if (s.blk[i]) { sum += intensity * W[i]; total += intensity; s.count++; }
  }
  s.err = (total > 0) ? sum / total : 0;
  s.leftOuter  = s.blk[0] || s.blk[1];
  s.rightOuter = s.blk[8] || s.blk[9];
  s.center     = s.blk[3] || s.blk[4] || s.blk[5] || s.blk[6];
  return true;
}

bool isJunction(const Snap& s) { return s.count >= JUNC_MIN_BLACK && (s.leftOuter || s.rightOuter); }
bool isNarrow(const Snap& s, bool needCenter) { return s.count >= 1 && s.count <= 4 && (!needCenter || s.center); }
char juncType(bool l, bool r) { return (l && r) ? 'T' : (l ? 'L' : (r ? 'R' : '-')); }

void driveMove(int l, int r) { MiniR4.DriveDC.Move(l, r); }
void stopMotors() { MiniR4.DriveDC.Move(0, 0); MiniR4.DriveDC.brake(true); }

void resetPD() { fErr = 0; lastErr = 0; }
void pdDrive(const Snap& s) {
  float raw = s.err;
  if (fabs(raw) < DEADBAND) raw = 0;
  fErr += ERROR_SMOOTH * (raw - fErr);
  float d = fErr - lastErr;
  lastErr = fErr;
  float turn = constrain(KP * fErr + KD * d, -(float)MAX_TURN, (float)MAX_TURN);
  driveMove(constrain((int)(BASE_SPEED + turn), -MAX_POWER, MAX_POWER),
            constrain((int)(BASE_SPEED - turn), -MAX_POWER, MAX_POWER));
}

// ═══════════════════════════════════════════════════════════════════════════
// 運動狀態機（路線表）
// ═══════════════════════════════════════════════════════════════════════════
bool motionBusy() {
  return ms == MS_SPIN || ms == MS_ACQUIRE || ms == MS_FOLLOW || ms == MS_CROSS ||
         ms == MS_AXLE || ms == MS_ROLL || ms == MS_CAL;
}

const Leg& curLeg() { return *mis.legs[mis.legIdx]; }

void enterState(MState s) {
  ms = s; msT0 = millis(); okCnt = 0; oledDirty = true;
}

void failMission(const char* why, const char* code) {
  stopMotors();
  if (ms == MS_CAL) MiniR4.I2C0.MXLineTracer.endCalibration();
  mis.active = false;
  failCode = code;
  logMsg(String("任務失敗：") + why);
  MiniR4.Buzzer.Tone(300, 500);
  enterState(MS_FAIL);
}

void abortMission(const char* why) {
  if (ms == MS_IDLE || ms == MS_FAIL || ms == MS_LINEVIEW) { stopMotors(); return; }
  failMission(why, "aborted");
}

void beginFollow() {
  resetPD();
  lostSince = 0; jcnt = 0; seenL = seenR = false; snapFails = 0;
  blankUntil = millis() + JUNC_BLANK_MS;
  segT0 = millis();
  enterState(MS_FOLLOW);
}

void startSpin(int dir, unsigned long minMs, AfterSpin after) {
  spinDir = dir; spinMin = minMs; afterSpin = after;
  enterState(MS_SPIN);
  driveMove(dir * SPIN_SPEED, -dir * SPIN_SPEED);
}

void legBegin() {
  Snap s;
  if (readSnap(s) && isNarrow(s, false)) { beginFollow(); return; }
  logMsg(F("還沒壓到線，直行找線"));
  enterState(MS_ACQUIRE);
  driveMove(ACQ_SPEED, ACQ_SPEED);
}

void startLeg() {
  const Leg& L = curLeg();
  mis.stepIdx = 0;
  curStation = ST_NONE;
  logMsg(String("路段 ") + L.name);
  if (L.turnFirst) startSpin(SPIN180_DIR, SPIN180_MIN_MS, AS_LEG_START);
  else             legBegin();
}

void startMission(const Leg* const* legs, uint8_t n, const char* name) {
  mis.legs = legs; mis.nLegs = n; mis.legIdx = 0; mis.active = true;
  missionName = name;
  logMsg(String("開始任務 ") + name);
  MiniR4.Buzzer.Tone(2000, 120);
  startLeg();
}

void missionDone() {
  stopMotors();
  mis.active = false;
  logMsg(F("任務完成"));
  MiniR4.Buzzer.Tone(2200, 200);
  msg1 = "DONE"; msg2 = String(missionName); msgUntil = millis() + 3000;
  enterState(MS_IDLE);
}

// 到站報告：把相機看到的東西印出來。手臂、夾爪尚未製作，這裡只做回報
void stationReport(Station st) {
  switch (st) {
    case ST_BURNER: {
      int p = ashPercent();
      logMsg("香爐站：香灰 " + (p < 0 ? String("未校正或看不到色條") : String(p) + "%") +
             "，香灰" + (ashCool() ? "已冷，可以整平" : "溫度未確認或還燙，不挖灰"));
      break;
    }
    case ST_TABLE:
      if (mvFresh())
        logMsg("供桌站：" + String(mv.plate ? "看到供盤" : "沒看到供盤") + "，盤外 " + String(mv.nOut) +
               " 個、盤上 " + String(mv.nOn) + " 個供品（夾爪尚未製作）");
      else
        logMsg(F("供桌站：M-Vision 沒有資料"));
      break;
    case ST_ASH:  logMsg(F("倒灰站：倒灰動作尚未製作")); break;
    case ST_DOCK: logMsg(F("充電座：已回到起點")); break;
    default: break;
  }
}

void legArrived() {
  stopMotors();
  const Leg& L = curLeg();
  curStation = L.dest;
  logMsg(String("已到站：") + L.name);
  stationReport(L.dest);
  MiniR4.Buzzer.Tone(1800, 120);
  if (mis.legIdx + 1 >= mis.nLegs) { missionDone(); return; }
  stationT0 = millis();
  enterState(MS_STATION);
}

void stationContinue() {
  mis.legIdx++;
  startLeg();
}

void onFollowEvent(bool lineEnd, char jt) {
  const Leg& L = curLeg();
  const Step& st = L.steps[mis.stepIdx];
  bool isEnd = (st.act == END_STOP || st.act == END_TURN180);

  if (isEnd) {
    if (!lineEnd) logMsg(F("線尾前看到大片黑色，視為到站"));
    pendingEnd = st.act;
    if (END_ROLL_MS > 0) { enterState(MS_ROLL); driveMove(BASE_SPEED, BASE_SPEED); return; }
    stopMotors();
    if (st.act == END_TURN180) startSpin(SPIN180_DIR, SPIN180_MIN_MS, AS_ARRIVED);
    else                       legArrived();
    return;
  }
  if (lineEnd) { failMission("還沒走完路口線就斷了", "line ended"); return; }

  String m = "第" + String(mis.stepIdx + 1) + "步 路口種類 " + String(jt) + "，預期 " + String(st.expect);
  if (st.expect != '-' && st.expect != jt) m += "（不符，仍照路線表）";
  logMsg(m + "：" + st.note);

  if (st.act == STRAIGHT) { enterState(MS_CROSS); driveMove(CROSS_SPEED, CROSS_SPEED); }
  else { pendingDir = (st.act == TURN_LEFT) ? -1 : 1; enterState(MS_AXLE); driveMove(AXLE_SPEED, AXLE_SPEED); }
}

void afterSpinDone() {
  switch (afterSpin) {
    case AS_LEG_START: legBegin(); break;
    case AS_STEP_DONE: mis.stepIdx++; beginFollow(); break;
    case AS_ARRIVED:   legArrived(); break;
  }
}

void startLineCal() {
  MiniR4.I2C0.MXLineTracer.startCalibration();
  calPhase = 0;
  enterState(MS_CAL);
  driveMove(30, -30);
  logMsg(F("循線校正：原地左右擺動"));
}

void tickMotion() {
  unsigned long now = millis();
  Snap s;
  switch (ms) {
    case MS_SPIN:
      if (now - msT0 > SPIN_TIMEOUT_MS) { failMission("原地轉逾時，找不到線", "spin timeout"); return; }
      if (now - msT0 < spinMin) return;
      if (readSnap(s) && isNarrow(s, true) && fabs(s.err) < ALIGN_ERR) {
        if (++okCnt >= ALIGN_CONFIRM) { stopMotors(); afterSpinDone(); }
      } else okCnt = 0;
      break;

    case MS_ACQUIRE:
      if (now - msT0 > ACQ_TIMEOUT_MS) { failMission("起點找不到線", "no start line"); return; }
      // 只接受細線，壓過充電座綠色邊框這種橫向色帶不會被當成線
      if (readSnap(s) && isNarrow(s, false)) { if (++okCnt >= ACQ_CONFIRM) beginFollow(); }
      else okCnt = 0;
      break;

    case MS_FOLLOW:
      if (now - segT0 > SEGMENT_TIMEOUT_MS) { failMission("這一段走太久，逾時停車", "timeout"); return; }
      if (!readSnap(s)) {
        if (++snapFails > 20) failMission("循線感測器讀取失敗，檢查 A3 埠", "sensor fail");
        return;
      }
      snapFails = 0;
      if (s.count == 0) {                       // 全白：這個場地全是直線，看不到線就是線尾
        if (lostSince == 0) lostSince = now;
        if (now - lostSince >= LOST_CONFIRM_MS) { onFollowEvent(true, '-'); return; }
        driveMove(BASE_SPEED, BASE_SPEED);
        return;
      }
      lostSince = 0;
      if (now >= blankUntil && isJunction(s)) {
        jcnt++; seenL |= s.leftOuter; seenR |= s.rightOuter;
        if (jcnt >= JUNC_CONFIRM) { onFollowEvent(false, juncType(seenL, seenR)); return; }
      } else { jcnt = 0; seenL = seenR = false; }
      pdDrive(s);
      break;

    case MS_CROSS:
      if (now - msT0 >= CROSS_MS) { mis.stepIdx++; beginFollow(); }
      break;

    case MS_AXLE:
      if (now - msT0 >= AXLE_MS) { stopMotors(); startSpin(pendingDir, SPIN90_MIN_MS, AS_STEP_DONE); }
      break;

    case MS_ROLL:
      if (now - msT0 >= END_ROLL_MS) {
        stopMotors();
        if (pendingEnd == END_TURN180) startSpin(SPIN180_DIR, SPIN180_MIN_MS, AS_ARRIVED);
        else legArrived();
      }
      break;

    case MS_STATION:
      if (STATION_WAIT_MS > 0 && now - stationT0 >= STATION_WAIT_MS) stationContinue();
      break;

    case MS_CAL: {
      const unsigned long dur[3] = { 1200, 2400, 1200 };
      const int dir[3] = { 1, -1, 1 };
      if (now - msT0 >= dur[calPhase]) {
        calPhase++;
        if (calPhase >= 3) {
          stopMotors();
          MiniR4.I2C0.MXLineTracer.endCalibration();
          MiniR4.Buzzer.Tone(1500, 150);
          logMsg(F("循線校正完成"));
          enterState(MS_IDLE);
        } else {
          msT0 = now;
          driveMove(dir[calPhase] * 30, -dir[calPhase] * 30);
        }
      }
      break;
    }

    case MS_LINEVIEW:
      if (now - lastLineView >= 150 && readSnap(s)) {
        lastLineView = now;
        char pat[11];
        for (int i = 0; i < 10; i++) pat[i] = s.blk[i] ? '#' : '.';
        pat[10] = 0;
        char jt = isJunction(s) ? juncType(s.leftOuter, s.rightOuter) : '-';
        Serial.print(F("# LINE ")); Serial.print(pat);
        Serial.print(F(" 黑=")); Serial.print(s.count);
        Serial.print(F(" 偏移=")); Serial.print(s.err, 2);
        Serial.print(F(" 路口=")); Serial.println(jt);
        msg1 = String(pat); msg2 = "n=" + String(s.count) + " e=" + String(s.err, 1) + " J=" + String(jt);
        msgUntil = now + 400;
        oledDirty = true;
      }
      break;

    default: break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 選單、按鍵、OLED、LED
// ═══════════════════════════════════════════════════════════════════════════
void showMsg(const String& a, const String& b, unsigned long ms_) {
  msg1 = a; msg2 = b; msgUntil = millis() + ms_; oledDirty = true;
}

void ashSet(bool empty) {
  int h = ashMedian();
  if (h <= 0) { MiniR4.Buzzer.Tone(300, 300); showMsg("ASH ERR", "no color strip seen", 2000); return; }
  if (empty) ashCal.hEmpty = h; else ashCal.hFull = h;
  ashSave();
  MiniR4.Buzzer.Tone(empty ? 1200 : 1600, 120);
  showMsg(empty ? "ASH EMPTY" : "ASH FULL", "h=" + String(h) + " saved", 2000);
  logMsg(String("香灰校正：") + (empty ? "空爐" : "滿爐") + " 高度 " + String(h) + " 已存入 EEPROM");
}

void showNetInfo() {
  String a, b;
  switch (netState) {
    case NET_DISABLED:   a = "NET disabled"; break;
    case NET_WIFI_DOWN:  a = "WiFi down"; break;
    case NET_DISCOVER:   a = "WiFi ok, find relay"; break;
    case NET_CONNECTING: a = "relay connecting"; break;
    case NET_ONLINE:     a = "relay ONLINE"; break;
  }
  if (netState >= NET_DISCOVER) {
    IPAddress ip = WiFi.localIP();
    b = String(ip[0]) + "." + ip[1] + "." + ip[2] + "." + ip[3] + " " + String(wifiRssi) + "dB";
  }
  showMsg(a, b, 4000);
  logMsg("網路：" + a + " " + b + "，已送 " + String(netSent) + " B，丟棄 " + String(netDropped) + " 行");
}

void runMenu(uint8_t i) {
  switch (i) {
    case MENU_MORNING:   startMission(MORNING, 2, "MORNING"); break;
    case MENU_EVENING:   startMission(EVENING, 3, "EVENING"); break;
    case MENU_A:         startMission(ONLY_A, 1, "LEG A"); break;
    case MENU_B:         startMission(ONLY_B, 1, "LEG B"); break;
    case MENU_C:         startMission(ONLY_C, 1, "LEG C"); break;
    case MENU_D:         startMission(ONLY_D, 1, "LEG D"); break;
    case MENU_E:         startMission(ONLY_E, 1, "LEG E"); break;
    case MENU_LINEVIEW:  enterState(MS_LINEVIEW); logMsg(F("循線檢視：# 是黑線，左邊是車子左側。按下鍵離開")); break;
    case MENU_LINECAL:   startLineCal(); break;
    case MENU_ASH_EMPTY: ashSet(true); break;
    case MENU_ASH_FULL:  ashSet(false); break;
    case MENU_ARMTEST:   armTest(); break;
    case MENU_NETINFO:   showNetInfo(); break;
  }
}

void serviceButtons() {
  unsigned long now = millis();
  if (now - lastBtn < BTN_POLL_MS) return;
  lastBtn = now;
  bool up = MiniR4.BTN_UP.getState();
  bool down = MiniR4.BTN_DOWN.getState();
  bool upEdge = up && !upPrev, downEdge = down && !downPrev;
  upPrev = up; downPrev = down;

  if (motionBusy()) { if (downEdge) abortMission("按鍵緊急停止"); return; }
  if (ms == MS_STATION) {
    if (downEdge) stationContinue();
    else if (upEdge) { stopMotors(); mis.active = false; logMsg(F("任務由使用者結束")); enterState(MS_IDLE); }
    return;
  }
  if (ms == MS_LINEVIEW) { if (downEdge) { msgUntil = 0; enterState(MS_IDLE); } return; }
  if (ms == MS_FAIL)     { if (upEdge || downEdge) enterState(MS_IDLE); return; }

  if (upEdge) { menuSel = (menuSel + 1) % MENU_COUNT; MiniR4.Buzzer.Tone(1200, 40); oledDirty = true; }
  if (downEdge) runMenu(menuSel);
}

// Adafruit SSD1306 每次 display() 會送整個畫面，約佔 I2C 十幾毫秒，
// 所以行進中只在狀態改變時重畫，靜止時每 0.5 秒一次
void serviceOLED() {
  unsigned long now = millis();
  bool moving = motionBusy();
  if (!oledDirty && (moving || now < oledNext)) return;
  oledNext = now + 500;
  oledDirty = false;

  String l0, l1, l2;
  if (now < msgUntil) {
    l0 = msg1; l1 = msg2;
  } else {
    switch (ms) {
      case MS_IDLE:    l0 = String(menuSel + 1) + "." + MENU_NAME[menuSel]; break;
      case MS_STATION: l0 = String("AT ") + stationName(curStation) + " DN>go UP>end"; break;
      case MS_FAIL:    l0 = String("FAIL ") + failCode; break;
      case MS_CAL:     l0 = "LINE CAL..."; break;
      default:
        l0 = String(mis.active && mis.legs ? curLeg().tag : "") + " " + String(mis.stepIdx + 1) + " " + motionName();
        break;
    }
    const char* ns = netState == NET_ONLINE ? "NET" : (netState == NET_DISABLED ? "" : "net-");
    l1 = "CO2 " + String(co2) + " F" + String(outDuty) + " " + localState + " " + ns;
    if (interlock || tcFault) l1 += " LOCK";
  }
  int ap = ashPercent();
  l2 = "ASH " + (ap < 0 ? String("--") : String(ap) + "%") +
       " MV " + (mvFresh() ? String(mv.plate ? "P" : "-") + String(mv.nOut) + "/" + String(mv.nOn) : String("--"));

  MiniR4.OLED.clearDisplay();
  MiniR4.OLED.setTextSize(1);
  MiniR4.OLED.setCursor(0, 0);  MiniR4.OLED.print(l0);
  MiniR4.OLED.setCursor(0, 11); MiniR4.OLED.print(l1);
  MiniR4.OLED.setCursor(0, 22); MiniR4.OLED.print(l2);
  MiniR4.OLED.display();

  // LED1：空氣與安全（綠常態、橙高峰、紅聯鎖）。LED2：機器人（綠待命、青行進、藍到站、紅失敗）
  if (tcFault || interlock)               MiniR4.LED.setColor(1, 255, 0, 0);
  else if (strcmp(localState, "S2") == 0) MiniR4.LED.setColor(1, 255, 120, 0);
  else                                    MiniR4.LED.setColor(1, 0, 255, 0);
  if (ms == MS_FAIL)          MiniR4.LED.setColor(2, 255, 0, 0);
  else if (ms == MS_STATION)  MiniR4.LED.setColor(2, 0, 0, 255);
  else if (moving)            MiniR4.LED.setColor(2, 0, 200, 200);
  else                        MiniR4.LED.setColor(2, 0, 60, 0);
}

// ═══════════════════════════════════════════════════════════════════════════
// 主程式
// ═══════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);

  // 上電先把致動器放在安全態
  pinMode(PIN_FAN, OUTPUT);
  analogWrite(PIN_FAN, 0);
  pinMode(PIN_FAN_TACH, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_FAN_TACH), tachISR, FALLING);
  pinMode(PIN_TC_CS, OUTPUT);  digitalWrite(PIN_TC_CS, HIGH);
  pinMode(PIN_TC_SCK, OUTPUT); digitalWrite(PIN_TC_SCK, LOW);
  pinMode(PIN_TC_SO, INPUT);
  baselineInit();

  // MATRIX 板級初始化。STM32 未就緒會停在這裡
  MiniR4.begin();
  MiniR4.PWR.setBattCell(2);   // 18650 x2（2S），依你的電池修改
  MiniR4.OLED.clearDisplay(); MiniR4.OLED.setTextSize(1);
  MiniR4.OLED.setCursor(0, 0); MiniR4.OLED.print(F("KEEPER ROBOT init..."));
  MiniR4.OLED.display();

  if (FLIP_FRONT) MiniR4.DriveDC.begin(4, 3, false, true);
  else            MiniR4.DriveDC.begin(3, 4, false, true);
  armHome();                  // 夾爪抬起、抹平臂收回、灰盤放平、不抽風

  // 循線感測器：A3 埠（Wire）
  MiniR4.I2C0.MXLineTracer.begin();
  MiniR4.I2C0.MXLineTracer.setWeights(-4.5, -3.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 3.5, 4.5);
  MiniR4.I2C0.MXLineTracer.setThreshold(LINE_TH);

  // 空氣感測：Wire1 經多工器
  Wire1.begin();
  Wire1.setClock(100000);
  muxSelect(CH_SCD41);
  scdOk = scd41.begin(Wire1);
  muxSelect(CH_SHT31);
  shtOk = sht31.begin(0x44);
#if USE_PCF8574
  pcfWrite(0);
#endif

  Serial.print(F("# SCD41:")); Serial.print(scdOk ? F("OK") : F("FAIL"));
  Serial.print(F("  SHT31:")); Serial.println(shtOk ? F("OK") : F("FAIL"));

  // 相機
  ashLoad();
#if USE_MVISION
  Serial1.begin(MVISION_BAUD);
#endif
  huskyRetryAt = 0;
  serviceHusky();
  Serial.print(F("# HuskyLens:")); Serial.println(huskyOK ? F("OK") : F("未連線，稍後自動重試"));
  if (ashCal.magic == ASH_EEPROM_MAGIC) {
    Serial.print(F("# 香灰校正 空爐=")); Serial.print(ashCal.hEmpty);
    Serial.print(F(" 滿爐=")); Serial.println(ashCal.hFull);
  } else {
    Serial.println(F("# 香灰尚未校正：選單 ASH SET EMPTY / ASH SET FULL"));
  }

  // 網路：開機時車子一定是靜止的，可以放心等 WiFi
#if USE_WIFI
  if (WiFi.status() == WL_NO_MODULE) {
    logMsg(F("找不到 WiFi 模組，改為只走 USB"));
    netState = NET_DISABLED;
  } else {
    netWifiConnect();
  }
#endif

  delay(300);
  lastTick = lastScdPoll = lastShtPoll = millis();
  logMsg(F("廟公機器人就緒。上鍵切換選單，下鍵執行，行進中按下鍵緊急停止"));
  oledDirty = true;
}

void loop() {
  serviceUsbRx();       // 外部指令
  serviceSafety();      // 熱電偶與聯鎖（最優先）
  serviceAir();         // CO2、溫濕度
  serviceFan();         // 風扇優先權解算
  serviceHood();        // RC4 抽風跟著風扇
  serviceMVision();     // 相機封包（每圈都收，避免緩衝區滿）
  tickMotion();         // 循線狀態機
  serviceHusky();       // 香灰（5 Hz）
  serviceTick();        // 每秒：轉速、電池、遙測
  serviceVisionSend();  // 相機結果（5 Hz）
  serviceNet();         // WiFi 中繼
  serviceSnapshot();    // M-Vision 照片（靜止時每 2 秒一張）
  serviceButtons();     // 按鍵
  serviceOLED();        // 顯示
}
