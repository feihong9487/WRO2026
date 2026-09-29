#pragma once
// route.h — 工字形場地的路線表（依早上、晚上兩張示範海報）
//
//      香爐 ●━━━━━━━┳━━━━━━━■ 供桌        上橫線
//                    ┃                       中間直線
//    充電座 ■━━━━━━━┻━━━━━━━■ 倒灰區      下橫線
//
// 動作照順序執行。路口種類只拿來檢查，因為同一個路口從不同方向經過，
// 左岔右岔會對調，只看種類容易轉錯。

#include "types.h"

const Step STEPS_A[] = {
  { TURN_LEFT,   'L', "下方路口：左轉往北" },
  { TURN_RIGHT,  'T', "上方 T 字：右轉往東" },
  { END_TURN180, '-', "供桌：停車並迴轉，讓車尾的夾爪和 M-Vision 對著供桌" },
};
const Step STEPS_B[] = {
  { STRAIGHT,    'L', "上方路口：直行往西" },
  { END_STOP,    '-', "香爐：停在旁邊，不碰香爐" },
};
const Step STEPS_C[] = {
  { STRAIGHT,    'R', "上方路口：直行往東" },
  { END_TURN180, '-', "供桌：停車並迴轉" },
};
const Step STEPS_D[] = {
  { TURN_LEFT,   'L', "上方路口：左轉往南" },
  { TURN_LEFT,   'T', "下方 T 字：左轉往東" },
  { END_STOP,    '-', "倒灰區：停車" },
};
const Step STEPS_E[] = {
  { STRAIGHT,    'R', "下方路口：直行往西" },
  { END_STOP,    '-', "充電座：停車" },
};

#define STEPS(x) x, (uint8_t)(sizeof(x) / sizeof(x[0]))
const Leg LEG_A = { "A 充電座到供桌",   "DOCK>TABLE", false, STEPS(STEPS_A), ST_TABLE  };
const Leg LEG_B = { "B 供桌到香爐",     "TABLE>BURN", false, STEPS(STEPS_B), ST_BURNER };
const Leg LEG_C = { "C 香爐到供桌",     "BURN>TABLE", true,  STEPS(STEPS_C), ST_TABLE  };
const Leg LEG_D = { "D 供桌到倒灰區",   "TABLE>ASH",  false, STEPS(STEPS_D), ST_ASH    };
const Leg LEG_E = { "E 倒灰區到充電座", "ASH>DOCK",   true,  STEPS(STEPS_E), ST_DOCK   };

// 早上：充電座 → 供桌整理供品 → 香爐旁收煙看香灰
const Leg* const MORNING[] = { &LEG_A, &LEG_B };
// 晚上：香爐 → 供桌 → 倒灰區 → 回充電座
const Leg* const EVENING[] = { &LEG_C, &LEG_D, &LEG_E };
// 單段測試用
const Leg* const ONLY_A[] = { &LEG_A };
const Leg* const ONLY_B[] = { &LEG_B };
const Leg* const ONLY_C[] = { &LEG_C };
const Leg* const ONLY_D[] = { &LEG_D };
const Leg* const ONLY_E[] = { &LEG_E };
