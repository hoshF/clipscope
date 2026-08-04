"""Download sync tool - check existing downloads and fetch new videos.

Usage:
    uv run douyin sync                     # Sync all users
    uv run douyin sync --dry-run           # Check only, no download
    uv run douyin sync <dir_name>          # Sync specific user

Description:
    Scans each user directory under downloads/,
    reads _meta.json for user info,
    then compares local files with the remote video list:
      - Downloads only new videos/albums
      - Marks posts deleted/hidden by the author
      - Concurrent downloads with progress persistence
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import time

import aiofiles
import httpx

from clipscope.crawler.douyin.web.web_crawler import DouyinWebCrawler
from clipscope.utils.paths import DOWNLOADS_DIR as DL_DIR
from clipscope.utils.paths import TRACKING_DIR as TRK_DIR

logger = logging.getLogger(__name__)

DOWNLOADS_DIR = str(DL_DIR)
LOG_FILE = str(TRK_DIR / "sync_log.jsonl")
TRACKED_FILE = os.path.join(DL_DIR, ".tracked.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.douyin.com/",
}

DOWNLOAD_CONCURRENCY = 5


def load_tracked() -> dict:
    """Load the centralized user tracking file."""
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "users": {}}


def save_tracked(data: dict) -> None:
    os.makedirs(os.path.dirname(TRACKED_FILE), exist_ok=True)
    with open(TRACKED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_user_to_tracked(sec_user_id: str, nickname: str, url: str, dir_name: str) -> None:
    data = load_tracked()
    data["users"][sec_user_id] = {
        "sec_user_id": sec_user_id,
        "nickname": nickname,
        "url": url,
        "dir_name": dir_name,
        "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "last_synced_at": None,
        "active": True,
    }
    save_tracked(data)


def append_log(entry: dict) -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    entry["_timestamp"] = time.time()
    entry["_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_existing_ids(directory: str) -> dict:
    """Scan local download directory, return index of existing files.

    Returns:
        {aweme_id: (filename, is_image, seq)} dict.
    """
    existing = {}
    if not os.path.exists(directory):
        return existing
    for name in os.listdir(directory):
        if name == "_meta.json":
            continue
        seq_match = re.match(r"(\d+)", name)
        seq = seq_match.group(1) if seq_match else "???"
        match = re.search(r"_(\d{19})_", name)
        aweme_id = match.group(1) if match else None
        if not aweme_id:
            match = re.search(r"(\d{19})", name)
            if match:
                aweme_id = match.group(1)
        if aweme_id:
            is_image = not name.endswith(".mp4") or os.path.isdir(os.path.join(directory, name))
            existing[aweme_id] = (name, is_image, seq)
    return existing


def _load_sync_state(user_dir: str) -> dict[str, set]:
    """Load per-user sync progress state for resumability.

    Returns:
        {"downloaded_ids": set(), "next_seq": int}
    """
    state_path = os.path.join(user_dir, ".sync_state.json")
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
        return {
            "downloaded_ids": set(data.get("downloaded_ids", [])),
            "next_seq": data.get("next_seq", 1),
        }
    return {"downloaded_ids": set(), "next_seq": 1}


def _write_sync_state(user_dir: str, state: dict) -> None:
    state_path = os.path.join(user_dir, ".sync_state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(
            {"downloaded_ids": sorted(state["downloaded_ids"]), "next_seq": state["next_seq"]},
            f,
            ensure_ascii=False,
            indent=2,
        )


def _extract_download_url(item: dict) -> str | None:
    """Extract a playable/downloadable URL from a user-post aweme_list item.

    Uses the internal video.play_addr.url_list from the list API response,
    avoiding a separate per-video API call.
    """
    video = item.get("video", {})
    play_addr = video.get("play_addr", {})
    url_list = play_addr.get("url_list", [])
    if url_list:
        return url_list[0].replace("playwm", "play")
    return None


def _extract_image_urls(item: dict) -> list[str]:
    """Extract image URLs from a user-post aweme_list item."""
    images = item.get("images", [])
    return [img["url_list"][0] for img in images if img.get("url_list")]


async def _download_file(client: httpx.AsyncClient, url: str, filepath: str, max_retries: int = 3) -> bool:
    """Download a single file with streaming and exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            async with client.stream("GET", url, headers=HEADERS) as resp:
                if resp.status_code == 200:
                    async with aiofiles.open(filepath, "wb") as f:
                        async for chunk in resp.aiter_bytes():
                            await f.write(chunk)
                    return True
                elif resp.status_code == 429:
                    if attempt < max_retries - 1:
                        wait = 2 ** (attempt + 2)
                        logger.warning(
                            "Rate limited (429), retrying in %ds (attempt %d/%d)",
                            wait, attempt + 1, max_retries,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error("Gave up after %d retries (429)", max_retries)
                else:
                    logger.warning(
                        "HTTP %d on attempt %d/%d for %s",
                        resp.status_code, attempt + 1, max_retries, url[:60],
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
        except Exception:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.debug("Download attempt %d failed, retrying in %ds", attempt + 1, wait)
                await asyncio.sleep(wait)
            else:
                logger.error("Download failed after %d retries: %s", max_retries, url[:60])
    return False


async def sync_user(meta_path: str, dry_run: bool = False) -> dict:
    """Sync a single user's videos/albums."""
    result = {"new_videos": 0, "new_images": 0, "failed": 0, "skipped": 0, "deleted": 0}

    with open(meta_path) as f:
        meta = json.load(f)

    user_dir = os.path.dirname(meta_path)
    sec_user_id = meta.get("sec_user_id")
    nickname = meta.get("nickname", "")
    user_url = meta.get("url", "")

    if not sec_user_id:
        logger.warning("Missing sec_user_id, skipping")
        return result

    display_name = nickname or sec_user_id[:20]
    existing = get_existing_ids(user_dir)
    existing_ids = set(existing.keys())

    # Fetch remote video list
    crawler = DouyinWebCrawler()
    all_videos = []
    max_cursor = 0
    has_more = True

    while has_more:
        try:
            data = await crawler.fetch_user_post_videos(
                sec_user_id=sec_user_id, max_cursor=max_cursor, count=20
            )
            aweme_list = data.get("aweme_list", [])
            all_videos.extend(aweme_list)
            max_cursor = data.get("max_cursor", 0)
            has_more = data.get("has_more", False)
            if not aweme_list:
                break
        except Exception as e:
            logger.error("%s fetch failed: %s", display_name, e)
            break

    remote_ids = {v.get("aweme_id") for v in all_videos if v.get("aweme_id")}
    deleted_ids = existing_ids - remote_ids
    new_videos = [v for v in all_videos if v.get("aweme_id") not in existing_ids]

    if not new_videos and not deleted_ids:
        logger.info("%s  up to date", display_name)
        append_log({
            "type": "user_sync", "user": display_name, "sec_user_id": sec_user_id,
            "dry_run": dry_run, "local_count": len(existing_ids),
            "remote_count": len(remote_ids), "new_videos": 0,
            "new_images": 0, "deleted": 0, "failed": 0,
        })
        return result

    logger.info("=" * 50)
    logger.info("%s", display_name)
    logger.info("   URL: %s", user_url)
    logger.info("   Dir: %s", user_dir)
    logger.info("   Local: %d -> Remote: %d", len(existing_ids), len(remote_ids))

    if deleted_ids:
        result["deleted"] = len(deleted_ids)
        logger.warning("%d deleted/hidden posts:", len(deleted_ids))
        for did in sorted(deleted_ids, reverse=True):
            info = existing.get(did, ("unknown", False, "???"))
            local_name, is_img, seq = info
            desc_preview = (
                local_name.split("_", 2)[-1].rsplit(".", 1)[0][:40]
                if "_" in local_name
                else local_name
            )
            icon = "[image]" if is_img else "[video]"
            logger.warning("      %s %s_%s  %s", icon, seq, did, desc_preview)

    if not new_videos:
        logger.info("No new posts")
        append_log({
            "type": "user_sync", "user": display_name, "sec_user_id": sec_user_id,
            "dry_run": dry_run, "local_count": len(existing_ids),
            "remote_count": len(remote_ids), "new_videos": 0,
            "new_images": 0, "deleted": result["deleted"], "failed": 0,
        })
        return result

    logger.info("%d new posts", len(new_videos))

    if dry_run:
        for v in new_videos:
            is_img = v.get("aweme_type") in (2, 68)
            icon = "[image]" if is_img else "[video]"
            logger.info("      -> %s %s %s", icon, v.get("aweme_id"), v.get("desc", "")[:40])
        result["new_videos"] = len(new_videos)
        return result

    # Determine starting sequence number
    existing_nums = []
    for name in os.listdir(user_dir):
        if name == "_meta.json":
            continue
        m = re.match(r"(\d+)", name)
        if m:
            existing_nums.append(int(m.group(1)))
    start_num = max(existing_nums) + 1 if existing_nums else 1

    # Load prior sync state for resumption
    state = _load_sync_state(user_dir)
    # Skip items already downloaded in a previous interrupted run
    pending = [(i, v) for i, v in enumerate(new_videos, start_num)
               if v.get("aweme_id") not in state["downloaded_ids"]]
    state["next_seq"] = max(state["next_seq"], start_num)

    if not pending:
        logger.info("All new posts already downloaded (resumed)")
        return result

    # Concurrent downloads
    sem = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    transport = httpx.AsyncHTTPTransport(proxy=None, local_address="0.0.0.0")

    async def download_one(seq: int, item: dict) -> None:
        async with sem:
            aweme_id = item.get("aweme_id", "")
            desc = item.get("desc", "\u65e0\u6807\u9898")[:40]
            aweme_type = item.get("aweme_type")
            is_image = aweme_type in (2, 68)
            ext = ".jpg" if is_image else ".mp4"

            safe_desc = re.sub(r'[\\/:*?"<>|]', "", desc).strip() or "video"
            safe_desc = safe_desc[:50]
            filename = f"{seq:03d}_{aweme_id}_{safe_desc}{ext}"
            filepath = os.path.join(user_dir, filename)

            icon = "[image]" if is_image else "[video]"
            logger.info("[%s] %s %s %s", seq, icon, aweme_id, desc)

            try:
                async with httpx.AsyncClient(timeout=120.0, transport=transport) as client:
                    if is_image:
                        image_urls = _extract_image_urls(item)
                        if image_urls:
                            img_dir = os.path.join(user_dir, f"{seq:03d}_{aweme_id}")
                            os.makedirs(img_dir, exist_ok=True)
                            dl_ok = 0
                            for ii, img_url in enumerate(image_urls):
                                img_path = os.path.join(img_dir, f"{ii + 1:02d}.jpg")
                                if await _download_file(client, img_url, img_path):
                                    dl_ok += 1
                            logger.info("      album (%d/%d)", dl_ok, len(image_urls))
                            result["new_images"] += 1
                        else:
                            logger.error("      No image URLs")
                            result["failed"] += 1
                            return
                    else:
                        download_url = _extract_download_url(item)
                        if not download_url:
                            download_url = (
                                item.get("video", {}).get("play_addr", {})
                                .get("url_list", [None])[0]
                            )
                        if not download_url:
                            logger.error("      No download URL")
                            result["failed"] += 1
                            return

                        ok = await _download_file(client, download_url, filepath)
                        if ok:
                            size_mb = os.path.getsize(filepath) / 1024 / 1024
                            logger.info("      (%.1f MB)", size_mb)
                            result["new_videos"] += 1
                        else:
                            logger.error("      Download failed")
                            result["failed"] += 1
                            return
            except Exception as e:
                logger.error("      %s", e)
                result["failed"] += 1
                return

            # Only persist progress on successful download
            state["downloaded_ids"].add(aweme_id)
            state["next_seq"] = max(state["next_seq"], seq + 1)
            _write_sync_state(user_dir, state)

    await asyncio.gather(*(download_one(seq, item) for seq, item in pending))

    # Clean up sync state after successful completion
    state_path = os.path.join(user_dir, ".sync_state.json")
    if os.path.exists(state_path):
        os.remove(state_path)

    # Update metadata
    total_new = result["new_videos"] + result["new_images"]
    meta["last_synced_at"] = time.time()
    meta["last_sync_new"] = total_new
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    new_downloaded = [
        (seq, item.get("aweme_id"), "image" if item.get("aweme_type") in (2, 68) else "video", item.get("desc", "")[:40])
        for seq, item in pending
        if item.get("aweme_id") in state.get("downloaded_ids", set())
    ]

    log_entry = {
        "type": "user_sync", "user": display_name, "sec_user_id": sec_user_id,
        "dry_run": dry_run, "local_count": len(existing_ids),
        "remote_count": len(remote_ids), "new_videos": result["new_videos"],
        "new_images": result["new_images"], "deleted": result["deleted"],
        "failed": result["failed"],
    }
    if deleted_ids:
        log_entry["deleted_ids"] = sorted(
            f"{existing.get(did, ('???', False, '???'))[2]}_{did}" for did in deleted_ids
        )
    if new_downloaded:
        log_entry["new_ids"] = [f"{seq:03d}_{aweme_id}" for seq, aweme_id, _, _ in new_downloaded]
    append_log(log_entry)

    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="douyin sync", description="Sync downloads for tracked users")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no download")
    parser.add_argument("target", nargs="?", help="Specific user directory name or sec_user_id")
    return parser.parse_args(argv)


async def main(args: argparse.Namespace | None = None):
    if args is None:
        args = parse_args()
    dry_run = args.dry_run

    if not os.path.exists(DOWNLOADS_DIR):
        logger.error("downloads/ directory not found")
        return

    tracked = load_tracked()
    user_metas = []
    for sec_id, info in tracked.get("users", {}).items():
        if not info.get("active", True):
            continue
        user_dir = os.path.join(DOWNLOADS_DIR, info.get("dir_name", ""))
        meta_path = os.path.join(user_dir, "_meta.json")
        if os.path.exists(meta_path):
            user_metas.append(meta_path)

    if not user_metas:
        logger.warning("No tracked users found")
        logger.info("  Use 'uv run douyin track add <url>' to add a user")
        return

    target = args.target

    if target:
        user_metas = [m for m in user_metas if target in m]
        if not user_metas:
            logger.error("No user matching '%s'", target)
            return

    logger.info("=" * 50)
    mode = "preview" if dry_run else "download"
    logger.info("Sync (%s mode)", mode)

    total_new_videos = 0
    total_new_images = 0
    total_failed = 0
    total_deleted = 0

    for meta_path in user_metas:
        result = await sync_user(meta_path, dry_run=dry_run)
        total_new_videos += result["new_videos"]
        total_new_images += result["new_images"]
        total_failed += result["failed"]
        total_deleted += result["deleted"]

    if total_new_videos or total_new_images or total_deleted or total_failed:
        logger.info("=" * 50)
        logger.info("Sync summary")
        if total_new_videos:
            logger.info("   New videos: %d", total_new_videos)
        if total_new_images:
            logger.info("   New albums: %d", total_new_images)
        if total_deleted:
            logger.info("   Deleted: %d", total_deleted)
        if total_failed:
            logger.info("   Failed: %d", total_failed)
        logger.info("=" * 50)

    append_log({
        "type": "sync_summary", "dry_run": dry_run,
        "total_users": len(user_metas), "total_new_videos": total_new_videos,
        "total_new_images": total_new_images, "total_deleted": total_deleted,
        "total_failed": total_failed,
    })


if __name__ == "__main__":
    asyncio.run(main())
