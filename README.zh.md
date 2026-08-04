# ClipScope

ClipScope 是一个本地优先的短视频归档工具集，面向抖音、TikTok 和 Bilibili。提供统一 CLI，支持批量下载、推荐流采集、评论爬取和 Cookie 管理。

爬虫引擎来自 [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)，已 vendored 到项目内以保证稳定性。

```bash
uv run douyin <command>
```

## 功能概览

| 功能 | 命令 | 说明 |
| --- | --- | --- |
| 批量同步 | `uv run douyin sync` | 检查已跟踪用户，只下载新增视频或图集 |
| 用户追踪 | `uv run douyin track add/list/remove` | 管理要同步的用户列表 |
| 推荐流追踪 | `uv run douyin feed --loop` | 定时采集推荐流快照 |
| 评论采集 | `uv run douyin comments <url>` | 采集用户作品下的评论和回复 |
| Cookie 管理 | `uv run douyin cookies apply` | 将浏览器导出的 Cookie 应用到爬虫配置 |
| 配置查看 | `uv run douyin config` | 显示配置结构说明 |
| 日志管理 | `uv run douyin logs` | 日志管理（状态 / 清理 / 修剪） |

## 安装

```bash
brew install uv
git clone <repo-url> clipscope
cd clipscope
uv sync
```

Cookie 文件放入 `cookies/`（已 gitignore）。爬虫运行时配置覆盖放入 `crawler_configs/`（已 gitignore）。

## Cookie 配置

1. 在浏览器中登录抖音或 TikTok。
2. 导出 Netscape 格式 Cookie。
3. 保存为 `cookies/douyin.txt` 或 `cookies/tiktok.txt`。
4. 应用配置：

```bash
uv run douyin cookies apply
```

`cookies/` 包含登录凭证，已被 Git 忽略。

## 常用命令

```bash
uv run douyin --help
uv run douyin config

# 同步下载
uv run douyin sync --dry-run
uv run douyin sync

# 用户追踪
uv run douyin track add "https://www.douyin.com/user/<sec_user_id>"
uv run douyin track list
uv run douyin track remove <sec_user_id>

# 推荐流采集
uv run douyin feed --loop --interval 5

# 评论采集
uv run douyin comments "https://www.douyin.com/user/<sec_user_id>"

# Cookie 管理
uv run douyin cookies apply
uv run douyin cookies -- --check
uv run douyin cookies -- --clear

# 日志管理
uv run douyin logs
uv run douyin logs clean
uv run douyin logs prune 30
```

## 数据目录

```text
clipscope/
├── src/clipscope/              CLI、爬虫引擎、采集器、工具函数
│   ├── cli.py
│   ├── crawler/                vendored 爬虫引擎
│   ├── collector/              sync、track、feed、comments、organize
│   └── utils/                  paths、logging、cookies、config
├── scripts/
│   ├── launchd/                macOS 定时任务模板
│   └── utils/auto_sync.sh      自动同步脚本
├── tests/                      pytest 测试
├── config.yaml                 应用配置
├── cookies/                    本地 Cookie 文件（忽略）
├── crawler_configs/            爬虫运行时配置覆盖（忽略）
└── data/                       本地归档数据（忽略）
```

以下目录不提交：

- `cookies/`：浏览器登录 Cookie
- `crawler_configs/`：爬虫配置覆盖（Cookie、token 等）
- `data/downloads/`：下载的视频和图集
- `data/downloads/.tracked.json`：用户追踪清单
- `data/comments/`：采集到的评论数据
- `data/tracking/`：推荐流快照、同步日志、launchd 输出
- `data/logs/`、`data/temp/`：运行日志和临时文件

## 定时同步

launchd 配置使用模板生成，项目移动目录后不需要手动改绝对路径。

```bash
scripts/launchd/install_sync_job.sh
scripts/launchd/uninstall_sync_job.sh
```

dry-run 方式验证自动同步脚本：

```bash
CLIPSCOPE_SYNC_ARGS="--dry-run" scripts/utils/auto_sync.sh
```

## 开发验证

```bash
uv run pytest -q
uv run ruff check .
```
