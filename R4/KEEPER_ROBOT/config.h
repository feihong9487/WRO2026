#pragma once
// config.h — 廟公機器人的所有可調參數與接線
// 改硬體、調參數都在這個檔案，主程式不用動。

#include <Arduino.h>

// ═══════════════════════ 身分與功能開關 ═══════════════════════
#define DEVICE_ID      "aroma01"   // 上雲的裝置代號，沿用儀表板既有的名稱
#define USE_WIFI       1           // 0 = 只走 USB，不連 WiFi
#define USE_HUSKY      1           // HuskyLens 香灰量測
#define USE_MVISION    1           // M-Vision 供品與供盤辨識
#define USE_PCF8574    0           // 舊香爐罩的霧化與 LED 板。廟公機器人預設不用
#define VISION_TO_USB  0           // 1 = 相機結果也印到 USB 序列埠（除錯用，資料量大）

// ═══════════════════════ I2C（Wire1 經 PCA9548A 多工器）═══════════════════════
// 多工器通道：I2C1 = 0、I2C2 = 1、I2C3 = 2、I2C4 = 3
const uint8_t MUX_ADDR = 0x70;
const uint8_t CH_SCD41 = 0;          // I2C1：SCD41（CO2、溫濕度）
const uint8_t CH_SHT31 = 1;          // I2C2：SHT31（溫濕度，雙感測交叉驗證）
const uint8_t CH_PCF   = 2;          // I2C3：PCF8574 致動板（USE_PCF8574 才會用）
#define HUSKY_I2C_PORT 4             // HuskyLens 接的 I2C 埠號 1~4。2026-09-30 實測 I2C3 讀不到，改接 I2C4 才找到
// 循線感測器固定接 A3 埠（I2C0，走 Wire）。原廠註明目前版本不支援多工器。

// ═══════════════════════ 腳位 ═══════════════════════
// MiniR4.begin() 會把 D2、D3 埠佔為 PS2 手把腳，所以只用 D1、D4。
const int PIN_TC_SCK   = 13;   // D4 埠左：MAX6675 SCK
const int PIN_TC_SO    = 10;   // D4 埠右：MAX6675 SO
const int PIN_TC_CS    = 2;    // D1 埠右：MAX6675 CS
const int PIN_FAN      = 3;    // D1 埠左：四線風扇的 PWM 控制線
const int PIN_FAN_TACH = A0;   // A1 埠右：風扇轉速回授。A1 埠的 5V 恆定供電給風扇，不可斬波
// M-Vision 接 UART 埠（Serial1）。A2 埠目前空著（原本的 DS18B20 已拿掉）。
// ⚠ 不要開 Serial2：它是主晶片通往 ESP32-S3 無線晶片的內部線路。

// ═══════════════════════ 底盤與手臂 ═══════════════════════
// 直流馬達：DC1 夾爪右、DC2 夾爪左、DC3 底盤右、DC4 底盤左
const bool FLIP_FRONT    = true;    // 沿用 ROUTE_FOLLOW：true = 左馬達 M4、右馬達 M3（與上面的分配相同）
const bool REVERSE_STEER = false;   // 感測器左右與車子相反時改 true

// 伺服角度（度）
const int RC_GRIP_UP   = 110, RC_GRIP_DOWN   = 15;   // RC1 夾爪上下
const int RC_LEVEL_HOME = 0,  RC_LEVEL_SWEEP = 60;   // RC2 抹平香灰
const int RC_TRAY_HOME = 10,  RC_TRAY_DUMP   = 45;   // RC3 裝香灰的盤
const int RC_HOOD_OFF  = 0,   RC_HOOD_ON     = 60;   // RC4 抽風：不抽 0 度、抽 60 度
// 開機姿勢：夾爪抬起、抹平臂收回、灰盤放平、不抽風。-1 = 開機不動它
const int  SERVO_HOME[4] = { RC_GRIP_UP, RC_LEVEL_HOME, RC_TRAY_HOME, RC_HOOD_OFF };
const uint16_t SERVO_SETTLE_MS = 600;   // 伺服轉到位的等待時間

