"""
Full comment collection tool for a Douyin user.

Crawls all comments (including replies) from a user's posts,
for subsequent fan profiling and social graph analysis.

Usage:
    python scripts/collect_comments.py <user_profile_url>

Example:
    python scripts/collect_comments.py "https://www.douyin.com/user/MS4wLjABAAAA..."

Options:
    --max-posts N      Only collect comments from last N posts (default: all)
    --max-comments N   Max N comments per post (default: all)
    --no-replies       Skip replies (top-level comments only)
    --resume           Resume interrupted collection
    --sync             Incremental sync: check and pull only new comments
    --interval N       Delay in seconds between posts (default: 2.0)
    --all              Collect all posts (including already collected)

Output:
    data/comments/<nickname>_<sec_user_id[:8]>/
        ├── _meta.json              Target user info + collection config
        ├── comments.json           All comments (JSON array)
        └── stats.json              Collection summary
"""

import asyncio
import json
import os
import random
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.paths import COMMENTS_DIR, ensure_project_paths

ensure_project_paths()
from crawlers.douyin.web.web_crawler import DouyinWebCrawler

ROOT = str(PROJECT_ROOT)
COMMENTS_DIR = str(COMMENTS_DIR)


# ═══════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════


def extract_sec_user_id(url: str) -> str:
    """Extract sec_user_id from a Douyin user profile URL."""
    match = re.search(r"/user/([^/?]+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"Unable to extract sec_user_id from URL: {url}")


def safe_text(text: str, max_len: int = 60) -> str:
    """Truncate long text for display."""
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len] + "..."


def sanitize_dirname(name: str, max_len: int = 40) -> str:
    """Sanitize string to be safe for use as a directory name."""
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    name = name.strip(". ")
    return name[:max_len] if name else "unknown"


def get_user_dir(sec_user_id: str, nickname: str = "") -> str:
    """Get user comment data directory path (format: nickname_sec_user_id[:8])."""
    if nickname:
        safe_nick = sanitize_dirname(nickname)
        suffix = sec_user_id[:8]
        return os.path.join(COMMENTS_DIR, f"{safe_nick}_{suffix}")
    # 兼容：没有昵称时用 sec_user_id 前缀
    return os.path.join(COMMENTS_DIR, sec_user_id[:16])


def load_existing_comments(user_dir: str) -> dict:
    """Load existing comment data (for resume collection)."""
    comments_path = os.path.join(user_dir, "comments.json")
    if not os.path.exists(comments_path):
        return {"videos": {}, "comments": []}

    with open(comments_path, encoding="utf-8") as f:
        return json.load(f)


