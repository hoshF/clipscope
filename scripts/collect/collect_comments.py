"""
用户全量评论采集工具

从指定抖音用户的所有作品中，爬取全部评论数据（含子回复），
用于后续的用户画像分析和关系拓扑构建。

使用方式：
    python scripts/collect_comments.py <用户主页URL>

示例：
    python scripts/collect_comments.py "https://www.douyin.com/user/MS4wLjABAAAA..."

可选参数：
    --max-posts N      只采集最近 N 个作品的评论（默认全部）
    --max-comments N   每个作品最多采集 N 条评论（默认全部）
    --no-replies       不采集子回复（只采一级评论）
    --resume           继续上次未完成的采集（基于已有数据增量）
    --sync             增量同步：只检查并拉取新评论（每个旧视频仅 1 次 API 请求）
    --interval N       作品间延迟秒数（默认 2.0）
    --all              采集全部作品（包括已采集过的）

输出：
    data/comments/<昵称>_<sec_user_id[:8]>/
        ├── _meta.json              目标用户信息 + 采集配置
        ├── comments.json           全部评论数据（JSON 数组）
        └── stats.json              采集统计摘要
"""

import asyncio
import json
import os
import random
import re
import sys
import time
from datetime import UTC, datetime

LIB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib"
)
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from crawlers.douyin.web.web_crawler import DouyinWebCrawler

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMMENTS_DIR = os.path.join(ROOT, "data", "comments")


# ═══════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════


def extract_sec_user_id(url: str) -> str:
    """从抖音用户主页 URL 中提取 sec_user_id"""
    match = re.search(r"/user/([^/?]+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"无法从 URL 中提取 sec_user_id: {url}")


def safe_text(text: str, max_len: int = 60) -> str:
    """截断过长文本用于显示"""
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len] + "..."


def sanitize_dirname(name: str, max_len: int = 40) -> str:
    """清理字符串，使其可用作目录名"""
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    name = name.strip(". ")
    return name[:max_len] if name else "unknown"


def get_user_dir(sec_user_id: str, nickname: str = "") -> str:
    """获取用户评论数据目录（格式：昵称_sec_user_id[:8]）"""
    if nickname:
        safe_nick = sanitize_dirname(nickname)
        suffix = sec_user_id[:8]
        return os.path.join(COMMENTS_DIR, f"{safe_nick}_{suffix}")
    # 兼容：没有昵称时用 sec_user_id 前缀
    return os.path.join(COMMENTS_DIR, sec_user_id[:16])


def load_existing_comments(user_dir: str) -> dict:
    """加载已有评论数据（用于断点续采）"""
    comments_path = os.path.join(user_dir, "comments.json")
    if not os.path.exists(comments_path):
        return {"videos": {}, "comments": []}

    with open(comments_path, encoding="utf-8") as f:
        return json.load(f)


