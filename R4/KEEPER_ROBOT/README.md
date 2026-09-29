# KEEPER_ROBOT：廟公機器人合併版 R4 韌體

一塊 MATRIX Mini R4 控制全部：循線路線表、空氣感測與熱電偶安全聯鎖、集煙風扇、
M-Vision（供品與供盤）、HuskyLens（香灰高度），並用 WiFi 把資料送到筆電中繼（`../../RELAY`）。
程式開頭的註解有完整的通訊協定與操作說明，可調參數都在 `config.h`。

## 編譯前要自己建立 `arduino_secrets.h`

這個檔案放 WiFi 密碼，已被 `.gitignore` 擋掉，不會進版控。在本資料夾建立：

```c
#pragma once
#define SECRET_SSID "熱點名稱"
#define SECRET_PASS "熱點密碼"
#define SERVER_IP   ""   // 留空＝自動找筆電中繼（UDP 廣播）；也可以填筆電 IP
```

R4 只支援 2.4 GHz。用 iPhone 熱點時要開「最大化相容性」。

## 編譯

開發板選 Arduino UNO R4 WiFi；需要的程式庫：MatrixMiniR4、SparkFun SCD4x、Adafruit SHT31、HUSKYLENS（DFRobot）。
