# 任務書 — 桌機部署 AI 線上學習服務（給桌機的 Claude Code）

> ✅ **2026-08-20 已由桌機 Claude Code 執行完畢**（成果見《部署紀錄.md》
> 附錄「AI 線上學習服務上線」）。本檔保留作重部署／除錯手冊。

> 2026-08-20 由筆電端建立。你在**桌機**（Tailscale 主機名 `desktop-c8l8ri6`，
> 雲端中心站所在機器）上執行。整體背景見 `cloud_dash/AI線上學習指南.md`，
> 本檔只管「把服務跑起來＋驗收」這一段。
>
> 適用規則：本 repo 的 `CLAUDE.md` 全部適用，特別是 §8（密碼不寫進任何
> 檔案）與 §9（卡關回報格式）。

---

## 目標

1. 在桌機 WSL 的雲端堆疊（`~/incense-cloud/`，四容器 mosquitto／influxdb／
   telegraf／grafana）旁邊，啟動第五個容器 `ai-online`：
   `cloud_dash/ai_online_learning.py --serve`，每 5 分鐘寫一輪 `ai_status`
   到 InfluxDB、每 6 小時用 aroma01 實測資料重訓兩個 AI。
2. 確認 `ai_status` 真的有資料進 InfluxDB。
3. 協助使用者把 `cloud_dash/grafana_dashboard_ai.json` 匯入 Grafana
   （面板顯示是否正常**只能由人確認**，你不得宣稱已驗證）。

## 紅線（先讀）

- **不碰 Pi、不碰 R4、不碰 mosquitto／telegraf／grafana 三個既有容器的設定。**
- `~/incense-cloud/docker-compose.yml` 是**工作副本、含使用者手改的密碼版本
  設定**——★只能追加段落，不得整檔覆蓋★。動手前先備份。
- Grafana admin 密碼由使用者保管：需要時**開口問**，用完即棄，
  不寫進任何檔案、腳本、shell 歷史可見的指令（用環境變數互動輸入）。
- 服務本身零機密：InfluxDB 用的是本地固定 token `incense-local-token`
  （已在 repo 的 compose 與 telegraf conf 內，非機密）。

## 步驟

### 0. 前置檢查

```bash
wsl -e bash -c "cd ~/incense-cloud && docker compose ps"
```

- 應看到 mosquitto／influxdb／telegraf／grafana 四容器 `running`。
- 不是的話 → 卡關回報，不要自行重啟堆疊。
- 以下所有指令都在 WSL 內執行（桌機 Claude Code 若跑在 Windows 端，
  一律用 `wsl -e bash -c "…"` 包）。

### 1. 取得最新檔案

```bash
# repo 已 clone 過就 git pull；沒有就：
cd ~ && git clone --depth 1 https://github.com/feihong9487/WRO2026.git wro-latest
cp ~/wro-latest/cloud_dash/ai_online_learning.py ~/incense-cloud/
```

### 2. 合併 docker-compose（追加，不覆蓋）

```bash
cp ~/incense-cloud/docker-compose.yml ~/incense-cloud/docker-compose.yml.bak-$(date +%m%d)
```

先 `grep -n "ai-online" ~/incense-cloud/docker-compose.yml`——已存在就跳過本步。
否則在 `services:` 區塊末尾（`grafana:` 服務之後）追加：

```yaml
  ai-online:
    image: python:3.12-alpine
    container_name: ai-online
    restart: unless-stopped
    depends_on:
      - influxdb
    environment:
      - INFLUX_URL=http://influxdb:8086
    volumes:
      - ./ai_online_learning.py:/app/ai_online_learning.py:ro
      - ai-models:/app/ai_models
    command: python /app/ai_online_learning.py --serve
```

並在檔尾頂層 `volumes:` 區塊加一行 `  ai-models:`（兩空格縮排）。
改完必跑：

```bash
cd ~/incense-cloud && docker compose config -q && echo YAML_OK
```

沒印 `YAML_OK` → 修到過為止（比對 `.bak` 確認沒動到別的服務）。

### 3. 啟動

```bash
cd ~/incense-cloud && docker compose up -d ai-online
sleep 90 && docker logs --tail 30 ai-online
```

成功樣貌（首輪 1–2 分鐘內）：