def save_comments_data(user_dir: str, data: dict):
    """保存评论数据"""
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, "comments.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_meta(user_dir: str, meta: dict):
    """保存元数据"""
    path = os.path.join(user_dir, "_meta.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def save_stats(user_dir: str, stats: dict):
    """保存统计摘要"""
    path = os.path.join(user_dir, "stats.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════
# 评论提取
# ═══════════════════════════════════════════════════════════════════


def extract_comment_info(comment: dict, aweme_id: str, reply_to_cid: str | None = None) -> dict:
    """
    从原始评论数据中提取关键字段。

    提取字段：
      - cid: 评论 ID
      - aweme_id: 所属视频 ID
      - text: 评论内容
      - create_time: 评论时间戳
      - digg_count: 点赞数
      - reply_count: 子回复数
      - ip_label: IP 归属地（如"广东"、"海外"等）
      - user: 评论者信息（uid, 昵称, sec_uid, 头像, 粉丝数等）
      - reply_to_uid: 回复的目标用户 ID（子回复时有效）
      - reply_to_name: 回复的目标用户昵称
    """
    user_info = comment.get("user", {}) or {}
    # IP 归属地可能在 ip_label 或 position 字段
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
        "reply_to_cid": reply_to_cid,  # 所回复的一级评论 ID
        "reply_to_uid": "",
        "reply_to_name": "",
    }

    # 如果是子回复，提取回复目标
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
    """
    分页采集一个视频下的所有评论（含子回复）。

    返回结构化评论列表。
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

            # 提取一级评论
            for comment in comments_data:
                if len(all_comments) >= max_count:
                    break
                extracted = extract_comment_info(comment, aweme_id)
                all_comments.append(extracted)

                # 如果有一级评论且有子回复，递归采集
                reply_count = comment.get("reply_count", 0)
                if fetch_replies and reply_count > 0:
                    replies = await fetch_all_replies(
                        crawler, aweme_id, comment.get("cid", ""), extracted["cid"]
                    )
                    all_comments.extend(replies)

            # 分页
            cursor = result.get("cursor", 0) or result.get("offset", 0)
            has_more = result.get("has_more", False)

            # 分页间随机延迟（加入更大抖动，模拟人类浏览行为）
            await asyncio.sleep(random.uniform(0.8, 2.0))

        except Exception as e:
            print(f"    ⚠️  第 {page} 页采集失败: {e}")
            break

    return all_comments


async def fetch_all_replies(
    crawler: DouyinWebCrawler,
    aweme_id: str,
    comment_id: str,
    reply_to_cid: str,
) -> list:
    """
    分页采集某个一级评论下的所有子回复。
    """
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
            print(f"      ⚠️  子回复第 {page} 页失败: {e}")
            break

    return replies


async def fetch_user_profile(crawler: DouyinWebCrawler, sec_user_id: str) -> dict:
    """获取目标用户的个人信息"""
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
        print(f"  ⚠️  获取用户信息失败: {e}")
        return {"sec_uid": sec_user_id}


async def check_has_new_comments(crawler: DouyinWebCrawler, aweme_id: str, known_cids: set) -> bool:
    """
    快速检查某个视频是否有新评论。
    只取最新 1 条评论比较 cid，无需全量拉取。
    """
    try:
        result = await crawler.fetch_video_comments(aweme_id=aweme_id, cursor=0, count=1)
        comments = result.get("comments", [])
        if not comments:
            return False
        newest_cid = comments[0].get("cid", "")
        return newest_cid not in known_cids
    except Exception:
        # 检查失败时保守处理：认为有新评论
        return True


async def fetch_all_posts(
    crawler: DouyinWebCrawler, sec_user_id: str, max_videos: int | None = None
) -> list:
    """
    分页获取用户的所有作品列表（含视频和图集）。

    返回格式：[{aweme_id, desc, create_time, aweme_type}, ...]
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

            # 作品列表分页间随机延迟，防止被风控
            if has_more:
                await asyncio.sleep(random.uniform(1.0, 2.5))

        except Exception as e:
            print(f"  ❌ 获取作品列表第 {page} 页失败: {e}")
            break

    return all_videos


# ═══════════════════════════════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════════════════════════════


def compute_stats(all_comments: list, target_user: dict) -> dict:
    """从全量评论数据生成统计摘要"""
    total = len(all_comments)
    commenters = {}
    ip_dist = {}
    video_comment_count = {}
    top_commenters = []

    for c in all_comments:
        uid = c.get("user", {}).get("uid", "")
        nickname = c.get("user", {}).get("nickname", "未知")
        ip = c.get("ip_label", "未知") or "未知"
        vid = c.get("aweme_id", "")

        # 评论者统计
        if uid:
            if uid not in commenters:
                commenters[uid] = {"uid": uid, "nickname": nickname, "count": 0}
            commenters[uid]["count"] += 1

        # IP 分布
        ip_dist[ip] = ip_dist.get(ip, 0) + 1

        # 视频评论数
        video_comment_count[vid] = video_comment_count.get(vid, 0) + 1

    # 排序取 top
    sorted_commenters = sorted(commenters.values(), key=lambda x: x["count"], reverse=True)
    top_commenters = sorted_commenters[:50]
    top_ips = sorted(ip_dist.items(), key=lambda x: x[1], reverse=True)[:20]

    # 时间范围
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
# 主流程
# ═══════════════════════════════════════════════════════════════════


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="抖音用户全量评论采集工具（默认采集全部作品的全部评论）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 采集指定用户的所有评论（默认采集全部作品的全部评论，含子回复）
  python scripts/collect_comments.py "https://www.douyin.com/user/MS4wLjABAAAA..."

  # 限制范围：只采集最近 10 个作品，每个作品最多 1000 条评论
  python scripts/collect_comments.py "https://..." --max-posts 10 --max-comments 1000

  # 不采子回复，快速概览
  python scripts/collect_comments.py "https://..." --no-replies

  # 断点续采
  python scripts/collect_comments.py "https://..." --resume

  # 增量同步（只检查并拉取新评论）
  python scripts/collect_comments.py "https://..." --sync
        """,
    )
    parser.add_argument("url", help="抖音用户主页 URL")
    parser.add_argument(
        "--max-posts",
        type=int,
        default=None,
        dest="max_videos",
        help="最多采集 N 个作品的评论（默认全部）",
    )
    parser.add_argument(
        "--max-comments", type=int, default=999999, help="每个作品最多采集 N 条评论（默认全部）"
    )
    parser.add_argument("--no-replies", action="store_true", help="不采集子回复")
    parser.add_argument("--resume", action="store_true", help="继续上次未完成的采集")
    parser.add_argument("--interval", type=float, default=2.0, help="作品间延迟秒数 (默认 2.0)")
    parser.add_argument("--all", action="store_true", help="采集全部作品（包括已采集过的）")
    parser.add_argument(
        "--sync", action="store_true", help="增量同步：只拉取新评论，已采集视频做快速检查"
    )

    args = parser.parse_args()
    sec_user_id = extract_sec_user_id(args.url)

    print("=" * 60)
    print("📝 抖音用户评论采集工具")
    print("=" * 60)
    print(f"🔍 用户 sec_user_id: {sec_user_id}")
    max_comments_display = "全部" if args.max_comments >= 999999 else args.max_comments
    print(
        f"⚙️  配置: max_posts={args.max_videos or '全部'}, "
        f"max_comments/post={max_comments_display}, "
        f"replies={'否' if args.no_replies else '是'}, "
        f"interval={args.interval}s"
    )
    print()

    # ── 初始化爬虫 ──
    crawler = DouyinWebCrawler()

    # ── 获取目标用户信息 ──
    print("👤 正在获取用户信息...")
    target_user = await fetch_user_profile(crawler, sec_user_id)
    nickname = target_user.get("nickname", sec_user_id[:16])
    print(f"   昵称: {nickname}")
    print(
        f"   粉丝: {target_user.get('follower_count', '?')}  "
        f"关注: {target_user.get('following_count', '?')}  "
        f"作品: {target_user.get('aweme_count', '?')}"
    )
    print()

    # ── 确定数据目录（格式：昵称_sec_user_id[:8]） ──
    user_dir = get_user_dir(sec_user_id, nickname)
    print(f"📂 数据目录: {user_dir}")

    # ── 获取视频列表 ──
    print("📋 正在获取作品列表...")
    all_videos = await fetch_all_posts(crawler, sec_user_id, args.max_videos)
    print(f"✅ 共获取到 {len(all_videos)} 个作品（含视频和图集）")
    print()

    # ── 加载已有数据（断点续采 / 增量同步） ──
    existing_data = {"videos": {}, "comments": []}
    if args.resume or args.sync:
        existing_data = load_existing_comments(user_dir)
        mode = "同步" if args.sync else "续采"
        print(
            f"♻️  {mode}模式: 已有 {len(existing_data.get('comments', []))} 条评论, "
            f"{len(existing_data.get('videos', {}))} 个作品已采集"
        )
        print()

    # ── 遍历每个作品采集评论 ──
    all_comments = list(existing_data.get("comments", []))
    processed_videos = dict(existing_data.get("videos", {}))
    total_videos = len(all_videos)
    skipped = 0

    # 构建已知评论 ID 集合（用于 --sync 快速检查）
    known_cids = {c["cid"] for c in all_comments if c.get("cid")}

    for idx, video in enumerate(all_videos, 1):
        aweme_id = video["aweme_id"]
        desc = safe_text(video.get("desc", "无标题"), 50)

        # 跳过已采集的作品
        if aweme_id in processed_videos:
            if args.all:
                # --all 模式：重新采集
                pass
            elif args.sync:
                # --sync 模式：快速检查是否有新评论
                print(f"  [{idx}/{total_videos}] 🔍 检查新评论: {aweme_id} - {desc}")
                has_new = await check_has_new_comments(crawler, aweme_id, known_cids)
                if not has_new:
                    print("    ✅ 无新增评论")
                    skipped += 1
                    continue
                print("    🔄 发现新评论，重新采集...")
                # 清洗旧评论，重新采集
                all_comments = [c for c in all_comments if c.get("aweme_id") != aweme_id]
            else:
                # 普通模式：跳过
                print(f"  [{idx}/{total_videos}] ⏭️  跳过已采集: {aweme_id} - {desc}")
                skipped += 1
                continue

        print(f"  [{idx}/{total_videos}] 📹 采集评论: {aweme_id} - {desc}")

        try:
            comments = await fetch_all_comments(
                crawler,
                aweme_id,
                max_count=args.max_comments,
                fetch_replies=not args.no_replies,
            )

            count = len(comments)
            print(f"    ✅ 采集到 {count} 条评论")
            all_comments.extend(comments)
            processed_videos[aweme_id] = {
                "aweme_id": aweme_id,
                "desc": video.get("desc", ""),
                "comment_count": count,
                "collected_at": time.time(),
            }

            # 每采集一个作品就保存一次（防丢失）
            save_data = {
                "videos": processed_videos,
                "comments": all_comments,
            }
            save_comments_data(user_dir, save_data)

            # 保存元数据
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
            print(f"    ❌ 采集失败: {e}")

        # 作品间延迟
        if idx < total_videos:
            # 作品间随机延迟：基础值 ±50% 随机抖动
            jitter = args.interval * random.uniform(0.5, 1.5)
            await asyncio.sleep(max(1.0, jitter))

    # ── 最终统计 ──
    print()
    print("=" * 60)
    print("📊 采集完成！")
    print(f"   目标用户: {nickname}")
    print(f"   总作品数: {total_videos}")
    print(f"   已采集作品: {len(processed_videos)} (跳过 {skipped} 个)")
    print(f"   总评论数: {len(all_comments)}")

    # 生成统计摘要
    stats = compute_stats(all_comments, target_user)
    save_stats(user_dir, stats)

    print(f"   唯一评论者: {stats['total_commenters']} 人")
    print("   IP 分布 Top5: ", end="")
    top_ips = list(stats["ip_distribution"].items())[:5]
    print(", ".join(f"{k}={v}" for k, v in top_ips))
    print("   最活跃评论者: ", end="")
    if stats["top_commenters"]:
        tc = stats["top_commenters"][0]
        print(f"{tc['nickname']} ({tc['count']} 条)")
    print(f"   数据保存至: {user_dir}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
