"""Exit-code tests for the grab command.

main() must return 0 on success and 1 on any failure so scripted callers can
detect problems. Network access is replaced by test doubles.
"""

from __future__ import annotations

import asyncio
import sys

import pytest

from clipscope.collector import grab


class _FakeCrawler:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    async def hybrid_parsing_single_video(self, url, minimal=False):
        if self._error is not None:
            raise self._error
        return self._result


def _prepare(monkeypatch, argv, ytdlp_result=None, crawler=None):
    monkeypatch.setattr(sys, "argv", ["grab", *argv])
    monkeypatch.setattr(grab, "grab_ytdlp", lambda url, target_dir: ytdlp_result)
    if crawler is not None:
        monkeypatch.setattr(grab, "HybridCrawler", lambda: crawler)


def _run_main() -> int:
    return asyncio.run(grab.main())


def test_missing_args_returns_1(monkeypatch):
    _prepare(monkeypatch, ["only-one-arg"])
    assert _run_main() == 1


def test_ytdlp_success_returns_0(monkeypatch, tmp_path):
    _prepare(monkeypatch, ["https://youtu.be/abc", str(tmp_path)], ytdlp_result=True)
    assert _run_main() == 0


def test_ytdlp_failure_returns_1(monkeypatch, tmp_path):
    _prepare(monkeypatch, ["https://youtu.be/abc", str(tmp_path)], ytdlp_result=False)
    assert _run_main() == 1


def test_douyin_video_success_returns_0(monkeypatch, tmp_path):
    crawler = _FakeCrawler(result={"aweme_type": 0})

    async def _video(result, target_dir):
        return True

    _prepare(monkeypatch, ["https://v.douyin.com/x/", str(tmp_path)], crawler=crawler)
    monkeypatch.setattr(grab, "_grab_video", _video)
    assert _run_main() == 0


def test_douyin_video_failure_returns_1(monkeypatch, tmp_path):
    crawler = _FakeCrawler(result={"aweme_type": 0})

    async def _video(result, target_dir):
        return False

    _prepare(monkeypatch, ["https://v.douyin.com/x/", str(tmp_path)], crawler=crawler)
    monkeypatch.setattr(grab, "_grab_video", _video)
    assert _run_main() == 1


def test_douyin_images_success_returns_0(monkeypatch, tmp_path):
    crawler = _FakeCrawler(result={"aweme_type": 2})

    async def _images(result, target_dir):
        return 3

    _prepare(monkeypatch, ["https://v.douyin.com/x/", str(tmp_path)], crawler=crawler)
    monkeypatch.setattr(grab, "_grab_images", _images)
    assert _run_main() == 0


def test_douyin_no_images_returns_1(monkeypatch, tmp_path):
    crawler = _FakeCrawler(result={"aweme_type": 2})

    async def _images(result, target_dir):
        return 0

    _prepare(monkeypatch, ["https://v.douyin.com/x/", str(tmp_path)], crawler=crawler)
    monkeypatch.setattr(grab, "_grab_images", _images)
    assert _run_main() == 1


def test_parse_error_returns_1(monkeypatch, tmp_path):
    crawler = _FakeCrawler(error=ValueError("cannot judge source"))
    _prepare(monkeypatch, ["https://v.douyin.com/x/", str(tmp_path)], crawler=crawler)
    assert _run_main() == 1


def test_unsupported_aweme_type_returns_1(monkeypatch, tmp_path):
    crawler = _FakeCrawler(result={"aweme_type": 999})
    _prepare(monkeypatch, ["https://v.douyin.com/x/", str(tmp_path)], crawler=crawler)
    assert _run_main() == 1


@pytest.mark.parametrize("exit_code", [0, 1])
def test_cli_propagates_exit_code(monkeypatch, exit_code):
    from clipscope import cli

    async def _fake_main():
        return exit_code

    monkeypatch.setattr("clipscope.collector.grab.main", _fake_main)
    with pytest.raises(SystemExit) as excinfo:
        cli.cmd_grab(["https://youtu.be/abc", "/tmp/x"])
    assert excinfo.value.code == exit_code
