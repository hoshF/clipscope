"""Download sync tool - check existing downloads and fetch new videos.

Usage:
    python scripts/sync_downloads.py                    # Sync all users
    python scripts/sync_downloads.py --dry-run           # Check only, no download
    python scripts/sync_downloads.py <dir_name>          # Sync specific user
    python scripts/sync_downloads.py --deleted           # Show deleted posts after sync

Description:
    Scans each user directory under downloads/,
    reads _meta.json for user info,
    then compares local files with the remote video list:
      - Downloads only new videos/albums
      - Marks posts deleted/hidden by the author
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.paths import DOWNLOADS_DIR, TRACKING_DIR, ensure_project_paths

ensure_project_paths()

import aiofiles
import httpx
from crawlers.douyin.web.web_crawler import DouyinWebCrawler
from crawlers.hybrid.hybrid_crawler import HybridCrawler

ROOT = str(PROJECT_ROOT)
DOWNLOADS_DIR = str(DOWNLOADS_DIR)
LOG_FILE = str(TRACKING_DIR / "sync_log.jsonl")


def append_log(entry: dict) -> None:
    """Append a sync log entry to sync_log.jsonl.

    Args:
        entry: Log entry dict; _timestamp and _date fields are auto-added.
    """
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    entry["_timestamp"] = time.time()
    entry["_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_existing_ids(directory: str) -> dict:
    """Scan local download directory, return index of existing files.

    Parses aweme_id (19-digit number) and sequence prefix from filenames.

    Args:
        directory: User download directory path.

    Returns:
        {aweme_id: (filename, is_image, seq)} dict,
        where is_image indicates album, seq is the sequence prefix.
    """
    existing = {}
    if not os.path.exists(directory):
        return existing
    for name in os.listdir(directory):
        if name == "_meta.json":
            continue
        # Extract sequence number
        seq_match = re.match(r"(\d+)", name)
        seq = seq_match.group(1) if seq_match else "???"
        # Video file: 001_7625870161799047537_desc.mp4
        match = re.search(r"_(\d{19})_", name)
        aweme_id = match.group(1) if match else None
        if not aweme_id:
            # Album directory: 002_7639283934052336485_desc/
            match = re.search(r"(\d{19})", name)
            if match:
                aweme_id = match.group(1)
        if aweme_id:
            is_image = not name.endswith(".mp4") or os.path.isdir(os.path.join(directory, name))
            existing[aweme_id] = (name, is_image, seq)
    return existing


async def sync_user(meta_path: str, dry_run: bool = False) -> dict:
    """Sync a single user's videos/albums for updates.

    Compares locally downloaded aweme_ids with the user's latest post list,
    downloads only new content, supports dedup and resume.

    Args:
        meta_path: Path to user's _meta.json file.
        dry_run: If True, only preview changes without downloading.

    Returns:
        Dict with new_videos, new_images, failed, skipped, deleted counts.
    """
    result = {"new_videos": 0, "new_images": 0, "failed": 0, "skipped": 0, "deleted": 0}

    # Read metadata
    with open(meta_path) as f:
        meta = json.load(f)

    user_dir = os.path.dirname(meta_path)
    sec_user_id = meta.get("sec_user_id")
    user_url = meta.get("url", "")
    nickname = meta.get("nickname", "")

    if not sec_user_id:
        print("  ⚠️  Missing sec_user_id, skipping")
        return result

    display_name = nickname or sec_user_id[:20]

    # Get already downloaded IDs
    existing = get_existing_ids(user_dir)
    existing_ids = set(existing.keys())

    # Initialize crawler
    douyin_crawler = DouyinWebCrawler()
    hybrid_crawler = HybridCrawler()

    # Get remote video list (silent)
    all_videos = []
    max_cursor = 0
    has_more = True
    page = 0

    while has_more:
        page += 1
        try:
            data = await douyin_crawler.fetch_user_post_videos(
                sec_user_id=sec_user_id,
                max_cursor=max_cursor,
                count=20,
            )
            aweme_list = data.get("aweme_list", [])
            all_videos.extend(aweme_list)
            max_cursor = data.get("max_cursor", 0)
            has_more = data.get("has_more", False)
            if not aweme_list:
                break
        except Exception as e:
            print(f"   ❌ {display_name} 获取失败: {e}")
            break

    remote_ids = {v.get("aweme_id") for v in all_videos if v.get("aweme_id")}

    # Detect posts deleted/hidden by author
    deleted_ids = existing_ids - remote_ids

    # Find new posts by comparison
    new_videos = [v for v in all_videos if v.get("aweme_id") not in existing_ids]

    # ── 无任何变化：只输出一行简洁信息 ──
    if not new_videos and not deleted_ids:
        print(f"👤 {display_name}  ✅ 已是最新")
        log_entry = {
            "type": "user_sync",
            "user": display_name,
            "sec_user_id": sec_user_id,
            "dry_run": dry_run,
            "local_count": len(existing_ids),
            "remote_count": len(remote_ids),
            "new_videos": 0,
            "new_images": 0,
            "deleted": 0,
            "failed": 0,
        }
        append_log(log_entry)
        return result

    # ── 有变化：打印详细信息 ──
    print(f"\n{'=' * 50}")
    print(f"👤 {display_name}")
    print(f"   URL: {user_url}")
    print(f"   Dir: {user_dir}")
    print(f"   Local: {len(existing_ids)} → Remote: {len(remote_ids)}")

    if deleted_ids:
        result["deleted"] = len(deleted_ids)
        print(f"\n   🗑️  删除/隐藏 {len(deleted_ids)} 个作品:")
        for did in sorted(deleted_ids, reverse=True):
            info = existing.get(did, ("未知", False, "???"))
            local_name, is_img, seq = info
            desc_preview = (
                local_name.split("_", 2)[-1].rsplit(".", 1)[0][:40]
                if "_" in local_name
                else local_name
            )
            icon = "🖼️" if is_img else "🎬"
            print(f"      {icon} {seq}_{did}  {desc_preview}")

    if not new_videos:
        # 只有删除没有新增
        print("\n   ✅ 无新作品")
        log_entry = {
            "type": "user_sync",
            "user": display_name,
            "sec_user_id": sec_user_id,
            "dry_run": dry_run,
            "local_count": len(existing_ids),
            "remote_count": len(remote_ids),
            "new_videos": 0,
            "new_images": 0,
            "deleted": result["deleted"],
            "failed": 0,
        }
        if deleted_ids:
            log_entry["deleted_ids"] = sorted(
                f"{existing.get(did, ('???', False, '???'))[2]}_{did}" for did in deleted_ids
            )
        append_log(log_entry)
        return result

    print(f"\n   🆕 新增 {len(new_videos)} 个作品（刚刚发布）")

    if dry_run:
        for v in new_videos:
            print(f"      → {v.get('aweme_id')} {v.get('desc', '')[:40]}")
        result["new_videos"] = len(new_videos)
        return result

    # 下载新作品
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.douyin.com/",
    }

    # 确定起始编号（接续已有文件）
    existing_nums = []
    for name in os.listdir(user_dir):
        if name == "_meta.json":
            continue
        m = re.match(r"(\d+)", name)
        if m:
            existing_nums.append(int(m.group(1)))
    start_num = max(existing_nums) + 1 if existing_nums else 1

    new_downloaded = []  # 记录本次新增

    for idx, video in enumerate(new_videos, start_num):
        aweme_id = video.get("aweme_id", "")
        desc = video.get("desc", "无标题")[:40]
        aweme_type = video.get("aweme_type")
        is_image = aweme_type in (2, 68)
        ext = ".jpg" if is_image else ".mp4"

        safe_desc = re.sub(r'[\\/:*?"<>|]', "", desc).strip() or "video"
        safe_desc = safe_desc[:50]
        filename = f"{idx:03d}_{aweme_id}_{safe_desc}{ext}"
        filepath = os.path.join(user_dir, filename)

        print(f"\n   🆕 [{idx}] {aweme_id} {'🖼️' if is_image else '🎬'} {desc}")

        try:
            parsed = await hybrid_crawler.hybrid_parsing_single_video(
                url=f"https://www.douyin.com/video/{aweme_id}",
                minimal=True,
            )

            media_type = parsed.get("type", "video")

            if media_type == "image" or is_image:
                image_data = parsed.get("image_data", {})
                image_urls = image_data.get("no_watermark_image_list", [])
                if not image_urls:
                    images = video.get("images", [])
                    image_urls = [
                        img.get("url_list", [None])[0] for img in images if img.get("url_list")
                    ]
                    image_urls = [u for u in image_urls if u]

                if image_urls:
                    img_dir = os.path.join(user_dir, f"{idx:03d}_{aweme_id}")
                    os.makedirs(img_dir, exist_ok=True)
                    transport = httpx.AsyncHTTPTransport(proxy=None, local_address="0.0.0.0")
                    async with httpx.AsyncClient(timeout=120.0, transport=transport) as client:
                        dl_ok = 0
                        for ii, img_url in enumerate(image_urls):
                            img_path = os.path.join(img_dir, f"{ii + 1:02d}.jpg")
                            try:
                                async with client.stream("GET", img_url, headers=headers) as resp:
                                    if resp.status_code == 200:
                                        async with aiofiles.open(img_path, "wb") as f:
                                            async for chunk in resp.aiter_bytes():
                                                await f.write(chunk)
                                        dl_ok += 1
                            except Exception:
                                pass
                    print(f"      ✅ 图集 ({dl_ok}/{len(image_urls)} 张)")
                    result["new_images"] += 1
                    new_downloaded.append((idx, aweme_id, "图集", desc))
                else:
                    print("      ❌ 无图集链接")
                    result["failed"] += 1
            else:
                video_data = parsed.get("video_data", {})
                download_url = (
                    video_data.get("nwm_video_url_HQ")
                    or video_data.get("nwm_video_url")
                    or video_data.get("wm_video_url_HQ")
                    or video_data.get("wm_video_url")
                )
                if not download_url:
                    video_info = video.get("video", {}) or {}
                    play_addr = video_info.get("play_addr", {}) or {}
                    url_list = play_addr.get("url_list", [])
                    download_url = url_list[0] if url_list else None

                if not download_url:
                    print("      ❌ 无下载链接")
                    result["failed"] += 1
                    continue

                transport = httpx.AsyncHTTPTransport(proxy=None, local_address="0.0.0.0")
                async with httpx.AsyncClient(timeout=120.0, transport=transport) as client:
                    try:
                        async with client.stream("GET", download_url, headers=headers) as resp:
                            if resp.status_code == 200:
                                async with aiofiles.open(filepath, "wb") as f:
                                    async for chunk in resp.aiter_bytes():
                                        await f.write(chunk)
                                size_mb = os.path.getsize(filepath) / 1024 / 1024
                                print(f"      ✅ ({size_mb:.1f} MB)")
                                result["new_videos"] += 1
                                new_downloaded.append((idx, aweme_id, "视频", desc))
                            else:
                                print(f"      ❌ HTTP {resp.status_code}")
                                result["failed"] += 1
                    except Exception as e:
                        print(f"      ⚠️ {e}")
                        result["failed"] += 1

            await asyncio.sleep(1.5)

        except Exception as e:
            print(f"      ❌ 解析失败: {e}")
            result["failed"] += 1

    # 更新元数据中的同步时间
    meta["last_synced_at"] = time.time()
    meta["last_sync_new"] = len(new_downloaded)
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # ── 写日志 ──
    log_entry = {
        "type": "user_sync",
        "user": display_name,
        "sec_user_id": sec_user_id,
        "dry_run": dry_run,
        "local_count": len(existing_ids),
        "remote_count": len(remote_ids),
        "new_videos": result["new_videos"],
        "new_images": result["new_images"],
        "deleted": result["deleted"],
        "failed": result["failed"],
    }
    if deleted_ids:
        log_entry["deleted_ids"] = sorted(
            f"{existing.get(did, ('???', False, '???'))[2]}_{did}" for did in deleted_ids
        )
    if new_downloaded:
        log_entry["new_ids"] = [f"{seq:03d}_{aweme_id}" for seq, aweme_id, _, _ in new_downloaded]
    if dry_run and new_videos:
        log_entry["pending_ids"] = [v.get("aweme_id") for v in new_videos]
    append_log(log_entry)

    return result


async def main():
    dry_run = "--dry-run" in sys.argv

    # 扫描 downloads/ 下的用户目录
    if not os.path.exists(DOWNLOADS_DIR):
        print("❌ downloads/ 目录不存在")
        return

    user_metas = []
    for item in os.listdir(DOWNLOADS_DIR):
        meta_path = os.path.join(DOWNLOADS_DIR, item, "_meta.json")
        if os.path.exists(meta_path):
            user_metas.append(meta_path)

    if not user_metas:
        print("⚠️  未找到已下载的用户（缺少 _meta.json）")
        print("   请先用 download_user_videos.py 下载后再同步")
        return

    # 检查是否有指定用户
    target = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            target = arg
            break

    if target:
        user_metas = [m for m in user_metas if target in m]
        if not user_metas:
            print(f"❌ 未找到匹配 '{target}' 的用户")
            return

    if not dry_run:
        print(f"🔄 同步检查 ({'预览模式' if dry_run else '正式下载'})")
    else:
        print(f"{'=' * 50}")
        print(f"🔄 同步检查 ({'预览模式' if dry_run else '正式下载'})")
        print("   使用 --dry-run 仅查看新增，不加 --dry-run 则实际下载")
        print(f"{'=' * 50}")

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

    # 只有有变化时才打印汇总
    if total_new_videos or total_new_images or total_deleted or total_failed:
        print(f"\n{'=' * 50}")
        print("📊 同步汇总")
        if total_new_videos:
            print(f"   🆕 新增视频: {total_new_videos}")
        if total_new_images:
            print(f"   🆕 新增图集: {total_new_images}")
        if total_deleted:
            print(f"   🗑️  作者已删除: {total_deleted}")
        if total_failed:
            print(f"   ❌ 失败: {total_failed}")
        print(f"{'=' * 50}")

    # 写汇总日志
    append_log(
        {
            "type": "sync_summary",
            "dry_run": dry_run,
            "total_users": len(user_metas),
            "total_new_videos": total_new_videos,
            "total_new_images": total_new_images,
            "total_deleted": total_deleted,
            "total_failed": total_failed,
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
