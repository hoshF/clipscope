#!/bin/bash
# 定时同步脚本 — 由 launchd 调用
# 每 6 小时自动检查并下载新增视频

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT" || exit 1

LOG="data/tracking/auto_sync.log"
mkdir -p "$(dirname "$LOG")"

{
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') 已更新 ====="
    .venv/bin/python scripts/download/sync_downloads.py ${CLIPSCOPE_SYNC_ARGS:-} 2>&1
    echo ""
} >> "$LOG"