```
[..] 資料來源=influxdb  抓取自 ...
  AI-1 重訓完成 v1：test MAE=...（常數 .../前日 ...） n=...h
  AI-2 重訓完成 v1：...
  AI-2 評分：score=... flag=...
  狀態已寫入 InfluxDB（measurement=ai_status）
```

注意：`AI-1 未換模型：未優於基線…` 是**守門條款的正常行為**不是錯誤；
只有連線錯誤、Python traceback、或反覆 `cycle 失敗` 才算失敗。

### 4. 驗證 ai_status 落庫（你可以自動驗）

```bash
curl -s -X POST "http://localhost:8086/api/v2/query?org=incense" \
  -H "Authorization: Token incense-local-token" \
  -H "Content-Type: application/vnd.flux" \
  -d 'from(bucket:"incense") |> range(start:-15m)
      |> filter(fn:(r)=> r._measurement=="ai_status")
      |> filter(fn:(r)=> r._field=="svc_heartbeat") |> count()'
```

回傳計數 ≥1 即通過。0 或空 → 看 `docker logs ai-online` 找原因。

### 5. 匯入 Grafana 儀表板

兩條路擇一：

**A（建議）— API 匯入**：向使用者要 Grafana admin 密碼（互動輸入，不落檔）：

```bash
read -s GPW   # 使用者當場輸入
jq '{dashboard: (. + {id: null}), overwrite: false,
     inputs: [{name:"DS_INFLUXDB", type:"datasource",
               pluginId:"influxdb", value:"incense-influx"}]}' \
  ~/wro-latest/cloud_dash/grafana_dashboard_ai.json \
| curl -s -u "admin:$GPW" -H "Content-Type: application/json" \
    -X POST http://localhost:3000/api/dashboards/import -d @- ; unset GPW
```

（datasource uid ★必須先查現值★：`curl -s -u admin:$GPW
http://localhost:3000/api/datasources | jq '.[].uid'`——2026-08-20 實測
為 `dftmtpkivyadcb`（name `InfluxDB-incense`），舊文獻寫的
`incense-influx` 已非現值，勿寫死。）

**B — 人工匯入**：使用者自己在 `http://localhost:3000` → Dashboards →
Import → 上傳該 JSON → 資料源選 InfluxDB-incense。

### 6. 驗收與收尾

- 請使用者**親眼**看儀表板「智慧香爐 AI 狀態」：心跳卡片綠、AI-1 版本
  與 MAE 有值、AI-2 旗標正常（CO₂ 硬警報期間 `safety_override` 接近
  100% 是預期行為）。★你只回報「資料已落庫」，畫面正常與否由人說了算★。
- 把部署結果（日期、容器狀態、首輪重訓數字、遇到的坑）追記到
  `部署紀錄.md`，commit + push。
- 若使用者要公開連結：Share → Public dashboard（人工操作）。

## 更新重部署（服務程式碼有新版時）

```bash
cd ~/wro-latest && git pull
cp cloud_dash/ai_online_learning.py ~/incense-cloud/
cd ~/incense-cloud && docker compose restart ai-online
sleep 90 && docker logs --tail 8 ai-online   # 確認新一輪「AI-1 重訓完成」
```

（2026-08-20 晚：訓練粒度升級 30 分鐘——樣本×2、A/B 實測 MAE −7.7%。
快取檔名從 `co2_hourly_cache.json` 換成 `co2_30m_cache.json`，
舊檔留著無妨，新檔首輪會自動重建。）

## 卡關時

依 CLAUDE.md §9 格式回報並停止。常見狀況：

| 症狀 | 方向 |
|---|---|
| `docker compose ps` 四容器不齊 | 堆疊本身有問題，先回報，別動 |
| 日誌「兩個資料來源都連不上」 | 容器內連 `http://influxdb:8086` 失敗——檢查 compose 網路（預設同專案同網路，通常是 depends_on 拼錯或段落貼錯層級） |
| 寫入 401/403 | InfluxDB token 非預設值——問使用者實際 token，用環境變數 `INFLUX_TOKEN` 傳入 compose，值不落 repo |
| 匯入 API 412/400 | uid 衝突或 datasource uid 不對——先查 `/api/datasources`，或改走 B 人工匯入 |
