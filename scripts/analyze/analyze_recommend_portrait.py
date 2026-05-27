"""
抖音推荐流分析工具 — 通过分析推荐给您的视频，反推您的人物画像

原理：
    抖音的推荐算法会根据您的画像（兴趣、年龄段、性别等）推送内容。
    分析推荐流中视频的共同特征，可以折射出算法对您的判断。

用法：
    python scripts/analyze/analyze_recommend_portrait.py              # 收集100条推荐并分析
    python scripts/analyze/analyze_recommend_portrait.py --count 50   # 自定义收集数量
    python scripts/analyze/analyze_recommend_portrait.py --json-only  # 只保存数据不分析
"""

import asyncio
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from urllib.parse import urlencode

import httpx
from crawlers.douyin.web.endpoints import DouyinAPIEndpoints
from crawlers.douyin.web.models import BaseRequestModel
from crawlers.douyin.web.utils import BogusManager
from crawlers.douyin.web.web_crawler import DouyinWebCrawler
from utils import data_utils

ROOT = data_utils.PROJECT_ROOT


async def fetch_recommend_feed(count: int = 20) -> list:
    """获取抖音推荐 Feed"""
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
        params["count"] = count
        params["type"] = 1  # 推荐页
        params["source"] = 6  # 推荐

        a_bogus = BogusManager.ab_model_2_endpoint(params, headers.get("User-Agent", ""))
        endpoint = f"{DouyinAPIEndpoints.TAB_FEED}?{urlencode(params)}&a_bogus={a_bogus}"

        resp = await client.get(endpoint)
        data = resp.json()

        videos = []
        aweme_list = data.get("aweme_list", [])
        for item in aweme_list:
            v = {
                "aweme_id": item.get("aweme_id", ""),
                "desc": item.get("desc", ""),
                "create_time": item.get("create_time", 0),
                "author": {
                    "nickname": item.get("author", {}).get("nickname", ""),
                    "unique_id": item.get("author", {}).get("unique_id", ""),
                    "follower_count": item.get("author", {}).get("follower_count", 0),
                },
                "statistics": {
                    "digg_count": item.get("statistics", {}).get("digg_count", 0),
                    "comment_count": item.get("statistics", {}).get("comment_count", 0),
                    "collect_count": item.get("statistics", {}).get("collect_count", 0),
                    "share_count": item.get("statistics", {}).get("share_count", 0),
                },
                "music": {
                    "title": item.get("music", {}).get("title", ""),
                    "author": item.get("music", {}).get("author", ""),
                },
                "duration": item.get("video", {}).get("duration", 0),
                "hashtags": [
                    t.get("hashtag_name", "")
                    for t in (item.get("text_extra", []) or [])
                    if t.get("hashtag_name")
                ],
                "aweme_type": item.get("aweme_type"),
            }
            videos.append(v)
        return videos


