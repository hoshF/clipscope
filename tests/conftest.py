"""Shared test fixtures for the social-archive-douyin test suite.

Provides realistic sample data that mimics actual Douyin API responses,
used across all test modules to ensure consistency.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ── Sample Comments ──────────────────────────────────────────────


@pytest.fixture
def sample_comments() -> list[dict[str, Any]]:
    """Realistic sample comment data mimicking Douyin API responses.

    Includes a mix of:
    - KOL users (follower_count >= 10k)
    - Core fans (follower_count >= 100)
    - Normal users (follower_count > 0)
    - New users (follower_count = 0)
    - Various IP locations (domestic, overseas, unknown)
    """
    return [
        {
            "aweme_id": "7643177223479316977",
            "user": {
                "uid": "100001",
                "nickname": "科技博主",
                "sec_uid": "MS4wLjABAAAAtest001",
                "follower_count": 50000,
            },
            "ip_label": "北京",
            "position": "北京",
        },
        {
            "aweme_id": "7643177223479316977",
            "user": {
                "uid": "100002",
                "nickname": "美食达人",
                "sec_uid": "MS4wLjABAAAAtest002",
                "follower_count": 25000,
            },
            "ip_label": "上海",
            "position": "上海",
        },
        {
            "aweme_id": "7643177223479316977",
            "user": {
                "uid": "100003",
                "nickname": "普通用户张三",
                "sec_uid": "MS4wLjABAAAAtest003",
                "follower_count": 500,
            },
            "ip_label": "广东",
            "position": "广东",
        },
        {
            "aweme_id": "7643177223479316978",
            "user": {
                "uid": "100003",
                "nickname": "普通用户张三",
                "sec_uid": "MS4wLjABAAAAtest003",
                "follower_count": 500,
            },
            "ip_label": "广东",
            "position": "广东",
        },
        {
            "aweme_id": "7643177223479316977",
            "user": {
                "uid": "100004",
                "nickname": "路人甲",
                "sec_uid": "MS4wLjABAAAAtest004",
                "follower_count": 50,
            },
            "ip_label": "浙江",
        },
        {
            "aweme_id": "7643177223479316977",
            "user": {
                "uid": "100005",
                "nickname": "新用户乙",
                "sec_uid": "MS4wLjABAAAAtest005",
                "follower_count": 0,
            },
            "ip_label": "",
        },
        {
            "aweme_id": "7643177223479316977",
            "user": {
                "uid": "100006",
                "nickname": "海外华人",
                "sec_uid": "MS4wLjABAAAAtest006",
                "follower_count": 300,
            },
            "ip_label": "美国",
            "position": "美国",
        },
        {
            "aweme_id": "7643177223479316977",
            "user": {
                "uid": "100007",
                "nickname": "东京小张",
                "sec_uid": "MS4wLjABAAAAtest007",
                "follower_count": 18000,
            },
            "ip_label": "日本",
        },
    ]


@pytest.fixture
def sample_comments_no_data() -> list[dict[str, Any]]:
    """Edge case: empty input."""
    return []


@pytest.fixture
def sample_comments_malformed() -> list[dict[str, Any]]:
    """Edge case: comments with missing/incomplete fields."""
    return [
        {},  # completely empty
        {"user": None},  # null user
        {"user": {}},  # user with no uid
        {"user": {"uid": ""}},  # empty uid
        {"user": {"uid": "999"}, "ip_label": None},  # null ip_label
    ]


# ── Temporary comment directory ─────────────────────────────────


@pytest.fixture
def temp_comment_dir() -> str:
    """Create a temporary data/comments/ structure with a _meta.json for testing.

    Returns the path to the temp directory, cleans up after test.
    """
    tmpdir = tempfile.mkdtemp(prefix="test_comments_")
    user_dir = os.path.join(tmpdir, "test_user_MS4wLjABAAAAtest")
    os.makedirs(user_dir, exist_ok=True)

    meta = {
        "target_user": {
            "sec_uid": "MS4wLjABAAAAtest_target",
            "nickname": "测试用户",
        },
        "stats": {
            "total_comments": 42,
            "total_videos": 5,
        },
    }
    with open(os.path.join(user_dir, "_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)

    yield tmpdir

    # Cleanup
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)


# ── Helpers ──────────────────────────────────────────────────────


@pytest.fixture
def patch_project_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch PROJECT_ROOT to point to a temp dir for safe file I/O."""
    tmpdir = Path(tempfile.mkdtemp(prefix="test_root_"))
    (tmpdir / "data" / "comments").mkdir(parents=True, exist_ok=True)
    import scripts.utils.data_utils as du

    monkeypatch.setattr(du, "PROJECT_ROOT", str(tmpdir))
    yield
    import shutil

    shutil.rmtree(str(tmpdir), ignore_errors=True)
