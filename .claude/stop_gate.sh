#!/usr/bin/env bash
# 智慧香爐 — Stop hook 自檢閘門
# ------------------------------------------------------------------
# 在 Claude Code 準備結束回應時觸發：測試沒過就擋下結束，把失敗訊息回饋給它繼續修。
#
# 退出碼約定：
#   0 = 放行（可以結束）
#   2 = 擋下結束，stderr 內容會回饋給 Claude
#
# ★ 迴圈上限 ★
#   若測試永遠修不好，無上限的 Stop hook 會變成無限迴圈並燒光額度。
#   本腳本最多擋 MAX_BLOCKS 次，之後強制放行並要求回報卡關。
#   請勿為了「讓它繼續努力」而移除這個上限。
#
# 安裝：
#   1. 放到 /mnt/d/WRO2026/.claude/stop_gate.sh
#   2. chmod +x .claude/stop_gate.sh
#   3. 於 .claude/settings.json 設定 Stop hook
#
# ★ 2026-08-02 修正 ★
#   原版把關 test_fsm_core.py，但該檔不存在於專案中，
#   `[ -f test_fsm_core.py ] || exit 0` 會直接放行——閘門形同虛設。
#   改為偵測任何 test_*.py，並改用 run_tests.py（不需 pytest）。

set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-/mnt/d/WRO2026}"
COUNTER="/tmp/incense_stop_gate_count"
MAX_BLOCKS=3

cd "$PROJECT_DIR" 2>/dev/null || exit 0

# 沒有任何測試檔就直接放行（例如還沒把檔案放進來）
if ! find . -name "test_*.py" -not -path "./.git/*" -print -quit | grep -q .; then
  exit 0
fi

# 優先用專案自帶的執行器（不依賴 pytest；系統 Python 受 PEP 668 保護裝不了）
if [ -f run_tests.py ]; then
  OUT="$(python3 run_tests.py -q 2>&1)"
else
  OUT="$(python3 -m pytest -q 2>&1)"
fi
RC=$?

if [ $RC -eq 0 ]; then
  rm -f "$COUNTER"
  exit 0                      # 全綠，放行
fi

# 讀取並累加擋下次數
COUNT=0
[ -f "$COUNTER" ] && COUNT="$(cat "$COUNTER" 2>/dev/null || echo 0)"
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER"

if [ "$COUNT" -gt "$MAX_BLOCKS" ]; then
  rm -f "$COUNTER"
  echo "測試仍未通過，但已達自檢上限（${MAX_BLOCKS} 次）。請依 CLAUDE.md §9 格式回報卡關，不要繼續盲修。" >&2
  echo "" >&2
  echo "$OUT" | tail -12 >&2
  exit 0                      # 強制放行，避免無限迴圈
fi

{
  echo "自檢未通過（第 ${COUNT}/${MAX_BLOCKS} 次）——請修正後再結束。"
  echo ""
  echo "$OUT" | tail -20
  echo ""
  echo "提醒：修正程式或設計參數，不得修改測試斷言、放寬安全常數或間隙下限（CLAUDE.md §5.2）。"
} >&2

exit 2                        # 擋下結束，讓 Claude 看到上面的訊息並繼續
