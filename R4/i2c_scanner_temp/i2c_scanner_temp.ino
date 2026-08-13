/**
 * 臨時 I²C 掃描器（診斷 SCD41 接線用，用完即刪）
 * ─────────────────────────────────────────────────
 * 掃三個層面，找出感測器實際掛在哪：
 *   1. Wire  = I2C0（A4/A5，即 A3 埠 / UNO 排針 SDA/SCL）
 *   2. Wire1 直通（多工器 PCA9548A 本尊應出現在 0x70）
 *   3. Wire1 經多工器 ch0–ch7（I²C1 埠=ch0、I²C2 埠=ch1…）
 * 預期：SCD41=0x62、SHT31=0x44
 */
#include <Wire.h>

const uint8_t MUX = 0x70;

void scanBus(TwoWire& w, const char* name, uint8_t skip = 0)
{
    for (uint8_t a = 1; a < 127; a++) {
        if (a == skip) continue;
        w.beginTransmission(a);
        if (w.endTransmission() == 0) {
            Serial.print(name);
            Serial.print(F(" -> 0x"));
            Serial.println(a, HEX);
        }
    }
}

void setup()
{
    Serial.begin(115200);
    while (!Serial && millis() < 5000) {}
    Wire.begin();
    Wire1.begin();
    Wire.setClock(100000);
    Wire1.setClock(100000);
    delay(200);
}

void loop()
{
    Serial.println(F("=== I2C scan start ==="));
    scanBus(Wire,  "Wire(I2C0/A4A5)");
    scanBus(Wire1, "Wire1(direct)");
    for (uint8_t ch = 0; ch < 8; ch++) {
        Wire1.beginTransmission(MUX);
        Wire1.write((uint8_t)(1 << ch));
        Wire1.endTransmission();
        delay(10);
        char label[20];
        snprintf(label, sizeof(label), "Wire1 mux ch%u", ch);
        scanBus(Wire1, label, MUX);   // 跳過 0x70 本尊
    }
    Serial.println(F("=== I2C scan done ==="));
    delay(3000);
}
