"""
推荐流自动采集器（定时任务版）
用爬虫定时抓取推荐数据

用法:
    python scripts/feed_collector.py               # 采集一次
    python scripts/feed_collector.py --loop         # 持续采集（每5分钟一次）
    python scripts/feed_collector.py --loop --interval 10  # 每10分钟一次
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
    """加载当天已记录的 aweme_id，避免重复采集。

    Args:
        date_str: 日期字符串，格式 YYYYMMDD。

    Returns:
        当天已有的 aweme_id 集合。
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
    """将推荐流快照追加写入 JSONL 文件。

    每条记录包含采集时间戳和视频列表，追加到当天文件末尾。

    Args:
        items: 视频条目列表，每个条目包含 aweme_id、desc 等字段。
        date_str: 日期字符串，格式 YYYYMMDD。
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
    """从抖音推荐接口获取 Feed 数据。

    使用 DouyinWebCrawler 获取推荐页视频列表，
    每次最多返回 30 条，包含视频元数据和话题标签。

    Returns:
        推荐视频条目列表，每个条目包含 aweme_id、desc、hashtags 等字段。
        网络异常或解析失败时返回空列表。
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
    """采集一次并保存"""
    date_str = datetime.now().strftime("%Y%m%d")
    existing = _load_existing(date_str)
    print("[FeedCollector] 📡 正在采集推荐数据...", end=" ")

    try:
        items = await fetch_feed()
    except Exception as e:
        print(f"❌ 失败: {e}")
        return 0

    # 去重
    new_items = [i for i in items if i["aweme_id"] not in existing]
    if new_items:
        save_snapshot(new_items, date_str)
        print(f"✅ 新增 {len(new_items)} 条 (去重 {len(items) - len(new_items)} 条)")
    else:
        print(f"⏭️ 无新增 (共 {len(items)} 条，均已存在)")

    return len(new_items)


async def main():
    args = sys.argv[1:]
    loop_mode = "--loop" in args

    interval = 5  # 默认5分钟
    for a in args:
        if a.startswith("--interval="):
            interval = int(a.split("=")[1])

    if loop_mode:
        print(f"[FeedCollector] 🔄 持续采集模式，每 {interval} 分钟一次")
        print("[FeedCollector] 按 Ctrl+C 停止\n")
        while True:
            await collect_once()
            print(f"[FeedCollector] 等待 {interval} 分钟后下一次采集...\n")
            await asyncio.sleep(interval * 60)
    else:
        await collect_once()
        print("[FeedCollector] 完成")


if __name__ == "__main__":
    asyncio.run(main())
