"""Rename user directories under data/ to "nickname_sec_user_id[:8]" format.

Supports both data/downloads/ and data/comments/ directory structures.

Usage:
    python -m clipscope.collector.organize                  # Rename downloads (default)
    python -m clipscope.collector.organize --target comments # Rename comments
    python -m clipscope.collector.organize --target all     # Rename both
    python -m clipscope.collector.organize --dry-run        # Preview only
"""

import asyncio
import json
import logging
import os
import re
import shutil
import time

from clipscope.crawler.douyin.web.web_crawler import DouyinWebCrawler
from clipscope.utils.paths import COMMENTS_DIR as CMT_DIR
from clipscope.utils.paths import DOWNLOADS_DIR as DL_DIR

logger = logging.getLogger(__name__)

DOWNLOADS_DIR = str(DL_DIR)
COMMENTS_DIR = str(CMT_DIR)


def sanitize_dirname(name: str, max_len: int = 40) -> str:
    """Sanitize a string for use as a directory name.

    Args:
        name: Raw string to sanitize.
        max_len: Maximum length of the result.

    Returns:
        Sanitized string safe for use as a directory name.
    """
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    name = name.strip(". ")
    if not name:
        name = "unknown"
    return name[:max_len]


async def get_nickname(sec_user_id: str) -> str | None:
    """Fetch user nickname via the crawler API.

    Args:
        sec_user_id: The user's sec_user_id.

    Returns:
        Nickname string, or None if lookup failed.
    """
    try:
        crawler = DouyinWebCrawler()
        resp = await crawler.handler_user_profile(sec_user_id)
        user = resp.get("user", {})
        return user.get("nickname") or user.get("unique_id") or None
    except Exception as e:
        logger.warning("  Failed to fetch user info: %s", e)
        return None


def _get_sec_user_id_from_meta(meta: dict) -> str:
    """Extract sec_user_id from _meta.json, compatible with both downloads and comments formats."""
    return meta.get("sec_user_id", "") or meta.get("target_user", {}).get("sec_uid", "") or ""


def _get_nickname_from_meta(meta: dict) -> str:
    """Extract nickname from _meta.json, compatible with both formats."""
    return meta.get("nickname", "") or meta.get("target_user", {}).get("nickname", "") or ""


