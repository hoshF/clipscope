# 代码注释规范 · Commenting Style Guide

本项目遵循以下注释规范，确保代码可读性和可维护性。

---

## 1. 📝 Docstring 规范

### 格式要求

统一使用 **Google 风格** docstring。

```python
def function_name(param1: str, param2: int) -> bool:
    """简短描述（一句话，句号结尾）。

    Args:
        param1: 参数1的描述。
        param2: 参数2的描述。

    Returns:
        返回值的描述。

    Raises:
        ValueError: 触发异常的条件描述。
    """
```

### 必须写 docstring 的场景

| 场景 | 要求 |
|---|---|
| 公开函数/方法 | ✅ 必须 |
| 私有函数 `_func` | ✅ 建议 |
| 类定义 `class` | ✅ 必须 |
| 模块/文件头部 | ✅ 必须 |
| FastAPI 路由 | ✅ 必须（同时用于生成 API 文档） |

### 模块头部 docstring

```python
"""
本模块功能的一句话描述。

详细说明（可选）：模块的职责、依赖关系、使用注意事项等。
"""
```

### 类 docstring

```python
class CrawlerClient:
    """爬虫客户端，管理 HTTP 会话和 Cookie。

    负责维护请求会话、自动刷新令牌、提供统一的请求接口。
    所有爬虫操作应通过此客户端进行。

    Attributes:
        session: HTTPX 异步客户端实例。
        base_url: 目标平台的基础 URL。
    """
```

---

## 2. 📌 行内注释规范

### 合适使用行内注释

```python
# ✅ 好的：解释复杂的业务逻辑
# 使用 SM3 哈希对参数排序后生成签名，
# 抖音服务端会用同样的方式校验请求合法性。
sign = generate_abogus(params)

# ✅ 好的：说明一个"为什么"而非"是什么"
time.sleep(1.5)  # 主动降速，避免触发频率限制

# ✅ 好的：标记临时或待完善代码
# TODO: 此处需要处理分页，目前只取第一页
# FIXME: 偶发空指针，需要在调用前检查 None
# HACK: 上游 API 返回的字段名不规范，先 hardcode 映射
```

### 避免的行内注释

```python
# ❌ 坏的：陈述显而易见的事
x = x + 1  # 将 x 加 1

# ❌ 坏的：注释与代码不符（过期注释）
```

### 语言选择

- **docstring**: 保持与项目当前语言一致（中/英皆可，建议与 README 语言对应）
- **行内注释**: 用**中文**（目标用户为中文使用者）
- **关键词标签**: 使用英文（`TODO`, `FIXME`, `HACK`, `NOTE`）

### 可视化分隔线

项目特有的风格，用于区分模块逻辑块：

```python
# ── 分隔线（短） ──
# ═══════════════════════════════════════════════════════════════════ 分隔线（长）
```

分隔线应与上下文空行隔开，不与代码行直接相邻。

---

## 3. 🏷️ 标签注释规范

在注释中使用以下标准标签：

| 标签 | 含义 | 用法 |
|---|---|---|
| `TODO` | 待办事项 | `# TODO: 需要处理边界情况` |
| `FIXME` | 已知问题 | `# FIXME: 此方法在大文件下 OOM` |
| `HACK` | 临时解决方案 | `# HACK: 绕过后端校验，后续需重构` |
| `NOTE` | 值得注意 | `# NOTE: 此 API 有频率限制 10 req/s` |
| `XXX` | 危险/易错 | `# XXX: 此处修改会影响下游所有调用方` |

---

## 4. 🔤 类型注解规范

```python
# ✅ 优先使用 Python 3.10+ 联合类型语法
def get_user(name: str | None) -> User | None: ...

# ✅ 复杂类型使用 typing 模块
from collections.abc import Sequence

def process(items: Sequence[str]) -> list[int]: ...

# ❌ 避免不必要的类型注释
x: int = 5  # 没必要，字面量已表明类型
```

### 何时需要类型注解

| 场景 | 要求 |
|---|---|
| 函数参数 | ✅ 必须 |
| 函数返回值 | ✅ 必须（`-> None` 除外可省略） |
| 模块/类变量 | ✅ 建议 |
| 局部变量 | ⚠️ 复杂类型建议标注 |
| `Any` 类型 | ⚠️ 尽量避免，或用 `# type: ignore[arg-type]` 替代 |

---

## 5. 🔧 工具配置

### Ruff（代码检查 + 格式化）

配置在 `pyproject.toml` 中，集成了：

- `E/W` — pycodestyle 错误/警告
- `F` — pyflakes 逻辑错误
- `I` — isort 导入排序
- `N` — pep8-naming 命名规范
- `D` — pydocstyle docstring 检查（Google 风格）
- `UP` — pyupgrade 现代语法升级
- `RUF100` — 无效的 `# noqa` 检查

```bash
# 检查代码风格
uv run ruff check .

# 自动修复
uv run ruff check --fix .

# 格式化代码
uv run ruff format .
```

### EditorConfig（编辑器统一配置）

配置在 `.editorconfig` 中，确保不同编辑器缩进一致。

---

## 6. ✅ 提交前检查清单

- [ ] `ruff check .` 无错误
- [ ] `ruff format .` 格式正确
- [ ] 新增的公开函数/类有 docstring
- [ ] 类型注解完整
- [ ] 无死代码注释（已废弃的代码块应删除，而非注释掉）
- [ ] `TODO`/`FIXME` 是有意留下的（而非忘记实现的）
