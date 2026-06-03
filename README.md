# Douyin/TikTok/Bilibili Crawler Toolkit

A Douyin (TikTok China) data collection & analysis toolkit built on top of [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API).

> Supports batch video/album downloading, recommendation feed tracking, user profiling, and more.

---

## 📦 Features

| Feature | CLI Command | Description |
|---|---|---|
| 🎬 **Batch Download** | `uv run douyin sync` | Check & download new videos from tracked users |
| 📡 **Feed Tracking** | `uv run douyin feed --loop` | Scheduled collection of recommendation feed data |
| 💬 **Comment Collection** | `uv run douyin comments <url>` | Collect all comments under a user's videos |
| 🔗 **Social Graph** | `uv run douyin analyze social-graph <user>` | Build relationship networks from comments |
| 🎯 **Fan Portrait** | `uv run douyin analyze fan-portrait <user>` | Analyze fan demographics & loyalty |
| 🕵️ **Identity Mining** | `uv run douyin analyze identity <user>` | Extract birthplace, education, relationships |
| 🔎 **Commenter Value** | `uv run douyin analyze commenter-value <user>` | Evaluate active commenters' worth |
| 📊 **Profile Inference** | `uv run douyin analyze recommend-portrait` | Infer algorithm's user profile |
| 🔄 **Upstream Sync** | `uv run douyin upstream update` | Update crawler engine from upstream |
| 🔑 **Cookie Mgmt** | `uv run douyin cookies apply` | Apply cookies from browser export |
| 📋 **Log Management** | `uv run douyin logs clean` | Clean empty/pruned log files |
| 🌐 **API Service** | `uv run uvicorn app.main:app` | FastAPI-based HTTP interface |

---

## 📁 Project Structure

```
social-archive-douyin/
│
├── app/                          ← API Server (FastAPI)
│   ├── main.py
│   ├── api/
│   │   ├── router.py
│   │   ├── models.py
│   │   └── endpoints/
│   │       ├── parser.py
│   │       ├── downloader.py
│   │       └── tracking.py
│   └── static/dashboard.html     Feed trend dashboard
│
├── scripts/                      ← CLI Tools
│   ├── cli.py                    Unified entry point (uv run douyin)
│   ├── download/
│   │   ├── sync_downloads.py
│   │   └── rename_user_dirs.py
│   ├── collect/
│   │   ├── feed_collector.py
│   │   └── collect_comments.py
│   ├── analyze/
│   │   ├── analyze_recommend_portrait.py
│   │   ├── analyze_social_graph.py
│   │   ├── analyze_fan_portrait.py
│   │   ├── analyze_identity_mining.py
│   │   └── analyze_commenter_value.py
│   └── utils/
│       ├── data_utils.py
│       ├── apply_cookies.py
│       ├── check_upstream.py
│       └── auto_sync.sh
│
├── lib/                          ← Crawler Engine (from upstream)
│   └── crawlers/{douyin,tiktok,bilibili,hybrid}/
│
├── tests/                        ← Test suite (pytest)
│   ├── test_data_utils.py
│   ├── test_check_upstream.py
│   └── conftest.py
│
├── cookies/                      ← Netscape-format cookie files
├── data/
│   ├── downloads/                Downloaded videos / analysis reports
│   ├── comments/                 Comment collection data
│   ├── tracking/                 Feed snapshots + sync logs
│   └── logs/                     Crawler logs
│
├── .github/workflows/ci.yml      ← CI (Ruff + pytest)
├── config.yaml
├── pyproject.toml
└── README.md
```

---

## 🚀 Quick Start

### 1. Install

```bash
# Prerequisites: Python 3.11+, uv
brew install uv
git clone <repo-url> && cd social-archive-douyin
uv sync --all-groups     # Install all deps (app + crawler + dev)
```

### 2. Configure Cookies

```bash
# Export cookies from browser (Netscape format) → cookies/douyin.txt
uv run douyin cookies apply
```

### 3. Use

```bash
# See all commands
uv run douyin

# Sync user videos (preview)
uv run douyin sync -- --dry-run

# Collect recommendation feed
uv run douyin feed -- --loop

# Check upstream updates
uv run douyin upstream check

# Manage logs
uv run douyin logs
```

### 4. Run Tests

```bash
uv run pytest -v
```

---

## 🎬 Feature Details

### 1. Batch Download User Videos

