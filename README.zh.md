# Douyin/TikTok/Bilibili 爬虫工具集

基于 [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) 构建的抖音数据采集与分析工具集。

> 支持抖音视频/图集批量下载、推荐流追踪分析、用户画像推断等功能。

---

## 📦 功能概览

| 功能 | CLI 命令 | 说明 |
|---|---|---|
| 🎬 **批量下载** | `uv run douyin sync` | 对比本地和远程，只下载新增视频 |
| 📡 **推荐流追踪** | `uv run douyin feed --loop` | 定时采集推荐页数据 |
| 💬 **评论采集** | `uv run douyin comments <url>` | 采集用户所有视频下的评论 |
| 🔗 **关系拓扑** | `uv run douyin analyze social-graph <user>` | 构建用户关系网络 |
| 🎯 **粉丝画像** | `uv run douyin analyze fan-portrait <user>` | 粉丝地域、活跃时段分析 |
| 🕵️ **身份挖掘** | `uv run douyin analyze identity <user>` | 挖掘出生地、教育、关系线索 |
| 🔎 **评论者价值** | `uv run douyin analyze commenter-value <user>` | 评估评论者是否值得爬取 |
| 📊 **用户画像** | `uv run douyin analyze recommend-portrait` | 反推算法对你的兴趣判断 |
| 🔄 **上游更新** | `uv run douyin upstream update` | 一键同步上游爬虫引擎更新 |
| 🔑 **Cookie 管理** | `uv run douyin cookies apply` | 应用浏览器导出的 Cookie |
| 📋 **日志管理** | `uv run douyin logs clean` | 清理空日志和过期日志 |
| 🌐 **API 服务** | `uv run uvicorn app.main:app` | FastAPI HTTP 接口 |

---

## 📁 项目结构

```
social-archive-douyin/
│
├── app/                          ← API 服务端 (FastAPI)
├── scripts/
│   ├── cli.py                   统一入口 (uv run douyin)
│   ├── download/                下载工具
│   ├── collect/                 数据采集
│   ├── analyze/                 数据分析
│   └── utils/                   工具函数
├── tests/                       测试 (pytest)
├── lib/                         爬虫引擎（上游代码）
├── cookies/                     Cookie 文件 (Netscape 格式)
├── data/
│   ├── downloads/               下载的视频/分析报告
│   ├── comments/                评论数据
│   ├── tracking/                推荐流快照 + 同步日志
│   └── logs/                    爬虫日志
├── .github/workflows/ci.yml     CI 配置
├── config.yaml
├── pyproject.toml
└── README.md
```

---

## 🚀 快速开始

### 1. 安装

```bash
brew install uv
cd social-archive-douyin
uv sync --all-groups
```

### 2. 配置 Cookie

```bash
# 浏览器导出 Cookie (Netscape 格式) → cookies/douyin.txt
uv run douyin cookies apply
```

### 3. 使用

```bash
# 查看所有命令
uv run douyin

# 同步用户视频（预览）
uv run douyin sync -- --dry-run

# 采集推荐流
uv run douyin feed -- --loop

# 检查上游更新
uv run douyin upstream check

# 管理日志
uv run douyin logs
```

### 4. 运行测试

```bash
uv run pytest -v
```

---

