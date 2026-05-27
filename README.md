# Douyin/TikTok/Bilibili Crawler Toolkit

A Douyin (TikTok China) data collection & analysis toolkit built on top of [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API).

> Supports batch video/album downloading, recommendation feed tracking, user profiling, and more.

---

## 📦 Features

| Feature | Tool | Description |
|---|---|---|
| 🎬 **Batch Download** | `download_user_videos.py` | Enter a user profile URL to download all their posts (watermark-free) |
| 🔄 **Sync Updates** | `scripts/download/sync_downloads.py` | Compare local vs remote, download only new videos |
| 📡 **Feed Tracking** | `scripts/collect/feed_collector.py` | Scheduled collection of recommendation feed data to track algorithmic trends |
| 📊 **Trend Dashboard** | `static/dashboard.html` | Visualize hashtag frequency changes over time |
| 🔍 **Profile Inference** | `scripts/analyze/analyze_recommend_portrait.py` | Infer how the algorithm profiles you through recommendation feed analysis |
| 💬 **Comment Collection** | `scripts/collect/collect_comments.py` | Collect all comments under a user's videos (including IP locations, replies) |
| 🔗 **Social Graph** | `scripts/analyze/analyze_social_graph.py` | Build relationship networks from comment interactions to discover communities and KOLs |
| 🎯 **Fan Portrait** | `scripts/analyze/analyze_fan_portrait.py` | Analyze fan demographics, active hours, loyalty from comment data |
| 🕵️ **Identity Mining** | `scripts/analyze/analyze_identity_mining.py` | Extract birthplace, education, relationships, and name clues from comments and post captions |
| 🔎 **Commenter Value** | `scripts/analyze/analyze_commenter_value.py` | Evaluate active commenters' followers/posts/popularity to decide who's worth crawling |
| 🔑 **Cookie Management** | `scripts/utils/apply_cookies.py` | Apply cookies from Netscape format files and check expiry |
| 🌐 **API Service** | `app/main.py` | FastAPI-based HTTP interface |

---

## 📁 Project Structure

```
douyin-crawler-app/
│
├── app/                          ← API Server
│   ├── main.py                   FastAPI entry point
│   ├── api/
│   │   ├── router.py             Route aggregation
│   │   ├── models.py             Response models
│   │   └── endpoints/
│   │       ├── parser.py         Data parsing endpoints
│   │       ├── downloader.py     File download endpoints
│   │       └── tracking.py       Feed tracking endpoints
│   └── static/
│       └── dashboard.html        Trend dashboard
│
├── scripts/                      ← CLI Tools
│   ├── download/                 🎬 Download
│   │   ├── sync_downloads.py     Incremental sync download
│   │   └── rename_user_dirs.py   Rename user directories
│   ├── collect/                  📡 Data Collection
│   │   ├── feed_collector.py     Feed collector (scheduled task)
│   │   └── collect_comments.py   💬 Comment collection
│   ├── analyze/                  🔍 Data Analysis
│   │   ├── analyze_recommend_portrait.py  📡 Recommendation profile
│   │   ├── analyze_social_graph.py        🔗 Social graph
│   │   ├── analyze_fan_portrait.py        🎯 Fan portrait
│   │   ├── analyze_identity_mining.py     🕵️ Identity mining
│   │   └── analyze_commenter_value.py     🔎 Commenter value
│   ├── utils/                    🔧 Utilities
│   │   ├── __init__.py
│   │   ├── data_utils.py         Shared data analysis functions
│   │   ├── apply_cookies.py      Cookie management
│   │   └── auto_sync.sh          Scheduled sync script
│   ├── com.user.douyin-sync.plist  launchd scheduled task config
│   └── douyin-feed-observer.user.js  Tampermonkey script (alternative)
│
├── lib/                          ← Crawler Engine (git clone)
│   └── crawlers/
│       ├── douyin/web/           Douyin web crawler
│       ├── tiktok/web/           TikTok web crawler
│       ├── tiktok/app/           TikTok app crawler
│       ├── bilibili/web/         Bilibili web crawler
│       └── hybrid/               Hybrid parser crawler
│
├── cookies/                      ← Cookie Files
│   ├── douyin.txt                Douyin cookie (Netscape format)
│   └── tiktok.txt                TikTok cookie
│
├── data/                         ← All Data
│   ├── downloads/                Downloaded user videos/albums + analysis reports
│   │   └── <username>/           Grouped by user (auto-sync analysis reports)
│   │       ├── profile/         🎯 Fan portrait reports
│   │       ├── relations/       🔗 Social graph reports
│   │       └── identity/        🕵️ Identity reports
│   ├── comments/                 Comment collection data
│   │   └── <sec_user_id>/       Grouped by user
│   │       ├── comments.json    Full comment data
│   │       ├── stats.json       Collection statistics
│   │       ├── relations/       Social graph analysis
│   │       └── profile/         Fan portrait analysis
│   ├── tracking/                 Feed snapshots (JSONL format)
│   └── temp/                     Temporary download cache
│
├── config.yaml                   Service configuration
├── download_user_videos.py       One-click download script
├── requirements.txt
├── LICENSE                       Apache License 2.0
└── README.md
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Recommended: use uv (100x faster than pip)
brew install uv    # if you don't have uv yet
cd douyin-crawler-app
uv venv
uv pip install -r requirements.txt
uv pip install httpx==0.27.0 socksio rich gmssl tenacity \
               pycryptodomex lz4 pyfiglet importlib_resources \
               aiofiles qrcode pypng pywebio pywebio-battery \
               browser-cookie3 numpy
```