```bash
uv run douyin sync        # Sync all tracked users (dry-run first)
uv run douyin sync -- --dry-run  # Preview mode
```

**Download directory structure:**
```
data/downloads/<userID>/
├── _meta.json                          ← User info
├── 001_7625870161799047537_title.mp4   ← Video
├── 002_7639283934052336485_title/      ← Album folder
│   ├── 01.jpg
│   └── 02.jpg
└── ...
```

### 2. Recommendation Feed Tracking

The collector fetches your Douyin recommendation feed every 5 minutes, recording trending hashtags:

```bash
uv run douyin feed -- --loop --interval 5
```

Data is saved to `data/tracking/feed_YYYYMMDD.jsonl` (JSONL format, deduplicated). The trend dashboard displays it automatically.

### 4. Profile Inference

```bash
uv run douyin analyze recommend-portrait
```

Sample output:
```
🎯 Inferred User Profile
   Primary interests: Music, Emotions, Comedy
   Content preference: Short videos (< 15 seconds)
   Format preference: Video 80% / Album 20%
```

### 5. 💬 Comment Collection

Collect all comments (including replies and IP locations) from a target user's videos, for fan profiling and social network analysis.

```bash
uv run douyin comments "https://www.douyin.com/user/<userID>"
uv run douyin comments "https://..." -- --max-posts 10 --max-comments 1000
uv run douyin comments "https://..." -- --no-replies
uv run douyin comments "https://..." -- --resume
```

**Output structure:**
```
data/comments/<userID>/
├── _meta.json              User info + collection config
├── comments.json           Full comments (JSON array)
├── stats.json              Collection summary
├── relations/              Social graph analysis
│   ├── relation_graph.json  Graph data (nodes + edges)
│   ├── communities.json     Community detection
│   └── report.txt           Text report
└── profile/                Fan portrait analysis
    ├── profile_report.json  Structured portrait report
    └── report.txt           Text report
```

### 6. 🔗 Social Graph Analysis

Build interaction networks from collected comment data to discover core fan circles and opinion leaders.

```bash
uv run douyin analyze social-graph <sec_user_id>
```

Sample output:
```
🌟 KOLs / Opinion Leaders: 12
  - UserA (12.3K followers, 45 comments)
  - UserB (5.6K followers, 32 comments)
💬 Core Fans / Active Interactors: 89
  - UserC (67 comments, 12 videos)
👥 Regular Fans: 342
```

### 7. 🎯 Fan Portrait Analysis (Comment-based)

Analyze multi-dimensional fan demographics from comment data.

```bash
uv run douyin analyze fan-portrait <sec_user_id>
```

| Dimension | Description |
|---|---|
| 🌍 **Geographic Distribution** | Province/country distribution based on IP locations |
| ⏰ **Active Hours** | When fans tend to comment (early morning, night, etc.) |
| 👤 **Fan Type** | KOL / Core Fan / Regular User / New User ratio |
| 📝 **Keywords** | Most frequent words appearing in comments |
| 💖 **Sentiment** | Positive / Neutral / Negative comment ratio |
| ⭐ **Fan Loyalty** | Cross-video commenters, frequent commenters, loyal fans |

### 8. 🕵️ Identity Mining

Extract identity clues from comment content and post captions.

```bash
uv run douyin analyze identity <sec_user_id>
```

Analysis dimensions:
| Dimension | Description |
|---|---|
| 📍 **Birthplace** | Infer hometown/location from most common commenter IP areas |
| 🎓 **Education** | Extract majors, courses, school clues from captions/comments |
| 👥 **Social Relations** | Analyze frequent interactors, self-described relationships |
| 🏠 **Activity Location** | Extract cities lived in or visited |
| 👤 **Name Clues** | Mine real name possibilities from nicknames and greetings |
| 🐾 **Other Traits** | Pets, fitness, music, content creation, and other interest tags |

### 9. 🔎 Commenter Value Assessment

Evaluate active commenters' user spaces to determine if they're worth crawling independently.

```bash
uv run douyin analyze commenter-value <sec_user_id>
uv run douyin analyze commenter-value <sec_user_id> -- --top 50
```

**Scoring dimensions** (composite score 0-100):
| Dimension | Weight | Description |
|---|---|---|
| Follower Count | 30% | More followers → stronger KOL effect |
| Post Count | 20% | More posts → more content to collect |
| Comment Engagement | 25% | Activity on their own posts |
| Activity in Target | 25% | Higher correlation → more worth collecting |