async def rename_dir(
    base_dir: str,
    dry_run: bool,
    target_label: str,
    use_api: bool = True,
) -> dict:
    """Rename all user directories under base_dir.

    Args:
        base_dir: Base directory containing user directories.
        dry_run: If True, only preview changes without renaming.
        target_label: Label for UI messages (e.g. "downloads").
        use_api: If True, fetch latest nickname via crawler API (for downloads);
                 if False, read nickname from _meta.json (for comments).

    Returns:
        Dict with count of renamed, dry_run status, etc.
    """
    stats = {"renamed": 0, "skipped": 0, "failed": 0}

    if not os.path.exists(base_dir):
        logger.error("Directory %s/ does not exist", target_label)
        return stats

    # Collect all user directories
    user_dirs = []
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        meta_path = os.path.join(item_path, "_meta.json")
        if os.path.isdir(item_path) and os.path.exists(meta_path):
            user_dirs.append(item)

    if not user_dirs:
        logger.warning("No %s user directories found", target_label)
        return stats

    logger.info("[ %s/ ] Found %d user directories", target_label, len(user_dirs))

    # Detect and merge duplicate directories first
    id_to_dirs = {}
    for d in user_dirs:
        try:
            with open(os.path.join(base_dir, d, "_meta.json")) as f:
                m = json.load(f)
                sid = _get_sec_user_id_from_meta(m)
        except Exception:
            sid = ""
        id_to_dirs.setdefault(sid, []).append(d)

    def count_items(path: str) -> int:
        total = 0
        for _, dirs, files in os.walk(path):
            total += len(dirs) + len(files)
        return total

    def merge_dirs(primary: str, other: str):
        primary_path = os.path.join(base_dir, primary)
        other_path = os.path.join(base_dir, other)
        logger.info("  Merge %s -> %s", other, primary)
        for name in os.listdir(other_path):
            if name == "_meta.json":
                continue
            src = os.path.join(other_path, name)
            dst = os.path.join(primary_path, name)

            if not os.path.exists(dst):
                if not dry_run:
                    shutil.move(src, dst)
                continue

            if os.path.isdir(src) and os.path.isdir(dst):
                for sub in os.listdir(src):
                    ssrc = os.path.join(src, sub)
                    sdst = os.path.join(dst, sub)
                    if not os.path.exists(sdst):
                        if not dry_run:
                            shutil.move(ssrc, sdst)
                    else:
                        suffix = f"_from_{other}_{int(time.time())}"
                        sdst2 = os.path.join(dst, sub + suffix)
                        if not dry_run:
                            shutil.move(ssrc, sdst2)
                try:
                    if not dry_run:
                        os.rmdir(src)
                except Exception:
                    pass
            else:
                suffix = f"_from_{other}_{int(time.time())}"
                base_name, ext = os.path.splitext(name)
                dst2 = os.path.join(primary_path, base_name + suffix + ext)
                if not dry_run:
                    shutil.move(src, dst2)

        primary_meta_path = os.path.join(primary_path, "_meta.json")
        other_meta_path = os.path.join(other_path, "_meta.json")
        try:
            with open(primary_meta_path, encoding="utf-8") as f:
                pmeta = json.load(f)
        except Exception:
            pmeta = {}
        try:
            with open(other_meta_path, encoding="utf-8") as f:
                ometa = json.load(f)
        except Exception:
            ometa = {}

        nh = pmeta.get("nickname_history", []) or []
        onh = ometa.get("nickname_history", []) or []
        for n in onh:
            if n not in nh:
                nh.append(n)
        pmeta["nickname_history"] = nh

        rr = pmeta.get("rename_history", []) or []
        orr = ometa.get("rename_history", []) or []
        rr.extend(orr)
        pmeta["rename_history"] = rr

        if not _get_nickname_from_meta(pmeta) and _get_nickname_from_meta(ometa):
            nick = _get_nickname_from_meta(ometa)
            if use_api:
                pmeta["nickname"] = nick
            else:
                pmeta["target_user"] = pmeta.get("target_user", {})
                pmeta["target_user"]["nickname"] = nick

        if not dry_run:
            with open(primary_meta_path, "w", encoding="utf-8") as f:
                json.dump(pmeta, f, ensure_ascii=False, indent=2)
            try:
                shutil.rmtree(other_path)
            except Exception:
                pass

    for sid, dirs in id_to_dirs.items():
        if not sid or len(dirs) <= 1:
            continue
        logger.warning("Duplicate directories found (sec_user_id=%s): %s", sid, dirs)
        best = None
        best_count = -1
        for d in dirs:
            try:
                c = count_items(os.path.join(base_dir, d))
            except Exception:
                c = 0
            if c > best_count:
                best = d
                best_count = c
        primary = best or dirs[0]
        for d in dirs:
            if d != primary:
                merge_dirs(primary, d)

    # Re-read directory list
    user_dirs = []
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        meta_path = os.path.join(item_path, "_meta.json")
        if os.path.isdir(item_path) and os.path.exists(meta_path):
            user_dirs.append(item)

    for old_name in sorted(user_dirs):
        old_path = os.path.join(base_dir, old_name)
        meta_path = os.path.join(old_path, "_meta.json")

        with open(meta_path) as f:
            meta = json.load(f)

        sec_user_id = _get_sec_user_id_from_meta(meta)
        if not sec_user_id:
            logger.info("  %s: no sec_user_id, skipping", old_name)
            stats["skipped"] += 1
            continue

        existing_nickname = _get_nickname_from_meta(meta)
        nickname_history = meta.get("nickname_history", [])

        logger.info(" [%s] %s", target_label, old_name)

        # Get nickname
        if use_api:
            nickname = await get_nickname(sec_user_id)
        else:
            nickname = existing_nickname

        if not nickname:
            logger.error("  Failed to get nickname")
            stats["failed"] += 1
            continue

        safe_nickname = sanitize_dirname(nickname)
        suffix = sec_user_id[:8]
        new_name = f"{safe_nickname}_{suffix}"

        # Handle nickname change
        old_nicknames_for_dir = []
        if existing_nickname and existing_nickname != nickname:
            old_nicknames_for_dir.append(existing_nickname)
        for old_nick in nickname_history:
            if old_nick != nickname and old_nick not in old_nicknames_for_dir:
                safe_old = sanitize_dirname(old_nick)
                if safe_old and safe_old not in safe_nickname:
                    old_nicknames_for_dir.append(old_nick)

        if old_nicknames_for_dir:
            old_part = "|".join(sanitize_dirname(n) for n in old_nicknames_for_dir)
            new_name = f"{safe_nickname}_({old_part})_{suffix}"

        new_path = os.path.join(base_dir, new_name)

        # Check if already current
        if old_path == new_path or os.path.basename(old_path) == new_name:
            logger.info("  Already up-to-date: %s", nickname)
            stats["skipped"] += 1
            continue

        # Target conflict
        if os.path.exists(new_path):
            logger.warning("  Target exists, appending timestamp")
            new_name = f"{new_name}_{int(time.time())}"
            new_path = os.path.join(base_dir, new_name)

        logger.info("  ->  %s", nickname)

        if dry_run:
            logger.info("    Will rename to: %s", new_name)
            stats["renamed"] += 1
            continue

        try:
            os.rename(old_path, new_path)

            # Update _meta.json
            if existing_nickname and existing_nickname != nickname:
                nickname_history.append(existing_nickname)
            meta["rename_history"] = meta.get("rename_history", [])
            meta["rename_history"].append(
                {
                    "old_dir": old_name,
                    "new_dir": new_name,
                    "nickname": nickname,
                    "renamed_at": time.time(),
                }
            )

            if use_api:
                meta["nickname"] = nickname
                meta["nickname_history"] = nickname_history
            else:
                meta["target_user"] = meta.get("target_user", {})
                meta["target_user"]["nickname"] = nickname

            with open(os.path.join(new_path, "_meta.json"), "w") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            logger.info("    -> %s", new_name)
            stats["renamed"] += 1
        except Exception as e:
            logger.error("    Rename failed: %s", e)
            stats["failed"] += 1

        if use_api:
            await asyncio.sleep(0.5)

    return stats


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Rename user directories to nickname_sec_user_id[:8] format",
    )
    parser.add_argument(
        "--target",
        choices=["downloads", "comments", "all"],
        default="downloads",
        help="Target directory (default: downloads)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no actual rename")

    args = parser.parse_args()
    dry_run = args.dry_run

    targets = []
    if args.target in ("downloads", "all"):
        targets.append(("downloads", DOWNLOADS_DIR, True))
    if args.target in ("comments", "all"):
        targets.append(("comments", COMMENTS_DIR, False))

    total = {"renamed": 0, "skipped": 0, "failed": 0}

    for label, dir_path, use_api in targets:
        stats = await rename_dir(dir_path, dry_run, label, use_api)
        for k in total:
            total[k] += stats[k]

    logger.info("=" * 50)
    if dry_run:
        logger.info("Preview completed (--dry-run, no changes made)")
    else:
        logger.info("All done")
    logger.info("   Success: %d", total["renamed"])
    logger.info("   Skipped: %d", total["skipped"])
    logger.info("   Failed: %d", total["failed"])
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
