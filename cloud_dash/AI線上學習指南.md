# AI 線上學習指南 — 兩個 AI 的持續自我訓練與 Grafana 呈現

> 2026-08-20 建立。落實《後續研究與優化方向建議書》第五章「資料與雲端」
> 的兩個 AI 未來計畫：**AI-1 負載預測**（B 案真實資料重訓，資料飛輪）與
> **AI-2 異常偵測**（drift 偵測：感測老化、濾材狀態的資料基礎）。

---

## 1. 系統一覽

```
aroma01 真爐（R4 → Pi5 pi_fsm.py）
   │  MQTT: incense/aroma01/sensor ＋ /decision（既有，不動）
   ▼
雲端中心站（桌機 WSL，docker compose）
   mosquitto → telegraf → InfluxDB（measurement: sensor / decision）
                             ▲│
              ┌──────────────┘│讀實測資料
              │               ▼
   ai-online 容器：cloud_dash/ai_online_learning.py --serve
     ├─ AI-1 負載預測：每 6h 以近 60 天實測重訓 ridge（12 維日曆特徵，
     │    與 PI5/pi_fsm.py ShadowAdvisor 完全同構）＋守門條款
     ├─ AI-2 異常偵測：滾動 14 天穩健統計（時段 CO₂、雙感測偏差、
     │    基線漂移、缺料率、風扇失效差）＋每 5 分鐘評分
     └─ 狀態寫回 InfluxDB（measurement: ai_status）
                             │
                             ▼
   Grafana 儀表板「智慧香爐 AI 狀態」（grafana_dashboard_ai.json）
```

- **持續自我學習** ＝ 服務常駐：每 5 分鐘評分一次、每 6 小時用最新實測
  資料重訓一次；重訓資料含當日新進資料，模型版本遞增、歷史留檔。
- **零相依**：純 Python 標準函式庫，容器用官方 `python:3.12-alpine` 即可。
- 筆電（或任何機器）也可跑 `--source grafana` 走**公開唯讀 API** 做
  單次重訓與健檢——不需任何密碼。

## 2. 部署步驟（桌機 WSL，人工執行）

```bash
# 1) 把真相來源同步到工作副本
cp cloud_dash/ai_online_learning.py  ~/incense-cloud/
cp cloud_dash/cloud-docker-compose.yml ~/incense-cloud/docker-compose.yml  # 已含 ai-online 服務
#    ★注意：工作副本的 docker-compose.yml 若曾手改（telegraf 密碼等），
#      用 diff 比對後手動合併 ai-online 段落，不要整檔覆蓋★

# 2) 啟動
cd ~/incense-cloud && docker compose up -d ai-online
docker logs -f ai-online        # 應看到「AI-1 重訓完成 v1 …」「狀態已寫入 InfluxDB」

# 3) 匯入儀表板（Grafana → Dashboards → Import）
#    上傳 cloud_dash/grafana_dashboard_ai.json，★資料源務必選 InfluxDB-incense★
#
#    ★★ 2026-08-20 踩到的坑（務必讀）★★
#    - 本 JSON 是「匯出格式」，含 41 個 ${DS_INFLUXDB} 佔位符與 __inputs 區塊。
#    - 走 POST /api/dashboards/import 帶 inputs 對應，API 會回 200/imported=true，
#      admin 手動查詢也正常——★但佔位符沒有寫進儲存的儀表板★，公開看板照儲存內容
#      跑就會全 No data（與 08-18 三個面板同一個坑，見部署紀錄附錄）。
#    - 對策二擇一：
#      (a) 用 UI 匯入（本步驟），對話框選 InfluxDB-incense，會正確落地；
#      (b) 若走 API，匯入後必須驗證資料庫無殘留：
#          docker cp grafana:/var/lib/grafana/grafana.db /tmp/g.db
#          python3 -c "print(open('/tmp/g.db','rb').read().count(b'DS_INFLUXDB'))"  # 應為 0
#    - 目前線上實際的 datasource uid 是 dftmtpkivyadcb（name=InfluxDB-incense）；
#      任務書舊文寫的 incense-influx 已非現值，勿寫死。
#    （要公開的話：Share → Public dashboard，同前三個面板做法）
```

單次測試（不常駐、不寫庫）：

```bash
python3 ai_online_learning.py --no-write            # 桌機（直連 InfluxDB）
python3 ai_online_learning.py --source grafana --no-write   # 筆電（公開 API）
```

## 3. 兩個 AI 的定義與守門條款

### AI-1 負載預測（B 案・影子）

- 目標量：每小時「香支負載代理量」＝ CO₂ 高程（當日最小值為基線）/26。
  ★26 ppm/支是模擬推導的穩態換算（`AI訓練/policies.py` v3 nowcast），
  代理量非實測香支★
- 模型：ridge 閉式解，12 維日曆特徵，**與 Pi 端 ShadowAdvisor 逐位元同構**
  （由 `AI訓練/驗證線上學習.py` 自動對照，改任一邊必跑）。
- 守門條款（不滿足就**沿用舊模型**，狀態照樣上報）：
  1. 訓練樣本 ≥ 72 小時
  2. 時序後 30% 測試段 MAE ≤ 常數基線，且 ≤ 前日同時刻基線 × 1.1
  3. 權重全部有限且 |w| < 1000
