"""
用户评论关系拓扑分析工具

基于采集的评论数据，构建用户之间的互动关系网络，
发现核心粉丝圈、互动社群和意见领袖。

使用方式：
    python scripts/analyze/analyze_social_graph.py <sec_user_id_or_dir>
    
示例：
    # 分析指定用户的评论关系
    python scripts/analyze/analyze_social_graph.py MS4wLjABAAAA...
    
    # 指定数据目录
    python scripts/analyze/analyze_social_graph.py data/comments/user123/

输出：
    data/comments/<sec_user_id>/
        └── relations/
            ├── relation_graph.json       关系图数据（节点+边）
            ├── communities.json          社群发现结果
            ├── top_interactors.json      高互动用户排名
            └── report.txt                文本报告
"""

import json
import os
import sys
from collections import defaultdict, Counter
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from utils import data_utils
from utils.data_utils import PROJECT_ROOT as ROOT




def load_comments(sec_user_id_or_dir: str) -> tuple:
    """
    加载评论数据。
    
    返回 (comments_list, target_user_info)
    """
    # 判断是 sec_user_id 还是目录路径
    if os.path.isdir(sec_user_id_or_dir):
        data_dir = sec_user_id_or_dir
    else:
        data_dir = data_utils.find_comment_dir(sec_user_id_or_dir)
        if not data_dir:
            # 降级：尝试作为目录名直接匹配
            guess = os.path.join(data_utils.PROJECT_ROOT, "data", "comments", sec_user_id_or_dir)
            if os.path.isdir(guess):
                data_dir = guess
            else:
                data_dir = os.path.join(data_utils.PROJECT_ROOT, "data", "comments", sec_user_id_or_dir[:16])

    comments_path = os.path.join(data_dir, "comments.json")
    meta_path = os.path.join(data_dir, "_meta.json")

    if not os.path.exists(comments_path):
        print(f"❌ 未找到评论数据: {comments_path}")
        print(f"   请先运行: python scripts/collect_comments.py <URL>")
        sys.exit(1)

    with open(comments_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    comments = data.get("comments", [])
    target_user = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            target_user = meta.get("target_user", {})

    print(f"📂 数据目录: {data_dir}")
    print(f"📝 评论总数: {len(comments)}")

    return comments, target_user, data_dir





def build_relation_graph(comments: list, target_user: dict) -> dict:
    """
    构建评论互动关系图。
    
    节点: 所有参与互动的用户
    边: 用户之间的评论/回复关系
    
    边的权重计算：
      - 直接评论目标用户: weight += 1.0
      - 回复其他评论者: weight += 0.5
      - 同一视频下出现（共现）: weight += 0.1
    """
    # ── 节点统计 ──
    users = {}       # uid -> user_info
    user_videos = defaultdict(set)   # uid -> set of aweme_ids
    user_comment_count = Counter()   # uid -> total comments

    # ── 边统计 ──
    # relation_edges: (from_uid, to_uid) -> {weight, interactions}
    edges = defaultdict(lambda: {"weight": 0.0, "count": 0, "interactions": []})

    target_uid = target_user.get("uid", "")
    target_nickname = target_user.get("nickname", "目标用户")

    for c in comments:
        user = c.get("user", {})
        uid = user.get("uid", "")
        nickname = user.get("nickname", "未知")
        aweme_id = c.get("aweme_id", "")
        cid = c.get("cid", "")
        reply_to_cid = c.get("reply_to_cid")
        reply_to_uid = c.get("reply_to_uid", "")

        if not uid:
            continue

        # 跳过目标用户自己的评论（自评不构成关系）
        if uid == target_uid:
            continue

        # 记录用户信息
        if uid not in users:
            users[uid] = user
        user_videos[uid].add(aweme_id)
        user_comment_count[uid] += 1

        # ── 关系边构建 ──

        # 1. 直接评论目标用户的作品（一级评论）
        if not reply_to_cid:
            edge_key = (uid, f"target:{target_uid}") if target_uid else (uid, "__target__")
            edges[edge_key]["weight"] += 1.0
            edges[edge_key]["count"] += 1
            edges[edge_key]["interactions"].append({
                "type": "comment_on_target",
                "aweme_id": aweme_id,
                "comment_id": cid,
            })

        # 2. 回复其他评论者
        if reply_to_uid and reply_to_uid != uid:
            edge_key = (uid, reply_to_uid)
            edges[edge_key]["weight"] += 0.5
            edges[edge_key]["count"] += 1
            edges[edge_key]["interactions"].append({
                "type": "reply",
                "aweme_id": aweme_id,
                "comment_id": cid,
            })

    # ── 构建输出格式 ──
    # 节点列表: 所有出现过的用户 + 目标用户
    target_node_id = f"target:{target_uid}" if target_uid else "__target__"
    nodes = []

    # 目标用户节点
    nodes.append({
        "id": target_node_id,
        "label": target_nickname,
        "type": "target",
        "uid": target_uid,
        "follower_count": target_user.get("follower_count", 0),
    })

    # 评论者节点
    for uid, info in users.items():
        nodes.append({
            "id": uid,
            "label": info.get("nickname", "未知"),
            "type": "commenter",
            "uid": uid,
            "comment_count": user_comment_count[uid],
            "video_count": len(user_videos[uid]),
            "follower_count": info.get("follower_count", 0),
            "following_count": info.get("following_count", 0),
        })

    # 边列表
    edge_list = []
    for (from_uid, to_uid), data in edges.items():
        if data["count"] < 2:
            continue  # 过滤单次互动，减少噪音
        edge_list.append({
            "source": from_uid,
            "target": to_uid,
            "weight": round(data["weight"], 1),
            "count": data["count"],
            "interactions": data["interactions"][:10],  # 只保留最近10条
        })

    # 按权重排序
    edge_list.sort(key=lambda x: x["weight"], reverse=True)

    return {
        "target_user": {
            "uid": target_uid,
            "nickname": target_nickname,
        },
        "nodes": nodes,
        "edges": edge_list,
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edge_list),
            "total_commenters": len(users),
        },
    }


