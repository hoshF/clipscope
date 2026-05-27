"""User comment social graph analysis tool.

Builds interaction networks from collected comment data to discover
core fan circles, communities, and opinion leaders.

Usage:
    python scripts/analyze/analyze_social_graph.py <sec_user_id_or_dir>

Example:
    # Analyze comment relationships for a user
    python scripts/analyze/analyze_social_graph.py MS4wLjABAAAA...

    # Specify data directory
    python scripts/analyze/analyze_social_graph.py data/comments/user123/

Output:
    data/comments/<sec_user_id>/
        └── relations/
            ├── relation_graph.json       Graph data (nodes + edges)
            ├── communities.json          Community detection results
            ├── top_interactors.json      Top interactors ranking
            └── report.txt                Text report
"""

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from utils import data_utils


def load_comments(sec_user_id_or_dir: str) -> tuple:
    """Load comment data.

    Returns (comments_list, target_user_info).
    """
    # Check if sec_user_id or directory path
    if os.path.isdir(sec_user_id_or_dir):
        data_dir = sec_user_id_or_dir
    else:
        data_dir = data_utils.find_comment_dir(sec_user_id_or_dir)
        if not data_dir:
            # Fallback: try as direct directory name match
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
        print(f"❌ Comment data not found: {comments_path}")
        print("   Please run: python scripts/collect_comments.py <URL>")
        sys.exit(1)

    with open(comments_path, encoding="utf-8") as f:
        data = json.load(f)

    comments = data.get("comments", [])
    target_user = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
            target_user = meta.get("target_user", {})

    print(f"📂 Data directory: {data_dir}")
    print(f"📝 Total comments: {len(comments)}")

    return comments, target_user, data_dir


