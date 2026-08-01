#!/usr/bin/env bash
# 智慧香爐 — 無人值守有界迴圈（headless）
# ------------------------------------------------------------------
# 用途：出門時讓 Claude Code 自己「驗證 → 修正 → 再驗證」，回來看報告。
#
# 設計原則（重要）：
#   1. 有明確停止條件 —— 驗證全綠就停，不是「一直優化」。
#   2. 有輪數上限 —— 修不好就停下等人，不無限燒額度。
#   3. 每輪從乾淨脈絡開始 —— 避免長對話的偏移（context drift）。
#   4. 全程留下 log —— 事後可稽核它到底改了什麼。
#
# 用法：
#   bash auto_loop.sh              # 預設 5 輪，跑 pytest 迴路
#   MAX_ROUNDS=3 bash auto_loop.sh
#   VERIFY_CMD="bash verify_cloud.sh" bash auto_loop.sh    # 改跑雲端迴路
#
# 前置：建議先用 git 建立版本控制，出事可回溯。

set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/mnt/d/WRO2026}"
MAX_ROUNDS="${MAX_ROUNDS:-5}"
VERIFY_CMD="${VERIFY_CMD:-python3 -m pytest -q}"
MODEL="${MODEL:-sonnet}"
LOG="$PROJECT_DIR/auto_loop_$(date +%Y%m%d_%H%M%S).log"

cd "$PROJECT_DIR" || { echo "找不到專案目錄 $PROJECT_DIR"; exit 1; }

echo "=== 有界自檢迴圈開始 $(date '+%F %T') ===" | tee "$LOG"
echo "驗證指令：$VERIFY_CMD｜上限：$MAX_ROUNDS 輪｜模型：$MODEL" | tee -a "$LOG"

for i in $(seq 1 "$MAX_ROUNDS"); do
  echo "" | tee -a "$LOG"
  echo "--- 第 $i/$MAX_ROUNDS 輪：執行驗證 ---" | tee -a "$LOG"

  OUT="$(eval "$VERIFY_CMD" 2>&1)"
  RC=$?
  echo "$OUT" | tail -30 | tee -a "$LOG"

  if [ $RC -eq 0 ]; then
    echo "" | tee -a "$LOG"
    echo "✅ 驗證通過，於第 $i 輪達成目標，迴圈結束。" | tee -a "$LOG"
    exit 0
  fi

  echo "--- 第 $i 輪：交給 Claude 修正 ---" | tee -a "$LOG"

  PROMPT="請先閱讀 CLAUDE.md（若任務涉及機構設計，另讀 CAD_LOOP.md）。

驗證指令 \`$VERIFY_CMD\` 失敗，輸出如下：

$OUT

請診斷並修正**程式或設計參數**，讓驗證通過。

嚴格禁止（違反即視為任務失敗）：
- 修改測試斷言或放寬驗證器容差
- 放寬安全常數、滑動間隙、最小壁厚、禁 PLA 區、過濾鏈順序
- 使用 skip / try-except-pass 消除失敗
- 把 *_MEASURED 旗標改成 True
- 聲稱任何需要實體硬體的事項已驗證

若你判斷此問題需要人類決策（例如設計參數互相衝突、需要實測數據），
不要猜測，直接依 CLAUDE.md §9 格式說明卡關點即可。"

  claude -p "$PROMPT" \
    --model "$MODEL" \
    --max-turns 25 \
    --permission-mode acceptEdits \
    2>&1 | tee -a "$LOG"
done

echo "" | tee -a "$LOG"
echo "⚠️ 已達 $MAX_ROUNDS 輪上限仍未通過，停止並等待人工介入。" | tee -a "$LOG"
echo "請檢查 $LOG，並用 git diff 檢視這段期間的所有改動。" | tee -a "$LOG"
exit 1