## 🎬 功能详情
│   │   └── collect_comments.py   💬 评论采集
│   ├── analyze/                   🔍 数据分析
│   │   ├── analyze_recommend_portrait.py  📡 推荐流画像
│   │   ├── analyze_social_graph.py        🔗 社交关系图谱
│   │   ├── analyze_fan_portrait.py        🎯 粉丝画像
│   │   ├── analyze_identity_mining.py     🕵️ 身份挖掘
│   │   └── analyze_commenter_value.py     🔎 评论者价值
│   ├── utils/                     🔧 工具
│   │   ├── __init__.py
│   │   ├── data_utils.py         数据分析共享工具函数
│   │   ├── apply_cookies.py      Cookie 管理
│   │   └── auto_sync.sh          定时同步脚本
│   ├── com.user.douyin-sync.plist  launchd 定时任务配置
│   └── douyin-feed-observer.user.js  油猴脚本（备选）
│
├── lib/                          ← 爬虫引擎（git clone）
│   └── crawlers/
│       ├── douyin/web/           抖音网页版爬虫
│       ├── tiktok/web/           TikTok 网页版爬虫
│       ├── tiktok/app/           TikTok APP 爬虫
│       ├── bilibili/web/         B站爬虫
│       └── hybrid/              混合解析爬虫
│
├── cookies/                      ← Cookie 文件
│   ├── douyin.txt               抖音 Cookie（Netscape 格式）
│   └── tiktok.txt               TikTok Cookie
│
├── data/                         ← 所有数据
│   ├── downloads/               下载的用户视频/图集 + 分析报告
│   │   └── <用户名>/             按用户分组（自动同步分析报告）
│   │       ├── profile/         🎯 粉丝画像报告
│   │       ├── relations/       🔗 关系拓扑报告
│   │       └── identity/        🕵️ 身份信息报告
│   ├── comments/                评论采集数据
│   │   └── <sec_user_id>/       按用户分组
│   │       ├── comments.json    全量评论数据
│   │       ├── stats.json       采集统计
│   │       ├── relations/       关系拓扑分析结果
│   │       └── profile/         粉丝画像分析结果
│   ├── tracking/                推荐流快照（JSONL 格式）
│   └── temp/                    临时下载缓存
│
├── config.yaml                   服务配置文件
├── download_user_videos.py       一键下载脚本
└── requirements.txt
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# 推荐用 uv（速度比 pip 快 100 倍）
brew install uv    # 如果还没有 uv
cd douyin-crawler-app
uv venv
uv pip install -r requirements.txt
uv pip install httpx==0.27.0 socksio rich gmssl tenacity \
               pycryptodomex lz4 pyfiglet importlib_resources \
               aiofiles qrcode pypng pywebio pywebio-battery \
               browser-cookie3 numpy
```

### 2. 配置 Cookie

Cookie 是爬虫的登录凭证，必须配置：

```bash
# 1. 浏览器登录 https://www.douyin.com
# 2. 用 Cookie-Editor 扩展导出 Netscape 格式
# 3. 覆盖 cookies/douyin.txt
# 4. 应用 Cookie
uv run python scripts/utils/apply_cookies.py
```

### 3. 启动服务

```bash
# 启动 API 服务（提供看板和接口）
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir .

# 启动推荐流采集器（每5分钟采集一次）
uv run python scripts/collect/feed_collector.py --loop --interval 5
```

### 4. 访问

| 地址 | 说明 |
|---|---|
| http://localhost:8000/docs | API 文档（Swagger UI） |
| http://localhost:8000/static/dashboard.html | 📊 推荐流趋势看板 |
| http://localhost:8000/health | 健康检查 |

---

## 🎬 功能详解

### 1. 批量下载用户视频

```bash
# 下载单个用户的所有视频/图集（自动去重）
uv run python download_user_videos.py "https://www.douyin.com/user/<用户ID>"

# 支持短视频和图集，无水印，自动分类保存
```

**下载目录结构：**
```
data/downloads/<用户ID>/
├── _meta.json                          ← 用户信息
├── 001_7625870161799047537_标题.mp4    ← 视频
├── 002_7639283934052336485_标题/       ← 图集文件夹
│   ├── 01.jpg
│   └── 02.jpg
└── ...
```

### 2. 同步更新已下载用户

```bash
# 检查所有用户是否有新视频（预览模式）
uv run python scripts/download/sync_downloads.py --dry-run

# 实际下载新增内容
uv run python scripts/download/sync_downloads.py
```

### 3. 推荐流趋势追踪

采集器会每 5 分钟抓取一次你的抖音推荐页数据，记录话题标签的变化：

```bash
# 启动持续采集
uv run python scripts/collect/feed_collector.py --loop --interval 5
```

数据自动保存到 `data/tracking/feed_YYYYMMDD.jsonl`（JSONL 格式，去重），趋势看板会自动展示。

### 4. 用户画像分析

```bash
# 分析推荐流，反推算法对你的兴趣判断
uv run python scripts/analyze/analyze_recommend_portrait.py --count 100
```

输出示例：
```
🎯 推断的人物画像
   主要兴趣方向: 音乐, 情感, 搞笑
   内容偏好: 偏好短视频（15秒以内）
   内容形式偏好: 视频 80% / 图集 20%
```

### 5. 💬 全量评论采集

采集目标用户所有视频下的全部评论（含子回复、IP 归属地），用于粉丝画像和关系网络分析。

```bash
# 采集指定用户的所有评论（默认全部视频 + 全部评论 + 含子回复）
uv run python scripts/collect/collect_comments.py "https://www.douyin.com/user/<用户ID>"

# 限制范围：只采集最近 10 个视频，每个视频最多 1000 条评论
uv run python scripts/collect/collect_comments.py "https://..." --max-posts 10 --max-comments 1000

# 不采子回复，只采一级评论
uv run python scripts/collect/collect_comments.py "https://..." --no-replies