- 產物：`ai_models/ai_predictor_real.json`（格式相容 `ai_predictor.json`，
  含 meta）＋ `ai1_history.json` 全程版本紀錄。
- ★換上 Pi 致動仍是人工決策：scp 到 Pi＋改名，本服務絕不碰 Pi/R4★

### AI-2 異常偵測（非監督 drift）

| 指標 | 學什麼 | 異常條件 |
|---|---|---|
| `co2_z` | 各時段 CO₂ 高程的中位數±MAD（14 天滾動） | \|z\| ≥ 4.5 |
| `t_bias_z` / `rh_bias_z` | SCD41−SHT31 偏差的長期分布 | \|z\| ≥ 4.5（偏差**漂移**＝老化訊號，偏差本身穩定無妨）|
| `dropout` | — | 近 1h 缺料 ≥ 60% |
| `duty_mismatch` | — | 實際 duty 低於指令平均 ≥ 20（風扇失效代理）|
| `safety_override` | — | **不算異常**：R4 就地全速（CO₂ 硬警報）蓋過 Pi 指令屬預期行為，僅回報比例 |
| `co2_drift` | 每日最小值線性斜率 ppm/日 | 資訊性（感測老化／環境改變訊號）|

「自我學習」＝統計基準每 6 小時隨滾動視窗重算，感測器慢性漂移會
被基準吸收、**跳變**會被 z 值抓到——這正是濾材「按狀態換」與
感測器「按老化換」的資料基礎。

## 4. 誠實邊界（照 CLAUDE.md §7）

1. aroma01 在**居家環境**：AI-1 學的是此環境的人員作息，**不是廟宇香客
   負載**；報告用語限「預測機制之真實資料遷移驗證」。
2. InfluxDB 中 aroma01 於 2026-08-08 01:15（台北）前為模擬資料；服務抓取
   起點寫死晚於此界線。
3. AI-2 是非監督統計模型，分數是**漂移指標不是故障判定**；沒有標註
   異常樣本可算召回率。
4. Grafana 面板是否正常顯示**必須由人開瀏覽器確認**——本指南所有
   「應看到」都是設計目標，不是已驗證事實。

## 5. 驗證

```bash
python3 AI訓練/驗證線上學習.py   # 特徵同構、守門、異常偵測單元檢查（14 項）
python3 run_tests.py             # 既有全部規則不受影響
```

改了 `ai_online_learning.py` 的 `feats()` 或 `PI5/pi_fsm.py` 的
`ShadowAdvisor._feats` 任何一邊 → 兩邊同步改＋重訓，並重跑上面第一條。

## 6. 首次真實訓練紀錄（2026-08-20，筆電經公開 API）

- 資料：aroma01 實測小時 CO₂ 140 筆（08-12 ～ 08-20，含缺口）
- AI-1 v1：測試段 MAE **6.56 支**，勝過常數（9.87）與前日同時刻（8.64）
  → 守門通過。★樣本僅 ~130h，MAE 數字波動大，僅供機制驗證★
- AI-2 v1：24 時段統計就緒；當下 `safety_override=100%`（CO₂ 高，R4
  硬警報全速中——判定為預期行為不觸發異常旗標，符合設計）

## 7. 外部公開資料的獨立機制驗證（2026-08-20）

`AI訓練/外部資料驗證.py` 以 UCI ML Repository #864「Room Occupancy
Estimation」（10,129 筆、CO₂＋CO₂斜率＋人數真值）對兩個 AI 的根基假設
做獨立驗證（資料在 `AI訓練/data/外部/`，產圖 `圖表/外部資料驗證.png`）：

| 機制 | 結果 |
|---|---|
| V1 CO₂ 高程∝人數（AI-1 nowcast 代理量前提） | **pass**：準穩態 r=0.711、中位高程 5→115→335→560 ppm 嚴格單調（0→3 人）、該房間擬合 175 ppm/人 |
| V2 CO₂ 斜率是前饋訊號（θ_ff 前提） | **inconclusive**：全資料集僅 4 個「空房→有人」事件，樣本不足以檢定；以本爐自有資料為準 |
| V3 AI-2 時段穩健統計誤報率 | **pass**：無故障資料上 z≥4.5 誤報率 0.00%（n=2,045） |

★ppm/人常數依房間體積與換氣率而異——V1 驗證的是單調線性**機制**，
不是 26 ppm/支這個場域常數★

## 8. 常見問題

- **筆電模式為何不寫狀態？** 公開儀表板 API 唯讀；寫 `ai_status` 只在
  直連 InfluxDB（桌機容器內）時發生。這是刻意設計：對外零憑證。
- **Prometheus 要不要加？** 現階段不建議：資料真相已在 InfluxDB，服務
  存活偵測用「心跳面板 15 分鐘計數＝0 變紅」即可覆蓋；等多爐機隊需要
  服務級告警（Alertmanager）時再引入才值得多養一個元件。
- **快取檔會不會爆？** `co2_hourly_cache.json` 每小時一筆 key，一年約
  9 千筆、< 1 MB，同時兼作雲端保留策略之外的歷史備份（資料飛輪）。
