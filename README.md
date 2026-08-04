# ClipScope

ClipScope is a local-first short-video archive toolkit for Douyin, TikTok, and Bilibili. It provides a stable CLI for batch downloading, feed collection, comment scraping, and cookie management.

The crawler engine from [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) is vendored into the project for stability.

```bash
uv run douyin <command>
```

## What It Does

| Area | Command | Purpose |
| --- | --- | --- |
| Batch sync | `uv run douyin sync` | Check tracked users and download newly published videos or albums |
| Single grab | `uv run douyin grab <url> <dir>` | Download images/video from a single post to any directory |
| User tracking | `uv run douyin track add/list/remove` | Manage which users to sync |
| Feed tracking | `uv run douyin feed --loop` | Capture recommendation-feed snapshots over time |
| Comment collection | `uv run douyin comments <url>` | Collect comments and replies for a Douyin user |
| Cookies | `uv run douyin cookies apply` | Apply exported browser cookies to crawler configs |
| Config | `uv run douyin config` | Show config structure guide |
| Logs | `uv run douyin logs` | Log management (status / clean / prune) |

## Install

```bash
brew install uv
git clone <repo-url> clipscope
cd clipscope
uv sync
```

Cookie files go under `cookies/` (gitignored). Crawler runtime config overrides go under `crawler_configs/` (gitignored).

## Cookie Setup

1. Log in to Douyin or TikTok in a browser.
2. Export cookies in Netscape format.
3. Save them as `cookies/douyin.txt` or `cookies/tiktok.txt`.
4. Apply them:

```bash
uv run douyin cookies apply
```

Cookie files are sensitive and ignored by Git.

## CLI Usage

```bash
uv run douyin --help
uv run douyin config

# Sync downloads
uv run douyin sync --dry-run
uv run douyin sync

# User tracking
uv run douyin track add "https://www.douyin.com/user/<sec_user_id>"
uv run douyin track list
uv run douyin track remove <sec_user_id>

# Feed collector
uv run douyin feed --loop --interval 5

# Comment collection
uv run douyin comments "https://www.douyin.com/user/<sec_user_id>"

# Cookie management
uv run douyin cookies apply
uv run douyin cookies -- --check
uv run douyin cookies -- --clear

# Log management
uv run douyin logs
uv run douyin logs clean
uv run douyin logs prune 30
```

## Data Layout

```text
clipscope/
├── src/clipscope/              CLI, crawler engine, collectors, utilities
│   ├── cli.py
│   ├── crawler/                vendored crawler engine
│   ├── collector/              sync, track, feed, comments, organize
│   └── utils/                  paths, logging, cookies, config
├── scripts/
│   ├── launchd/                macOS scheduled job templates
│   └── utils/auto_sync.sh      scheduled sync script
├── tests/                      pytest suite
├── config.yaml                 app settings
├── cookies/                    local cookie files (ignored)
├── crawler_configs/            crawler runtime config overrides (ignored)
└── data/                       local archive and analysis data (ignored)
```

Ignored local assets:

- `cookies/`: browser login cookies
- `crawler_configs/`: crawler config overrides (Cookie, tokens)
- `data/downloads/`: downloaded videos and albums
- `data/downloads/.tracked.json`: user tracking manifest
- `data/comments/`: collected comments
- `data/tracking/`: feed snapshots, sync logs, launchd output
- `data/logs/`, `data/temp/`: runtime artifacts

## Scheduled Sync

The launchd files are templates so the project can be moved without editing absolute paths.

```bash
scripts/launchd/install_sync_job.sh
scripts/launchd/uninstall_sync_job.sh
```

For a dry-run style invocation of the sync script:

```bash
CLIPSCOPE_SYNC_ARGS="--dry-run" scripts/utils/auto_sync.sh
```

## Development

```bash
uv run pytest -q
uv run ruff check .
```