# 断点续采（继续上次未完成的采集）
uv run python scripts/collect/collect_comments.py "https://..." --resume

# 增量同步（快速检查新评论，无需全量重爬）
uv run python scripts/collect/collect_comments.py "https://..." --sync
```

**输出目录结构：**
```
data/comments/<用户ID>/
├── _meta.json              用户信息 + 采集配置
├── comments.json           全量评论（JSON 数组）
├── stats.json              采集统计摘要
├── relations/              关系拓扑分析结果
│   ├── relation_graph.json  关系图数据（节点+边）
│   ├── communities.json     社群发现结果
│   └── report.txt           文本报告
└── profile/                粉丝画像分析结果
    ├── profile_report.json  结构化画像报告
    └── report.txt           文本报告
```

### 6. 🔗 评论关系拓扑分析

基于采集的评论数据，构建粉丝之间的互动关系网络，发现核心粉丝圈和意见领袖。

```bash
# 分析指定用户的评论关系
uv run python scripts/analyze/analyze_social_graph.py <sec_user_id_or_dir>
```

输出示例：
```
🌟 KOL / 意见领袖: 12 人
  - 用户A (粉丝 12.3万, 评论 45 次)
  - 用户B (粉丝 5.6万, 评论 32 次)
💬 核心粉丝 / 活跃互动者: 89 人
  - 用户C (评论 67 次, 12 个视频)
👥 普通粉丝: 342 人
```

### 7. 🎯 粉丝画像分析（评论版）

从评论数据分析粉丝群体的多维画像。

```bash
# 分析粉丝画像
uv run python scripts/analyze/analyze_fan_portrait.py <sec_user_id_or_dir>
```

### 8. 🕵️ 身份信息挖掘

从评论内容和作品描述中自动提取目标用户的身份线索。

```bash
# 挖掘身份信息
uv run python scripts/analyze/analyze_identity_mining.py <sec_user_id_or_dir>
```

分析维度：
| 维度 | 说明 |
|---|---|
| 📍 **出生地推断** | 基于最多评论者 IP 归属地推测家乡/生活地 |
| 🎓 **教育背景** | 从描述/评论中提取专业、课程、学校线索 |
| 👥 **社交关系** | 分析高频互动者、关系自述（情侣/闺蜜/亲戚） |
| 🏠 **活动地点** | 提取去过/生活过的城市（如春熙路→成都） |
| 👤 **姓名线索** | 从昵称、称呼中挖掘真实姓名可能性 |
| 🐾 **其他特征** | 宠物、健身、音乐、自媒体等兴趣标签 |

### 9. 🔎 评论者价值探测

分析活跃评论者的用户空间，判断是否值得单独爬取。

```bash
# 探测 Top 20 最活跃评论者
uv run python scripts/analyze/analyze_commenter_value.py <sec_user_id_or_dir>

# 探测 Top 50
uv run python scripts/analyze/analyze_commenter_value.py <sec_user_id> --top 50
```

**评分维度**（综合 0-100）：
| 维度 | 权重 | 说明 |
|---|---|---|
| 粉丝数 | 30% | 粉丝越多 → KOL 效应越强 |
| 作品数 | 20% | 作品越多 → 可采集内容越多 |
| 评论互动热度 | 25% | 自己作品的评论活跃度 |
| 在目标用户下活跃度 | 25% | 相关性越高越值得 |

**输出示例：**
```
🌟🌟🌟 高价值 (评分≥70):
  · 山樱念樱 (评分 41.0, 粉丝 102, 作品 83)
🌟🌟 有价值 (评分20-69):
  · 你明哥最帅 (评分 26.0, 粉丝 199, 作品 38)
💤 低价值 (评分<20): 5 人
```

### 10. API 接口
| 维度 | 说明 |
|---|---|
| 🌍 **地域分布** | 基于 IP 归属地的省份/国家分布 |
| ⏰ **活跃时段** | 粉丝评论的时间段偏好（凌晨/早间/深夜等） |
| 👤 **粉丝类型** | KOL / 核心粉丝 / 普通用户 / 新用户比例 |
| 📝 **高频关键词** | 评论中出现最多的词汇 |
| 💖 **情感倾向** | 正面 / 中性 / 负面评论比例 |
| ⭐ **粉丝忠诚度** | 跨视频评论者、高频评论者、铁粉识别 |

### 8. API 接口

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/parser/video?url=...` | GET | 解析单个视频/图集数据 |
| `/api/parser/batch` | POST | 批量解析多个链接 |
| `/api/parser/extract?text=...` | GET | 从分享口令文本中提取链接并解析 |
| `/api/downloader/video?url=...` | GET | 下载无水印视频 |
| `/api/downloader/images?url=...` | GET | 获取图集无水印图片链接 |
| `/api/tracking/feed` | POST | 接收推荐快照（供油猴/采集器推送） |
| `/api/tracking/history` | GET | 历史采集记录 |
| `/api/tracking/stats` | GET | 话题频率趋势数据 |

