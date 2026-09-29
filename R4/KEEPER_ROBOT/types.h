#pragma once
// types.h — 共用型別
// 放在標頭檔，是因為 Arduino 會把自動產生的函式宣告插在第一個函式前面，
// 型別若定義在 .ino 裡面會比宣告晚出現而編譯失敗。

#include <Arduino.h>

// 循線感測器一次讀值，已換成車子座標：索引 0 = 車子左邊
struct Snap {
  uint8_t raw[10];
  bool    blk[10];
  uint8_t count;
  bool    leftOuter, rightOuter, center;
  float   err;           // 負 = 線偏左，正 = 線偏右
};

// 路線表
enum Act : uint8_t { STRAIGHT, TURN_LEFT, TURN_RIGHT, END_STOP, END_TURN180 };
enum Station : uint8_t { ST_NONE, ST_TABLE, ST_BURNER, ST_ASH, ST_DOCK };

struct Step {
  Act act;
  char expect;           // 預期路口種類 'L'、'R'、'T'，'-' 不檢查
  const char* note;
};

struct Leg {
  const char* name;      // 序列埠顯示用
  const char* tag;       // OLED 只能顯示英數
  bool turnFirst;        // 出發前先原地迴轉
  const Step* steps;
  uint8_t n;
  Station dest;
};

// 運動狀態機
enum MState : uint8_t {
  MS_IDLE, MS_SPIN, MS_ACQUIRE, MS_FOLLOW, MS_CROSS, MS_AXLE, MS_ROLL,
  MS_STATION, MS_CAL, MS_LINEVIEW, MS_FAIL
};
enum AfterSpin : uint8_t { AS_LEG_START, AS_STEP_DONE, AS_ARRIVED };

// 網路狀態機
enum NetState : uint8_t { NET_DISABLED, NET_WIFI_DOWN, NET_DISCOVER, NET_CONNECTING, NET_ONLINE };

// 相機結果
struct MVision {
  bool plate, target;
  int  px, py, pw, ph;    // 供盤
  int  tx, ty, tw, th;    // 要夾的供品
  int  nOut, nOn;         // 盤外、盤上供品數
  uint16_t frame;
  unsigned long ms;       // 收到的時間，0 = 從沒收到
};

struct HuskyRes {
  bool seen;
  int  x, y, w, h;
  uint8_t n;
  unsigned long ms;
};

// 與 ASH_LEVEL 的 EEPROM 格式相同，校正值可以沿用
struct AshCalib {
  uint16_t magic;
  int16_t  hEmpty;
  int16_t  hFull;
};
