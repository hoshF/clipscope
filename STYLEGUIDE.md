# Commenting Style Guide

This project follows these commenting conventions for readability and maintainability.

---

## 1. Docstring Standards

### Format

Use **Google style** docstrings.

```python
def function_name(param1: str, param2: int) -> bool:
    """Brief description (one sentence, ending with period).

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of the return value.

    Raises:
        ValueError: Condition under which this exception is raised.
    """
```

### When docstrings are required

| Scenario | Required |
|---|---|
| Public functions/methods | Yes |
| Private functions `_func` | Recommended |
| Class definitions | Yes |
| Module/file header | Yes |

### Module-level docstring

```python
"""One-line description of module functionality.

Extended description (optional): module responsibilities,
dependencies, usage notes, etc.
"""
```

### Class docstring

```python
class CrawlerClient:
    """Crawler client managing HTTP sessions and cookies.

    Maintains request sessions, auto-refreshes tokens,
    and provides a unified request interface.

    Attributes:
        session: HTTPX async client instance.
        base_url: Base URL of the target platform.
    """
```

---

## 2. Inline Comment Rules

### Good inline comments

```python
# Good: explains complex business logic
# SM3 hash is used to sort params and generate a signature.
# Douyin's server verifies request authenticity the same way.
sign = generate_abogus(params)

# Good: explains "why", not "what"
time.sleep(1.5)  # Rate limit: avoid triggering frequency control

# Good: marks temporary or incomplete code
# TODO: handle pagination - currently only fetches first page
# FIXME: occasional null pointer, check for None before calling
# HACK: upstream API returns inconsistent field names, hardcode mapping for now
```

### Bad inline comments

```python
# Bad: states the obvious
x = x + 1  # Increment x by 1

# Bad: outdated or misleading comment
```

### Language

- **All comments (docstrings + inline)**: **English**
- **Keywords**: English (`TODO`, `FIXME`, `HACK`, `NOTE`, `XXX`)

### Visual separators

Project-specific style for separating logical blocks:

```python
# -- Separator (short) --
# ============================================================
# Separator (long)
# ============================================================
```

Separators should have blank lines above and below.

---

## 3. Tag Comment Standards

| Tag | Meaning | Usage |
|---|---|---|
| `TODO` | To be done | `# TODO: handle edge case for empty input` |
| `FIXME` | Known issue | `# FIXME: this method OOMs on large files` |
| `HACK` | Temporary workaround | `# HACK: bypass server-side validation, needs refactor` |
| `NOTE` | Worth noting | `# NOTE: this API has a 10 req/s rate limit` |
| `XXX` | Dangerous / error-prone | `# XXX: modifying this affects all downstream callers` |

---

## 4. Type Annotation Rules

```python
# Prefer Python 3.10+ union syntax
def get_user(name: str | None) -> User | None: ...

# Use typing module for complex types
from collections.abc import Sequence

def process(items: Sequence[str]) -> list[int]: ...

# Avoid unnecessary type annotations
x: int = 5  # Unnecessary: literal already indicates type
```

### When type annotations are required

| Scenario | Requirement |
|---|---|
| Function parameters | Required |
| Return values | Required (optional for `-> None`) |
| Module/class variables | Recommended |
| Local variables | Recommended for complex types |
| `Any` type | Avoid when possible |

---

## 5. Tool Configuration

### Ruff (linter + formatter)

Configured in `pyproject.toml`:

- `E/W` — pycodestyle errors/warnings
- `F` — pyflakes logic errors
- `I` — isort import sorting
- `N` — pep8-naming conventions
- `D` — pydocstyle docstring checking (Google style)
- `UP` — pyupgrade modern syntax
- `RUF` — ruff-specific rules

**Per-file exceptions:**
- `src/clipscope/crawler/**/*.py` — all rules ignored (vendored upstream code)
- `tests/*.py` — docstring requirements relaxed

```bash
# Check code style
uv run ruff check .

# Auto-fix
uv run ruff check --fix .
```

### EditorConfig

Configured in `.editorconfig` to ensure consistent indentation across editors.

---

## 6. Pre-commit Checklist

- [ ] `ruff check .` passes (no errors)
- [ ] New public functions/classes have Google-style docstrings
- [ ] Type annotations are complete
- [ ] No dead code comments (commented-out code blocks should be deleted)
- [ ] `TODO`/`FIXME` tags are intentional (not forgotten implementations)
- [ ] All comments are in **English**