### 2. Configure Cookies

Cookies are required as login credentials:

```bash
# 1. Log in to https://www.douyin.com in your browser
# 2. Export cookies in Netscape format using a Cookie-Editor extension
# 3. Save/overwrite cookies/douyin.txt
# 4. Apply cookies
uv run python scripts/utils/apply_cookies.py
```

### 3. Start Services

```bash
# Start API server (provides dashboard and HTTP interfaces)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir .

# Start feed collector (collects every 5 minutes)
uv run python scripts/collect/feed_collector.py --loop --interval 5
```

### 4. Access

| URL | Description |
|---|---|
| http://localhost:8000/docs | API Documentation (Swagger UI) |
| http://localhost:8000/static/dashboard.html | 📊 Feed Trend Dashboard |
| http://localhost:8000/health | Health Check |

---

## 🎬 Feature Details

### 1. Batch Download User Videos

```bash
# Download all videos/albums from a user (auto-deduplication)
uv run python download_user_videos.py "https://www.douyin.com/user/<userID>"

# Supports both videos and albums, watermark-free, auto-categorized
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

### 2. Sync Update Downloaded Users

```bash
# Check all users for new videos (preview mode)
uv run python scripts/download/sync_downloads.py --dry-run

# Actually download new content
uv run python scripts/download/sync_downloads.py
```

### 3. Recommendation Feed Tracking

The collector fetches your Douyin recommendation feed every 5 minutes, recording trending hashtags:

```bash
# Start continuous collection
uv run python scripts/collect/feed_collector.py --loop --interval 5
```

Data is saved to `data/tracking/feed_YYYYMMDD.jsonl` (JSONL format, deduplicated). The trend dashboard displays it automatically.

### 4. Profile Inference

```bash
# Analyze recommendation feed to infer how the algorithm profiles you
uv run python scripts/analyze/analyze_recommend_portrait.py --count 100
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
# Collect all comments from a user (default: all videos + all comments + replies)
uv run python scripts/collect/collect_comments.py "https://www.douyin.com/user/<userID>"

# Limit scope: only the last 10 videos, max 1000 comments per video
uv run python scripts/collect/collect_comments.py "https://..." --max-posts 10 --max-comments 1000

# Skip replies, collect top-level comments only
uv run python scripts/collect/collect_comments.py "https://..." --no-replies

# Resume interrupted collection
uv run python scripts/collect/collect_comments.py "https://..." --resume

# Incremental sync (quick check for new comments, no full re-crawl needed)
uv run python scripts/collect/collect_comments.py "https://..." --sync
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
# Analyze comment relationships for a specific user
uv run python scripts/analyze/analyze_social_graph.py <sec_user_id_or_dir>
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
# Analyze fan portrait
uv run python scripts/analyze/analyze_fan_portrait.py <sec_user_id_or_dir>
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
# Mine identity information
uv run python scripts/analyze/analyze_identity_mining.py <sec_user_id_or_dir>
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
# Evaluate Top 20 most active commenters
uv run python scripts/analyze/analyze_commenter_value.py <sec_user_id_or_dir>

# Evaluate Top 50
uv run python scripts/analyze/analyze_commenter_value.py <sec_user_id> --top 50
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

Cookies are essential. Use `cookies/douyin.txt` with `apply_cookies.py`:

```bash
# Check current cookie expiry status
uv run python scripts/utils/apply_cookies.py --check

# Apply cookies to the crawler configuration
uv run python scripts/utils/apply_cookies.py
```

**Cookie expiry criteria:**
- `sessionid` / `sid_tt` — Login session, most critical. Expiry breaks all functionality (~30-60 days)
- `__ac_nonce` — Short-lived anti-crawl token (a few hours), auto-refreshable
- `ttwid` — Device identifier, long-lived

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