**Sample output:**
```
🌟🌟🌟 High Value (score ≥70):
  · ShanYingNianYing (Score 41.0, Followers 102, Posts 83)
🌟🌟 Valuable (score 20-69):
  · NiMingZuiShuai (Score 26.0, Followers 199, Posts 38)
💤 Low Value (score <20): 5 users
```

### 10. API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/parser/video?url=...` | GET | Parse single video/album data |
| `/api/parser/batch` | POST | Batch parse multiple URLs |
| `/api/parser/extract?text=...` | GET | Extract links from share text and parse |
| `/api/downloader/video?url=...` | GET | Download watermark-free video |
| `/api/downloader/images?url=...` | GET | Get album image URLs (watermark-free) |
| `/api/tracking/feed` | POST | Receive feed snapshot (from Tampermonkey/collector) |
| `/api/tracking/history` | GET | Historical collection records |
| `/api/tracking/stats` | GET | Hashtag frequency trend data |

> **Note**: API examples are described in [API Examples](#api-examples) below.

---

## 🔑 Cookie Management

```bash
# Check expiry
uv run douyin cookies -- --check

# Apply from cookies/douyin.txt
uv run douyin cookies apply

# Clear from config
uv run douyin cookies -- --clear

# View config structure
uv run douyin config
```

**Critical cookies:**
- `sessionid` / `sid_tt` — Login session, most critical (~30-60 days)
- `__ac_nonce` — Short-lived anti-crawl token (hours)
- `ttwid` — Device identifier, long-lived

---

## 🧪 Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest -v --cov

# Lint & format
uv run ruff check .
uv run ruff format .

# Check upstream updates
uv run douyin upstream check

# Apply upstream changes
uv run douyin upstream update
```

CI is automatically run on push/PR via GitHub Actions: ruff check → ruff format → pytest.

---

## 🛡️ Anti-Detection Mechanisms

The project bypasses Douyin's anti-crawling measures through:

| Mechanism | Implementation | Location |
|---|---|---|
| A-Bogus Signature | SM3 hash + RC4 encryption | `lib/crawlers/douyin/web/abogus.py` |
| Cookie Authentication | User login credentials | `cookies/douyin.txt` |
| User-Agent Spoofing | Mimics Chrome browser | `config.yaml` |
| msToken | Fetches token from Douyin's token server | `lib/crawlers/douyin/web/utils.py` |
| Rate Limiting | `asyncio.sleep()` to actively slow down | Various scripts |
| Device Fingerprint | Generates fake `s_v_web_id` | `lib/crawlers/douyin/web/utils.py` |

---

## 📊 Data Storage

| Data Type | Storage Location | Format |
|---|---|---|
| User Videos | `data/downloads/<user_id>/` | MP4 / JPG |
| User Metadata | `data/downloads/<user_id>/_meta.json` | JSON |
| Feed Snapshots | `data/tracking/feed_YYYYMMDD.jsonl` | JSON Lines |
| Profile Analysis | `data/downloads/_profile_analysis/` | JSON |

---

## ⚙️ Tech Stack

| Component | Technology |
|---|---|
| Crawler Engine | [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) |
| API Framework | FastAPI + Uvicorn |
| Async HTTP | HTTPX |
| Signature Algorithm | SM3 (gmssl) + RC4 |
| Runtime | Python 3.14 / uv |
| Frontend Dashboard | Vanilla HTML + JavaScript + Chart.js |

---

## ⚠️ Notes

1. **Cookies expire** — re-export and re-apply after expiry
2. **More feed data = better trends** — recommend long-running collection
3. **Don't download too aggressively** — recommend 1.5s interval between downloads
4. **This tool is for personal learning and research only** — do not use for illegal purposes

---

## API Examples

### Parse Single Video

```http
GET /api/parser/video?url=https://v.douyin.com/L4FJNR3/&minimal=true
```

### Batch Parse

```http
GET /api/parser/batch?urls=https://v.douyin.com/L4FJNR3/&urls=https://www.bilibili.com/video/BV1M1421t7hT
```

### Extract Links from Text

```http
GET /api/parser/extract?text=7.43 pda:/ 让你记住我 https://v.douyin.com/L5pbfdP/
```

### Download Watermark-Free Video

```http
GET /api/downloader/video?url=https://v.douyin.com/L4FJNR3/
```

### Get Album Download Links

```http
GET /api/downloader/images?url=https://www.douyin.com/note/xxx
```
