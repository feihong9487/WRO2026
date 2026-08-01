#!/usr/bin/env bash
# 智慧香爐 — 節點佈建腳本
# 把一台已完成 P0 的 Pi 變成「開機即上線」的多爐節點。
#
# 用法（在 Pi 上、於含 pi_fsm.py 與 incense-fsm.service 的資料夾執行）：
#   sudo DEVICE_ID=aroma01 CLOUD_MQTT=100.x.y.z MQTT_USER=burner \
#        MQTT_PASS='橋接密碼' TS_AUTHKEY=tskey-auth-xxxx ./provision.sh
#
# TS_AUTHKEY 可省略；省略則之後手動執行 sudo tailscale up --hostname incense-<爐號>

set -euo pipefail

DEVICE_ID="${DEVICE_ID:?請以 DEVICE_ID=xxx 指定香爐代號（例 aroma01）}"
CLOUD_MQTT="${CLOUD_MQTT:?請以 CLOUD_MQTT=xxx 指定雲端主機位址（Tailscale IP）}"
MQTT_USER="${MQTT_USER:-burner}"
MQTT_PASS="${MQTT_PASS:?請以 MQTT_PASS=xxx 指定橋接密碼}"
INSTALL_DIR=/opt/incense

echo "== [1/6] 裝置身分：incense-${DEVICE_ID} =="
hostnamectl set-hostname "incense-${DEVICE_ID}"
mkdir -p /etc/incense
echo "DEVICE_ID=${DEVICE_ID}" > /etc/incense/device.conf

echo "== [2/6] 程式進駐 ${INSTALL_DIR} =="
mkdir -p "${INSTALL_DIR}"
if [ -f pi_fsm.py ]; then
  cp -f pi_fsm.py "${INSTALL_DIR}/"
else
  echo "（目前資料夾找不到 pi_fsm.py，略過複製——請確認 ${INSTALL_DIR}/pi_fsm.py 已存在）"
fi

echo "== [3/6] mosquitto 橋接（QoS1 斷線佇列）=="
cat > /etc/mosquitto/conf.d/queue.conf <<'EOF'
max_queued_messages 100000
EOF
cat > /etc/mosquitto/conf.d/bridge.conf <<EOF
connection to-cloud
address ${CLOUD_MQTT}:1883
remote_username ${MQTT_USER}
remote_password ${MQTT_PASS}
cleansession false
try_private true
# 本地 incense/... 上雲時自動改寫為 incense/${DEVICE_ID}/...
topic # out 1 incense/ incense/${DEVICE_ID}/
EOF
chmod 600 /etc/mosquitto/conf.d/bridge.conf
systemctl enable mosquitto
systemctl restart mosquitto

echo "== [4/6] 開機自啟服務 =="
if [ -f incense-fsm.service ]; then
  cp -f incense-fsm.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now incense-fsm
  echo "incense-fsm 已啟用（狀態：$(systemctl is-active incense-fsm)）"
else
  echo "（找不到 incense-fsm.service，略過——FSM 將不會開機自啟）"
fi
if command -v docker >/dev/null 2>&1; then
  systemctl enable docker || true
fi

echo "== [5/6] Tailscale 維運通道 =="
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
if [ -n "${TS_AUTHKEY:-}" ]; then
  tailscale up --authkey "${TS_AUTHKEY}" --hostname "incense-${DEVICE_ID}"
  echo "Tailscale IP：$(tailscale ip -4 | head -1)"
else
  echo "（未提供 TS_AUTHKEY，之後請手動：sudo tailscale up --hostname incense-${DEVICE_ID}）"
fi

echo "== [6/6] 佈建完成 =="
echo "驗證：sudo reboot 後不碰鍵盤，雲端面板應在 2 分鐘內看到 ${DEVICE_ID} 的資料。"
