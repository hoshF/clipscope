"""User tracking — add/list/remove users for sync.

Usage:
    uv run douyin track add <url>
    uv run douyin track list
    uv run douyin track remove <sec_user_id>
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys

from clipscope.crawler.douyin.web.web_crawler import DouyinWebCrawler
from clipscope.utils.paths import DOWNLOADS_DIR as DL_DIR

logger = logging.getLogger(__name__)

DOWNLOADS_DIR = str(DL_DIR)
TRACKED_FILE = os.path.join(DOWNLOADS_DIR, ".tracked.json")


def load_tracked() -> dict:
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "users": {}}


def save_tracked(data: dict) -> None:
    os.makedirs(os.path.dirname(TRACKED_FILE), exist_ok=True)
    with open(TRACKED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def _resolve_user(url: str) -> dict[str, str]:
    """Extract sec_user_id and nickname from a Douyin user URL."""
    crawler = DouyinWebCrawler()

    sec_match = re.search(r"user/([\w.]+)", url)
    if sec_match:
        sec_user_id = sec_match.group(1)
    else:
        sec_user_id = await crawler.get_sec_user_id(url)

    resp = await crawler.handler_user_profile(sec_user_id)
    user = resp.get("user", {})
    nickname = user.get("nickname") or user.get("unique_id") or sec_user_id[:16]

    return {"sec_user_id": sec_user_id, "nickname": nickname, "url": url}


def _sanitize_dirname(nickname: str, sec_user_id: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "", nickname).strip() or "unknown"
    return f"{safe[:30]}_{sec_user_id[:8]}"


def cmd_track_add(url: str) -> None:
    async def _add():
        info = await _resolve_user(url)
        data = load_tracked()

        if info["sec_user_id"] in data["users"]:
            existing = data["users"][info["sec_user_id"]]
            logger.info("User already tracked: %s (%s)", existing["nickname"], info["sec_user_id"])
            return

        dir_name = _sanitize_dirname(info["nickname"], info["sec_user_id"])
        data["users"][info["sec_user_id"]] = {
            "sec_user_id": info["sec_user_id"],
            "nickname": info["nickname"],
            "url": info["url"],
            "dir_name": dir_name,
            "added_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
            "last_synced_at": None,
            "active": True,
        }
        save_tracked(data)
        logger.info("Added: %s (%s)", info["nickname"], info["sec_user_id"])
        logger.info("   Directory: data/downloads/%s", dir_name)

    asyncio.run(_add())


def cmd_track_list() -> None:
    data = load_tracked()
    users = data.get("users", {})

    if not users:
        logger.info("No tracked users. Use 'uv run douyin track add <url>' to add one.")
        return

    logger.info("Tracked users (%d):", len(users))
    for sec_id, info in users.items():
        status = "active" if info.get("active", True) else "disabled"
        nickname = info.get("nickname", "?")
        last_sync = info.get("last_synced_at")
        last_str = __import__("time").strftime("%Y-%m-%d", __import__("time").localtime(last_sync)) if last_sync else "never"
        logger.info("  %s  %s  %s  (last sync: %s)", status, nickname, sec_id[:20], last_str)


def cmd_track_remove(sec_user_id: str) -> None:
    data = load_tracked()
    if sec_user_id in data["users"]:
        nickname = data["users"][sec_user_id].get("nickname", "?")
        data["users"][sec_user_id]["active"] = False
        save_tracked(data)
        logger.info("Deactivated: %s", nickname)
        logger.info("   Downloaded data is preserved. Re-add with 'track add' to re-enable.")
    else:
        logger.warning("User not found: %s", sec_user_id)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        cmd_track_list()
        return

    cmd = args[0]
    if cmd == "add":
        if len(args) < 2:
            logger.error("Usage: uv run douyin track add <url>")
            return
        cmd_track_add(args[1])
    elif cmd == "list":
        cmd_track_list()
    elif cmd == "remove":
        if len(args) < 2:
            logger.error("Usage: uv run douyin track remove <sec_user_id>")
            return
        cmd_track_remove(args[1])
    else:
        logger.error("Unknown track subcommand: %s", cmd)
        logger.info("Available: add <url> | list | remove <sec_user_id>")


if __name__ == "__main__":
    main()
