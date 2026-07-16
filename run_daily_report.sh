#!/bin/bash
# run_daily_report.sh — CentOS 每日自动：采集 → 生成战报 → 推送
#
# crontab 配置（每天 8:30 执行）:
#   30 8 * * * bash /opt/PUBG/run_daily_report.sh >> /opt/PUBG/cron.log 2>&1

set -e
cd "$(dirname "$0")"

# ========== 配置 ==========
PYTHON="python3"          # CentOS 上可能是 python3.11 等
DATE=$(date +%Y-%m-%d)
LOG_FILE="cron.log"
# 保留最近 30 天的日志
MAX_LINES=5000
# ==========================

echo ""
echo "══════════════════════════════════════════════"
echo "  PUBG 每日战报 — $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════"

# ── 1. 拉取远程（防止本地落后） ──
echo "[1/4] git pull..."
git checkout main -q 2>/dev/null || true
git pull origin main -q 2>&1 || echo "  (pull 失败，继续执行)"

# ── 2. 自动测试 ──
echo "[2/5] 运行自动测试..."
$PYTHON -m unittest discover -s tests -v 2>&1

# ── 3. 采集数据 ──
echo "[3/5] 采集 dak.gg 数据..."
$PYTHON fetch_matches.py 2>&1

# ── 4. 生成战报 ──
echo "[4/5] 生成战报..."
$PYTHON generate_report.py 2>&1

# ── 5. 提交并推送 ──
echo "[5/5] git commit & push..."
git add data/ reports/ 2>&1

if git diff --cached --quiet 2>/dev/null; then
    echo "  (无变更，跳过)"
else
    git commit -m "📊 每日战报 ${DATE}" 2>&1
    git push origin main 2>&1
    echo "  ✅ 已推送"
fi

echo "══════════════════════════════════════════════"
echo "  完成 — $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════"

# 保留最近 N 行日志
if [ -f "$LOG_FILE" ]; then
    tail -n $MAX_LINES "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi
