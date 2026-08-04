#!/bin/bash
# Scheduled sync script — invoked by launchd
# Runs every 6 hours to check and download new videos

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT" || exit 1

LOG="data/tracking/auto_sync.log"
mkdir -p "$(dirname "$LOG")"

{
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') sync started ====="
    uv run douyin sync ${CLIPSCOPE_SYNC_ARGS:-} 2>&1
    echo ""
} >> "$LOG"
