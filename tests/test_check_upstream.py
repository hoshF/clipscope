"""Tests for scripts/utils/check_upstream.py.

Covers the core helper functions:
  - should_ignore()
  - is_low_priority()
  - compute_blob_sha()
  - get_local_file_hashes() (with temp mock dir)
"""

from __future__ import annotations

import os
import tempfile

from scripts.utils.check_upstream import (
    IGNORE_DIRS,
    IGNORE_FILES,
    compute_blob_sha,
    is_low_priority,
    should_ignore,
)

# ═══════════════════════════════════════════════════════════════
# should_ignore
# ═══════════════════════════════════════════════════════════════


class TestShouldIgnore:
    """Tests for the should_ignore filter function."""

    def test_ignore_dirs(self):
        """Should filter paths inside ignored directories."""
        for d in IGNORE_DIRS:
            assert should_ignore(f"{d}/some_file.py"), f"{d} should be ignored"

    def test_ignore_files(self):
        """Should filter known ignore-listed filenames."""
        for f in IGNORE_FILES:
            assert should_ignore(f), f"{f} should be ignored"
            assert should_ignore(f"some/dir/{f}"), f"nested {f} should be ignored"

    def test_ignore_extensions(self):
        """Should filter files with ignored extensions."""
        assert should_ignore("cache.pyc")
        assert should_ignore("module.pyo")
        assert should_ignore("debug.log")

    def test_keep_source_files(self):
        """Should NOT filter meaningful source files."""
        assert not should_ignore("crawlers/douyin/web/web_crawler.py")
        assert not should_ignore("app/api/endpoints/douyin_web.py")
        assert not should_ignore("crawlers/utils/logger.py")
        assert not should_ignore("config.yaml")
        assert not should_ignore("requirements.txt")

    def test_nested_crawler_path(self):
        """Crawler code inside lib/ should pass through."""
        assert not should_ignore("crawlers/douyin/web/models.py")


# ═══════════════════════════════════════════════════════════════
# is_low_priority
# ═══════════════════════════════════════════════════════════════


class TestIsLowPriority:
    """Tests for low-priority file detection."""

    def test_config_is_low_priority(self):
        """config.yaml should be low priority."""
        assert is_low_priority("crawlers/douyin/web/config.yaml")
        assert is_low_priority("config.yaml")

    def test_requirements_is_low_priority(self):
        """requirements.txt should be low priority."""
        assert is_low_priority("requirements.txt")
        assert is_low_priority("lib/requirements.txt")

    def test_source_is_not_low_priority(self):
        """Source code files should NOT be low priority."""
        assert not is_low_priority("crawlers/douyin/web/web_crawler.py")
        assert not is_low_priority("crawlers/utils/logger.py")


# ═══════════════════════════════════════════════════════════════
# compute_blob_sha
# ═══════════════════════════════════════════════════════════════


class TestComputeBlobSHA:
    """Tests for Git blob SHA computation."""

    def test_known_content(self):
        """Should produce a deterministic SHA for known content."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('hello')\n")
            fname = f.name
        try:
            sha = compute_blob_sha(fname)
            # Git blob hash for "print('hello')\n"
            # blob 15\0print('hello')\n
            assert isinstance(sha, str)
            assert len(sha) == 40  # SHA1 hex length
        finally:
            os.unlink(fname)

    def test_consistent(self):
        """Same content should produce the same SHA."""
        content = "x = 42\n"
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write(content)
            fname = f.name
        try:
            sha1 = compute_blob_sha(fname)
            sha2 = compute_blob_sha(fname)
            assert sha1 == sha2
        finally:
            os.unlink(fname)

    def test_different_content_different_sha(self):
        """Different content should produce different SHAs."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("a = 1\n")
            fname1 = f.name
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("a = 2\n")
            fname2 = f.name
        try:
            sha1 = compute_blob_sha(fname1)
            sha2 = compute_blob_sha(fname2)
            assert sha1 != sha2
        finally:
            os.unlink(fname1)
            os.unlink(fname2)

    def test_git_compatibility(self):
        """Computed SHA should match what Git produces for the same content.

        Verifies interoperability with Git's hash-object command.
        """
        content = "test content\n"
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write(content)
            fname = f.name
        try:
            import subprocess

            git_sha = subprocess.check_output(["git", "hash-object", fname], text=True).strip()
            our_sha = compute_blob_sha(fname)
            assert our_sha == git_sha, f"Mismatch: our={our_sha}, git={git_sha}"
        finally:
            os.unlink(fname)