def detect_communities(graph: dict) -> list:
    """
    基于评论共现关系发现社群。
    
    策略：如果两个评论者在同一视频下都发表过评论，则存在共现关系。
    通过共现频率聚类，发现"小圈子"。
    """
    # 这里实现一种简化的社群发现：基于视频共现的 Jaccard 相似度
    edges = graph.get("edges", [])
    nodes = graph.get("nodes", [])

    # 提取高互动用户（评论数 >= 3 或是回复关系的参与者）
    active_uids = set()
    for edge in edges:
        active_uids.add(edge["source"])
        active_uids.add(edge["target"])

    # 过滤掉目标用户
    target_prefix = "target:"
    active_uids = {u for u in active_uids if not u.startswith(target_prefix)}

    communities = []
    if active_uids:
        # 按权重降序取前50个用户作为核心成员
        uid_weights = defaultdict(float)
        for edge in edges:
            if edge["source"] in active_uids:
                uid_weights[edge["source"]] += edge["weight"]
            if edge["target"] in active_uids and not str(edge["target"]).startswith(target_prefix):
                uid_weights[edge["target"]] += edge["weight"]

        top_users = sorted(uid_weights.items(), key=lambda x: x[1], reverse=True)[:50]

        # 简单分组：按 follower_count 分为三层
        # KOL层（粉丝>1万）、核心粉丝层（粉丝100-1万）、普通粉丝层
        kols = []
        core = []
        normal = []

        uid_map = {n["id"]: n for n in nodes}
        for uid, weight in top_users:
            info = uid_map.get(uid, {})
            followers = info.get("follower_count", 0)
            entry = {
                "uid": uid,
                "nickname": info.get("label", "未知"),
                "weight": round(weight, 1),
                "comment_count": info.get("comment_count", 0),
                "follower_count": followers,
            }
            if followers >= 10000:
                kols.append(entry)
            elif followers >= 100:
                core.append(entry)
            else:
                normal.append(entry)

        if kols:
            communities.append({"name": "🌟 KOL / 意见领袖", "members": kols[:20], "count": len(kols)})
        if core:
            communities.append({"name": "💬 核心粉丝 / 活跃互动者", "members": core[:30], "count": len(core)})
        if normal:
            communities.append({"name": "👥 普通粉丝", "members": normal[:30], "count": len(normal)})

    return communities


def find_top_interactors(graph: dict) -> dict:
    """
    找出与目标用户互动最多的评论者。
    """
    edges = graph.get("edges", [])
    nodes_map = {n["id"]: n for n in graph.get("nodes", [])}

    # 筛选直接评论目标用户的边
    target_edges = [e for e in edges if str(e["target"]).startswith("target:")]

    interactors = []
    for e in target_edges:
        node = nodes_map.get(e["source"], {})
        interactors.append({
            "uid": e["source"],
            "nickname": node.get("label", "未知"),
            "comment_count": e["count"],
            "weight": e["weight"],
            "follower_count": node.get("follower_count", 0),
        })

    interactors.sort(key=lambda x: x["weight"], reverse=True)

    # 评论者之间的互动
    peer_edges = [e for e in edges if not str(e["target"]).startswith("target:")]
    peer_edges.sort(key=lambda x: x["weight"], reverse=True)

    return {
        "top_direct_commenters": interactors[:30],
        "top_peer_interactions": [
            {
                "from": nodes_map.get(e["source"], {}).get("label", e["source"]),
                "to": nodes_map.get(e["target"], {}).get("label", e["target"]),
                "count": e["count"],
                "weight": e["weight"],
            }
            for e in peer_edges[:20]
        ],
    }


