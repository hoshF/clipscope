"""Tests for scripts/utils/data_utils.py.

Covers the four public functions:
  - analyze_ip_distribution()
  - analyze_commenter_fan_tiers()
  - analyze_top_commenters()
  - find_comment_dir()
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from scripts.utils import data_utils as du

# ═══════════════════════════════════════════════════════════════
# analyze_ip_distribution
# ═══════════════════════════════════════════════════════════════


class TestAnalyzeIPDistribution:
    """Tests for IP location distribution analysis."""

    def test_basic_distribution(self, sample_comments):
        """Should correctly count IP locations and classify domestic/overseas."""
        result = du.analyze_ip_distribution(sample_comments)

        assert result["total_with_ip"] == 8  # 8 unique IPs, empty→"未知"
        assert "北京" in result["domestic"]
        assert "上海" in result["domestic"]
        assert "广东" in result["domestic"]
        assert "浙江" in result["domestic"]
        assert "美国" in result["overseas"]
        assert "日本" in result["overseas"]
        assert result["unknown_count"] == 1  # empty ip_label falls back to "未知"

    def test_unknown_ip_handling(self, sample_comments_malformed):
        """Should handle missing/null IP labels gracefully."""
        result = du.analyze_ip_distribution(sample_comments_malformed)
        # All should be counted as unknown or empty
        assert result["total_with_ip"] > 0

    def test_empty_input(self, sample_comments_no_data):
        """Should handle empty list without crashing."""
        result = du.analyze_ip_distribution(sample_comments_no_data)
        # total defaults to 1 (division safety), but actual count is 0
        assert result["total_with_ip"] == 1
        assert result["domestic"] == {}
        assert result["overseas"] == {}
        assert result["inferred_home"] is None

    def test_top_regions(self, sample_comments):
        """Should return top regions sorted by frequency."""
        result = du.analyze_ip_distribution(sample_comments)
        assert len(result["top_regions"]) > 0
        # Beijing appears once, should be in top regions
        assert "北京" in result["top_regions"]

    def test_inferred_home(self, sample_comments):
        """Should infer the most common IP location as home."""
        result = du.analyze_ip_distribution(sample_comments)
        # Guangdong appears twice (user 100003 comments twice), most frequent
        assert result["inferred_home"] == "广东"
        assert result["inferred_confidence"] > 0


# ═══════════════════════════════════════════════════════════════
# analyze_commenter_fan_tiers
# ═══════════════════════════════════════════════════════════════


class TestAnalyzeCommenterFanTiers:
    """Tests for commenter fan tier classification."""

    def test_tier_classification(self, sample_comments):
        """Should correctly classify users into KOL/core/normal/new tiers."""
        result = du.analyze_commenter_fan_tiers(sample_comments)

        assert result["total_commenters"] == 7

        # KOLs: follower_count >= 10000
        assert result["kols"]["count"] == 3  # 科技博主(50k), 美食达人(25k), 东京小张(18k)
        assert result["kols"]["percentage"] == pytest.approx(42.9, rel=0.1)

        # Core fans: follower_count >= 100
        assert result["core_fans"]["count"] == 2  # 普通用户张三(500), 海外华人(300)

        # Normal: follower_count > 0
        assert result["normal_fans"]["count"] == 1  # 路人甲(50)

        # New: follower_count == 0
        assert result["new_users"]["count"] == 1  # 新用户乙(0)

    def test_kol_list_sorted_by_followers(self, sample_comments):
        """KOL list should be sorted by follower_count descending."""
        result = du.analyze_commenter_fan_tiers(sample_comments)
        kols = result["kols"]["list"]
        for i in range(len(kols) - 1):
            assert kols[i]["follower_count"] >= kols[i + 1]["follower_count"]

    def test_empty_input(self, sample_comments_no_data):
        """Should handle empty list."""
        result = du.analyze_commenter_fan_tiers(sample_comments_no_data)
        # total defaults to 1 (division safety), but counts are all 0
        assert result["total_commenters"] == 1
        assert result["kols"]["count"] == 0
        assert result["core_fans"]["count"] == 0

    def test_malformed_input(self, sample_comments_malformed):
        """Should skip malformed entries without crashing."""
        result = du.analyze_commenter_fan_tiers(sample_comments_malformed)
        # Only the entry with uid "999" should be counted
        assert result["total_commenters"] == 1


# ═══════════════════════════════════════════════════════════════
# analyze_top_commenters
# ═══════════════════════════════════════════════════════════════


class TestAnalyzeTopCommenters:
    """Tests for top commenters ranking."""

    def test_ranking(self, sample_comments):
        """Should rank commenters by comment_count descending."""
        result = du.analyze_top_commenters(sample_comments, top_n=10)

        assert len(result) == 7

        # 普通用户张三 appears twice (comment_count = 2)
        top = result[0]
        assert top["nickname"] == "普通用户张三"
        assert top["comment_count"] == 2
        assert top["video_count"] == 2  # comments on 2 different videos

    def test_top_n_limit(self, sample_comments):
        """Should respect top_n parameter."""
        result = du.analyze_top_commenters(sample_comments, top_n=3)
        assert len(result) == 3

    def test_video_count_dedup(self, sample_comments):
        """Should deduplicate video IDs per commenter."""
        result = du.analyze_top_commenters(sample_comments, top_n=10)
        # 普通用户张三 commented on 2 different videos
        zhang = next(r for r in result if r["nickname"] == "普通用户张三")
        assert zhang["video_count"] == 2

    def test_empty_input(self, sample_comments_no_data):
        """Should return empty list."""
        result = du.analyze_top_commenters(sample_comments_no_data)
        assert result == []

    def test_default_top_n(self, sample_comments):
        """Should default to top_n=50."""
        result = du.analyze_top_commenters(sample_comments)
        assert len(result) == 7  # less than 50, so all items
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════
# find_comment_dir
# ═══════════════════════════════════════════════════════════════


class TestFindCommentDir:
    """Tests for finding comment directories."""

    def test_find_existing(self, monkeypatch):
        """Should find a matching comment directory by sec_uid."""
        # Build a proper data/comments/ structure under a temp PROJECT_ROOT
        tmpdir = tempfile.mkdtemp(prefix="test_comments_")
        comments_dir = os.path.join(tmpdir, "data", "comments")
        user_dir = os.path.join(comments_dir, "test_user_MS4wLjABAAAAtest")
        os.makedirs(user_dir, exist_ok=True)
        meta = {
            "target_user": {
                "sec_uid": "MS4wLjABAAAAtest_target",
                "nickname": "测试用户",
            },
        }
        with open(os.path.join(user_dir, "_meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)

        monkeypatch.setattr(du, "PROJECT_ROOT", tmpdir)
        result = du.find_comment_dir("MS4wLjABAAAAtest_target")

        assert result is not None
        assert "test_user_MS4wLjABAAAAtest" in result

        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_not_found(self, temp_comment_dir, monkeypatch):
        """Should return None when no directory matches."""
        monkeypatch.setattr(du, "PROJECT_ROOT", os.path.dirname(temp_comment_dir))
        result = du.find_comment_dir("nonexistent_sec_uid")
        assert result is None

    def test_no_comments_dir(self, monkeypatch, tmp_path):
        """Should return None when data/comments/ doesn't exist."""
        monkeypatch.setattr(du, "PROJECT_ROOT", str(tmp_path))
        result = du.find_comment_dir("anything")
        assert result is None
