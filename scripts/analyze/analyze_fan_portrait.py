"""
Fan portrait analysis tool (comment-based).

Analyzes fan demographics from comment data under a user's videos:
  - Geographic distribution (based on IP locations)
  - Active time distribution
  - Fan type distribution (KOL ratio, regular user ratio)
  - Sentiment analysis
  - Keyword extraction
  - Commenter loyalty assessment

Usage:
    python scripts/analyze/analyze_fan_portrait.py <sec_user_id_or_dir>

Example:
    python scripts/analyze/analyze_fan_portrait.py MS4wLjABAAAA...
    python scripts/analyze/analyze_fan_portrait.py data/comments/user123/

Output:
    data/comments/<sec_user_id>/
        └── profile/
            ├── profile_report.json     Structured portrait report
            └── report.txt              Text report
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from utils import data_utils

# ── 简单停用词表 ──
STOP_WORDS = {
    "的",
    "了",
    "是",
    "在",
    "我",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "着",
    "没有",
    "看",
    "好",
    "自己",
    "这",
    "他",
    "她",
    "它",
    "们",
    "那",
    "些",
    "吗",
    "吧",
    "啊",
    "呢",
    "呀",
    "哦",
    "嗯",
    "哈",
    "嘿",
    "啦",
    "嘛",
    "这个",
    "那个",
    "什么",
    "怎么",
    "为什么",
    "因为",
    "所以",
    "但是",
    "可以",
    "还是",
    "就是",
    "不是",
    "真的",
    "这么",
    "那么",
    "https",
    "http",
    "www",
    "com",
    "@",
    "#",
    "转发",
    "回复",
    # 抖音表情转译词（非用户真实表达，应过滤）
    "舔屏",
    "流泪",
    "发呆",
    "玫瑰",
    "黑脸",
    "呲牙",
    "摸头",
    "比心",
    "小鼓掌",
    "泣不成声",
    "酷拽",
    "鼓掌",
    "爱心",
    "捂脸",
    "送心",
    "抱抱你",
    "飞吻",
    "来看我",
    "赞",
    "惊喜",
    "惊恐",
    "憨笑",
    "大笑",
    "可爱",
    "亲亲",
    "吐舌",
    "白眼",
    "抠鼻",
    "阴险",
    "右哼哼",
    "左哼哼",
    "哈欠",
    "鄙视",
    "委屈",
    "骷髅",
    "口罩",
    "皱眉",
    "色",
    "得意",
    "睡",
    "撇嘴",
    "流泪",
    "愉快",
    "害羞",
    "调皮",
    "调皮",
    "尴尬",
}


def load_comments(sec_user_id_or_dir: str) -> tuple:
    """加载评论数据及元信息。

    支持传入 sec_user_id 或直接传入 data/comments/ 下的目录路径。

    Args:
        sec_user_id_or_dir: 用户的 sec_user_id 或 data/comments/ 下的目录路径。

    Returns:
        (comments, target_user, data_dir) 元组，
        comments 为评论列表，target_user 为用户元信息字典，data_dir 为数据目录路径。
    """
    if os.path.isdir(sec_user_id_or_dir):
        data_dir = sec_user_id_or_dir
    else:
        data_dir = data_utils.find_comment_dir(sec_user_id_or_dir)
        if not data_dir:
            guess = os.path.join(data_utils.PROJECT_ROOT, "data", "comments", sec_user_id_or_dir)
            if os.path.isdir(guess):
                data_dir = guess
            else:
                data_dir = os.path.join(
                    data_utils.PROJECT_ROOT, "data", "comments", sec_user_id_or_dir[:16]
                )

    comments_path = os.path.join(data_dir, "comments.json")
    meta_path = os.path.join(data_dir, "_meta.json")

    if not os.path.exists(comments_path):
        print(f"❌ 未找到评论数据: {comments_path}")
        print("   请先运行: python scripts/collect_comments.py <URL>")
        sys.exit(1)

    with open(comments_path, encoding="utf-8") as f:
        data = json.load(f)

    comments = data.get("comments", [])
    target_user = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
            target_user = meta.get("target_user", {})

    return comments, target_user, data_dir


def analyze_geo_distribution(comments: list) -> dict:
    """分析评论 IP 归属地分布。

    委托 data_utils.analyze_ip_distribution 实现。

    Args:
        comments: 评论列表。

    Returns:
        地域分布字典，包含国内/海外统计。
    """
    return data_utils.analyze_ip_distribution(comments)


def analyze_active_time(comments: list) -> dict:
    """分析评论者的活跃时段分布。

    根据评论的 create_time 字段统计各时段（凌晨/上午/下午/晚上）的评论量。

    Args:
        comments: 评论列表，每条需包含 create_time 字段。

    Returns:
        各时段的评论计数和占比字典。
    """
    hourly = Counter()
    weekday = Counter()

    for c in comments:
        ts = c.get("create_time", 0)
        if not ts:
            continue
        try:
            dt = datetime.fromtimestamp(ts, tz=UTC)
            hourly[dt.hour] += 1
            weekday[dt.strftime("%A")] += 1
        except (OSError, ValueError):
            pass

    # 时段划分
    time_slots = {
        "凌晨 (0-6点)": sum(hourly.get(h, 0) for h in range(0, 6)),
        "早间 (6-9点)": sum(hourly.get(h, 0) for h in range(6, 9)),
        "上午 (9-12点)": sum(hourly.get(h, 0) for h in range(9, 12)),
        "下午 (12-18点)": sum(hourly.get(h, 0) for h in range(12, 18)),
        "晚间 (18-21点)": sum(hourly.get(h, 0) for h in range(18, 21)),
        "深夜 (21-24点)": sum(hourly.get(h, 0) for h in range(21, 24)),
    }

    total = sum(time_slots.values()) or 1
    time_slots_pct = {
        k: {"count": v, "percentage": round(v / total * 100, 1)} for k, v in time_slots.items()
    }

    # 最活跃小时
    peak_hours = sorted(hourly.items(), key=lambda x: x[1], reverse=True)[:5]
    peak_hours = [{"hour": h, "count": c} for h, c in peak_hours]

    return {
        "time_slots": time_slots_pct,
        "peak_hours": peak_hours,
        "weekday_distribution": dict(weekday.most_common()),
    }


def analyze_follower_type(comments: list) -> dict:
    """分析评论者的粉丝类型分布。

    根据评论者的粉丝数、作品数等维度，将评论者分为 KOL、核心粉丝、普通用户等类型。

    Args:
        comments: 评论列表，每条需包含 user 字段（含 follower_count 等）。

    Returns:
        各粉丝类型的计数和占比字典。
    """
    users = {}
    for c in comments:
        user = c.get("user", {})
        uid = user.get("uid", "")
        if uid:
            if uid not in users:
                users[uid] = user

    kols = 0
    core_users = 0
    normal = 0
    new_users = 0

    kols_list = []
    for uid, user in users.items():
        followers = user.get("follower_count", 0) or 0
        following = user.get("following_count", 0) or 0
        total_fav = user.get("total_favorited", 0) or 0

        if followers >= 10000:
            kols += 1
            kols_list.append(
                {
                    "uid": uid,
                    "nickname": user.get("nickname", "未知"),
                    "follower_count": followers,
                    "total_favorited": total_fav,
                }
            )
        elif followers >= 100:
            core_users += 1
        elif followers < 10 and following < 10:
            new_users += 1
        else:
            normal += 1

    # 按粉丝数排序 KOL
    kols_list.sort(key=lambda x: x["follower_count"], reverse=True)

    total = len(users) or 1
    return {
        "total_commenters": len(users),
        "kols": {"count": kols, "percentage": round(kols / total * 100, 1)},
        "core_users": {"count": core_users, "percentage": round(core_users / total * 100, 1)},
        "normal_users": {"count": normal, "percentage": round(normal / total * 100, 1)},
        "new_users": {"count": new_users, "percentage": round(new_users / total * 100, 1)},
        "top_kols": kols_list[:20],
    }


def extract_keywords(comments: list, top_n: int = 50) -> list:
    """
    简单关键词提取：基于词频。

    注意：这是一个基础实现。如需更准确的 NLP 关键词提取，
    可接入 jieba 分词 + TF-IDF。
    """
    # 简单分词：以中文字符为单位提取 2-4 字词语
    word_counter = Counter()

    for c in comments:
        text = c.get("text", "")
        if not text:
            continue
        # 提取中文短语
        tokens = re.findall(r"[\u4e00-\u9fff]+", text)
        for token in tokens:
            # 2-4 字词更可能是有意义的词组
            if 2 <= len(token) <= 10 and token not in STOP_WORDS:
                word_counter[token] += 1

    most_common = word_counter.most_common(top_n)
    return [{"word": word, "count": count} for word, count in most_common]


def analyze_sentiment_simple(comments: list) -> dict:
    """
    简单情感倾向分析。

    基于正面/负面关键词匹配。这是轻量级实现，
    如需更准确的结果可接入专门的 NLP 情感分析模型。
    """
    positive_words = {
        "好",
        "好看",
        "喜欢",
        "太棒",
        "优秀",
        "厉害",
        "可爱",
        "漂亮",
        "美",
        "美美",
        "美美哒",
        "帅",
        "帅气",
        "赞",
        "点赞",
        "支持",
        "牛逼",
        "牛",
        "强",
        "精彩",
        "绝了",
        "完美",
        "不错",
        "爱了",
        "感动",
        "感人",
        "加油",
        "期待",
        "棒",
        "给力",
        "良心",
    }
    negative_words = {
        "差",
        "不好",
        "难看",
        "无聊",
        "讨厌",
        "恶心",
        "垃圾",
        "烂",
        "假的",
        "骗人",
        "骗子",
        "举报",
        "拉黑",
        "取关",
        "晦气",
        "无语",
        "烦",
        "恶心",
        "受不了",
        "辣鸡",
        "什么玩意",
    }

    positive_count = 0
    negative_count = 0
    neutral_count = 0

    for c in comments:
        text = c.get("text", "")
        if not text:
            neutral_count += 1
            continue

        has_positive = any(w in text for w in positive_words)
        has_negative = any(w in text for w in negative_words)

        if has_positive and not has_negative:
            positive_count += 1
        elif has_negative and not has_positive:
            negative_count += 1
        else:
            neutral_count += 1

    total = positive_count + negative_count + neutral_count or 1
    return {
        "positive": {"count": positive_count, "percentage": round(positive_count / total * 100, 1)},
        "neutral": {"count": neutral_count, "percentage": round(neutral_count / total * 100, 1)},
        "negative": {"count": negative_count, "percentage": round(negative_count / total * 100, 1)},
    }


def analyze_loyalty(comments: list) -> dict:
    """
    评论者忠诚度分析。

    评估指标：
      - 跨视频评论者：在多个视频下都有评论
      - 高频评论者：评论总数多
      - 长线关注者：评论跨越时间范围大
    """
    user_videos = defaultdict(set)
    user_counts = Counter()
    user_times = defaultdict(list)

    for c in comments:
        uid = c.get("user", {}).get("uid", "")
        if not uid:
            continue
        user_videos[uid].add(c.get("aweme_id", ""))
        user_counts[uid] += 1
        ts = c.get("create_time", 0)
        if ts:
            user_times[uid].append(ts)

    # 跨视频评论者（在 >=3 个视频下评论）
    cross_video = sum(1 for v in user_videos.values() if len(v) >= 3)

    # 高频评论者（评论 >= 5 条）
    high_freq = sum(1 for c in user_counts.values() if c >= 5)

    # 铁粉：跨视频 >= 3 且 评论 >= 5
    loyal = sum(1 for uid in user_counts if len(user_videos[uid]) >= 3 and user_counts[uid] >= 5)

    # 最忠实的粉丝
    loyal_scores = []
    for uid in user_counts:
        video_count = len(user_videos[uid])
        comment_count = user_counts[uid]
        if video_count >= 2 and comment_count >= 3:
            times = user_times.get(uid, [])
            span = (max(times) - min(times)) / 86400 if len(times) >= 2 else 0
            score = comment_count * 0.5 + video_count * 1.0 + min(span / 30, 5)
            loyal_scores.append(
                {
                    "uid": uid,
                    "nickname": next(
                        (
                            c.get("user", {}).get("nickname", "")
                            for c in comments
                            if c.get("user", {}).get("uid", "") == uid
                        ),
                        "未知",
                    ),
                    "comment_count": comment_count,
                    "video_count": video_count,
                    "time_span_days": round(span, 1),
                    "loyalty_score": round(score, 1),
                }
            )

    loyal_scores.sort(key=lambda x: x["loyalty_score"], reverse=True)

    total_users = len(user_counts) or 1
    return {
        "total_commenters": total_users,
        "cross_video_commenters": {
            "count": cross_video,
            "percentage": round(cross_video / total_users * 100, 1),
        },
        "high_freq_commenters": {
            "count": high_freq,
            "percentage": round(high_freq / total_users * 100, 1),
        },
        "loyal_fans": {
            "count": loyal,
            "percentage": round(loyal / total_users * 100, 1),
        },
        "top_loyal_fans": loyal_scores[:30],
    }


def generate_profile_report(comments: list, target_user: dict) -> dict:
    """生成完整的用户画像报告"""
    print("  🌍 分析地域分布...")
    geo = analyze_geo_distribution(comments)

    print("  ⏰ 分析活跃时段...")
    time_dist = analyze_active_time(comments)

    print("  👤 分析粉丝类型...")
    follower_type = analyze_follower_type(comments)

    print("  📝 提取关键词...")
    keywords = extract_keywords(comments)

    print("  💖 分析情感倾向...")
    sentiment = analyze_sentiment_simple(comments)

    print("  ⭐ 分析粉丝忠诚度...")
    loyalty = analyze_loyalty(comments)

    return {
        "target_user": {
            "nickname": target_user.get("nickname", ""),
            "sec_uid": target_user.get("sec_uid", ""),
        },
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_scope": {
            "total_comments_analyzed": len(comments),
        },
        "geo_distribution": geo,
        "active_time": time_dist,
        "follower_type": follower_type,
        "top_keywords": keywords[:30],
        "sentiment": sentiment,
        "loyalty": loyalty,
    }


def format_report(profile: dict) -> str:
    """将画像报告格式化为文本"""
    t = profile["target_user"]
    lines = []
    lines.append("=" * 60)
    lines.append("🎯 用户画像分析报告（评论版）")
    lines.append("=" * 60)
    lines.append(f"目标用户: {t.get('nickname', '未知')}")
    lines.append(f"分析时间: {profile['analysis_time']}")
    lines.append(f"数据规模: {profile['data_scope']['total_comments_analyzed']} 条评论")
    lines.append("")

    # ── 地域分布 ──
    geo = profile["geo_distribution"]
    lines.append("─── 🌍 粉丝地域分布 ───")
    lines.append("  国内 Top 10:")
    for i, (region, data) in enumerate(list(geo.get("domestic", {}).items())[:10], 1):
        lines.append(f"    {i:2d}. {region}: {data['count']} ({data['percentage']}%)")
    if geo.get("overseas"):
        lines.append(f"  海外: {sum(d['count'] for d in geo['overseas'].values())} 条")
        for i, (region, data) in enumerate(list(geo.get("overseas", {}).items())[:5], 1):
            lines.append(f"    {i:2d}. {region}: {data['count']} ({data['percentage']}%)")
    lines.append("")

    # ── 活跃时段 ──
    time_dist = profile["active_time"]
    lines.append("─── ⏰ 粉丝活跃时段 ───")
    for slot, data in sorted(time_dist["time_slots"].items()):
        bar = "█" * int(data["percentage"] / 2) if data["percentage"] > 0 else ""
        lines.append(f"  {slot}: {data['count']:>6} 条 ({data['percentage']:5.1f}%)  {bar}")
    lines.append("")

    # ── 粉丝类型 ──
    ft = profile["follower_type"]
    lines.append("─── 👤 粉丝类型分布 ───")
    lines.append(
        f"  🌟 KOL / 意见领袖 (粉丝>1万): {ft['kols']['count']} 人 ({ft['kols']['percentage']}%)"
    )
    lines.append(
        f"  💬 核心粉丝 (粉丝100-1万): {ft['core_users']['count']} 人 ({ft['core_users']['percentage']}%)"
    )
    lines.append(
        f"  👥 普通粉丝: {ft['normal_users']['count']} 人 ({ft['normal_users']['percentage']}%)"
    )
    lines.append(
        f"  🆕 新用户/低互动: {ft['new_users']['count']} 人 ({ft['new_users']['percentage']}%)"
    )
    if ft["top_kols"]:
        lines.append("  发现 KOL:")
        for m in ft["top_kols"][:10]:
            lines.append(f"    - {m['nickname']} (粉丝 {m['follower_count']})")
    lines.append("")

    # ── 关键词 ──
    lines.append("─── 📝 高频关键词 Top 20 ───")
    kws = profile["top_keywords"][:20]
    for i, kw in enumerate(kws, 1):
        lines.append(f"  {i:2d}. {kw['word']} ({kw['count']} 次)")
    lines.append("")

    # ── 情感倾向 ──
    s = profile["sentiment"]
    lines.append("─── 💖 评论情感倾向 ───")
    lines.append(f"  😊 正面: {s['positive']['count']} ({s['positive']['percentage']}%)")
    lines.append(f"  😐 中性: {s['neutral']['count']} ({s['neutral']['percentage']}%)")
    lines.append(f"  😠 负面: {s['negative']['count']} ({s['negative']['percentage']}%)")
    pos_bar = "█" * int(s["positive"]["percentage"] / 2)
    neg_bar = "█" * int(s["negative"]["percentage"] / 2)
    lines.append(
        f"  倾向: 正面 {pos_bar} {s['positive']['percentage']}%  |  负面 {neg_bar} {s['negative']['percentage']}%"
    )
    lines.append("")

    # ── 忠诚度 ──
    loy = profile["loyalty"]
    lines.append("─── ⭐ 粉丝忠诚度 ───")
    lines.append(f"  总评论者: {loy['total_commenters']} 人")
    lines.append(
        f"  跨视频评论者: {loy['cross_video_commenters']['count']} 人 ({loy['cross_video_commenters']['percentage']}%)"
    )
    lines.append(
        f"  高频评论者: {loy['high_freq_commenters']['count']} 人 ({loy['high_freq_commenters']['percentage']}%)"
    )
    lines.append(f"  💎 铁粉: {loy['loyal_fans']['count']} 人 ({loy['loyal_fans']['percentage']}%)")
    if loy["top_loyal_fans"]:
        lines.append("  铁粉榜 Top 10:")
        for i, fan in enumerate(loy["top_loyal_fans"][:10], 1):
            lines.append(
                f"    {i:2d}. {fan['nickname']}  "
                f"(评论 {fan['comment_count']} 次, {fan['video_count']} 个视频, "
                f"跨度 {fan['time_span_days']} 天, 忠诚度 {fan['loyalty_score']})"
            )

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/analyze/analyze_fan_portrait.py <sec_user_id_or_dir>")
        print("示例: python scripts/analyze/analyze_fan_portrait.py MS4wLjABAAAA...")
        sys.exit(1)

    sec_user_id_or_dir = sys.argv[1]

    print("=" * 60)
    print("🎯 用户画像分析（评论版）")
    print("=" * 60)

    # 加载数据
    comments, target_user, data_dir = load_comments(sec_user_id_or_dir)
    print(f"\n📊 分析 {len(comments)} 条评论数据...\n")

    if not comments:
        print("❌ 没有评论数据可供分析")
        sys.exit(1)

    # 生成画像报告
    profile = generate_profile_report(comments, target_user)

    # ── 保存结果 ──
    profile_dir = os.path.join(data_dir, "profile")
    os.makedirs(profile_dir, exist_ok=True)

    # JSON 报告
    json_path = os.path.join(profile_dir, "profile_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON 报告已保存: {json_path}")

    # 文本报告
    report = format_report(profile)
    txt_path = os.path.join(profile_dir, "report.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"💾 文本报告已保存: {txt_path}")

    print()
    print(report)


if __name__ == "__main__":
    main()