// 夾爪直流馬達（DC1 右、DC2 左）。兩顆面對面裝，通常一顆要反轉；方向不對就改 REVERSE
const int  GRIP_POWER        = 40;      // 夾緊／放開的力道（-100~100）
const int  GRIP_HOLD_POWER   = 15;      // 夾住後維持的力道，0 = 不維持
const bool GRIP_R_REVERSE    = true;      // 2026-09-29 實測：原本夾放顛倒，兩顆都對調
const bool GRIP_L_REVERSE    = false;
const uint16_t GRIP_MOVE_MS  = 700;     // 夾緊或放開要轉多久

// RC4 抽風跟著風扇：風扇在轉就轉到 60 度、停了回 0 度。行進中一律收回，避免撞到東西
#define HOOD_FOLLOWS_FAN 1

// ═══════════════════════ 循線（沿用 ROUTE_FOLLOW 調好的值）═══════════════════════
const int   BASE_SPEED   = 40;
const float KP           = 7.0;
const float KD           = 4.0;
const int   MAX_TURN     = 45;
const float DEADBAND     = 0.15;
const float ERROR_SMOOTH = 0.5;
const int   MAX_POWER    = 100;
const int   LINE_TH      = 30;      // 100 - 讀值 > 30 算黑線

const uint8_t JUNC_MIN_BLACK = 5;           // 同時至少幾顆看到黑才可能是路口
const uint8_t JUNC_CONFIRM   = 3;           // 連續幾次都是路口才算
const unsigned long JUNC_BLANK_MS = 400;    // 起步、轉彎、穿越後這段時間不偵測路口
const int   CROSS_SPEED = 35;  const unsigned long CROSS_MS = 300;   // 直行穿越岔路
const int   AXLE_SPEED  = 30;  const unsigned long AXLE_MS  = 280;   // 轉彎前往前推到路口中心
const int   SPIN_SPEED  = 28;
const unsigned long SPIN90_MIN_MS  = 350;
const unsigned long SPIN180_MIN_MS = 900;
const unsigned long SPIN_TIMEOUT_MS = 3500;
const float   ALIGN_ERR     = 1.0;
const uint8_t ALIGN_CONFIRM = 2;
const int     SPIN180_DIR   = -1;           // 原地迴轉方向，-1 左、+1 右
const unsigned long LOST_CONFIRM_MS = 80;   // 連續這麼久看不到線才算到線尾
const unsigned long END_ROLL_MS = 0;        // 到線尾後再往前滑多久
const int   ACQ_SPEED = 30;
const uint8_t ACQ_CONFIRM = 4;
const unsigned long ACQ_TIMEOUT_MS = 4000;
const unsigned long SEGMENT_TIMEOUT_MS = 10000;
const unsigned long STATION_WAIT_MS = 0;    // 到站後：0 = 等按鍵；>0 = 自動等這麼久再走

// ═══════════════════════ 安全與空氣（逐項沿用原香爐韌體）═══════════════════════
// T_LOCK / T_RELEASE 是原韌體標註的「臨時值、待實測」，沒有實測依據前不可宣稱為驗證過的安全設定。
const float    T_LOCK        = 150.0;
const float    T_RELEASE     = 130.0;
const uint32_t PI_TIMEOUT_MS = 5000;    // 多久沒收到外部指令就改用本地 FSM
const uint8_t  FALLBACK_DUTY = 80;
const uint16_t CO2_ALARM_PPM   = 1500;
const uint32_t SENSOR_STALE_MS = 15000;
const uint16_t CO2_IDLE_DELTA = 50;
const uint16_t T1_DELTA       = 300;
const uint16_t T1_EXIT_DELTA  = 200;
const uint8_t  BASELINE_WINDOW_MIN = 10;
const uint16_t CO2_BASELINE_INIT = 450;
const float    SLOPE_TH    = 120.0;
const uint32_t IDLE_HOLD_MS = 60000;
// 文化海報「不對燃燒的香頭噴氣，溫和捕集」：風扇轉速上限。255 = 不限制（與原韌體相同）
const uint8_t  FAN_MAX_DUTY = 255;
// 「香灰還燙就不挖」：熱電偶讀值低於此溫度才算可以挖灰。臨時值，待實測
const float    ASH_COOL_C = 50.0;

