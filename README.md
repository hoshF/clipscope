# ClipScope

ClipScope is a local-first short-video archive and analysis toolkit for Douyin, TikTok, and Bilibili. It wraps the upstream [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) crawler engine with a stable CLI, FastAPI service, scheduled sync helpers, and analysis scripts.

The command name remains `douyin` for compatibility:

```bash
uv run douyin <command>
```

## What It Does

| Area | Command | Purpose |
| --- | --- | --- |
| Batch sync | `uv run douyin sync` | Check tracked users and download newly published videos or albums |
| Feed tracking | `uv run douyin feed -- --loop` | Capture recommendation-feed snapshots over time |
| Comment collection | `uv run douyin comments <url>` | Collect comments and replies for a Douyin user |
| Analysis | `uv run douyin analyze ...` | Build fan portraits, social graphs, identity clues, and commenter value reports |
| API service | `uv run uvicorn app.main:app` | Expose parsing, download, and tracking endpoints |
| Cookies | `uv run douyin cookies apply` | Apply exported browser cookies to crawler configs |
| Upstream engine | `uv run douyin upstream ...` | Bootstrap, check, and update the ignored `lib/` crawler engine |

## Install

```bash
brew install uv
git clone <repo-url> clipscope
cd clipscope
uv sync --all-extras --all-groups
uv run douyin upstream bootstrap
```

`lib/` is not committed. It is a local clone of the upstream crawler engine and can be recreated with `uv run douyin upstream bootstrap`.

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

uv run douyin sync -- --dry-run
uv run douyin sync

uv run douyin feed -- --loop --interval=5
uv run douyin comments "https://www.douyin.com/user/<sec_user_id>"

uv run douyin analyze recommend-portrait
uv run douyin analyze social-graph <sec_user_id>
uv run douyin analyze fan-portrait <sec_user_id>
uv run douyin analyze identity <sec_user_id>
uv run douyin analyze commenter-value <sec_user_id>

uv run douyin upstream check
uv run douyin upstream bootstrap
uv run douyin upstream bootstrap -- --update
uv run douyin upstream update
```

## API Service

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Useful endpoints:

| Path | Purpose |
| --- | --- |
| `/docs` | Swagger UI |
| `/health` | Health check |
| `/api/parser/video` | Parse one video or album URL |
| `/api/parser/extract` | Extract links from shared text and parse them |
| `/api/downloader/info` | Return downloadable video or album metadata |
| `/api/tracking/feed` | Receive feed snapshots |
| `/static/dashboard.html` | Local feed dashboard |

## Data Layout

```text
clipscope/
├── app/                 FastAPI service
├── scripts/             CLI commands, collectors, analyzers, utilities
├── tests/               pytest suite
├── config.yaml          ClipScope app config
├── cookies/             local cookie files, ignored
├── data/                local archive and analysis data, ignored
└── lib/                 upstream crawler engine, ignored
```

Ignored local assets:

- `cookies/`: browser login cookies
- `data/downloads/`: downloaded videos and albums
- `data/comments/`: collected comments
- `data/tracking/`: feed snapshots and sync logs
- `data/logs/`, `data/temp/`: runtime artifacts
- `lib/`: upstream crawler engine checkout

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

The project keeps crawler engine code in `lib/` outside version control. Use `uv run douyin upstream check` before applying upstream changes.
