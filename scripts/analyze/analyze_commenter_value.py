"""
评论者价值探测工具

分析目标用户的活跃评论者，探测其用户空间：
  - 粉丝数、作品数、获赞数
  - 近期作品评论热度
  - 综合评分：判断是否值得数据爬取

使用方式：
python scripts/analyze/analyze_commenter_value.py <sec_user_id_or_dir> [--top N]
    
示例：
    # 分析 Top 20 活跃评论者
    python scripts/analyze/analyze_commenter_value.py MS4wLjABAAAA...
    # 分析 Top 50
    python scripts/analyze/analyze_commenter_value.py MS4wLjABAAAA... --top 50
    # 指定数据目录
    python scripts/analyze/analyze_commenter_value.py data/comments/user123/

输出：
    data/comments/<sec_user_id>/
        └── commenters/
            ├── commenter_report.json     探测结果
            └── report.txt                文本报告
"""

import asyncio
import json
import os
import sys
import re
import time
import random
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# data_utils 必须在 crawlers 之前导入（它负责添加 lib/ 到 sys.path）
from utils import data_utils
from crawlers.douyin.web.web_crawler import DouyinWebCrawler





def load_comments(sec_user_id_or_dir: str) -> tuple:
    """加载评论数据"""
    if os.path.isdir(sec_user_id_or_dir):
        data_dir = sec_user_id_or_dir
    else:
        data_dir = data_utils.find_comment_dir(sec_user_id_or_dir)
        if not data_dir:
            guess = os.path.join(data_utils.PROJECT_ROOT, "data", "comments", sec_user_id_or_dir)
            if os.path.isdir(guess):
                data_dir = guess
            else:
                data_dir = os.path.join(data_utils.PROJECT_ROOT, "data", "comments", sec_user_id_or_dir[:16])

    comments_path = os.path.join(data_dir, "comments.json")
    meta_path = os.path.join(data_dir, "_meta.json")

    if not os.path.exists(comments_path):
        print(f"❌ 未找到评论数据: {comments_path}")
        sys.exit(1)

    with open(comments_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    comments = data.get("comments", [])
    target_user = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            target_user = meta.get("target_user", {})

    return comments, target_user, data_dir





async def probe_commenter(crawler: DouyinWebCrawler, sec_uid: str, nickname: str, comment_count: int) -> dict:
    """
    探测一个评论者的用户空间。
    返回结构化信息，异常时返回基础数据。
    """
    result = {
        "nickname": nickname,
        "sec_uid": sec_uid,
        "comment_count_on_target": comment_count,
        "follower_count": 0,
        "following_count": 0,
        "total_favorited": 0,
        "aweme_count": 0,
        "signature": "",
        "recent_video_comment_avg": 0,
        "sample_videos": 0,
        "error": None,
    }

    # 1. 获取用户个人信息
    try:
        profile = await crawler.handler_user_profile(sec_uid)
        user_data = profile.get("user", {}) or profile.get("user_info", {}) or profile.get("data", {}).get("user", {})
        result["follower_count"] = user_data.get("follower_count", 0) or 0
        result["following_count"] = user_data.get("following_count", 0) or 0
        result["total_favorited"] = user_data.get("total_favorited", 0) or 0
        result["aweme_count"] = user_data.get("aweme_count", 0) or 0
        result["signature"] = (user_data.get("signature", "") or "")[:100]
        result["uid"] = user_data.get("uid", "")
    except Exception as e:
        result["error"] = f"profile_fetch_failed: {e}"
        return result

    # 2. 采样最近视频的评论热度
    if result["aweme_count"] > 0:
        try:
            posts = await crawler.fetch_user_post_videos(
                sec_user_id=sec_uid, max_cursor=0, count=5
            )
            aweme_list = posts.get("aweme_list", [])
            if aweme_list:
                comment_counts = []
                for v in aweme_list[:5]:
                    stat = v.get("statistics", {}) or {}
                    cc = stat.get("comment_count", 0) or 0
                    comment_counts.append(cc)
                if comment_counts:
                    result["recent_video_comment_avg"] = round(sum(comment_counts) / len(comment_counts), 1)
                    result["sample_videos"] = len(comment_counts)
        except Exception as e:
            if result["error"] is None:
                result["error"] = f"post_fetch_failed: {e}"

    return result


def compute_value_score(probed: dict) -> float:
    """
    计算评论者的"数据爬取价值"评分 (0-100)。
    
    权重：
    - 粉丝数 30%：粉丝越多越有价值（KOL效应）
    - 作品数 20%：作品越多可采集内容越多
    - 评论互动热度 25%：自己作品的评论活跃度
    - 在本目标用户下的活跃度 25%：相关性越高越值得
    """
    score = 0.0

    # 粉丝数评分 (0-30)
    f = probed.get("follower_count", 0)
    if f >= 100000:
        score += 30
    elif f >= 10000:
        score += 25
    elif f >= 5000:
        score += 20
    elif f >= 1000:
        score += 15
    elif f >= 100:
        score += 8
    elif f > 0:
        score += 3

    # 作品数评分 (0-20)
    a = probed.get("aweme_count", 0)
    if a >= 200:
        score += 20
    elif a >= 100:
        score += 17
    elif a >= 50:
        score += 13
    elif a >= 20:
        score += 8
    elif a >= 5:
        score += 4
    elif a > 0:
        score += 2

    # 自身评论互动热度 (0-25)
    c = probed.get("recent_video_comment_avg", 0)
    if c >= 500:
        score += 25
    elif c >= 100:
        score += 20
    elif c >= 50:
        score += 15
    elif c >= 20:
        score += 10
    elif c >= 5:
        score += 5
    elif c > 0:
        score += 2

    # 在本目标用户下的活跃度 (0-25)
    ct = probed.get("comment_count_on_target", 0)
    if ct >= 100:
        score += 25
    elif ct >= 50:
        score += 20
    elif ct >= 20:
        score += 15
    elif ct >= 10:
        score += 10
    elif ct >= 5:
        score += 5
    elif ct > 0:
        score += 2

    return round(score, 1)


def value_label(score: float) -> str:
    if score >= 70:
        return "🌟🌟🌟 高价值"
    elif score >= 40:
        return "🌟🌟 有价值"
    elif score >= 20:
        return "🌟 可考虑"
    else:
        return "💤 低价值"


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="评论者价值探测工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="用户 sec_user_id 或数据目录")
    parser.add_argument("--top", type=int, default=20, help="探测前 N 个最活跃评论者 (默认 20)")
    parser.add_argument("--interval", type=float, default=1.5, help="请求间隔秒数 (默认 1.5)")

    args = parser.parse_args()

    print("=" * 60)
    print("🔎 评论者价值探测")
    print("=" * 60)

    comments, target_user, data_dir = load_comments(args.input)
    print(f"\n📊 {len(comments)} 条评论数据已加载")

    # ── 统计评论者活跃度 ──
    commenter_stats = Counter()
    commenter_info = {}
    for c in comments:
        u = c.get("user", {})
        uid = u.get("uid", "")
        if uid:
            commenter_stats[uid] += 1
            if uid not in commenter_info:
                commenter_info[uid] = u

    # 排除目标用户自己
    target_uid = target_user.get("uid", "")
    if target_uid in commenter_stats:
        del commenter_stats[target_uid]

    top_commenters = commenter_stats.most_common(args.top)
    print(f"👥 总评论者: {len(commenter_stats)} 人")
    print(f"🔝 将探测前 {len(top_commenters)} 名活跃评论者")
    print()

    # ── 逐个探测 ──
    crawler = DouyinWebCrawler()
    probed_list = []

    for idx, (uid, count) in enumerate(top_commenters, 1):
        info = commenter_info.get(uid, {})
        nickname = info.get("nickname", "未知")
        sec_uid = info.get("sec_uid", "")

        if not sec_uid:
            print(f"  [{idx}/{len(top_commenters)}] ⏭️  {nickname}: 无 sec_uid，跳过")
            continue

        print(f"  [{idx}/{len(top_commenters)}] 🔍 探测: {nickname} (在目标下评论 {count} 次)")
        probed = await probe_commenter(crawler, sec_uid, nickname, count)

        if probed.get("error"):
            print(f"    ⚠️  部分失败: {probed['error']}")

        score = compute_value_score(probed)
        probed["value_score"] = score
        probed["value_label"] = value_label(score)
        probed_list.append(probed)

        # 输出摘要
        print(f"    📊 粉丝 {probed['follower_count']} | "
              f"作品 {probed['aweme_count']} | "
              f"获赞 {probed['total_favorited']} | "
              f"均评 {probed['recent_video_comment_avg']}")
        print(f"    💎 价值评分: {score}/100 → {probed['value_label']}")
        print(f"    📝 签名: {probed['signature'][:50]}")
        print()

        # 请求间延迟
        delay = args.interval + random.uniform(-0.3, 0.5)
        await asyncio.sleep(max(0.5, delay))

    # ── 排序输出 ──
    probed_list.sort(key=lambda x: x["value_score"], reverse=True)

    print("=" * 60)
    print("📊 探测结果排名 (按价值评分)")
    print("=" * 60)
    print(f"{'排名':>4} {'昵称':<20} {'评分':>6} {'粉丝':>8} {'作品':>6} {'均评':>6} {'标签'}")
    print("-" * 70)
    for i, p in enumerate(probed_list, 1):
        nick = p["nickname"][:18]
        print(f"{i:>4} {nick:<20} {p['value_score']:>6} "
              f"{p['follower_count']:>8} {p['aweme_count']:>6} "
              f"{p['recent_video_comment_avg']:>6} {p['value_label']}")

    # ── 推荐爬取列表 ──
    high_value = [p for p in probed_list if p["value_score"] >= 40]
    medium_value = [p for p in probed_list if 20 <= p["value_score"] < 40]

    print()
    print("─── 🎯 推荐爬取建议 ───")
    if high_value:
        print(f"  🌟🌟🌟 高价值 (评分≥70):")
        for p in high_value:
            print(f"    · {p['nickname']} (评分 {p['value_score']}, "
                  f"粉丝 {p['follower_count']}, 作品 {p['aweme_count']})")
    if medium_value:
        print(f"  🌟🌟 有价值 (评分20-69):")
        for p in medium_value[:10]:
            print(f"    · {p['nickname']} (评分 {p['value_score']}, "
                  f"粉丝 {p['follower_count']}, 作品 {p['aweme_count']})")
    low_count = len([p for p in probed_list if p["value_score"] < 20])
    if low_count:
        print(f"  💤 低价值 (评分<20): {low_count} 人")

    # ── 保存结果 ──
    commenters_dir = os.path.join(data_dir, "commenters")
    os.makedirs(commenters_dir, exist_ok=True)

    report = {
        "target_user": {
            "nickname": target_user.get("nickname", ""),
            "sec_uid": target_user.get("sec_uid", ""),
        },
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_commenters": len(commenter_stats),
        "probed_count": len(probed_list),
        "top_commenters": probed_list,
        "recommendations": {
            "high_value": [
                {"nickname": p["nickname"], "sec_uid": p["sec_uid"],
                 "score": p["value_score"], "follower_count": p["follower_count"],
                 "aweme_count": p["aweme_count"]}
                for p in high_value
            ],
            "medium_value": [
                {"nickname": p["nickname"], "sec_uid": p["sec_uid"],
                 "score": p["value_score"], "follower_count": p["follower_count"],
                 "aweme_count": p["aweme_count"]}
                for p in medium_value[:20]
            ],
        },
    }

    json_path = os.path.join(commenters_dir, "commenter_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON 报告已保存: {json_path}")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
