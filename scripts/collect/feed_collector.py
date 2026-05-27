"""Recommendation feed auto-collector (scheduled task).

Periodically fetches Douyin's recommendation feed data.

Usage:
    python scripts/feed_collector.py               # Collect once
    python scripts/feed_collector.py --loop         # Continuous (every 5 min)
    python scripts/feed_collector.py --loop --interval 10  # Every 10 min
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime

LIB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib"
)
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from urllib.parse import urlencode

import httpx
from crawlers.douyin.web.endpoints import DouyinAPIEndpoints
from crawlers.douyin.web.models import BaseRequestModel
from crawlers.douyin.web.utils import BogusManager
from crawlers.douyin.web.web_crawler import DouyinWebCrawler

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TRACKING_DIR = os.path.join(ROOT, "data", "tracking")


def _load_existing(date_str: str) -> set:
    """Load existing aweme_ids already recorded for today, avoiding duplicates.

    Args:
        date_str: Date string in YYYYMMDD format.

    Returns:
        Set of aweme_ids already recorded for today.
    """
    path = os.path.join(TRACKING_DIR, f"feed_{date_str}.jsonl")
    if not os.path.exists(path):
        return set()
    seen = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    record = json.loads(line)
                    for item in record.get("items", []):
                        if item.get("aweme_id"):
                            seen.add(item["aweme_id"])
                except Exception:
                    pass
    return seen


def save_snapshot(items: list, date_str: str) -> None:
    """Append a feed snapshot to the JSONL file.

    Each record includes the capture timestamp and video list,
    appended to the end of the day's file.

    Args:
        items: List of video entries, each containing aweme_id, desc, etc.
        date_str: Date string in YYYYMMDD format.
    """
    os.makedirs(TRACKING_DIR, exist_ok=True)
    path = os.path.join(TRACKING_DIR, f"feed_{date_str}.jsonl")
    record = {
        "captured_at": time.time(),
        "captured_at_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(items),
        "items": items,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def fetch_feed() -> list:
    """Fetch feed data from Douyin's recommendation endpoint.

    Uses DouyinWebCrawler to get the recommendation video list.
    Returns up to 30 items per call, including metadata and hashtags.

    Returns:
        List of recommended video entries, each with aweme_id, desc, hashtags, etc.
        Returns empty list on network error or parse failure.
    """
    crawler = DouyinWebCrawler()
    kwargs = await crawler.get_douyin_headers()
    headers = kwargs["headers"]
    proxies = kwargs["proxies"]

    transport = httpx.AsyncHTTPTransport(retries=3)
    async with httpx.AsyncClient(
        headers=headers,
        proxies=proxies,
        timeout=httpx.Timeout(15),
        transport=transport,
    ) as client:
        params = BaseRequestModel().model_dump()
        params["msToken"] = ""
        params["count"] = 30
        params["type"] = 1
        params["source"] = 6

        a_bogus = BogusManager.ab_model_2_endpoint(params, headers.get("User-Agent", ""))
        endpoint = f"{DouyinAPIEndpoints.TAB_FEED}?{urlencode(params)}&a_bogus={a_bogus}"

        resp = await client.get(endpoint)
        data = resp.json()
        aweme_list = data.get("aweme_list", []) or []

        items = []
        for item in aweme_list:
            items.append(
                {
                    "aweme_id": item.get("aweme_id", ""),
                    "desc": (item.get("desc") or "")[:80],
                    "hashtags": [
                        t.get("hashtag_name", "")
                        for t in (item.get("text_extra") or [])
                        if t.get("hashtag_name")
                    ],
                    "author_name": (item.get("author") or {}).get("nickname", ""),
                    "author_id": (item.get("author") or {}).get("unique_id", ""),
                    "digg_count": (item.get("statistics") or {}).get("digg_count", 0),
                    "duration": (item.get("video") or {}).get("duration", 0),
                    "aweme_type": item.get("aweme_type", 0),
                }
            )
        return items


async def collect_once():
    """Collect once and save."""
    date_str = datetime.now().strftime("%Y%m%d")
    existing = _load_existing(date_str)
    print("[FeedCollector] 📡 Collecting feed data...", end=" ")

    try:
        items = await fetch_feed()
    except Exception as e:
        print(f"❌ Failed: {e}")
        return 0

    # Dedup
    new_items = [i for i in items if i["aweme_id"] not in existing]
    if new_items:
        save_snapshot(new_items, date_str)
        print(f"✅ Added {len(new_items)} new (dedup {len(items) - len(new_items)})")
    else:
        print(f"⏭️ No new items ({len(items)} total, all already exist)")

    return len(new_items)


async def main():
    args = sys.argv[1:]
    loop_mode = "--loop" in args

    interval = 5  # 默认5分钟
    for a in args:
        if a.startswith("--interval="):
            interval = int(a.split("=")[1])

    if loop_mode:
        print(f"[FeedCollector] 🔄 Continuous mode, every {interval} min")
        print("[FeedCollector] Press Ctrl+C to stop\n")
        while True:
            await collect_once()
            print(f"[FeedCollector] Waiting {interval} min for next collection...\n")
            await asyncio.sleep(interval * 60)
    else:
        await collect_once()
        print("[FeedCollector] Done")


if __name__ == "__main__":
    asyncio.run(main())