def analyze_profile(videos: list) -> dict:
    """分析推荐视频，推断用户画像"""
    if not videos:
        return {"error": "没有数据"}

    total = len(videos)

    # ---- 1. 话题标签分析 ----
    all_tags = []
    for v in videos:
        all_tags.extend(v.get("hashtags", []))
    tag_counter = Counter(all_tags)
    top_tags = tag_counter.most_common(20)

    # ---- 2. 内容类别推断 ----
    # 通过热门话题推断内容类别
    category_keywords = {
        "情感": ["情感", "爱情", "恋爱", "失恋", "婚姻", "乙木女", "crush", "暧昧"],
        "搞笑": ["搞笑", "段子", "沙雕", "哈哈哈", "搞笑视频"],
        "美食": ["美食", "做饭", "吃播", "探店", "好吃的"],
        "游戏": ["游戏", "电竞", "王者", "吃鸡", "原神"],
        "音乐": ["音乐", "唱歌", "翻唱", "乐器", "弹唱"],
        "舞蹈": ["舞蹈", "跳舞", "街舞", "爵士"],
        "宠物": ["猫", "狗", "宠物", "萌宠", "猫咪", "狗狗"],
        "美妆": ["美妆", "化妆", "护肤", "穿搭", "变美"],
        "知识": ["知识", "科普", "学习", "读书", "历史", "哲学"],
        "健身": ["健身", "运动", "减肥", "肌肉", "撸铁"],
        "旅游": ["旅行", "旅游", "风景", "探店", "Vlog"],
        "影视": ["电影", "电视剧", "剪辑", "解说", "影评"],
        "二次元": ["二次元", "动漫", "cos", "漫展", "番剧"],
    }

    category_scores = defaultdict(float)
    desc_text = " ".join(v.get("desc", "") for v in videos).lower()
    for cat, keywords in category_keywords.items():
        for kw in keywords:
            if kw.lower() in desc_text:
                category_scores[cat] += 1

    # 归一化
    category_pct = {
        k: round(v / total * 100, 1)
        for k, v in sorted(category_scores.items(), key=lambda x: -x[1])
    }

    # ---- 3. 视频时长分析 ----
    durations = [v.get("duration", 0) for v in videos if v.get("duration", 0) > 0]
    avg_duration = sum(durations) / len(durations) if durations else 0

    # ---- 4. 互动偏好分析 ----
    avg_digg = sum(v.get("statistics", {}).get("digg_count", 0) for v in videos) / total
    avg_comment = sum(v.get("statistics", {}).get("comment_count", 0) for v in videos) / total

    # ---- 5. 内容形式分析 ----
    type_counter = Counter()
    for v in videos:
        t = v.get("aweme_type", 0)
        if t in (0, 4, 51, 55, 58, 61):
            type_counter["视频"] += 1
        elif t in (2, 68, 150):
            type_counter["图集"] += 1
        else:
            type_counter["其他"] += 1

    # ---- 6. 作者粉丝量级分析 ----
    follower_ranges = {"0-1万": 0, "1-10万": 0, "10-100万": 0, "100万+": 0}
    for v in videos:
        f = v.get("author", {}).get("follower_count", 0)
        if f < 10000:
            follower_ranges["0-1万"] += 1
        elif f < 100000:
            follower_ranges["1-10万"] += 1
        elif f < 1000000:
            follower_ranges["10-100万"] += 1
        else:
            follower_ranges["100万+"] += 1

    # ---- 7. 音乐使用分析 ----
    music_counter = Counter()
    for v in videos:
        music = v.get("music", {})
        music_title = music.get("title", "")
        music_author = music.get("author", "")
        if music_title:
            music_counter[f"{music_title} - {music_author}"] += 1
    top_music = music_counter.most_common(10)

    # ---- 8. 活跃时段推断 ----
    time_ranges = {"凌晨(0-6点)": 0, "上午(6-12点)": 0, "下午(12-18点)": 0, "晚上(18-24点)": 0}
    # 使用当前时间作为代理 - 推荐流能反映当前时段的活跃度偏好
    h = datetime.now().hour
    if h < 6:
        time_ranges["凌晨(0-6点)"] = 1
    elif h < 12:
        time_ranges["上午(6-12点)"] = 1
    elif h < 18:
        time_ranges["下午(12-18点)"] = 1
    else:
        time_ranges["晚上(18-24点)"] = 1

    # ---- 生成画像总结 ----
    inferred_profile = {}

    # 推断主要兴趣
    main_interests = [k for k, v in category_pct.items() if v > 5]
    inferred_profile["主要兴趣方向"] = main_interests[:5] if main_interests else ["数据不足"]

    # 推断内容偏好
    if avg_duration < 15000:
        inferred_profile["内容偏好"] = "偏好短视频（15秒以内）"
    elif avg_duration < 30000:
        inferred_profile["内容偏好"] = "偏好中等时长视频（15-30秒）"
    else:
        inferred_profile["内容偏好"] = "偏好长视频（30秒以上）"

    # 推断互动习惯
    if avg_digg > 50000:
        inferred_profile["互动活跃度"] = "高（倾向于点赞热门内容）"
    elif avg_digg > 10000:
        inferred_profile["互动活跃度"] = "中"
    else:
        inferred_profile["互动活跃度"] = "一般"

    # 内容形式偏好
    video_pct = type_counter.get("视频", 0) / total * 100
    inferred_profile["内容形式偏好"] = (
        f"视频 {video_pct:.0f}% / 图集 {type_counter.get('图集', 0) / total * 100:.0f}%"
    )

    # 作者偏好
    big_creator = follower_ranges["100万+"] + follower_ranges["10-100万"]
    inferred_profile["创作者偏好"] = (
        f"大V占 {big_creator / total * 100:.0f}% / 小创作者占 {(total - big_creator) / total * 100:.0f}%"
    )

    return {
        "分析时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "样本数量": total,
        "推断画像": inferred_profile,
        "兴趣分布": category_pct,
        "热门话题": top_tags[:15],
        "视频时长均值(秒)": round(avg_duration / 1000, 1),
        "平均点赞": round(avg_digg),
        "平均评论": round(avg_comment),
        "创作者粉丝分布": follower_ranges,
        "热门音乐": top_music[:5],
    }


