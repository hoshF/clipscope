"""Tests for clipscope/collector/sync.py.

Covers pure helper functions:
  - _extract_download_url()
  - _extract_image_urls()
  - get_existing_ids()
  - _load_sync_state() / _write_sync_state()
"""

from __future__ import annotations

import json
import os

import pytest

from clipscope.collector.sync import (
    _extract_download_url,
    _extract_image_urls,
    _load_sync_state,
    _write_sync_state,
    get_existing_ids,
)


@pytest.fixture
def video_item() -> dict:
    return {
        "aweme_id": "1234567890123456789",
        "desc": "test video",
        "aweme_type": 0,
        "video": {
            "play_addr": {
                "url_list": ["https://example.com/playwm/video.mp4"],
            },
        },
    }


@pytest.fixture
def image_item() -> dict:
    return {
        "aweme_id": "9876543210987654321",
        "desc": "test album",
        "aweme_type": 2,
        "images": [
            {"url_list": ["https://example.com/img1.jpg"]},
            {"url_list": ["https://example.com/img2.jpg"]},
        ],
    }


class TestExtractDownloadUrl:
    def test_normal_video(self, video_item):
        url = _extract_download_url(video_item)
        assert url is not None
        assert "play" in url
        assert "playwm" not in url

    def test_no_video_field(self):
        assert _extract_download_url({}) is None

    def test_no_play_addr(self):
        assert _extract_download_url({"video": {}}) is None

    def test_empty_url_list(self):
        item = {"video": {"play_addr": {"url_list": []}}}
        assert _extract_download_url(item) is None


class TestExtractImageUrls:
    def test_normal_album(self, image_item):
        urls = _extract_image_urls(image_item)
        assert len(urls) == 2
        assert urls[0] == "https://example.com/img1.jpg"

    def test_no_images_field(self):
        assert _extract_image_urls({}) == []

    def test_missing_url_list(self):
        item = {"images": [{"url_list": []}]}
        assert _extract_image_urls(item) == []


class TestGetExistingIds:
    def test_empty_dir(self, tmp_path):
        result = get_existing_ids(str(tmp_path))
        assert result == {}

    def test_nonexistent_dir(self):
        result = get_existing_ids("/tmp/no_such_dir_99999")
        assert result == {}

    def test_skips_meta_json(self, tmp_path):
        (tmp_path / "_meta.json").write_text("{}")
        result = get_existing_ids(str(tmp_path))
        assert "_meta.json" not in str(result)

    def test_video_file(self, tmp_path):
        (tmp_path / "001_1234567890123456789_desc.mp4").write_text("")
        result = get_existing_ids(str(tmp_path))
        assert "1234567890123456789" in result
        _name, is_image, seq = result["1234567890123456789"]
        assert not is_image
        assert seq == "001"

    def test_album_directory(self, tmp_path):
        album = tmp_path / "002_9876543210987654321_album"
        album.mkdir()
        result = get_existing_ids(str(tmp_path))
        assert "9876543210987654321" in result
        _name, is_image, seq = result["9876543210987654321"]
        assert is_image
        assert seq == "002"

    def test_video_without_seq_prefix(self, tmp_path):
        """Filenames without initial 3-digit prefix still match via 19-digit ID."""
        (tmp_path / "video_1234567890123456789.mp4").write_text("")
        result = get_existing_ids(str(tmp_path))
        assert "1234567890123456789" in result


class TestSyncState:
    def test_load_no_file(self, tmp_path):
        state = _load_sync_state(str(tmp_path))
        assert state["downloaded_ids"] == set()
        assert state["next_seq"] == 1

    def test_write_and_load_roundtrip(self, tmp_path):
        state = {"downloaded_ids": {"id1", "id2"}, "next_seq": 5}
        _write_sync_state(str(tmp_path), state)

        loaded = _load_sync_state(str(tmp_path))
        assert loaded["downloaded_ids"] == {"id1", "id2"}
        assert loaded["next_seq"] == 5

    def test_write_serializes_downloaded_ids_as_sorted_list(self, tmp_path):
        state = {"downloaded_ids": {"c", "a", "b"}, "next_seq": 1}
        _write_sync_state(str(tmp_path), state)

        with open(os.path.join(str(tmp_path), ".sync_state.json")) as f:
            data = json.load(f)
        assert data["downloaded_ids"] == ["a", "b", "c"]

    def test_load_partial_file(self, tmp_path):
        state_path = os.path.join(str(tmp_path), ".sync_state.json")
        with open(state_path, "w") as f:
            json.dump({}, f)

        state = _load_sync_state(str(tmp_path))
        assert state["downloaded_ids"] == set()
        assert state["next_seq"] == 1