// ═══════════════════════ 週期 ═══════════════════════
const uint32_t TICK_MS         = 1000;   // 遙測
const uint32_t TC_READ_MS      = 500;    // MAX6675 轉換最長 220 ms
const uint32_t SCD_POLL_MS     = 1000;   // SCD41 自己約 5 秒才更新一筆
const uint32_t SHT_POLL_MS     = 1000;   // SHT31 每次量測約卡 20 ms，所以限 1 Hz
const uint32_t HUSKY_PERIOD_MS = 200;
const uint32_t VISION_SEND_MS  = 200;
const uint32_t BTN_POLL_MS     = 50;     // 按鍵經 STM32 讀取，限制頻率

// ═══════════════════════ 相機 ═══════════════════════
const long     MVISION_BAUD     = 115200;   // 要和 MVISION_OFFERING/main.py 一致
const uint32_t MVISION_STALE_MS = 500;
const uint8_t  ASH_COLOR_ID     = 1;        // HuskyLens 顏色辨識學到的色條 ID
const uint8_t  ASH_SAMPLES      = 25;       // 香灰量測的樣本數（5 Hz，約 5 秒）。排序後去掉最高、最低各 1/4 再平均，可以算出小數像素
// 香灰量用框的哪個值換算：0 = 框的高度（側面看色條，沿用 ASH_LEVEL）；
// 1 = 框的中心 y（斜上方看香灰表面，灰少了表面往下沉）；
// 2 = 框的上緣（中心 y − 高度/2）：灰多時框往上移又變高，兩個變化加在一起，差距最大。
// 2026-09-30 實測（相機調整後）：中心 y 空滿差 10 像素，上緣約差 20 像素
#define ASH_MEASURE 2
const int      ASH_EEPROM_ADDR  = 0;        // 與 ASH_LEVEL 相同
// 換了量法，舊的校正值單位不同，所以用不同的標記：換量法後要重新校正空爐和滿爐
const uint16_t ASH_EEPROM_MAGIC = 0xA51E + ASH_MEASURE;   // 0 → 0xA51E（與 ASH_LEVEL 相同）、1 → 0xA51F、2 → 0xA520
const unsigned long HUSKY_TIMEOUT_MS = 40;  // HuskyLens 回應逾時，程式庫預設 100 ms 太久

// M-Vision 拍照回傳（給監控網站看真的畫面）。只在車子靜止、且已連上筆電中繼時才要照片，
// 行進中不拍，避免影響循線的迴圈時間。照片約 2~4 KB，WiFi 約 0.5 秒送完。
#define USE_SNAPSHOT 1
const uint32_t SNAP_PERIOD_MS  = 2000;      // 多久要一張
const uint32_t SNAP_TIMEOUT_MS = 2000;      // 相機多久沒回就放棄這一張
const uint16_t SNAP_MAX_BYTES  = 3000;      // 要和 MVISION_OFFERING/main.py 的 SNAP_MAX_BYTES 搭配（相機端 2900）。R4 的 RAM 只剩這麼多

// ═══════════════════════ 網路（依 WIFI_SPEED_TEST 實測結果）═══════════════════════
const uint16_t RELAY_TCP_PORT = 5005;
const uint16_t BEACON_PORT    = 5006;
#define BEACON_TAG "WRO2026-RELAY"
const uint32_t WIFI_CONNECT_TIMEOUT_MS = 12000;
const uint32_t WIFI_RETRY_MS  = 30000;
const size_t   TX_CHUNK_MOVING = 128;   // 行進中每圈最多寫多少，約卡 12 ms
const size_t   TX_CHUNK_IDLE   = 256;   // 靜止時，約卡 27 ms
const uint32_t NET_RX_POLL_MS  = 100;
const float    BLOCK_TEMP_MARGIN = 20.0;   // 溫度離 T_LOCK 不到這麼多時，禁止會阻塞的網路動作

// ═══════════════════════ 遠端操控（監控網站 → 桌機 → 筆電中繼 → R4）═══════════════════════
#define REMOTE_CONTROL 1                   // 0 = 只接受 STOP，不接受遠端開始任務
const float REMOTE_MIN_BATT_V = 6.0;       // 電池低於這個電壓不接受遠端開始任務（海報規則：低電量要回充電座）
