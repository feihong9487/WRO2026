/*
 * M1 風扇獨立測試 — 不理感測器、不跑 FSM，直接命令 M1 轉速。
 * 用途：把「FSM 命令 0（S0 待機）」和「M1 沒電／接線問題」一刀切開。
 *
 *   風扇會轉 → M1 接線與供電 OK，主韌體不轉純粹是 FSM 在 S0/低 duty。
 *   風扇不轉 → M1 沒馬達電（檢查 DC 電源輸入 6-24V，USB 不供馬達）
 *              或接線／風扇本身問題。
 *
 * 開發板：Arduino UNO R4 WiFi。OLED 會顯示目前送出的百分比。
 */
#include "MatrixMiniR4.h"

void spin(int pct)
{
    MiniR4.M1.setPower(pct);
    MiniR4.OLED.clearDisplay();
    MiniR4.OLED.setTextSize(2);
    MiniR4.OLED.setCursor(0, 8);
    MiniR4.OLED.print("M1=");
    MiniR4.OLED.print(pct);
    MiniR4.OLED.print("%");
    MiniR4.OLED.display();
    Serial.print("M1 setPower ");
    Serial.println(pct);
}

void setup()
{
    Serial.begin(115200);
    MiniR4.begin();
    Serial.println("=== M1 fan test ===");
}

void loop()
{
    spin(100); delay(3000);   // 全速
    spin(60);  delay(3000);   // 中速
    spin(0);   delay(2000);   // 停
}
