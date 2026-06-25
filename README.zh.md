# ClipScope

ClipScope 是一个本地优先的短视频归档与分析工具集，面向抖音、TikTok 和 Bilibili。项目基于上游 [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) 爬虫引擎，额外提供统一 CLI、FastAPI 服务、定时同步脚本、评论采集和画像分析能力。

为了兼容现有脚本和定时任务，命令名仍保留为 `douyin`：

```bash
uv run douyin <command>
```

## 功能概览

| 功能 | 命令 | 说明 |
| --- | --- | --- |
| 批量同步 | `uv run douyin sync` | 检查已跟踪用户，只下载新增视频或图集 |
| 推荐流追踪 | `uv run douyin feed -- --loop` | 定时采集推荐流快照 |
| 评论采集 | `uv run douyin comments <url>` | 采集用户作品下的评论和回复 |
| 数据分析 | `uv run douyin analyze ...` | 粉丝画像、关系图谱、身份线索、评论者价值分析 |
| API 服务 | `uv run uvicorn app.main:app` | 提供解析、下载和推荐流数据接口 |
| Cookie 管理 | `uv run douyin cookies apply` | 将浏览器导出的 Cookie 应用到爬虫配置 |
| 上游引擎 | `uv run douyin upstream ...` | 初始化、检查和更新本地 `lib/` 爬虫引擎 |

## 安装

```bash
brew install uv
git clone <repo-url> clipscope
cd clipscope
uv sync --all-extras --all-groups
uv run douyin upstream bootstrap
```

`lib/` 不提交到仓库，它是上游爬虫引擎的本地副本。新环境中用 `uv run douyin upstream bootstrap` 重新初始化即可。

## Cookie 配置

1. 在浏览器中登录抖音或 TikTok。
2. 使用 Cookie 导出工具导出 Netscape 格式 Cookie。
3. 保存为 `cookies/douyin.txt` 或 `cookies/tiktok.txt`。
4. 应用到上游爬虫配置：

```bash
uv run douyin cookies apply
```

`cookies/` 包含登录凭证，已被 Git 忽略，不应提交。

## 常用命令

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

## API 服务

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

常用地址：

| 路径 | 说明 |
| --- | --- |
| `/docs` | Swagger API 文档 |
| `/health` | 健康检查 |
| `/api/parser/video` | 解析单个视频或图集链接 |
| `/api/parser/extract` | 从分享文本中提取链接并解析 |
| `/api/downloader/info` | 返回视频或图集下载信息 |
| `/api/tracking/feed` | 接收推荐流快照 |
| `/static/dashboard.html` | 本地推荐流看板 |

## 数据目录

```text
clipscope/
├── app/                 FastAPI 服务
├── scripts/             CLI、采集、分析和工具脚本
├── tests/               pytest 测试
├── config.yaml          ClipScope 应用配置
├── cookies/             本地 Cookie，忽略
├── data/                本地归档和分析数据，忽略
└── lib/                 上游爬虫引擎，忽略
```

以下目录是本地运行资产，不提交：

- `cookies/`：浏览器登录 Cookie
- `data/downloads/`：下载的视频和图集
- `data/comments/`：采集到的评论数据
- `data/tracking/`：推荐流快照和同步日志
- `data/logs/`、`data/temp/`：运行日志和临时文件
- `lib/`：上游爬虫引擎副本

## 定时同步

launchd 配置使用模板生成，项目移动目录后不需要手动改绝对路径。

```bash
scripts/launchd/install_sync_job.sh
scripts/launchd/uninstall_sync_job.sh
```

如需用 dry-run 方式验证自动同步脚本：

```bash
CLIPSCOPE_SYNC_ARGS="--dry-run" scripts/utils/auto_sync.sh
```

## 开发验证

```bash
uv run pytest -q
uv run ruff check .
```

上游爬虫引擎不进入版本控制。应用上游更新前，先运行 `uv run douyin upstream check` 查看差异。