async def main():
    count = 100
    json_only = False

    for arg in sys.argv[1:]:
        if arg.startswith("--count="):
            count = int(arg.split("=")[1])
        elif arg == "--json-only":
            json_only = True

    print(f"📡 正在收集推荐视频 ({count}条)...")
    print("   这需要调用推荐接口几次，请稍候...\n")

    all_videos = []
    batch_size = 20
    batches = (count + batch_size - 1) // batch_size

    for i in range(batches):
        batch_count = min(batch_size, count - len(all_videos))
        try:
            videos = await fetch_recommend_feed(count=batch_count)
            all_videos.extend(videos)
            print(
                f"   ✅ 第 {i + 1}/{batches} 批: 获取到 {len(videos)} 条 (累计 {len(all_videos)})"
            )
            await asyncio.sleep(2)  # 避免频率过高
        except Exception as e:
            print(f"   ❌ 第 {i + 1} 批失败: {e}")

    if not all_videos:
        print("\n❌ 未获取到推荐视频，请检查 Cookie 是否有效")
        return

    # 保存原始数据
    output_dir = os.path.join(ROOT, "data", "downloads", "_profile_analysis")
    os.makedirs(output_dir, exist_ok=True)

    data_file = os.path.join(output_dir, f"recommend_data_{int(time.time())}.json")
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(all_videos, f, ensure_ascii=False, indent=2)
    print(f"\n💾 原始数据已保存: {data_file}")

    if json_only:
        return

    # 分析
    print(f"\n{'=' * 50}")
    print("📊 正在分析您的人物画像...")
    print("=" * 50)

    profile = analyze_profile(all_videos)

    print("\n🎯 推断的人物画像")
    print("-" * 40)
    for k, v in profile.get("推断画像", {}).items():
        if isinstance(v, list):
            print(f"   {k}: {', '.join(v)}")
        else:
            print(f"   {k}: {v}")

    print("\n📈 兴趣分布")
    print("-" * 40)
    for cat, pct in list(profile.get("兴趣分布", {}).items())[:10]:
        bar = "█" * int(pct / 2) + "░" * (20 - int(pct / 2))
        print(f"   {cat:6s} {bar} {pct:.1f}%")

    print("\n🏷️ 热门话题 (Top 15)")
    print("-" * 40)
    for tag, count in profile.get("热门话题", []):
        print(f"   #{tag} ({count}次)")

    print("\n📏 内容特征")
    print("-" * 40)
    print(f"   平均视频时长: {profile.get('视频时长均值(秒)', 'N/A')}秒")
    print(f"   推荐视频平均点赞: {profile.get('平均点赞', 'N/A')}")
    print(f"   推荐视频平均评论: {profile.get('平均评论', 'N/A')}")

    print("\n👤 推荐作者粉丝分布")
    print("-" * 40)
    for r, c in profile.get("创作者粉丝分布", {}).items():
        bar = "█" * int(c / max(len(profile.get("创作者粉丝分布", {}).values()), 1) * 20)
        print(f"   {r:12s} {bar} {c}个视频")

    # 保存分析结果
    profile_file = os.path.join(output_dir, f"profile_{int(time.time())}.json")
    with open(profile_file, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    print(f"\n💾 分析报告已保存: {profile_file}")
    print(f"\n{'=' * 50}")
    print("💡 提示: 每次运行结果可能不同")
    print("   多次收集分析取平均会更准确")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    asyncio.run(main())