---

## 🔑 Cookie 管理

Cookie 是项目的核心。推荐使用 `cookies/douyin.txt` 管理，配合 `apply_cookies.py` 应用：

```bash
# 检查当前 Cookie 过期状态
uv run python scripts/utils/apply_cookies.py --check

# 应用 Cookie 到爬虫配置
uv run python scripts/utils/apply_cookies.py
```

**Cookie 过期判断标准：**
- `sessionid` / `sid_tt` — 登录会话，最核心，过期则所有功能失效（约30-60天）
- `__ac_nonce` — 短效防爬令牌（约几小时），过期可自动补充
- `ttwid` — 设备标识，长期有效

---

## 🛡️ 防检测机制

项目通过以下方式绕过抖音风控：

| 机制 | 实现 | 位置 |
|---|---|---|
| A-Bogus 签名 | SM3 哈希 + RC4 加密 | `lib/crawlers/douyin/web/abogus.py` |
| Cookie 认证 | 用户登录凭证 | `cookies/douyin.txt` |
| User-Agent 伪装 | 模拟 Chrome 浏览器 | `config.yaml` |
| msToken 令牌 | 请求抖音令牌服务器获取 | `lib/crawlers/douyin/web/utils.py` |
| 请求频率控制 | `asyncio.sleep()` 主动降速 | 各脚本中 |
| 设备指纹 | 生成伪 `s_v_web_id` | `lib/crawlers/douyin/web/utils.py` |

---

## 📊 数据存储

| 数据类型 | 存储位置 | 格式 |
|---|---|---|
| 用户视频 | `data/downloads/<user_id>/` | MP4 / JPG |
| 用户元数据 | `data/downloads/<user_id>/_meta.json` | JSON |
| 推荐快照 | `data/tracking/feed_YYYYMMDD.jsonl` | JSON Lines |
| 画像分析 | `data/downloads/_profile_analysis/` | JSON |

---

## ⚙️ 技术栈

| 组件 | 技术 |
|---|---|
| 爬虫引擎 | [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) |
| API 框架 | FastAPI + Uvicorn |
| 异步 HTTP | HTTPX |
| 签名算法 | SM3 (gmssl) + RC4 |
| 运行环境 | Python 3.14 / uv |
| 前端看板 | 原生 HTML + JavaScript + Chart.js |

---

## ⚠️ 注意事项

1. **Cookie 有时效性**，过期后需要重新导出并应用
2. **推荐流采集数据越多趋势越准**，建议长期运行
3. **下载频率不宜过高**，建议每次下载间隔 1.5 秒
4. **本工具仅用于个人学习研究**，请勿用于违法用途


## API 示例

### 解析单个视频

```http
GET /api/parser/video?url=https://v.douyin.com/L4FJNR3/&minimal=true
```

### 批量解析

```http
GET /api/parser/batch?urls=https://v.douyin.com/L4FJNR3/&urls=https://www.bilibili.com/video/BV1M1421t7hT
```

### 从文本提取链接并解析

```http
GET /api/parser/extract?text=7.43 pda:/ 让你记住我 https://v.douyin.com/L5pbfdP/
```

### 下载无水印视频

```http
GET /api/downloader/video?url=https://v.douyin.com/L4FJNR3/
```

### 获取图集下载链接

```http
GET /api/downloader/images?url=https://www.douyin.com/note/xxx
```

## 项目结构

```
douyin-crawler-app/
├── app/                       ← API 服务端
│   ├── main.py               FastAPI 入口
│   ├── api/
│   │   ├── router.py         路由聚合
│   │   ├── models.py         响应模型
│   │   └── endpoints/
│   │       ├── parser.py     解析接口
│   │       ├── downloader.py 下载接口
│   │       └── tracking.py   推荐流追踪接口
│   └── static/
│       └── dashboard.html    趋势看板
│
├── scripts/                   ← CLI 工具
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
│       ├── __init__.py
│       ├── data_utils.py
│       ├── apply_cookies.py
│       └── auto_sync.sh
│
├── lib/                       ← 爬虫引擎 (git submodule)
│   ├── crawlers/
│   ├── app/
│   └── config.yaml
│
├── config.yaml
├── download_user_videos.py
├── requirements.txt
└── README.md
```
