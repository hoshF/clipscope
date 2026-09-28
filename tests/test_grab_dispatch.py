"""Tests for the yt-dlp backed grab dispatch layer.

Covers pure helpers and the download wrapper's fallback behavior:
  - detect_platform()
  - resolve_cookies() / CookiePlan
  - build_ydl_opts()
  - download()
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from clipscope.collector.downloader import (
    CookiePlan,
    build_ydl_opts,
    detect_platform,
    download,
    grab_ytdlp,
    resolve_cookies,
)


class TestDetectPlatform:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=pslHmoR5-7M",
            "https://youtu.be/pslHmoR5-7M",
            "https://m.youtube.com/watch?v=pslHmoR5-7M",
            "https://music.youtube.com/watch?v=pslHmoR5-7M",
        ],
    )
    def test_youtube_urls(self, url):
        assert detect_platform(url) == "youtube"

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "https://b23.tv/abc123",
            "https://m.bilibili.com/video/BV1xx411c7mD",
        ],
    )
    def test_bilibili_urls(self, url):
        assert detect_platform(url) == "bilibili"

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.douyin.com/video/7300000000000000000",
            "https://v.douyin.com/abcdef/",
            "https://www.tiktok.com/@user/video/7300000000000000000",
            "https://example.com/watch?v=abc",
            "not a url",
        ],
    )
    def test_non_ytdlp_urls(self, url):
        assert detect_platform(url) is None

    def test_does_not_match_lookalike_host(self):
        assert detect_platform("https://notyoutube.com/watch?v=x") is None


class TestResolveCookies:
    def test_file_present_uses_file(self, tmp_path):
        (tmp_path / "youtube.txt").write_text("# Netscape HTTP Cookie File\n")
        plan = resolve_cookies("youtube", cookies_dir=str(tmp_path))
        assert plan.file == str(tmp_path / "youtube.txt")
        assert plan.browser is None

    def test_file_absent_falls_back_to_browser(self, tmp_path):
        plan = resolve_cookies("bilibili", cookies_dir=str(tmp_path))
        assert plan.file is None
        assert plan.browser == "chrome"


class TestBuildYdlOpts:
    def test_merges_best_quality_to_mp4(self, tmp_path):
        opts = build_ydl_opts(CookiePlan(file=None, browser=None), str(tmp_path))
        assert opts["format"] == "bv*+ba/b"
        assert opts["merge_output_format"] == "mp4"
        assert opts["paths"]["home"] == str(tmp_path)

    def test_includes_cookie_file(self, tmp_path):
        opts = build_ydl_opts(CookiePlan(file="/x/y.txt", browser=None), str(tmp_path))
        assert opts["cookiefile"] == "/x/y.txt"
        assert "cookiesfrombrowser" not in opts

    def test_includes_browser_cookies(self, tmp_path):
        opts = build_ydl_opts(CookiePlan(file=None, browser="chrome"), str(tmp_path))
        assert opts["cookiesfrombrowser"] == ("chrome",)


class _FakeYDL:
    """Fake yt-dlp client with scripted cookie-load and download outcomes.

    yt-dlp loads cookies lazily on first access to ``cookiejar``, so cookie
    failures surface there rather than in __init__.
    """

    calls: ClassVar[list[dict]] = []
    cookie_errors: ClassVar[list[Exception | None]] = []
    download_errors: ClassVar[list[Exception | None]] = []

    def __init__(self, opts):
        self.opts = opts
        type(self).calls.append(opts)

    @property
    def cookiejar(self):
        error = type(self).cookie_errors.pop(0)
        if error is not None:
            raise error
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def download(self, urls):
        error = type(self).download_errors.pop(0)
        if error is not None:
            raise error


@pytest.fixture
def fake_ydl():
    _FakeYDL.calls = []
    _FakeYDL.cookie_errors = []
    _FakeYDL.download_errors = []
    return _FakeYDL


class TestDownload:
    def test_success(self, tmp_path, fake_ydl):
        fake_ydl.cookie_errors = [None]
        fake_ydl.download_errors = [None]
        ok = download(
            "https://youtu.be/abc",
            str(tmp_path),
            CookiePlan(file=None, browser=None),
            ydl_factory=fake_ydl,
        )
        assert ok is True
        assert len(fake_ydl.calls) == 1

    def test_download_failure_returns_false(self, tmp_path, fake_ydl):
        fake_ydl.cookie_errors = [None]
        fake_ydl.download_errors = [RuntimeError("page needs to be reloaded")]
        ok = download(
            "https://youtu.be/abc",
            str(tmp_path),
            CookiePlan(file=None, browser=None),
            ydl_factory=fake_ydl,
        )
        assert ok is False

    def test_download_failure_does_not_discard_cookies(self, tmp_path, fake_ydl):
        """A download-time error must not trigger the cookieless retry."""
        fake_ydl.cookie_errors = [None]
        fake_ydl.download_errors = [RuntimeError("Sign in to confirm you're not a bot")]
        ok = download(
            "https://youtu.be/abc",
            str(tmp_path),
            CookiePlan(file=None, browser="chrome"),
            ydl_factory=fake_ydl,
        )
        assert ok is False
        assert len(fake_ydl.calls) == 1

    def test_browser_cookie_load_failure_retries_without_cookies(self, tmp_path, fake_ydl):
        fake_ydl.cookie_errors = [RuntimeError("could not find chrome cookies database"), None]
        fake_ydl.download_errors = [None]
        ok = download(
            "https://youtu.be/abc",
            str(tmp_path),
            CookiePlan(file=None, browser="chrome"),
            ydl_factory=fake_ydl,
        )
        assert ok is True
        assert len(fake_ydl.calls) == 2
        assert "cookiesfrombrowser" in fake_ydl.calls[0]
        assert "cookiesfrombrowser" not in fake_ydl.calls[1]

    def test_cookie_file_load_failure_returns_false(self, tmp_path, fake_ydl):
        fake_ydl.cookie_errors = [RuntimeError("failed to load cookies")]
        ok = download(
            "https://youtu.be/abc",
            str(tmp_path),
            CookiePlan(file="/x/y.txt", browser=None),
            ydl_factory=fake_ydl,
        )
        assert ok is False
        assert len(fake_ydl.calls) == 1


class TestGrabYtdlp:
    def test_unsupported_url_returns_none_without_downloading(self, tmp_path, fake_ydl):
        result = grab_ytdlp(
            "https://www.douyin.com/video/7300000000000000000",
            str(tmp_path),
            ydl_factory=fake_ydl,
        )
        assert result is None
        assert fake_ydl.calls == []

    def test_supported_url_reports_success(self, tmp_path, fake_ydl):
        fake_ydl.cookie_errors = [None]
        fake_ydl.download_errors = [None]
        result = grab_ytdlp("https://youtu.be/abc", str(tmp_path), ydl_factory=fake_ydl)
        assert result is True
        assert len(fake_ydl.calls) == 1

    def test_supported_url_reports_failure(self, tmp_path, fake_ydl):
        fake_ydl.cookie_errors = [None]
        fake_ydl.download_errors = [RuntimeError("boom")]
        result = grab_ytdlp(
            "https://www.bilibili.com/video/BV1xx411c7mD", str(tmp_path), ydl_factory=fake_ydl
        )
        assert result is False
