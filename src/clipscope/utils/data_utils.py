"""Shared data analysis utility functions for comment data.

Provides:
  - PROJECT_ROOT               — Project root directory constant
  - find_comment_dir()         — Find comment directory by sec_uid in data/comments/
  - analyze_ip_distribution()  — IP location distribution analysis
  - analyze_commenter_fan_tiers() — Commenter fan tier classification (KOL/core/regular)
  - analyze_top_commenters()   — Top commenters ranking
"""

import json
import os
from collections import Counter

from clipscope.utils.paths import PROJECT_ROOT as PROOT

PROJECT_ROOT = str(PROOT)


def find_comment_dir(sec_user_id: str) -> str | None:
    """Find the comment directory matching a sec_uid in data/comments/.

    Iterates through each subdirectory under data/comments/ and checks
    if _meta.json's target_user.sec_uid matches the parameter.

    Args:
        sec_user_id: The target user's sec_uid.

    Returns:
        Absolute path to the matching directory, or None if not found.
    """
    comments_root = os.path.join(PROJECT_ROOT, "data", "comments")
    if not os.path.isdir(comments_root):
        return None
    for dname in os.listdir(comments_root):
        meta_path = os.path.join(comments_root, dname, "_meta.json")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("target_user", {}).get("sec_uid", "") == sec_user_id:
                    return os.path.join(comments_root, dname)
            except Exception:
                continue
    return None


# ═══════════════════════════════════════════════════════════════════
# Shared comment data analysis functions
# ═══════════════════════════════════════════════════════════════════

OVERSEAS_KEYWORDS = [
    "Overseas",
    "United States",
    "Japan",
    "Korea",
    "United Kingdom",
    "France",
    "Germany",
    "Canada",
    "Australia",
    "Singapore",
    "Malaysia",
    "Thailand",
    "Vietnam",
    "Philippines",
    "Indonesia",
    "India",
    "Russia",
    "Brazil",
    "Italy",
    "Spain",
    "Netherlands",
    "Sweden",
]


def analyze_ip_distribution(comments: list) -> dict:
    """Analyze IP location distribution from comments.

    Aggregates ip_label or position fields from each comment by region.
    Results are reused by fan_portrait (geo distribution) and identity_mining (birthplace inference).

    Args:
        comments: List of comments, each must have ip_label or position field.

    Returns:
        Distribution dict with domestic, overseas, and top_regions.
    """
    ip_counter = Counter()
    for c in comments:
        ip = c.get("ip_label", "") or c.get("position", "") or "unknown"
        if ip:
            ip_counter[ip] += 1

    total = sum(ip_counter.values()) or 1
    distribution = {}
    for region, count in ip_counter.most_common():
        distribution[region] = {
            "count": count,
            "percentage": round(count / total * 100, 1),
        }

    domestic = {}
    overseas = {}
    unknown = 0

    for region, data in distribution.items():
        if not region or region == "unknown":
            unknown += data["count"]
        elif any(k in region for k in OVERSEAS_KEYWORDS) or "国" in region:
            overseas[region] = data
        else:
            domestic[region] = data

    top_domestic = dict(sorted(domestic.items(), key=lambda x: x[1]["count"], reverse=True)[:15])
    top_overseas = dict(sorted(overseas.items(), key=lambda x: x[1]["count"], reverse=True)[:10])

    top_region = next(iter(distribution.keys())) if distribution else "unknown"
    top_pct = distribution[top_region]["percentage"] if top_region in distribution else 0

    return {
        "total_with_ip": total,
        "domestic": top_domestic,
        "overseas": top_overseas,
        "unknown_count": unknown,
        "top_regions": list(distribution.keys())[:10],
        "inferred_home": top_region if top_region != "unknown" else None,
        "inferred_confidence": top_pct,
    }


def analyze_commenter_fan_tiers(comments: list) -> dict:
    """Classify commenters into tiers: KOL / core fans / regular fans / new users."""
    commenters = {}
    for c in comments:
        u = c.get("user", {}) or {}
        uid = u.get("uid", "")
        if not uid:
            continue
        if uid not in commenters:
            commenters[uid] = {
                "uid": uid,
                "nickname": u.get("nickname", "unknown"),
                "follower_count": u.get("follower_count", 0) or 0,
                "comment_count": 0,
            }
        commenters[uid]["comment_count"] += 1

    total = len(commenters) or 1
    kols = []
    core = []
    normal = []
    new_users = []

    for uid, info in commenters.items():
        fc = info["follower_count"]
        if fc >= 10000:
            kols.append(info)
        elif fc >= 100:
            core.append(info)
        elif fc > 0:
            normal.append(info)
        else:
            new_users.append(info)

    kols.sort(key=lambda x: x["follower_count"], reverse=True)
    core.sort(key=lambda x: x["comment_count"], reverse=True)
    normal.sort(key=lambda x: x["comment_count"], reverse=True)

    return {
        "total_commenters": total,
        "kols": {
            "count": len(kols),
            "percentage": round(len(kols) / total * 100, 1),
            "list": kols[:20],
        },
        "core_fans": {
            "count": len(core),
            "percentage": round(len(core) / total * 100, 1),
            "list": core[:30],
        },
        "normal_fans": {"count": len(normal), "percentage": round(len(normal) / total * 100, 1)},
        "new_users": {
            "count": len(new_users),
            "percentage": round(len(new_users) / total * 100, 1),
        },
    }


def analyze_top_commenters(comments: list, top_n: int = 50) -> list:
    """Rank top commenters by comment frequency.

    Returns list sorted by comment count descending.
    """
    commenter_stats = {}
    for c in comments:
        u = c.get("user", {}) or {}
        uid = u.get("uid", "")
        if not uid:
            continue
        if uid not in commenter_stats:
            commenter_stats[uid] = {
                "uid": uid,
                "nickname": u.get("nickname", "unknown"),
                "sec_uid": u.get("sec_uid", ""),
                "comment_count": 0,
                "videos": set(),
            }
        commenter_stats[uid]["comment_count"] += 1
        commenter_stats[uid]["videos"].add(c.get("aweme_id", ""))

    result = []
    for uid, info in commenter_stats.items():
        result.append(
            {
                "uid": uid,
                "nickname": info["nickname"],
                "sec_uid": info["sec_uid"],
                "comment_count": info["comment_count"],
                "video_count": len(info["videos"]),
            }
        )

    result.sort(key=lambda x: x["comment_count"], reverse=True)
    return result[:top_n]
