"""
推荐流数据采集 API
供油猴脚本推送抖音推荐页数据
"""

import json
import os
import time
from datetime import datetime

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.api.models import ResponseModel

router = APIRouter()

TRACKING_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data",
    "tracking",
)

# ── 内存去重缓存 ──
# 记录每个日期的文件已有哪些 aweme_id，避免重复读取文件
_dedup_cache = {}  # {date_str: set(aweme_ids)}
_DEDUP_MAX_DAYS = 7  # 最多缓存7天


def _load_seen_ids(date_str: str) -> set:
    """加载某天已记录的 aweme_id，带内存缓存。

    缓存最多保留 _DEDUP_MAX_DAYS 天，避免重复读取文件。

    Args:
        date_str: 日期字符串，格式 YYYYMMDD。

    Returns:
        该日期已记录的 aweme_id 集合。
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

    # 缓存并限制缓存大小
    _dedup_cache[date_str] = seen
    if len(_dedup_cache) > _DEDUP_MAX_DAYS:
        oldest = min(_dedup_cache.keys())
        del _dedup_cache[oldest]

    return seen


def _prune_old_cache() -> None:
    """清理 _dedup_cache 中过期（非今天）的缓存条目。"""
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


@router.post("/feed", summary="接收推荐快照（自动去重）")
async def receive_feed_snapshot(snapshot: FeedSnapshot, request: Request):
    """油猴脚本推送的推荐页快照（自动过滤已存在的视频 ID）"""
    _ensure_dir()
    ts = snapshot.captured_at or time.time()
    date_str = datetime.fromtimestamp(ts).strftime("%Y%m%d")
    day_file = os.path.join(TRACKING_DIR, f"feed_{date_str}.jsonl")

    # 加载已见过的 ID + 从本次数据中提取所有 ID
    seen_ids = _load_seen_ids(date_str)
    all_ids_incoming = {item.aweme_id for item in snapshot.items if item.aweme_id}

    # 过滤出真正新增的
    new_items = [item for item in snapshot.items if item.aweme_id not in seen_ids]

    if not new_items:
        return ResponseModel(
            code=200,
            message=f"无新增视频（共 {len(snapshot.items)} 条，均已存在）",
            data={"new_count": 0, "total_today": len(seen_ids)},
        )

    # 写入新数据
    record = {
        "captured_at": ts,
        "captured_at_str": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(new_items),
        "all_count": len(snapshot.items),
        "items": [item.model_dump() for item in new_items],
    }

    with open(day_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 更新缓存
    _dedup_cache[date_str] = seen_ids | all_ids_incoming

    return ResponseModel(
        code=200,
        message=f"新增 {len(new_items)} 条（去重 {len(snapshot.items) - len(new_items)} 条重复）",
        data={"new_count": len(new_items), "total_today": len(_dedup_cache[date_str])},
    )


@router.get("/history", summary="获取历史记录概要（去重统计）")
async def get_tracking_history(request: Request):
    """返回所有历史快照的日期和数量（按 aweme_id 去重）"""
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


@router.get("/detail", summary="获取某天的详细数据（去重）")
async def get_tracking_detail(
    request: Request,
    date: str = Query(..., example="20260526", description="日期 YYYYMMDD"),
):
    """获取指定日期的所有快照详情（按 aweme_id 去重）"""
    _ensure_dir()
    fpath = os.path.join(TRACKING_DIR, f"feed_{date}.jsonl")
    if not os.path.exists(fpath):
        return ResponseModel(code=404, message="该日期无数据")

    seen_ids = set()
    snapshots = []
    with open(fpath) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    record = json.loads(line)
                    # 去重：只保留该快照中新增的 item
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


@router.get("/stats", summary="获取趋势统计数据（去重）")
async def get_tracking_stats(request: Request):
    """计算各话题/类别随时间的变化趋势（按 aweme_id 去重）"""
    _ensure_dir()
    files = sorted(
        [f for f in os.listdir(TRACKING_DIR) if f.startswith("feed_") and f.endswith(".jsonl")]
    )

    if not files:
        return ResponseModel(code=200, data={"trends": [], "message": "暂无数据"})

    # 按天汇总话题频率
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
