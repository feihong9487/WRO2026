# 廟公機器人監控網站：部署到桌機

網站和 Grafana 一樣放在桌機的 docker compose 裡。

- 公開展示頁：`https://desktop-c8l8ri6-1.tail7920c6.ts.net:8443/`，免登入，給評審和觀眾看。
- 團隊台：同一個網址後面加 `/team`，要登入，可以遠端操控機器人。

Grafana 原本的網址不受影響。

## 1. 複製檔案

把整個 `KEEPER_WEB` 資料夾複製到桌機放 `docker-compose.yml` 的資料夾，改名為 `keeper_web`。
**不要複製 `data/`**，那是筆電測試用的，裡面有測試帳號。

在同一層另外建一個空資料夾 `keeper_web_data`。

## 2. 建立網站專用的 MQTT 帳號

建議不要和筆電中繼共用 `burner` 帳號，這樣帳號外流時可以單獨停用。在桌機執行下面兩行（密碼自己取）：

```bash
docker compose exec mosquitto mosquitto_passwd -b /mosquitto/config/passwd keeper-web '網站用的密碼'
docker compose restart mosquitto
```

## 3. 設定密碼

在 `keeper_web_data/` 裡建立 `keeper_web.json`：

```json
{
  "mqtt_user": "keeper-web",
  "mqtt_password": "上一步設定的密碼"
}
```

## 4. 加入 docker compose 並啟動

把 `deploy/compose-snippet.yml` 的內容貼到 `docker-compose.yml` 的 `services:` 底下，然後執行：

```bash
docker compose up -d keeper-web
docker compose logs -f keeper-web
```

看到 `MQTT：已連上 mosquitto:1883` 就代表成功了。這時在桌機打開 `http://localhost:8090/` 應該就能看到公開頁。

## 5. 建立團隊帳號

每個隊員一個帳號，密碼至少 10 個字，輸入時畫面不會顯示：

```bash
docker compose exec keeper-web python /app/manage_users.py add 帳號名稱
docker compose exec keeper-web python /app/manage_users.py list
```

## 6. 開公網網址（Tailscale Funnel）

在桌機跑 Tailscale 的地方（和當初開 Grafana 公網時同一個地方）執行：

```bash
tailscale funnel --bg --https=8443 http://localhost:8090
```

Grafana 用的是 443 埠，這裡用 8443，兩個網址互不影響。執行 `tailscale funnel status` 可以確認目前開了哪些。

## 安全設計

- 公開頁只看得到展示用的資料，沒有任何操控功能。事件紀錄只顯示到站和任務進度，不顯示除錯訊息。
- 團隊台的操控 API 在伺服器端檢查登入，不是只把按鈕藏起來。
- 同一個帳號密碼錯 5 次會鎖 5 分鐘；全站 5 分鐘內錯 30 次也會暫停登入。
- 密碼只存 PBKDF2 雜湊值。登入 12 小時後自動登出。
- 指令會經過三層檢查：
  1. 網站只接受固定幾種指令。
  2. 筆電中繼拒絕超過 30 秒才送到的指令，避免延遲的「開始任務」突然讓車子動起來。
  3. R4 檢查自己是否待命、電池電壓是否足夠。
- 所有遠端指令都記在 `keeper_web_data/commands.log`，包括送出者和時間。
- R4 上的實體按鍵永遠可以緊急停車。遠端操控不能取代旁邊顧車的人。

## 更新網站

換掉 `keeper_web/` 裡的檔案，然後執行：

```bash
docker compose restart keeper-web
```

帳號與設定都在 `keeper_web_data/`，更新時不會被覆蓋。
