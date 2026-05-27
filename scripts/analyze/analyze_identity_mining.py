"""
用户身份信息挖掘工具（评论 + 作品描述版）

基于评论内容和作品描述，自动提取目标用户的身份线索：
  - 出生地推断（基于最多评论 IP 归属地）
  - 教育背景（学校、专业、年级）
  - 社交关系（好友、伴侣、亲戚）
  - 活动地点轨迹
  - 姓名昵称线索
  - 其他身份特征（宠物、职业、爱好）

使用方式：
    python scripts/analyze/analyze_identity_mining.py <sec_user_id_or_dir>

示例：
    python scripts/analyze/analyze_identity_mining.py MS4wLjABAAAA...
    python scripts/analyze/analyze_identity_mining.py data/comments/user123/

输出：
    data/comments/<sec_user_id>/
        └── identity/
            ├── identity_report.json    结构化身份报告
            └── report.txt              文本报告
"""

import json
import os
import sys
import re
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from utils import data_utils





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
        print(f"   请先运行: python scripts/collect/collect_comments.py <URL>")
        sys.exit(1)

    with open(comments_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    comments = data.get("comments", [])
    videos = data.get("videos", {})
    target_user = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            target_user = meta.get("target_user", {})

    return comments, videos, target_user, data_dir


# ═══════════════════════════════════════════════════════════════════
# 分析引擎
# ═══════════════════════════════════════════════════════════════════

def analyze_birthplace(comments: list) -> dict:
    """
    基于 IP 归属地分布推断出生地。
    
    使用 data_utils.analyze_ip_distribution 获取 IP 分布数据，
    从中提取占比最高的地区作为出生地推断。
    """
    ip_data = data_utils.analyze_ip_distribution(comments)
    top_region = ip_data.get("inferred_home", "无法推断")
    confidence = ip_data.get("inferred_confidence", 0)
    total = ip_data.get("total_with_ip", 0)

    region_type = "海外" if top_region and any(
        k in top_region for k in ["海外", "美国", "日本", "韩国", "英国"]
    ) else "国内"

    return {
        "possible_birthplace": top_region or "无法推断",
        "region_type": region_type,
        "confidence": confidence,
        "total_samples": total,
        "ip_distribution_top5": {
            r: ip_data["domestic"].get(r) or ip_data["overseas"].get(r)
            for r in ip_data["top_regions"][:5] if r in ip_data["domestic"] or r in ip_data["overseas"]
        },
        "reasoning": f"评论IP归属地中「{top_region}」占比最高（{confidence}%），"
                     f"推测目标用户的家乡或主要生活地区在{top_region}",
    }


def analyze_relationships(comments: list, videos: dict, target_user: dict) -> dict:
    """
    从评论内容和 @ 提及中提取社交关系。
    
    自动过滤目标用户自己的评论（自评不构成社交关系）。
    """
    target_nickname = target_user.get("nickname", "")
    target_uid = target_user.get("uid", "")

    # 收集所有 @ 提及（从作品描述中）
    mentioned_users = Counter()
    for vid, vinfo in videos.items():
        desc = vinfo.get("desc", "")
        mentions = re.findall(r"@([\u4e00-\u9fff\w]+)", desc)
        for m in mentions:
            mentioned_users[m] += 1

    # 分析评论中自称关系的语句
    # 注意：在中文女性社交语境中，"老婆""我老婆"通常是闺蜜间的亲昵称呼，
    # 不代表真实婚姻或恋爱关系，归为"闺蜜/亲密好友"类型。
    relationship_keywords = {
        "女朋友": ["女朋友", "女友", "我对象"],
        "男朋友": ["男朋友", "男友", "我老公"],
        "闺蜜/亲密好友": ["闺蜜", "姐妹", "集美", "老婆", "我老婆", "宝贝", "宝宝"],
        "家人": ["三叔", "叔叔", "姑姑", "舅舅", "妈妈", "爸爸", "老妈", "老爸",
                 "奶奶", "爷爷", "哥哥", "姐姐", "弟弟", "妹妹", "表姐", "表哥"],
        "同学": ["同学", "室友", "舍友"],
    }

    # 过滤：排除目标用户自己的评论（自评不构成社交关系）
    other_comments = [c for c in comments
                      if c.get("user", {}).get("uid", "") != target_uid]

    # 评论者之间的关系自述
    relationship_declarations = []
    for c in other_comments:
        text = c.get("text", "")
        if not text:
            continue
        nickname = c.get("user", {}).get("nickname", "")

        for rel_type, keywords in relationship_keywords.items():
            for kw in keywords:
                if kw in text:
                    relationship_declarations.append({
                        "commenter": nickname,
                        "relation_type": rel_type,
                        "keyword_matched": kw,
                        "text": text[:80],
                        "ip_label": c.get("ip_label", ""),
                    })
                    break

    # 找出跨视频互动最频繁的评论者（关系密切）
    user_video_count = Counter()
    user_comments = defaultdict(list)
    for c in other_comments:
        uid = c.get("user", {}).get("uid", "")
        nickname = c.get("user", {}).get("nickname", "")
        if uid:
            user_video_count[uid] += 1
            user_comments[uid].append({
                "nickname": nickname,
                "text": c.get("text", ""),
                "aweme_id": c.get("aweme_id", ""),
                "ip_label": c.get("ip_label", ""),
            })

    # 频繁互动者 = 可能的好友/铁粉
    top_commenters = data_utils.analyze_top_commenters(comments, top_n=10)
    frequent_interactors = []
    for c in top_commenters:
        ip = ""
        for cm in comments:
            if cm.get("user", {}).get("uid") == c["uid"]:
                ip = cm.get("ip_label", "")
                break
        frequent_interactors.append({
            "nickname": c["nickname"],
            "uid": c["uid"],
            "comment_count": c["comment_count"],
            "ip_label": ip,
        })

    return {
        "frequent_interactors": frequent_interactors,
        "mentioned_users_in_posts": [
            {"username": name, "mention_count": count}
            for name, count in mentioned_users.most_common(10)
        ],
        "relationship_declarations": relationship_declarations,
    }


def analyze_education(videos: dict, comments: list, target_user: dict) -> dict:
    """
    从作品描述和评论中提取教育背景线索。
    
    视频描述中的线索为高置信度，评论中仅目标用户自己发的为高置信度，
    其他评论者的教育相关发言为低置信度（可能是他人的教育经历）。
    """
    clues = []

    # 从视频描述中搜索教育相关关键词
    education_keywords = {
        "专业": ["数学", "计算机", "软件", "物理", "化学", "英语", "文学",
                "历史", "法学", "医学", "建筑", "艺术", "设计", "金融",
                "经济", "会计", "统计", "机械", "电子", "通信"],
        "课程": ["常微分", "高数", "线代", "概率论", "数分", "高代",
                "C语言", "Python", "Java", "数据结构"],
        "阶段": ["大学", "上学", "上课", "考研", "期末", "考试", "作业",
                "实验", "毕设", "论文", "导师", "教授", "老师"],
        "学校": ["清华", "北大", "复旦", "交大", "浙大", "南大", "武大",
                "川大", "山大", "吉大", "华科", "中科大", "哈工大", "西交"],
    }

    target_uid = ""  # 会在外部设置

    for vid, vinfo in videos.items():
        desc = vinfo.get("desc", "")
        for category, keywords in education_keywords.items():
            for kw in keywords:
                if kw in desc:
                    clues.append({
                        "category": category,
                        "keyword": kw,
                        "source": "video_desc",
                        "context": desc[:60],
                        "aweme_id": vid,
                        "confidence": "high",
                    })

    # 从评论中搜索教育相关（仅限目标用户自己的评论，避免他人教育背景干扰）
    target_nickname = target_user.get("nickname", "")
    for c in comments:
        text = c.get("text", "")
        commenter = c.get("user", {}).get("nickname", "")
        if not text:
            continue
        # 只有目标用户自己发的评论才计入高置信度线索
        is_target_self = (commenter == target_nickname)
        for category, keywords in education_keywords.items():
            for kw in keywords:
                if kw in text:
                    clues.append({
                        "category": category,
                        "keyword": kw,
                        "source": "comment",
                        "context": text[:60],
                        "commenter": commenter,
                        "confidence": "high" if is_target_self else "low",
                    })

    # 按置信度归类
    high_conf = [c for c in clues if c["confidence"] == "high"]
    low_conf = [c for c in clues if c["confidence"] == "low"]

    # 推断结论（仅基于高置信度线索）
    high_summary = defaultdict(set)
    for clue in high_conf:
        high_summary[clue["category"]].add(clue["keyword"])

    conclusions = []
    if "课程" in high_summary and ("常微分" in high_summary["课程"] or "高数" in high_summary["课程"]):
        conclusions.append("正在学习高等数学/常微分方程，推测为理工科专业")
    if "专业" in high_summary and "数学" in high_summary["专业"]:
        conclusions.append("专业与数学相关")
    if "阶段" in high_summary and ("大学" in high_summary["阶段"] or "上学" in high_summary["阶段"]):
        conclusions.append("在读大学生")

    all_summary = defaultdict(set)
    for clue in clues:
        all_summary[clue["category"]].add(clue["keyword"])

    return {
        "clues_found": len(clues),
        "high_confidence_clues": len(high_conf),
        "low_confidence_clues": len(low_conf),
        "clue_details": clues[:30],
        "summary": {k: list(v) for k, v in all_summary.items()},
        "conclusions": conclusions,
    }


def analyze_locations(videos: dict, comments: list) -> dict:
    """
    从作品描述和评论中提取去过/生活过的地点。
    """
    # 知名地点关键词
    location_db = {
        "成都": ["成都", "春熙路", "IFS", "太古里", "宽窄巷子", "锦里", "新津", "都江堰"],
        "北京": ["北京", "三里屯", "国贸", "王府井", "南锣鼓巷", "颐和园", "天安门"],
        "上海": ["上海", "外滩", "陆家嘴", "南京路", "新天地", "迪士尼"],
        "武汉": ["武汉", "江汉路", "光谷", "黄鹤楼", "东湖"],
        "长沙": ["长沙", "太平街", "五一广场", "橘子洲", "岳麓山"],
        "重庆": ["重庆", "解放碑", "洪崖洞", "磁器口"],
        "西安": ["西安", "钟楼", "回民街", "大雁塔"],
        "广州": ["广州", "小蛮腰", "天河", "北京路"],
        "深圳": ["深圳", "南山", "福田", "华强北"],
    }

    locations_found = defaultdict(list)

    # 从视频描述中搜索
    for vid, vinfo in videos.items():
        desc = vinfo.get("desc", "")
        for city, keywords in location_db.items():
            for kw in keywords:
                if kw in desc:
                    locations_found[city].append({
                        "keyword": kw,
                        "source": "video_desc",
                        "context": desc[:60],
                        "aweme_id": vid,
                    })

    # 从评论中搜索
    for c in comments:
        text = c.get("text", "")
        if not text:
            continue
        for city, keywords in location_db.items():
            for kw in keywords:
                if kw in text:
                    locations_found[city].append({
                        "keyword": kw,
                        "source": "comment",
                        "context": text[:60],
                        "commenter": c.get("user", {}).get("nickname", ""),
                    })

    # 统计每个城市出现的次数
    city_counts = {}
    for city, mentions in locations_found.items():
        city_counts[city] = {
            "count": len(mentions),
            "keywords_found": list(set(m["keyword"] for m in mentions)),
            "samples": mentions[:3],
        }

    # 排序
    sorted_cities = sorted(city_counts.items(), key=lambda x: x[1]["count"], reverse=True)

    return {
        "locations_found": dict(sorted_cities),
        "total_cities": len(sorted_cities),
    }


def analyze_names(comments: list, videos: dict, target_user: dict) -> dict:
    """
    提取姓名/昵称线索。
    """
    clue_list = []

    # 1. 目标用户的抖音昵称
    nickname = target_user.get("nickname", "")
    if nickname:
        clue_list.append({
            "type": "抖音昵称",
            "content": nickname,
            "source": "user_profile",
            "note": "用户自定义昵称，可能包含真实姓名信息",
        })

    # 2. 评论中可能称呼目标用户的词语
    # 常见的爱称/称呼模式（含黑名单过滤）
    name_patterns = [
        (r"老([\u4e00-\u9fff]{1,2})", "老X"),
        (r"小([\u4e00-\u9fff]{1,2})", "小X"),
        (r"阿([\u4e00-\u9fff])", "阿X"),
        (r"([\u4e00-\u9fff])宝", "X宝"),
        (r"宝[\u4e00-\u9fff]", "宝宝/宝贝"),
        (r"([\u4e00-\u9fff]{2,4})美", "X美"),
    ]
    # 这些“老X/小X/阿X”的 X 不可能是名字
    name_blacklist = {
        "老": ["婆", "师", "妈", "公", "板", "铁", "弟", "妹", "哥", "大",
               "少", "乡", "外", "人", "年", "鼠", "虎", "牛", "实", "板"],
        "小": ["心", "区", "时", "孩", "伙", "姐", "妹", "说", "学", "吃",
               "型", "组", "菜", "店", "屋", "院", "路", "道", "巷", "山"],
        "阿": ["姨", "门", "里", "拉", "哥", "姐", "妹", "婆"],
    }

    all_comment_text = " ".join(c.get("text", "") for c in comments if c.get("text"))
    for pattern, pattern_name in name_patterns:
        matches = re.findall(pattern, all_comment_text)
        prefix = pattern_name.replace("X", "").strip()  # "老", "小", "阿"
        blacklist = name_blacklist.get(prefix, [])
        for m in matches[:15]:
            word = m if isinstance(m, str) else m[0]
            if word in blacklist:
                continue
            clue_list.append({
                "type": f"称呼 ({pattern_name})",
                "content": word,
                "source": "comment_text",
                "note": "评论中出现的称呼用语，可能是昵称或真实姓名的一部分",
            })

    # 3. 从描述中提取被@的好友名单
    all_mentions = set()
    for vid, vinfo in videos.items():
        desc = vinfo.get("desc", "")
        mentions = re.findall(r"@([\u4e00-\u9fff\w]+)", desc)
        for name in mentions:
            if len(name) >= 2 and not name.isdigit():
                all_mentions.add(name)

    if all_mentions:
        clue_list.append({
            "type": "常@的好友",
            "content": "、".join(sorted(all_mentions)[:10]),
            "source": "video_mentions",
            "note": "作品中频繁提及的用户",
        })

    # 去重
    seen = set()
    unique_clues = []
    for clue in clue_list:
        key = (clue["type"], clue["content"])
        if key not in seen:
            seen.add(key)
            unique_clues.append(clue)

    return {"name_clues": unique_clues, "total_clues": len(unique_clues)}


def analyze_other_identity(comments: list, videos: dict) -> dict:
    """
    提取其他身份特征：宠物、职业、爱好等。
    """
    features = defaultdict(list)

    # 宠物关键词
    pet_keywords = ["达达", "Dusty", "猫", "狗", "宠物", "主子", "毛孩子", "修狗", "喵"]
    # 职业/兴趣关键词
    hobby_keywords = {
        "健身": ["健身", "撸铁", "举铁", "练完", "训练"],
        "音乐": ["弹琴", "钢琴", "吉他", "唱歌", "KTV"],
        "舞蹈": ["手势舞", "跳舞", "舞"],
        "拍照": ["拍照", "摄影", "原相机", "相机", "图集"],
        "电竞": ["游戏", "打游戏", "电竞", "lol", "王者"],
        "手工": ["手工", "DIY", "手作"],
        "自媒体": ["抖加", "推广", "投流", "博主", "自媒体", "创作"],
    }

    # 从描述中搜索
    for vid, vinfo in videos.items():
        desc = vinfo.get("desc", "")

        # 宠物
        for kw in pet_keywords:
            if kw in desc:
                features["pet"].append({
                    "keyword": kw,
                    "context": desc[:60],
                    "source": "video_desc",
                })

        # 爱好
        for hobby, keywords in hobby_keywords.items():
            for kw in keywords:
                if kw in desc:
                    features["hobby"].append({
                        "category": hobby,
                        "keyword": kw,
                        "context": desc[:60],
                        "source": "video_desc",
                    })

    # 从评论中搜索
    for c in comments:
        text = c.get("text", "")
        if not text:
            continue

        for kw in pet_keywords:
            if kw in text:
                features["pet"].append({
                    "keyword": kw,
                    "context": text[:60],
                    "source": "comment",
                    "commenter": c.get("user", {}).get("nickname", ""),
                })

    # 去重
    for category in features:
        seen = set()
        unique_items = []
        for item in features[category]:
            key = (item.get("keyword", ""), item.get("category", ""))
            if key not in seen:
                seen.add(key)
                unique_items.append(item)
        features[category] = unique_items

    # 总结
    conclusions = []
    if len(features.get("pet", [])) >= 2:
        conclusions.append("可能养有宠物")
    if any(f["category"] == "健身" for f in features.get("hobby", [])):
        conclusions.append("爱好健身")
    if any(f["category"] == "自媒体" for f in features.get("hobby", [])):
        conclusions.append("可能从事自媒体/内容创作")
    if any(f["category"] == "舞蹈" for f in features.get("hobby", [])):
        conclusions.append("喜欢拍舞蹈/手势舞类视频")
    if any(f["category"] == "音乐" for f in features.get("hobby", [])):
        conclusions.append("喜欢音乐")

    return {
        "features": {k: v[:10] for k, v in features.items()},
        "conclusions": conclusions,
    }


# ═══════════════════════════════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════════════════════════════

def generate_report(
    birthplace: dict,
    relationships: dict,
    education: dict,
    locations: dict,
    names: dict,
    other: dict,
    target_user: dict,
) -> str:
    """生成文本报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("🕵️  用户身份信息挖掘报告")
    lines.append("=" * 60)
    lines.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # ── 出生地推断 ──
    lines.append("─── 📍 出生地 / 主要生活地推断 ───")
    lines.append(f"  推测结果: {birthplace['possible_birthplace']}")
    lines.append(f"  置信度: {birthplace['confidence']}% (基于 {birthplace['total_samples']} 条评论IP)")
    lines.append(f"  推理逻辑: {birthplace['reasoning']}")
    lines.append("  IP分布Top:")
    for region, data in list(birthplace.get("ip_distribution_top5", {}).items())[:8]:
        bar = "█" * int(data["percentage"] / 3)
        lines.append(f"    {region}: {data['count']}条 ({data['percentage']}%) {bar}")
    lines.append("")

    # ── 教育背景 ──
    lines.append("─── 🎓 教育背景 ───")
    if education["clues_found"] > 0:
        lines.append(f"  共发现 {education['clues_found']} 条线索:")
        for cat, keywords in education["summary"].items():
            lines.append(f"    [{cat}] {'、'.join(keywords)}")
        for conclusion in education["conclusions"]:
            lines.append(f"  → {conclusion}")
        lines.append("  详细线索:")
        for clue in education["clue_details"][:10]:
            lines.append(f"    · [{clue['category']}] \"{clue['keyword']}\" → {clue['context']}")
    else:
        lines.append("  (未发现明确的教育背景线索)")
    lines.append("")

    # ── 社交关系 ──
    lines.append("─── 👥 社交关系 ───")
    lines.append("  高频互动者（可能的好友/铁粉）:")
    for i, person in enumerate(relationships.get("frequent_interactors", [])[:10], 1):
        lines.append(f"    {i:2d}. {person['nickname']} ({person['comment_count']} 条评论, IP: {person['ip_label']})")

    if relationships.get("relationship_declarations"):
        lines.append("  关系自述:")
        for decl in relationships["relationship_declarations"][:10]:
            lines.append(f"    · {decl['commenter']}: \"{decl['text']}\"")
    lines.append("")

    # ── 地点轨迹 ──
    lines.append("─── 🏠 活动地点轨迹 ───")
    if locations["locations_found"]:
        for city, info in locations["locations_found"].items():
            kws = "、".join(info["keywords_found"][:5])
            lines.append(f"    · {city} (提及 {info['count']} 次) — {kws}")
    else:
        lines.append("    (未发现明确的地点线索)")
    lines.append("")

    # ── 姓名线索 ──
    lines.append("─── 👤 姓名 / 昵称线索 ───")
    if names["total_clues"] > 0:
        for clue in names["name_clues"][:15]:
            if clue["type"] != "提及的用户名":  # 过滤掉大量@提及
                lines.append(f"    · [{clue['type']}] \"{clue['content']}\" — {clue['note']}")
    # 再单独显示提及的好友
    mention_clues = [c for c in names["name_clues"] if c["type"] == "提及的用户名"]
    if mention_clues:
        mentioned = list(set(c["content"] for c in mention_clues))
        lines.append(f"    作品中@的好友: {'、'.join(mentioned[:8])}")
    lines.append("")

    # ── 其他特征 ──
    lines.append("─── 🐾 其他身份特征 ───")
    for category, items in other["features"].items():
        if category == "pet":
            lines.append(f"  宠物相关:")
            for item in items[:5]:
                lines.append(f"    · \"{item['keyword']}\" — {item['context']}")
        elif category == "hobby":
            lines.append(f"  兴趣/职业:")
            for item in items[:8]:
                lines.append(f"    · [{item['category']}] \"{item['keyword']}\" — {item['context']}")
    for conclusion in other["conclusions"]:
        lines.append(f"  → {conclusion}")
    lines.append("")

    # ── 综合画像 ──
    lines.append("─── 📋 综合用户画像 ───")
    lines.append(f"  昵称: {target_user.get('nickname', '未知')}")
    lines.append(f"  推测籍贯: {birthplace['possible_birthplace']} (置信度 {birthplace['confidence']}%)")
    if education["conclusions"]:
        lines.append(f"  教育: {'; '.join(education['conclusions'])}")
    if birthplace.get("region_type"):
        lines.append(f"  地区类型: {birthplace['region_type']}")
    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/analyze/analyze_identity_mining.py <sec_user_id_or_dir>")
        print("示例: python scripts/analyze/analyze_identity_mining.py MS4wLjABAAAA...")
        sys.exit(1)

    sec_user_id_or_dir = sys.argv[1]

    print("=" * 60)
    print("🕵️  用户身份信息挖掘")
    print("=" * 60)

    # 加载数据
    comments, videos, target_user, data_dir = load_comments(sec_user_id_or_dir)
    print(f"\n📊 分析 {len(comments)} 条评论, {len(videos)} 个作品...\n")

    if not comments:
        print("❌ 没有评论数据可供分析")
        sys.exit(1)

    # ── 各维度分析 ──
    print("  📍 分析 IP 归属地推断出生地...")
    birthplace = analyze_birthplace(comments)

    print("  👥 分析社交关系...")
    relationships = analyze_relationships(comments, videos, target_user)

    print("  🎓 分析教育背景...")
    education = analyze_education(videos, comments, target_user)

    print("  🏠 分析活动地点...")
    locations = analyze_locations(videos, comments)

    print("  👤 提取姓名/昵称线索...")
    names = analyze_names(comments, videos, target_user)

    print("  🐾 提取其他身份特征...")
    other = analyze_other_identity(comments, videos)

    # ── 汇总 ──
    identity_report = {
        "target_user": {
            "nickname": target_user.get("nickname", ""),
            "sec_uid": target_user.get("sec_uid", ""),
            "follower_count": target_user.get("follower_count", 0),
        },
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_scope": {
            "total_comments": len(comments),
            "total_videos": len(videos),
        },
        "birthplace_analysis": birthplace,
        "relationship_analysis": relationships,
        "education_analysis": education,
        "location_analysis": locations,
        "name_analysis": names,
        "other_features": other,
    }

    # ── 保存结果 ──
    identity_dir = os.path.join(data_dir, "identity")
    os.makedirs(identity_dir, exist_ok=True)

    # JSON 报告
    json_path = os.path.join(identity_dir, "identity_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(identity_report, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON 报告已保存: {json_path}")

    # 文本报告
    report = generate_report(birthplace, relationships, education, locations, names, other, target_user)
    txt_path = os.path.join(identity_dir, "report.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"💾 文本报告已保存: {txt_path}")

    print()
    print(report)


if __name__ == "__main__":
    main()
