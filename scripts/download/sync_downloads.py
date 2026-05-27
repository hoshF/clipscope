"""
下载同步工具 — 检查已有下载目录，自动补全新视频

用法:
    python scripts/sync_downloads.py                    # 同步所有用户
    python scripts/sync_downloads.py --dry-run           # 仅检查，不下载
    python scripts/sync_downloads.py 下载目录名          # 仅同步指定用户
    python scripts/sync_downloads.py --deleted           # 同步后显示已删除的作品
    
说明:
    脚本会扫描 downloads/ 下的每个用户目录，
    读取 _meta.json 获取用户信息，
    然后对比本地已有文件和远程视频列表：
      - 只下载新增的视频/图集
      - 标记已被作者删除/隐藏的作品
"""

import asyncio
import json
import os
import sys
import re
import time

# ── 将 lib 加入 Python 路径 ──
LIB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

import httpx
import aiofiles
from crawlers.douyin.web.web_crawler import DouyinWebCrawler
from crawlers.hybrid.hybrid_crawler import HybridCrawler

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOWNLOADS_DIR = os.path.join(ROOT, "data", "downloads")
LOG_FILE = os.path.join(ROOT, "data", "tracking", "sync_log.jsonl")


def append_log(entry: dict):
    """追加一条日志到 sync_log.jsonl"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    entry["_timestamp"] = time.time()
    entry["_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_existing_ids(directory: str) -> dict:
    """扫描本地目录，返回 {aweme_id: (filename, is_image, seq)} 字典"""
    existing = {}
    if not os.path.exists(directory):
        return existing
    for name in os.listdir(directory):
        if name == "_meta.json":
            continue
        # 提取序号
        seq_match = re.match(r"(\d+)", name)
        seq = seq_match.group(1) if seq_match else "???"
        # 视频文件: 001_7625870161799047537_描述.mp4
        match = re.search(r"_(\d{19})_", name)
        aweme_id = match.group(1) if match else None
        if not aweme_id:
            # 图集目录: 002_7639283934052336485_描述/
            match = re.search(r"(\d{19})", name)
            if match:
                aweme_id = match.group(1)
        if aweme_id:
            is_image = not name.endswith(".mp4") or os.path.isdir(os.path.join(directory, name))
            existing[aweme_id] = (name, is_image, seq)
    return existing


async def sync_user(meta_path: str, dry_run: bool = False) -> dict:
    """同步单个用户，返回统计信息"""
    result = {"new_videos": 0, "new_images": 0, "failed": 0, "skipped": 0, "deleted": 0}

    # 读取元数据
    with open(meta_path, "r") as f:
        meta = json.load(f)

    user_dir = os.path.dirname(meta_path)
    sec_user_id = meta.get("sec_user_id")
    user_url = meta.get("url", "")
    nickname = meta.get("nickname", "")

    if not sec_user_id:
        print(f"  ⚠️  缺少 sec_user_id，跳过")
        return result

    display_name = nickname or sec_user_id[:20]
    print(f"\n{'='*50}")
    print(f"👤 {display_name}")
    print(f"   URL: {user_url}")
    print(f"   目录: {user_dir}")

    # 获取已下载的 ID（返回 dict: {aweme_id: (filename, is_image)}）
    existing = get_existing_ids(user_dir)
    existing_ids = set(existing.keys())
    print(f"   本地已有: {len(existing_ids)} 个作品")

    # 初始化爬虫
    douyin_crawler = DouyinWebCrawler()
    hybrid_crawler = HybridCrawler()

    # 获取远程视频列表
    print(f"   📋 正在获取远程视频列表...")
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
            print(f"   ❌ 获取第 {page} 页失败: {e}")
            break

    remote_ids = {v.get("aweme_id") for v in all_videos if v.get("aweme_id")}
    print(f"   远程共有: {len(remote_ids)} 个作品")

    # ── 检测已被作者删除/隐藏的作品 ──
    deleted_ids = existing_ids - remote_ids
    if deleted_ids:
        print(f"\n   🗑️  以下 {len(deleted_ids)} 个作品已被作者删除/隐藏:")
        for did in sorted(deleted_ids, reverse=True):
            info = existing.get(did, ("未知", False, "???"))
            local_name, is_img, seq = info
            desc_preview = local_name.split("_", 2)[-1].rsplit(".", 1)[0][:40] if "_" in local_name else local_name
            icon = "🖼️" if is_img else "🎬"
            print(f"      {icon} {seq}_{did}  {desc_preview}")
        result["deleted"] = len(deleted_ids)

    # 对比找出新作品
    new_videos = [v for v in all_videos if v.get("aweme_id") not in existing_ids]
    if not new_videos:
        print(f"\n   ✅ 已是最新，无需更新")
        # 即使无更新也写日志
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
                f"{existing.get(did, ('???', False, '???'))[2]}_{did}"
                for did in deleted_ids
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
                    image_urls = [img.get("url_list", [None])[0] for img in images if img.get("url_list")]
                    image_urls = [u for u in image_urls if u]

                if image_urls:
                    img_dir = os.path.join(user_dir, f"{idx:03d}_{aweme_id}")
                    os.makedirs(img_dir, exist_ok=True)
                    transport = httpx.AsyncHTTPTransport(proxy=None, local_address="0.0.0.0")
                    async with httpx.AsyncClient(timeout=120.0, transport=transport) as client:
                        dl_ok = 0
                        for ii, img_url in enumerate(image_urls):
                            img_path = os.path.join(img_dir, f"{ii+1:02d}.jpg")
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
                    print(f"      ❌ 无图集链接")
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
                    print(f"      ❌ 无下载链接")
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
            f"{existing.get(did, ('???', False, '???'))[2]}_{did}"
            for did in deleted_ids
        )
    if new_downloaded:
        log_entry["new_ids"] = [
            f"{seq:03d}_{aweme_id}"
            for seq, aweme_id, _, _ in new_downloaded
        ]
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

    print(f"{'='*50}")
    print(f"🔄 同步检查 ({'预览模式' if dry_run else '正式下载'})")
    if dry_run:
        print(f"   使用 --dry-run 仅查看新增，不加 --dry-run 则实际下载")
    print(f"{'='*50}")

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

    print(f"\n{'='*50}")
    print(f"📊 同步完成")
    if total_new_videos:
        print(f"   🆕 新增视频: {total_new_videos}")
    if total_new_images:
        print(f"   🆕 新增图集: {total_new_images}")
    if total_failed:
        print(f"   ❌ 失败: {total_failed}")
    if total_deleted:
        print(f"   🗑️  作者已删除: {total_deleted}")
    if not total_new_videos and not total_new_images and not total_deleted:
        print(f"   ✅ 全部已是最新，无变化")
    print(f"{'='*50}")

    # 写汇总日志
    append_log({
        "type": "sync_summary",
        "dry_run": dry_run,
        "total_users": len(user_metas),
        "total_new_videos": total_new_videos,
        "total_new_images": total_new_images,
        "total_deleted": total_deleted,
        "total_failed": total_failed,
    })


if __name__ == "__main__":
    asyncio.run(main())