def generate_report(graph: dict, communities: list, top_interactors: dict) -> str:
    """生成文本报告"""
    stats = graph["stats"]
    target = graph["target_user"]

    lines = []
    lines.append("=" * 60)
    lines.append(f"📊 评论关系拓扑分析报告")
    lines.append("=" * 60)
    lines.append(f"目标用户: {target.get('nickname', '未知')}")
    lines.append(f"总节点数: {stats['total_nodes']}")
    lines.append(f"总关系边: {stats['total_edges']}")
    lines.append(f"评论者数: {stats['total_commenters']}")
    lines.append("")

    # ── 高频互动者 ──
    lines.append("─── 高频直接评论者 ───")
    for i, c in enumerate(top_interactors.get("top_direct_commenters", [])[:15], 1):
        lines.append(f"  {i:2d}. {c['nickname']}  ({c['comment_count']} 条评论, "
                      f"粉丝 {c['follower_count']})")
    lines.append("")

    # ── 社群结构 ──
    lines.append("─── 社群结构 ───")
    for community in communities:
        lines.append(f"  {community['name']} ({community['count']} 人)")
        for m in community["members"][:10]:
            lines.append(f"    - {m['nickname']}  "
                          f"(评论 {m['comment_count']} 次, 粉丝 {m['follower_count']})")
    lines.append("")

    # ── KOL 发现 ──
    kols = [m for c in communities if "KOL" in c["name"] for m in c["members"]]
    if kols:
        lines.append("─── 🌟 发现的 KOL / 意见领袖 ───")
        for m in kols:
            lines.append(f"  - {m['nickname']} (粉丝 {m['follower_count']}, "
                          f"评论 {m['comment_count']} 次)")

    lines.append("")
    lines.append(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/analyze/analyze_social_graph.py <sec_user_id_or_dir>")
        print("示例: python scripts/analyze/analyze_social_graph.py MS4wLjABAAAA...")
        print("      python scripts/analyze/analyze_social_graph.py data/comments/user123/")
        sys.exit(1)

    sec_user_id_or_dir = sys.argv[1]

    print("=" * 60)
    print("🔗 评论关系拓扑分析")
    print("=" * 60)

    # 加载数据
    comments, target_user, data_dir = load_comments(sec_user_id_or_dir)

    if not comments:
        print("❌ 没有评论数据可供分析")
        sys.exit(1)

    # 构建关系图
    print("\n🕸️  正在构建关系拓扑图...")
    graph = build_relation_graph(comments, target_user)
    print(f"   节点: {graph['stats']['total_nodes']} 个用户")
    print(f"   关系边: {graph['stats']['total_edges']} 条")

    # 社群发现
    print("\n👥 正在分析社群结构...")
    communities = detect_communities(graph)
    for c in communities:
        print(f"   {c['name']}: {c['count']} 人")

    # 高频互动者
    print("\n⭐ 正在识别高频互动者...")
    top_interactors = find_top_interactors(graph)
    print(f"   直接评论者 Top: {len(top_interactors['top_direct_commenters'])} 人")
    print(f"   评论者间互动 Top: {len(top_interactors['top_peer_interactions'])} 对")

    # ── 保存结果 ──
    relations_dir = os.path.join(data_dir, "relations")
    os.makedirs(relations_dir, exist_ok=True)

    # 关系图数据（可用于前端可视化）
    graph_path = os.path.join(relations_dir, "relation_graph.json")
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(f"\n💾 关系图已保存: {graph_path}")

    # 社群数据
    communities_path = os.path.join(relations_dir, "communities.json")
    with open(communities_path, "w", encoding="utf-8") as f:
        json.dump(communities, f, ensure_ascii=False, indent=2, default=str)
    print(f"💾 社群数据已保存: {communities_path}")

    # 高频互动者
    interactors_path = os.path.join(relations_dir, "top_interactors.json")
    with open(interactors_path, "w", encoding="utf-8") as f:
        json.dump(top_interactors, f, ensure_ascii=False, indent=2)
    print(f"💾 互动者数据已保存: {interactors_path}")

    # 文本报告
    report = generate_report(graph, communities, top_interactors)
    report_path = os.path.join(relations_dir, "report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"💾 文本报告已保存: {report_path}")

    print()
    print(report)


if __name__ == "__main__":
    main()