def build_relation_graph(comments: list, target_user: dict) -> dict:
    """Build a comment interaction relationship graph.

    Nodes: all users who participated in interactions.
    Edges: comment/reply relationships between users.

    Edge weight calculation:
      - Direct comment on target: weight += 1.0
      - Reply to another commenter: weight += 0.5
      - Co-occurrence in same video: weight += 0.1
    """
    # Node statistics
    users = {}  # uid -> user_info
    user_videos = defaultdict(set)  # uid -> set of aweme_ids
    user_comment_count = Counter()  # uid -> total comments

    # Edge statistics
    # relation_edges: (from_uid, to_uid) -> {weight, interactions}
    edges = defaultdict(lambda: {"weight": 0.0, "count": 0, "interactions": []})

    target_uid = target_user.get("uid", "")
    target_nickname = target_user.get("nickname", "(target user)")

    for c in comments:
        user = c.get("user", {})
        uid = user.get("uid", "")
        aweme_id = c.get("aweme_id", "")
        cid = c.get("cid", "")
        reply_to_cid = c.get("reply_to_cid")
        reply_to_uid = c.get("reply_to_uid", "")

        if not uid:
            continue

        # Skip target user's own comments (self-comments don't form relationships)
        if uid == target_uid:
            continue

        # Record user info
        if uid not in users:
            users[uid] = user
        user_videos[uid].add(aweme_id)
        user_comment_count[uid] += 1

        # Edge construction

        # 1. Direct comment on target's post (top-level comment)
        if not reply_to_cid:
            edge_key = (uid, f"target:{target_uid}") if target_uid else (uid, "__target__")
            edges[edge_key]["weight"] += 1.0
            edges[edge_key]["count"] += 1
            edges[edge_key]["interactions"].append(
                {
                    "type": "comment_on_target",
                    "aweme_id": aweme_id,
                    "comment_id": cid,
                }
            )

        # 2. Reply to another commenter
        if reply_to_uid and reply_to_uid != uid:
            edge_key = (uid, reply_to_uid)
            edges[edge_key]["weight"] += 0.5
            edges[edge_key]["count"] += 1
            edges[edge_key]["interactions"].append(
                {
                    "type": "reply",
                    "aweme_id": aweme_id,
                    "comment_id": cid,
                }
            )

    # Build output format
    # Nodes: all users who appeared + target user
    target_node_id = f"target:{target_uid}" if target_uid else "__target__"
    nodes = []

    # Target user node
    nodes.append(
        {
            "id": target_node_id,
            "label": target_nickname,
            "type": "target",
            "uid": target_uid,
            "follower_count": target_user.get("follower_count", 0),
        }
    )

    # Commenter nodes
    for uid, info in users.items():
        nodes.append(
            {
                "id": uid,
                "label": info.get("nickname", "(unknown)"),
                "type": "commenter",
                "uid": uid,
                "comment_count": user_comment_count[uid],
                "video_count": len(user_videos[uid]),
                "follower_count": info.get("follower_count", 0),
                "following_count": info.get("following_count", 0),
            }
        )

    # 边列表
    edge_list = []
    for (from_uid, to_uid), data in edges.items():
        if data["count"] < 2:
            continue  # Filter single interactions to reduce noise
        edge_list.append(
            {
                "source": from_uid,
                "target": to_uid,
                "weight": round(data["weight"], 1),
                "count": data["count"],
                "interactions": data["interactions"][:10],  # Keep last 10 only
            }
        )

    # Sort by weight
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
    """Detect communities based on comment co-occurrence.

    Strategy: if two commenters both commented on the same video,
    they have a co-occurrence relationship. Cluster by frequency
    to discover "cliques".
    """
    # Simplified community detection: Jaccard similarity based on video co-occurrence
    edges = graph.get("edges", [])
    nodes = graph.get("nodes", [])

    # Extract highly interactive users (>=3 comments or participated in replies)
    active_uids = set()
    for edge in edges:
        active_uids.add(edge["source"])
        active_uids.add(edge["target"])

    # Filter out target user
    target_prefix = "target:"
    active_uids = {u for u in active_uids if not u.startswith(target_prefix)}

    communities = []
    if active_uids:
        # Take top 50 users by weight as core members
        uid_weights = defaultdict(float)
        for edge in edges:
            if edge["source"] in active_uids:
                uid_weights[edge["source"]] += edge["weight"]
            if edge["target"] in active_uids and not str(edge["target"]).startswith(target_prefix):
                uid_weights[edge["target"]] += edge["weight"]

        top_users = sorted(uid_weights.items(), key=lambda x: x[1], reverse=True)[:50]

        # Simple grouping by follower_count into 3 tiers
        # KOL (>10K), Core fans (100-10K), Regular fans (<100)
        kols = []
        core = []
        normal = []

        uid_map = {n["id"]: n for n in nodes}
        for uid, weight in top_users:
            info = uid_map.get(uid, {})
            followers = info.get("follower_count", 0)
            entry = {
                "uid": uid,
                "nickname": info.get("label", "(unknown)"),
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
            communities.append(
                {"name": "🌟 KOLs / Opinion Leaders", "members": kols[:20], "count": len(kols)}
            )
        if core:
            communities.append(
                {
                    "name": "💬 Core Fans / Active Interactors",
                    "members": core[:30],
                    "count": len(core),
                }
            )
        if normal:
            communities.append(
                {"name": "👥 Regular Fans", "members": normal[:30], "count": len(normal)}
            )

    return communities


def find_top_interactors(graph: dict) -> dict:
    """Find the commenters who interact most with the target user."""
    edges = graph.get("edges", [])
    nodes_map = {n["id"]: n for n in graph.get("nodes", [])}

    # Filter edges that directly target the target user
    target_edges = [e for e in edges if str(e["target"]).startswith("target:")]

    interactors = []
    for e in target_edges:
        node = nodes_map.get(e["source"], {})
        interactors.append(
            {
                "uid": e["source"],
                "nickname": node.get("label", "(unknown)"),
                "comment_count": e["count"],
                "weight": e["weight"],
                "follower_count": node.get("follower_count", 0),
            }
        )

    interactors.sort(key=lambda x: x["weight"], reverse=True)

    # Inter-commenter interactions
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
    """Generate a text report."""
    stats = graph["stats"]
    target = graph["target_user"]

    lines = []
    lines.append("=" * 60)
    lines.append("📊 Comment Relationship Topology Report")
    lines.append("=" * 60)
    lines.append(f"Target user: {target.get('nickname', '(unknown)')}")
    lines.append(f"Total nodes: {stats['total_nodes']}")
    lines.append(f"Total edges: {stats['total_edges']}")
    lines.append(f"Commenters: {stats['total_commenters']}")
    lines.append("")

    # Top interactors
    lines.append("─── Top Direct Commenters ───")
    for i, c in enumerate(top_interactors.get("top_direct_commenters", [])[:15], 1):
        lines.append(
            f"  {i:2d}. {c['nickname']}  ({c['comment_count']} comments, {c['follower_count']} followers)"
        )
    lines.append("")

    # Community structure
    lines.append("─── Community Structure ───")
    for community in communities:
        lines.append(f"  {community['name']} ({community['count']} 人)")
        for m in community["members"][:10]:
            lines.append(
                f"    - {m['nickname']}  ({m['comment_count']} comments, {m['follower_count']} followers)"
            )
    lines.append("")

    # KOL discovery
    kols = [m for c in communities if "KOL" in c["name"] for m in c["members"]]
    if kols:
        lines.append("─── 🌟 Discovered KOLs ───")
        for m in kols:
            lines.append(
                f"  - {m['nickname']} ({m['follower_count']} followers, {m['comment_count']} comments)"
            )

    lines.append("")
    lines.append(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze/analyze_social_graph.py <sec_user_id_or_dir>")
        print("Example: python scripts/analyze/analyze_social_graph.py MS4wLjABAAAA...")
        print("         python scripts/analyze/analyze_social_graph.py data/comments/user123/")
        sys.exit(1)

    sec_user_id_or_dir = sys.argv[1]

    print("=" * 60)
    print("🔗 Comment Relationship Topology Analysis")
    print("=" * 60)

    # Load data
    comments, target_user, data_dir = load_comments(sec_user_id_or_dir)

    if not comments:
        print("❌ No comment data available for analysis")
        sys.exit(1)

    # Build relationship graph
    print("\n🕸️  Building relationship graph...")
    graph = build_relation_graph(comments, target_user)
    print(f"   Nodes: {graph['stats']['total_nodes']} users")
    print(f"   Edges: {graph['stats']['total_edges']}")

    # Community detection
    print("\n👥 Analyzing community structure...")
    communities = detect_communities(graph)
    for c in communities:
        print(f"   {c['name']}: {c['count']} people")

    # Top interactors
    print("\n⭐ Identifying top interactors...")
    top_interactors = find_top_interactors(graph)
    print(f"   Top direct commenters: {len(top_interactors['top_direct_commenters'])} users")
    print(f"   Top peer interactions: {len(top_interactors['top_peer_interactions'])} pairs")

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
