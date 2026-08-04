"""Grab a single Douyin post — download images or video to a target directory.

Usage:
    uv run douyin grab <url> <target_dir>
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys

import aiofiles
import httpx

from clipscope.crawler.hybrid.hybrid_crawler import HybridCrawler

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.douyin.com/",
}

CONCURRENCY = 5


def _remove_quarantine(target_dir: str) -> None:
    if sys.platform != "darwin":
        return
    try:
        subprocess.run(
            ["xattr", "-d", "com.apple.quarantine", f"{target_dir}/*"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


async def _grab_images(result: dict, target_dir: str) -> int:
    images = result.get("images", [])
    if not images:
        return 0

    total = len(images)
    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0

    async def dl_one(i: int, img: dict) -> None:
        nonlocal done
        async with sem:
            url = img.get("url_list", [None])[0]
            if not url:
                return
            path = os.path.join(target_dir, f"{i + 1:03d}.jpg")
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    async with client.stream("GET", url, headers=HEADERS) as resp:
                        if resp.status_code == 200:
                            async with aiofiles.open(path, "wb") as f:
                                async for chunk in resp.aiter_bytes():
                                    await f.write(chunk)
                            done += 1
                            logger.info("[%d/%d] %03d.jpg", done, total, i + 1)
                        else:
                            logger.warning("[%d] HTTP %d", i + 1, resp.status_code)
            except Exception as e:
                logger.warning("[%d] %s", i + 1, e)

    logger.info("Downloading %d images to %s ...", total, target_dir)
    await asyncio.gather(*(dl_one(i, img) for i, img in enumerate(images)))

    _remove_quarantine(target_dir)
    return done


async def _grab_video(result: dict, target_dir: str) -> bool:
    video_data = result.get("video", {})
    play_addr = video_data.get("play_addr", {})
    url_list = play_addr.get("url_list", [])
    if not url_list:
        return False

    url = url_list[0].replace("playwm", "play")
    filename = "video.mp4"
    path = os.path.join(target_dir, filename)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("GET", url, headers=HEADERS) as resp:
                if resp.status_code == 200:
                    async with aiofiles.open(path, "wb") as f:
                        async for chunk in resp.aiter_bytes():
                            await f.write(chunk)
                    size_mb = os.path.getsize(path) / 1024 / 1024
                    logger.info("Saved %s (%.1f MB)", filename, size_mb)
                    _remove_quarantine(target_dir)
                    return True
                else:
                    logger.error("HTTP %d", resp.status_code)
    except Exception as e:
        logger.error("%s", e)
    return False


async def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        logger.error("Usage: uv run douyin grab <url> <target_dir>")
        return

    url = args[0]
    target_dir = os.path.expanduser(args[1])
    os.makedirs(target_dir, exist_ok=True)

    crawler = HybridCrawler()
    try:
        result = await crawler.hybrid_parsing_single_video(url, minimal=False)
    except Exception as e:
        logger.error("Failed to parse URL: %s", e)
        return

    aweme_type = result.get("aweme_type", 0)

    if aweme_type in (2, 68):
        count = await _grab_images(result, target_dir)
        logger.info("Done: %d images saved to %s", count, target_dir)
    elif aweme_type in (0, 4):
        ok = await _grab_video(result, target_dir)
        if not ok:
            logger.error("Failed to download video")
    else:
        logger.error("Unsupported aweme_type: %d", aweme_type)


if __name__ == "__main__":
    asyncio.run(main())
