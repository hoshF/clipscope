"""Recommendation feed data collection API.

Receives Douyin feed data pushed by Tampermonkey scripts.
"""

import json
import os
import time
from datetime import datetime

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.api.models import ResponseModel
from scripts.utils.paths import TRACKING_DIR

router = APIRouter()

TRACKING_DIR = str(TRACKING_DIR)

_dedup_cache: dict[str, set] = {}  # {date_str: set(aweme_ids)}
_DEDUP_MAX_DAYS = 7


def _load_seen_ids(date_str: str) -> set:
    """Load previously recorded aweme_ids for a given date, with cache.

    Cache persists for up to _DEDUP_MAX_DAYS to avoid repeated file reads.

    Args:
        date_str: Date string in YYYYMMDD format.

    Returns:
        Set of aweme_ids already recorded for that date.
    """
    if date_str in _dedup_cache:
        return _dedup_cache[date_str]

    seen = set()
    day_file = os.path.join(TRACKING_DIR, f"feed_{date_str}.jsonl")
    if os.path.exists(day_file):
        with open(day_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        for item in record.get("items", []):
                            if item.get("aweme_id"):
                                seen.add(item["aweme_id"])
                    except json.JSONDecodeError:
                        pass

    _dedup_cache[date_str] = seen
    if len(_dedup_cache) > _DEDUP_MAX_DAYS:
        oldest = min(_dedup_cache.keys())
        del _dedup_cache[oldest]

    return seen


def _prune_old_cache() -> None:
    """Remove expired (non-today) entries from _dedup_cache."""
    today = datetime.now().strftime("%Y%m%d")
    for date_str in list(_dedup_cache.keys()):
        if date_str < today:
            del _dedup_cache[date_str]


def _ensure_dir():
    os.makedirs(TRACKING_DIR, exist_ok=True)


class FeedSnapshotItem(BaseModel):
    aweme_id: str
    desc: str = ""
    hashtags: list[str] = []
    author_name: str = ""
    author_id: str = ""
    digg_count: int = 0
    duration: int = 0
    aweme_type: int = 0


class FeedSnapshot(BaseModel):
    items: list[FeedSnapshotItem]
    captured_at: float  # timestamp


@router.post("/feed", summary="Receive feed snapshot (auto-dedup)")
async def receive_feed_snapshot(snapshot: FeedSnapshot, request: Request):
    """Receive a feed snapshot pushed by the Tampermonkey script (auto-dedup)."""
    _ensure_dir()
    ts = snapshot.captured_at or time.time()
    date_str = datetime.fromtimestamp(ts).strftime("%Y%m%d")
    day_file = os.path.join(TRACKING_DIR, f"feed_{date_str}.jsonl")

    # Load existing IDs + extract all IDs from incoming data
    seen_ids = _load_seen_ids(date_str)
    all_ids_incoming = {item.aweme_id for item in snapshot.items if item.aweme_id}

    # Filter to truly new items
    new_items = [item for item in snapshot.items if item.aweme_id not in seen_ids]

    if not new_items:
        return ResponseModel(
            code=200,
            message=f"No new videos ({len(snapshot.items)} total, all already exist)",
            data={"new_count": 0, "total_today": len(seen_ids)},
        )

    # Write new data
    record = {
        "captured_at": ts,
        "captured_at_str": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(new_items),
        "all_count": len(snapshot.items),
        "items": [item.model_dump() for item in new_items],
    }

    with open(day_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Update cache
    _dedup_cache[date_str] = seen_ids | all_ids_incoming

    return ResponseModel(
        code=200,
        message=f"Added {len(new_items)} new items (dedup {len(snapshot.items) - len(new_items)} duplicates)",
        data={"new_count": len(new_items), "total_today": len(_dedup_cache[date_str])},
    )


@router.get("/history", summary="Get history summary (dedup stats)")
async def get_tracking_history(request: Request):
    """Return all historical snapshots' dates and counts (dedup by aweme_id)."""
    _ensure_dir()
    files = sorted(
        [f for f in os.listdir(TRACKING_DIR) if f.startswith("feed_") and f.endswith(".jsonl")]
    )

    history = []
    for fname in files:
        fpath = os.path.join(TRACKING_DIR, fname)
        total_snapshots = 0
        total_raw = 0
        unique_ids = set()
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if line:
                    total_snapshots += 1
                    try:
                        record = json.loads(line)
                        for item in record.get("items", []):
                            total_raw += 1
                            if item.get("aweme_id"):
                                unique_ids.add(item["aweme_id"])
                    except json.JSONDecodeError:
                        pass

        date_str = fname.replace("feed_", "").replace(".jsonl", "")
        history.append(
            {
                "date": date_str,
                "snapshots": total_snapshots,
                "raw_items": total_raw,
                "unique_items": len(unique_ids),
                "file": fname,
            }
        )

    return ResponseModel(code=200, data=history)


@router.get("/detail", summary="Get detailed data for a date (dedup)")
async def get_tracking_detail(
    request: Request,
    date: str = Query(..., example="20260526", description="日期 YYYYMMDD"),
):
    """Get all snapshot details for a specific date (dedup by aweme_id)."""
    _ensure_dir()
    fpath = os.path.join(TRACKING_DIR, f"feed_{date}.jsonl")
    if not os.path.exists(fpath):
        return ResponseModel(code=404, message="No data for this date")

    seen_ids = set()
    snapshots = []
    with open(fpath) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    record = json.loads(line)
                    # Dedup: keep unique items
                    deduped_items = []
                    for item in record.get("items", []):
                        aid = item.get("aweme_id")
                        if aid and aid not in seen_ids:
                            seen_ids.add(aid)
                            deduped_items.append(item)
                    if deduped_items:
                        record["items"] = deduped_items
                        record["count"] = len(deduped_items)
                        snapshots.append(record)
                except json.JSONDecodeError:
                    pass

    return ResponseModel(
        code=200,
        data={
            "date": date,
            "unique_items": len(seen_ids),
            "snapshots": snapshots,
        },
    )


@router.get("/stats", summary="Get trend statistics (dedup)")
async def get_tracking_stats(request: Request):
    """Calculate hashtag/category trends over time (dedup by aweme_id)."""
    _ensure_dir()
    files = sorted(
        [f for f in os.listdir(TRACKING_DIR) if f.startswith("feed_") and f.endswith(".jsonl")]
    )

    if not files:
        return ResponseModel(code=200, data={"trends": [], "message": "No data yet"})

    # Aggregate hashtag frequency by day
    daily_tags = {}

    for fname in files:
        date_str = fname.replace("feed_", "").replace(".jsonl", "")
        fpath = os.path.join(TRACKING_DIR, fname)

        tags_counter = {}
        with open(fpath) as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    for item in record.get("items", []):
                        for tag in item.get("hashtags", []):
                            tags_counter[tag] = tags_counter.get(tag, 0) + 1

        daily_tags[date_str] = tags_counter

    # 取 Top 10 话题
    all_tags = set()
    for tags in daily_tags.values():
        all_tags.update(tags.keys())

    top_tags = sorted(
        all_tags, key=lambda t: sum(d.get(t, 0) for d in daily_tags.values()), reverse=True
    )[:15]

    # 生成趋势数据
    trend_dates = sorted(daily_tags.keys())
    trends = []
    for tag in top_tags:
        points = []
        for d in trend_dates:
            points.append(
                {
                    "date": d,
                    "count": daily_tags[d].get(tag, 0),
                }
            )
        trends.append({"tag": tag, "points": points})

    return ResponseModel(
        code=200,
        data={
            "trend_dates": trend_dates,
            "trends": trends,
        },
    )