def save_comments_data(user_dir: str, data: dict):
    """Save comment data to disk."""
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, "comments.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_meta(user_dir: str, meta: dict):
    """Save metadata to disk."""
    path = os.path.join(user_dir, "_meta.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def save_stats(user_dir: str, stats: dict):
    """Save statistics summary to disk."""
    path = os.path.join(user_dir, "stats.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════
# Comment extraction
# ═══════════════════════════════════════════════════════════════════


def extract_comment_info(comment: dict, aweme_id: str, reply_to_cid: str | None = None) -> dict:
    """Extract key fields from raw comment data.

    Extracted fields:
      - cid: Comment ID
      - aweme_id: Parent video ID
      - text: Comment content
      - create_time: Comment timestamp
      - digg_count: Like count
      - reply_count: Reply count
      - ip_label: IP location (e.g. "Guangdong", "Overseas")
      - user: Commenter info (uid, nickname, sec_uid, avatar, followers, etc.)
      - reply_to_uid: Target user ID of the reply (for sub-replies)
      - reply_to_name: Target user nickname of the reply
    """
    user_info = comment.get("user", {}) or {}
    # IP location may be in ip_label or position field
    ip_label = comment.get("ip_label", "") or comment.get("position", "") or ""

    result = {
        "cid": comment.get("cid", ""),
        "aweme_id": aweme_id,
        "text": comment.get("text", "") or comment.get("content", ""),
        "create_time": comment.get("create_time", 0),
        "digg_count": comment.get("digg_count", 0),
        "reply_count": comment.get("reply_count", 0),
        "ip_label": ip_label,
        "user": {
            "uid": user_info.get("uid", ""),
            "nickname": user_info.get("nickname", ""),
            "sec_uid": user_info.get("sec_uid", ""),
            "avatar": user_info.get("avatar_168x168", "")
            or user_info.get("avatar_300x300", "")
            or user_info.get("avatar", ""),
            "following_count": user_info.get("following_count", 0),
            "follower_count": user_info.get("follower_count", 0),
            "total_favorited": user_info.get("total_favorited", 0),
            "short_id": user_info.get("short_id", ""),
            "unique_id": user_info.get("unique_id", ""),
        },
        "reply_to_cid": reply_to_cid,  # Parent top-level comment ID
        "reply_to_uid": "",
        "reply_to_name": "",
    }

    # If it's a sub-reply, extract the reply target
    if reply_to_cid:
        reply_to = comment.get("reply_to", None) or comment.get("reply_to_user", None) or {}
        if reply_to:
            result["reply_to_uid"] = reply_to.get("uid", "") or reply_to.get("user_id", "")
            result["reply_to_name"] = reply_to.get("nickname", "")

    return result


async def fetch_all_comments(
    crawler: DouyinWebCrawler,
    aweme_id: str,
    max_count: int = 5000,
    fetch_replies: bool = True,
) -> list:
    """Fetch all comments (paginated) for a video, including sub-replies.

    Returns a list of structured comment dicts.
    """
    all_comments = []
    cursor = 0
    has_more = True
    page = 0

    while has_more and len(all_comments) < max_count:
        page += 1
        try:
            result = await crawler.fetch_video_comments(
                aweme_id=aweme_id,
                cursor=cursor,
                count=20,
            )

            comments_data = result.get("comments", [])
            if not comments_data:
                break

            # Extract top-level comments
            for comment in comments_data:
                if len(all_comments) >= max_count:
                    break
                extracted = extract_comment_info(comment, aweme_id)
                all_comments.append(extracted)

                # If top-level comment has replies, fetch them recursively
                reply_count = comment.get("reply_count", 0)
                if fetch_replies and reply_count > 0:
                    replies = await fetch_all_replies(
                        crawler, aweme_id, comment.get("cid", ""), extracted["cid"]
                    )
                    all_comments.extend(replies)

            cursor = result.get("cursor", 0) or result.get("offset", 0)
            has_more = result.get("has_more", False)

            await asyncio.sleep(random.uniform(0.8, 2.0))  # Random delay to simulate human behavior

        except Exception as e:
            print(f"    ⚠️  Page {page} fetch failed: {e}")
            break

    return all_comments


async def fetch_all_replies(
    crawler: DouyinWebCrawler,
    aweme_id: str,
    comment_id: str,
    reply_to_cid: str,
) -> list:
    """Fetch all sub-replies (paginated) under a specific top-level comment."""
    replies = []
    cursor = 0
    has_more = True
    page = 0

    while has_more:
        page += 1
        try:
            result = await crawler.fetch_video_comments_reply(
                item_id=aweme_id,
                comment_id=comment_id,
                cursor=cursor,
                count=20,
            )

            reply_list = result.get("comments", [])
            if not reply_list:
                break

            for reply in reply_list:
                extracted = extract_comment_info(reply, aweme_id, reply_to_cid=reply_to_cid)
                replies.append(extracted)

            cursor = result.get("cursor", 0)
            has_more = result.get("has_more", False)

            await asyncio.sleep(random.uniform(0.5, 1.5))

        except Exception as e:
            print(f"      ⚠️  Replies page {page} failed: {e}")
            break

    return replies


async def fetch_user_profile(crawler: DouyinWebCrawler, sec_user_id: str) -> dict:
    """Fetch target user's profile info."""
    try:
        result = await crawler.handler_user_profile(sec_user_id)
        user_data = (
            result.get("user", {})
            or result.get("user_info", {})
            or result.get("data", {}).get("user", {})
        )
        return {
            "uid": user_data.get("uid", ""),
            "nickname": user_data.get("nickname", ""),
            "sec_uid": user_data.get("sec_uid", ""),
            "avatar": user_data.get("avatar_168x168", "") or user_data.get("avatar_300x300", ""),
            "signature": user_data.get("signature", ""),
            "follower_count": user_data.get("follower_count", 0),
            "following_count": user_data.get("following_count", 0),
            "total_favorited": user_data.get("total_favorited", 0),
            "aweme_count": user_data.get("aweme_count", 0),
        }
    except Exception as e:
        print(f"  ⚠️  Failed to fetch user info: {e}")
        return {"sec_uid": sec_user_id}


async def check_has_new_comments(crawler: DouyinWebCrawler, aweme_id: str, known_cids: set) -> bool:
    """Quick check if a video has new comments.

    Fetches only the latest comment's cid for comparison,
    avoiding a full pull.
    """
    try:
        result = await crawler.fetch_video_comments(aweme_id=aweme_id, cursor=0, count=1)
        comments = result.get("comments", [])
        if not comments:
            return False
        newest_cid = comments[0].get("cid", "")
        return newest_cid not in known_cids
    except Exception:
        return True  # Conservative: assume new comments on failure


async def fetch_all_posts(
    crawler: DouyinWebCrawler, sec_user_id: str, max_videos: int | None = None
) -> list:
    """Fetch all user posts (paginated), including videos and albums.

    Returns: [{aweme_id, desc, create_time, aweme_type}, ...]
    """
    all_videos = []
    max_cursor = 0
    has_more = True
    page = 0

    while has_more:
        page += 1
        try:
            result = await crawler.fetch_user_post_videos(
                sec_user_id=sec_user_id,
                max_cursor=max_cursor,
                count=20,
            )

            aweme_list = result.get("aweme_list", [])
            for v in aweme_list:
                all_videos.append(
                    {
                        "aweme_id": v.get("aweme_id", ""),
                        "desc": v.get("desc", ""),
                        "create_time": v.get("create_time", 0),
                        "aweme_type": v.get("aweme_type", 0),
                    }
                )

            max_cursor = result.get("max_cursor", 0)
            has_more = result.get("has_more", False)

            print(f"  作品列表第 {page} 页: {len(aweme_list)} 个 (累计 {len(all_videos)} 个)")

            if not aweme_list:
                break

            if max_videos and len(all_videos) >= max_videos:
                all_videos = all_videos[:max_videos]
                break

            if has_more:
                await asyncio.sleep(random.uniform(1.0, 2.5))  # Random delay to avoid anti-crawl

        except Exception as e:
            print(f"  ❌ Failed to fetch posts page {page}: {e}")
            break

    return all_videos


# ═══════════════════════════════════════════════════════════════════
# Statistics
# ═══════════════════════════════════════════════════════════════════


def compute_stats(all_comments: list, target_user: dict) -> dict:
    """Generate statistics summary from all comments."""
    total = len(all_comments)
    commenters = {}
    ip_dist = {}
    video_comment_count = {}
    top_commenters = []

    for c in all_comments:
        uid = c.get("user", {}).get("uid", "")
        nickname = c.get("user", {}).get("nickname", "(unknown)")
        ip = c.get("ip_label", "(unknown)") or "(unknown)"
        vid = c.get("aweme_id", "")

        # Commenter stats
        if uid:
            if uid not in commenters:
                commenters[uid] = {"uid": uid, "nickname": nickname, "count": 0}
            commenters[uid]["count"] += 1

        # IP distribution
        ip_dist[ip] = ip_dist.get(ip, 0) + 1

        # Video comment count
        video_comment_count[vid] = video_comment_count.get(vid, 0) + 1

    # Sort and take top
    sorted_commenters = sorted(commenters.values(), key=lambda x: x["count"], reverse=True)
    top_commenters = sorted_commenters[:50]
    top_ips = sorted(ip_dist.items(), key=lambda x: x[1], reverse=True)[:20]

    # Time range
    timestamps = [c.get("create_time", 0) for c in all_comments if c.get("create_time")]
    earliest = min(timestamps) if timestamps else 0
    latest = max(timestamps) if timestamps else 0

    return {
        "target_user": {
            "nickname": target_user.get("nickname", ""),
            "sec_uid": target_user.get("sec_uid", ""),
        },
        "total_comments": total,
        "total_commenters": len(commenters),
        "total_videos_with_comments": len(video_comment_count),
        "time_range": {
            "earliest": earliest,
            "earliest_str": datetime.fromtimestamp(earliest, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
            if earliest
            else "",
            "latest": latest,
            "latest_str": datetime.fromtimestamp(latest, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
            if latest
            else "",
        },
        "ip_distribution": dict(top_ips),
        "top_commenters": top_commenters[:20],
        "collection_time": time.time(),
        "collection_time_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ═══════════════════════════════════════════════════════════════════
# Main flow
# ═══════════════════════════════════════════════════════════════════


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Douyin user full comment collector (collects all comments from all posts by default)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Collect all comments from a user (default: all posts, all comments, with replies)
  python scripts/collect_comments.py "https://www.douyin.com/user/MS4wLjABAAAA..."

  # Limit scope: only last 10 posts, max 1000 comments per post
  python scripts/collect_comments.py "https://..." --max-posts 10 --max-comments 1000

  # No replies, quick overview
  python scripts/collect_comments.py "https://..." --no-replies

  # Resume interrupted collection
  python scripts/collect_comments.py "https://..." --resume

  # Incremental sync (only pull new comments)
  python scripts/collect_comments.py "https://..." --sync
        """,
    )
    parser.add_argument("url", help="Douyin user profile URL")
    parser.add_argument(
        "--max-posts",
        type=int,
        default=None,
        dest="max_videos",
        help="Max N posts to collect comments from (default: all)",
    )
    parser.add_argument(
        "--max-comments", type=int, default=999999, help="Max N comments per post (default: all)"
    )
    parser.add_argument("--no-replies", action="store_true", help="Skip sub-replies")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted collection")
    parser.add_argument(
        "--interval", type=float, default=2.0, help="Delay between posts in seconds (default: 2.0)"
    )
    parser.add_argument(
        "--all", action="store_true", help="Collect all posts (including already collected)"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Incremental sync: only pull new comments, fast-check existing posts",
    )

    args = parser.parse_args()
    sec_user_id = extract_sec_user_id(args.url)

    print("=" * 60)
    print("📝 Douyin Comment Collector")
    print("=" * 60)
    print(f"🔍 User sec_user_id: {sec_user_id}")
    max_comments_display = "all" if args.max_comments >= 999999 else args.max_comments
    print(
        f"⚙️  Config: max_posts={args.max_videos or 'all'}, "
        f"max_comments/post={max_comments_display}, "
        f"replies={'no' if args.no_replies else 'yes'}, "
        f"interval={args.interval}s"
    )
    print()

    # ── 初始化爬虫 ──
    crawler = DouyinWebCrawler()

    # ── 获取目标用户信息 ──
    print("👤 Fetching user info...")
    target_user = await fetch_user_profile(crawler, sec_user_id)
    nickname = target_user.get("nickname", sec_user_id[:16])
    print(f"   Nickname: {nickname}")
    print(
        f"   Followers: {target_user.get('follower_count', '?')}  "
        f"Following: {target_user.get('following_count', '?')}  "
        f"Posts: {target_user.get('aweme_count', '?')}"
    )
    print()

    # Determine data directory (format: nickname_sec_user_id[:8])
    user_dir = get_user_dir(sec_user_id, nickname)
    print(f"📂 Data directory: {user_dir}")

    # Fetch video list
    print("📋 Fetching post list...")
    all_videos = await fetch_all_posts(crawler, sec_user_id, args.max_videos)
    print(f"✅ Total: {len(all_videos)} posts (videos + albums)")
    print()

    # Load existing data (resume / incremental sync)
    existing_data = {"videos": {}, "comments": []}
    if args.resume or args.sync:
        existing_data = load_existing_comments(user_dir)
        mode = "sync" if args.sync else "resume"
        print(
            f"♻️  {mode} mode: {len(existing_data.get('comments', []))} comments, "
            f"{len(existing_data.get('videos', {}))} posts already collected"
        )
        print()

    # Iterate through each post and collect comments
    all_comments = list(existing_data.get("comments", []))
    processed_videos = dict(existing_data.get("videos", {}))
    total_videos = len(all_videos)
    skipped = 0

    # Build known comment ID set (for --sync fast check)
    known_cids = {c["cid"] for c in all_comments if c.get("cid")}

    for idx, video in enumerate(all_videos, 1):
        aweme_id = video["aweme_id"]
        desc = safe_text(video.get("desc", "(no title)"), 50)

        # Skip already collected posts
        if aweme_id in processed_videos:
            if args.all:
                pass  # --all: re-collect
            elif args.sync:
                # --sync: quick check for new comments
                print(f"  [{idx}/{total_videos}] 🔍 Checking for new comments: {aweme_id} - {desc}")
                has_new = await check_has_new_comments(crawler, aweme_id, known_cids)
                if not has_new:
                    print("    ✅ No new comments")
                    skipped += 1
                    continue
                print("    🔄 Found new comments, re-collecting...")
                # Remove old comments for this post, re-collect
                all_comments = [c for c in all_comments if c.get("aweme_id") != aweme_id]
            else:
                # Normal mode: skip
                print(
                    f"  [{idx}/{total_videos}] ⏭️  Skipping already collected: {aweme_id} - {desc}"
                )
                skipped += 1
                continue

        print(f"  [{idx}/{total_videos}] 📹 Collecting comments: {aweme_id} - {desc}")

        try:
            comments = await fetch_all_comments(
                crawler,
                aweme_id,
                max_count=args.max_comments,
                fetch_replies=not args.no_replies,
            )

            count = len(comments)
            print(f"    ✅ Collected {count} comments")
            all_comments.extend(comments)
            processed_videos[aweme_id] = {
                "aweme_id": aweme_id,
                "desc": video.get("desc", ""),
                "comment_count": count,
                "collected_at": time.time(),
            }

            # Save after each post (crash-proof)
            save_data = {
                "videos": processed_videos,
                "comments": all_comments,
            }
            save_comments_data(user_dir, save_data)

            # Save metadata
            save_meta(
                user_dir,
                {
                    "target_user": target_user,
                    "sec_user_id": sec_user_id,
                    "url": args.url,
                    "config": {
                        "max_videos": args.max_videos,
                        "max_comments": args.max_comments,
                        "fetch_replies": not args.no_replies,
                    },
                    "collected_at": time.time(),
                    "collected_at_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_videos": total_videos,
                    "videos_collected": len(processed_videos),
                    "total_comments": len(all_comments),
                },
            )

        except Exception as e:
            print(f"    ❌ Collection failed: {e}")

        # Inter-post delay
        if idx < total_videos:
            jitter = args.interval * random.uniform(0.5, 1.5)  # Base ±50% random jitter
            await asyncio.sleep(max(1.0, jitter))

    # Final statistics
    print()
    print("=" * 60)
    print("📊 Collection complete!")
    print(f"   Target user: {nickname}")
    print(f"   Total posts: {total_videos}")
    print(f"   Collected: {len(processed_videos)} (skipped {skipped})")
    print(f"   Total comments: {len(all_comments)}")

    # 生成统计摘要
    stats = compute_stats(all_comments, target_user)
    save_stats(user_dir, stats)

    print(f"   Unique commenters: {stats['total_commenters']}")
    print("   IP distribution Top5: ", end="")
    top_ips = list(stats["ip_distribution"].items())[:5]
    print(", ".join(f"{k}={v}" for k, v in top_ips))
    print("   Top commenter: ", end="")
    if stats["top_commenters"]:
        tc = stats["top_commenters"][0]
        print(f"{tc['nickname']} ({tc['count']} comments)")
    print(f"   Data saved to: {user_dir}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
