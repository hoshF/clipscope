# 重构日志 — ClipScope

## v0.3.0 — 工程改进

### 1. 日志标准化

- 新建 `src/clipscope/utils/logging.py`，包装 Python stdlib `logging`
- 所有模块使用 `logger = logging.getLogger(__name__)`（`clipscope.collector.sync` 等）
- CLI 启动时调用 `setup_logging()`，默认 INFO 级别
- 替换全部 65+ 处 `print()` 为 `logger.info/warning/error()`

**注意：** comments.py 使用 sed 批量转换时丢失了 f-string 前缀，手动修复为 `%s` 格式化日志调用。

### 2. sync.py 测试覆盖

- 新建 `tests/test_sync.py`（17 个测试）
- 覆盖：`_extract_download_url`(4)、`_extract_image_urls`(3)、`get_existing_ids`(6)、sync state 读写(4)
- 全部纯函数单元测试，无需网络

### 3. 下载重试 + 异常修复

- `_download_file()` 增加指数退避重试（HTTP 429: 4s/8s/16s，其他: 1s/2s/4s）
- 重试用 `logger.warning/debug` 记录原因和次数
- 修复 bug：图集无 URL 或下载失败时，不再错误保存 `downloaded_ids` 到断点续传状态（添加 `return`）

### 4. 用户追踪集中化

- 新建 `src/clipscope/collector/track.py`
- `data/downloads/.tracked.json` 集中管理追踪用户
- 新增 CLI 命令：`douyin track add <url>` / `track list` / `track remove <id>`
- `sync.py` 的 `main()` 改为从 `.tracked.json` 读取而非扫描目录

### 5. 爬虫 config 路径分离

- 新建 `src/clipscope/utils/crawler_config.py`：`load_crawler_config(platform, subdir)`
- 加载顺序：`crawler_configs/` (用户 override) → `src/clipscope/crawler/` (默认模板)
- `deep_merge` 递归合并，用户只需指定 Cookie 字段
- 更新 4 个 `web_crawler.py/app_crawler.py`（douyin/tiktok-web/tiktok-app/bilibili）
- `apply_cookies.py` CONFIG_MAP 指向 `crawler_configs/`
- 修复 `update_cookie()` 方法，写入 override 路径
- `.gitignore` 添加 `crawler_configs/`

### 6. CLI argparse 统一

- `sync.py` 和 `feed.py` 添加 `parse_args(argv)` 函数
- sync: `--dry-run`、`[target]` 位置参数
- feed: `--loop`、`--interval`（默认 5 分钟）
- CLI 入口从 `sys.argv` 拼接改为传递解析后的 Namespace

### 验证结果

- ruff: All checks passed
- pytest: 34 passed（17 data_utils + 17 sync）
- CLI: `douyin --help / track list / config` 正常


## v0.2.0 — 结构重构

### 目标

1. **上游 Vendor**：将 `Evil0ctal/Douyin_TikTok_Download_API` 爬虫代码直接纳入项目，不再依赖外部 git clone
2. **精简结构**：移除 FastAPI 服务、分析脚本、上游管理工具，CLI-only
3. **性能优化**：重写 sync 脚本，去冗余 API 调用、添加并发下载和断点续传

### 过程记录

#### 删除清单

- `app/` — FastAPI 服务（只用 CLI）
- `scripts/analyze/` — 5 个分析脚本（2761 行），数据留给 AI 分析
- `scripts/utils/bootstrap_lib.py` + `check_upstream.py` — 上游管理工具
- `lib/` — 外部爬虫引擎 git clone
- `download_user_videos.py` — 与 sync 功能重复
- `tests/test_check_upstream.py` — 对应代码已删除

#### Phase 1-2: Vendor 爬虫代码

**操作：** `lib/crawlers/` → `src/clipscope/crawler/`，29 个文件

**导入修复：** 39 处 `from crawlers.xxx` → `from clipscope.crawler.xxx`，批量 `sed` 替换。

**依赖问题：** 逐次发现缺失依赖（`rich`, `qrcode`, `pypng`, `browser-cookie3`, `importlib_resources`），最终保留上游核心运行时依赖。

#### Phase 3: 迁移应用代码

**核心变更：** 移除所有 `sys.path.insert()` hack。统一使用 `from clipscope.xxx import yyy` 绝对导入。

**paths.py 重构：** 删除 `LIB_DIR`、`ensure_project_paths()`，`PROJECT_ROOT` 改为 `Path(__file__).resolve().parents[3]`。

#### Phase 5: sync.py 重写

| 优化 | 说明 |
|------|------|
| 去 HybridCrawler | 从 `aweme_list` item 直接提取 `video.play_addr.url_list[0]`，省去 `fetch_one_video` 调用 |
| 并发下载 | `asyncio.Semaphore(5)` 控制并发，`asyncio.gather()` 并行执行 |
| 断点续传 | 每下载一个视频写 `.sync_state.json`，崩溃可续传 |
| 去硬延迟 | 移除 `asyncio.sleep(1.5)`，Semaphore 自然控速 |

#### Phase 6: pyproject.toml

- `src/` layout: `[tool.setuptools.packages.find] where = ["src"]`
- Entry point: `douyin = "clipscope.cli:main"`
- 合并 crawler 依赖至 `dependencies`，移除 FastAPI 相关可选依赖
- `ruff` per-file-ignores: vendored 爬虫代码 `ALL` 忽略

### 错误自检

- [x] 所有 `sys.path.insert` 已移除（grep 确认 0 结果）
- [x] 所有 `from scripts.xxx` → `from clipscope.xxx`（grep 确认 0 残留）
- [x] 所有 `from crawlers.xxx` → `from clipscope.crawler.xxx`（grep 确认 0 残留）
- [x] `lib/` 目录已删除，`.gitignore` 移除 `lib/` 规则
- [x] `app/` 目录已删除
- [x] `scripts/analyze/` 已删除
- [x] `__init__.py` 文件已添加到所有包目录
- [x] `pyproject.toml` dependencies 完整（经逐次 `uv sync` 验证）
- [x] CLI 所有命令可正常显示帮助
- [x] `ruff check` 通过
- [x] `pytest` 通过（17/17 → 34/34）

### 最终结构

```
clipscope/
├── src/clipscope/
│   ├── cli.py              ← CLI 入口（sync/track/feed/comments/cookies/config/logs）
│   ├── crawler/            ← vendor 爬虫引擎（douyin/hybrid/bilibili/tiktok）
│   ├── collector/          ← 数据管道（sync/track/feed/comments/organize）
│   └── utils/              ← 工具（paths/data_utils/apply_cookies/logging/crawler_config）
├── scripts/
│   ├── launchd/            ← macOS 定时任务模板
│   └── utils/auto_sync.sh  ← 自动同步脚本
├── tests/                  ← 测试（test_data_utils.py + test_sync.py）
├── config.yaml             ← 项目配置
├── pyproject.toml          ← 包定义 + 依赖
├── cookies/                ← Cookie 文件（gitignored）
└── crawler_configs/        ← 爬虫运行时配置覆盖（gitignored）
```
