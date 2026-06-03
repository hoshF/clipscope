#!/bin/bash
# 定时同步脚本 — 由 launchd 调用
# 每 6 小时自动检查并下载新增视频

cd /Users/hoshf/Project/social-archive-douyin || exit 1

# 日志追加到单独文件，方便排查
LOG="data/tracking/auto_sync.log"
echo "===== $(date) =====" >> "$LOG"

.venv/bin/python scripts/download/sync_downloads.py >> "$LOG" 2>&1

echo "" >> "$LOG"
