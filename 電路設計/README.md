# 電路設計 — 接線圖與驗證

本資料夾是 P0 硬體通電前的設計驗證，回答一個問題：**照這張圖接下去，電路會不會動？**

| 檔案 | 內容 |
|---|---|
| `kicad/` | **KiCad 正式電路圖**（`incense_p0.kicad_sch`）＋網表＋產生器 |
| `接線圖.html` | 視覺化接線圖（可用瀏覽器開，也可截圖進報告）。三板拓撲、逐腳位對照、驗算總表 |
| `麵包板接線圖.html` | **Fritzing 風格寫實圖**：麵包板＋實體元件外觀＋彩色跳線，照著插就能動；與 KiCad rev D 逐腳一致 |
| `電氣驗證計算.md` | 完整計算書。9 項介面逐項給規格值 → 計算 → 餘量 → 判定 |
| `wokwi_R4安全層/` | Wokwi 模擬：驗證安全優先權、看門狗、聯鎖遲滯 |
| `wokwi_S3感測層/` | Wokwi 模擬：驗證 CO₂ 斜率計算、雙感測交叉驗證、警報門檻 |

---

## KiCad 電路圖

```
kicad/incense_p0.kicad_sch   電路圖本體（A3，11 元件 / 17 條網路，訊號以導線連接）
kicad/佈線定義.py             元件位置與佈線通道（改版面只要動這個檔）
kicad/incense_p0.kicad_pro   KiCad 專案檔
kicad/incense.kicad_sym      專案專用符號庫
kicad/sym-lib-table          符號庫註冊（KiCad 才不會報「找不到 incense 庫」）
kicad/電路圖.pdf              ★ 報告可直接用 ★
kicad/incense_p0.svg         向量圖，可再編輯
kicad/netlist.net            KiCad 官方網表
kicad/erc報告.rpt             ERC 結果：0 錯誤 0 警告
kicad/網表.md                 人可讀的網表，供與接線表交叉核對
kicad/產生電路圖.py            產生器（可重跑）
kicad/驗證電路圖.py            結構與連通性檢查
kicad/輸出網表.py              網表輸出
```

**怎麼開**：開 `incense_p0.kicad_pro` → 雙擊電路圖。
`電路圖.pdf` 已經產好，報告要用可直接拿。

### ✅ 已在 KiCad 10.0.5 實機驗證

```
$ kicad-cli sch erc --severity-all incense_p0.kicad_sch
  Found 0 violations
  ** ERC messages: 0  Errors 0  Warnings 0
```

PDF/SVG 匯出成功、官方網表與《網表.md》逐條吻合。關鍵的警報旁路：
`ALARM` 3 點 = `U1` GPIO4（S3 輸出）、`A1` A0（R4 類比判位）、`R1`（10 kΩ 下拉）。

> ⚠️ **KiCad 開著檔案時重跑產生器**：KiCad 不會自動重載，且會留下 `.lck` 鎖定檔。
> 請先關閉 KiCad 再重跑，或重跑後在 KiCad 關閉專案重開。

重跑全套驗證：

```bash
python3 產生電路圖.py
python3 驗證電路圖.py
python3 輸出網表.py
kicad-cli sch erc --severity-all incense_p0.kicad_sch
kicad-cli sch export pdf --output 電路圖.pdf incense_p0.kicad_sch
```

### 設計說明

- **訊號線實際畫出導線**，含轉角與接點（junction），並在導線上標註網路名稱。
- **電源網路（GND / +3V3 / +5V / +12V）用電源符號**，不拉線——GND 有 10 個接點，
  全部拉線會變成一團亂麻。這是電路圖的標準做法。
- **符號全部內嵌在 `lib_symbols`**，不依賴本機 KiCad 符號庫，換電腦開不會出現「找不到符號」。
- 模組（ESP32-S3 開發板、MAX6675 模組、D4184 模組）以**方塊符號**表示，這是 breakout board
  在電路圖上的慣例。

### ERC 修正紀錄

第一版 ERC 跑出 44 項違規，兩類問題都已修正：

| 問題 | 原因 | 修法 |
|---|---|---|
| `power_pin_not_driven` ×4 | 所有電源腳都標成 `power_in`，等於沒有任何元件在供電 | 把真正的供電端改成 `power_out`：U1 的 3V3（板載 LDO 輸出）、A2 的 USB 5V（Pi 供電）、J2 的 +12V（變壓器）。GND 沒有「誰在驅動」的概念，改放 `PWR_FLAG` |
| `lib_symbol_issues` ×40 | 符號雖內嵌可顯示，但沒註冊 `incense` 符號庫 | 另存 `incense.kicad_sym` 並加 `sym-lib-table` |

（第三版把警報線由 74HCT125 改為類比判位後重跑，仍是 0 錯誤 0 警告。）

第二版 ERC：**0 錯誤 0 警告**。

> 這 44 項是本機靜態分析抓不到的——`驗證電路圖.py` 驗的是「檔案結構與座標連通性」，
> ERC 驗的是「電氣語意」。兩層互補，都要跑。

---

## 🔴 本次驗證的關鍵結論

**警報線不能接 R4 的數位腳，要接類比腳 A0——而且不需要買任何額外元件。**

```
S3 輸出              3.30 V
R4 數位腳判 HIGH 需要  4.00 V   （RA4M1：VIH = 0.8 × VCC）
────────────────────────────
餘量                −0.70 V   ✗ 讀不到

改接類比腳 A0：
S3 拉高 3.3 V  →  ADC ≈ 675 / 1023
S3 放開 0.0 V  →  ADC = 0
韌體門檻            > 500 判警報、< 300 才解除（軟體遲滯）
────────────────────────────
兩側餘量 175 / 500 counts     ✓ 零元件解決
```

原《P0接線與驗證指南》寫「3.3V 是邊界值，實務上幾乎都過」——那是 UNO **R3** 的經驗
（ATmega328P 門檻 3.0 V）。UNO **R4** 換了 Renesas RA4M1，數位輸入門檻升到 4.0 V，同一條線就不成立。

**這條線壞掉特別難查**：它正是「Pi 當機時保命」的硬體旁路，平常完全測不出來。

> 也可以用 74HCT125／74HCT14 之類的 HCT 緩衝器（**HCT 才行，HC 的 V<sub>IH</sub> = 3.5 V 一樣不夠**），
> 但要買料。**不要用 BSS138 雙向模組**：S3 斷電時它的 HV 側上拉會讓 R4 誤判為警報中，
> 風扇鎖死全速永不回 FALLBACK，反而破壞降級行為。各方案比較見《電氣驗證計算.md》§1.4。

《P0接線與驗證指南》已同步更新（§1 備料表、§2.0 拓撲、§2.1／§2.2 接線表、§5 第 3 關、§6 疑難排解）。

---

## Wokwi 模擬怎麼用

[Wokwi](https://wokwi.com) 是免安裝的線上模擬器，可直接跑 Arduino／ESP32 韌體。

1. 開 <https://wokwi.com> → New Project → 選對應開發板
2. 把資料夾裡的 `diagram.json` 內容貼到 Wokwi 的 **diagram.json** 分頁（整份覆蓋）
3. 把 `sketch.ino` 內容貼到程式碼分頁
4. 按 ▶ 開始，打開序列監控（115200）

### 兩個專案各自驗證什麼

**`wokwi_R4安全層/`** — 用電位器代替熱電偶、按鈕代替 S3 警報線、LED 亮度顯示風扇 duty。
決策邏輯與正式韌體**逐行相同**，可驗證：

- 開機頭 5 秒維持 `FALLBACK`／duty 80（`piSeen` 修正的驗證點）
- `FAN 220` → 轉 PI 模式；停止輸入 5 秒 → 看門狗回 FALLBACK
- 爐溫 > 80 °C → 聯鎖、風扇強制 0；降到 < 60 °C 才解除（遲滯）
- 聯鎖優先於 S3 警報：同時觸發時風扇仍為 0

**`wokwi_S3感測層/`** — 用電位器代替 SCD41，並重現「每 5 秒才更新一筆」的硬體限制。可驗證：

- CO₂ 斜率計算（12 筆 ≈ 60 秒視窗）與前饋門檻 θ_ff = 120 的觸發
- 雙溫度交叉驗證 → `conf` 值
- CO₂ ≥ 1500 → 警報線拉高（LED 亮）
- 輸出 JSON 格式與正式韌體完全一致

### ⚠️ 模擬的邊界

- **Wokwi 沒有 UNO R4 Minima**，R4 專案用 UNO R3 當替身。邏輯驗證不受影響，
  但 R3／R4 的**輸入準位規格不同**——那正是本次發現的問題，模擬器驗證不了，只能靠規格書算。
- Wokwi 沒有 SCD41／SHT31／MAX6675 模型，故以電位器代入。
  驗證的是**訊號處理邏輯**，不是感測器本身的精度。
- 模擬版省略了 WiFi／MQTT／序列上雲，改為直接印 JSON 到序列監控。

一句話：**模擬器驗證「演算法對不對」，計算書驗證「電路通不通」，兩者互補，缺一不可。**
