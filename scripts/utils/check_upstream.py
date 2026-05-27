"""Check upstream repository update script.

Compares the local lib/ (from Evil0ctal/Douyin_TikTok_Download_API)
with the latest upstream code, filtering meaningful changes.

Usage:
    python scripts/utils/check_upstream.py                  # Check updates and show diffs
    python scripts/utils/check_upstream.py --brief           # Show only changed file list
    python scripts/utils/check_upstream.py --apply <file>    # Apply single upstream file locally
"""

import json
import os
import sys
from pathlib import Path

UPSTREAM_REPO = "Evil0ctal/Douyin_TikTok_Download_API"
UPSTREAM_BRANCH = "main"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(ROOT, "lib")

# Insignificant file/directory patterns (filter out, don't show diffs)
IGNORE_DIRS = {
    "__pycache__",
    ".github",
    ".idea",
    ".vscode",
    "Screenshots",
    "logo",
    "bash",
    "chrome-cookie-sniffer",
    "daemon",
}
IGNORE_FILES = {
    ".gitignore",
    ".gitattributes",
    "README.md",
    "README.en.md",
    "LICENSE",
    ".env",
    ".env.sample",
    ".dockerignore",
    "Dockerfile",
    "Procfile",
    "start.py",
    "start.sh",
    "docker-compose.yml",
    ".DS_Store",
}
IGNORE_EXTENSIONS = {".pyc", ".pyo", ".log"}


def should_ignore(file_path: str) -> bool:
    """Determine if a file should be ignored."""
    parts = file_path.split("/")
    filename = parts[-1]
    for part in parts[:-1]:
        if part in IGNORE_DIRS:
            return True
    if filename in IGNORE_FILES:
        return True
    if any(filename.endswith(ext) for ext in IGNORE_EXTENSIONS):
        return True
    return False


def is_low_priority(file_path: str) -> bool:
    """Determine if a file is low priority (config/dependency, not source logic)."""
    return file_path.split("/")[-1] in {"requirements.txt", "config.yaml"}


def fetch_upstream_tree() -> dict:
    """
    通过 GitHub API 获取上游仓库的文件列表及其原始内容 URL。

    返回 {file_path: download_url} 映射。
    """
    import urllib.request

    api_url = (
        f"https://api.github.com/repos/{UPSTREAM_REPO}/git/trees/{UPSTREAM_BRANCH}?recursive=1"
    )

    try:
        with urllib.request.urlopen(api_url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"❌ Failed to fetch upstream repo info: {e}")
        print(f"   Please verify that {UPSTREAM_REPO} exists and is accessible")
        sys.exit(1)

    files = {}
    for item in data.get("tree", []):
        if item["type"] == "blob" and not should_ignore(item["path"]):
            # Build raw file URL
            files[item["path"]] = (
                f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/{UPSTREAM_BRANCH}/{item['path']}"
            )

    return files


def get_local_files() -> dict:
    """Get all file contents from local lib/ directory."""
    local_files = {}
    lib_path = Path(LIB_DIR)

    if not lib_path.exists():
        print(f"❌ Local lib/ directory not found: {LIB_DIR}")
        sys.exit(1)

    for fpath in lib_path.rglob("*"):
        if not fpath.is_file():
            continue
        rel_path = str(fpath.relative_to(lib_path))
        if should_ignore(rel_path):
            continue
        try:
            local_files[rel_path] = fpath.read_text(encoding="utf-8")
        except Exception:
            pass  # 二进制文件跳过

    return local_files


def check_updates(brief: bool = False) -> list:
    """
    检查上游更新，返回变更文件列表。

    每个元素: {"file": str, "status": "added"|"modified"|"deleted", "low_priority": bool}
    """
    print(f"🔍 Checking upstream updates: {UPSTREAM_REPO} @ {UPSTREAM_BRANCH}")
    print()

    upstream_files = fetch_upstream_tree()
    local_files = get_local_files()

    changes = []

    # Check for new or modified upstream files
    for fpath, url in upstream_files.items():
        if fpath not in local_files:
            changes.append(
                {
                    "file": fpath,
                    "status": "added",
                    "low_priority": is_low_priority(fpath),
                }
            )
        else:
            # Compare content
            local_content = local_files[fpath]
            try:
                import urllib.request

                with urllib.request.urlopen(url, timeout=10) as resp:
                    upstream_content = resp.read().decode("utf-8")
                if local_content != upstream_content:
                    changes.append(
                        {
                            "file": fpath,
                            "status": "modified",
                            "low_priority": is_low_priority(fpath),
                        }
                    )
            except Exception:
                pass  # 网络问题跳过

    # Check for files that exist locally but were deleted upstream
    for fpath in local_files:
        if fpath not in upstream_files:
            changes.append(
                {
                    "file": fpath,
                    "status": "deleted",
                    "low_priority": is_low_priority(fpath),
                }
            )

    # Sort: low priority items last
    changes.sort(key=lambda x: (x["low_priority"], x["file"]))

    return changes


def show_diff(file_path: str):
    """显示某个文件的详细 diff"""
    upstream_url = (
        f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/{UPSTREAM_BRANCH}/{file_path}"
    )
    local_path = os.path.join(LIB_DIR, file_path)

    try:
        import urllib.request

        with urllib.request.urlopen(upstream_url, timeout=10) as resp:
            upstream_content = resp.read().decode("utf-8").splitlines(keepends=True)
    except Exception as e:
        print(f"  ⚠️  无法获取上游文件: {e}")
        return

    if not os.path.exists(local_path):
        # 新增文件
        print("  📄 上游新增文件（本地无此文件）:")
        for line in upstream_content[:30]:
            print(f"    + {line.rstrip()}")
        if len(upstream_content) > 30:
            print(f"    ... (共 {len(upstream_content)} 行)")
        return

    with open(local_path, encoding="utf-8") as f:
        local_content = f.readlines()

    # 简单的行对比
    import difflib

    diff = difflib.unified_diff(
        local_content,
        upstream_content,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    )
    diff_lines = list(diff)
    if diff_lines:
        # 限制显示行数
        show_lines = diff_lines[:60]
        for line in show_lines:
            print(f"  {line}")
        if len(diff_lines) > 60:
            print(f"  ... (还有 {len(diff_lines) - 60} 行差异)")
    else:
        print("  (内容相同)")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="检查上游仓库更新并对比本地 lib/ 差异",
    )
    parser.add_argument("--brief", action="store_true", help="仅列出变更文件，不显示详细 diff")
    parser.add_argument(
        "--apply", type=str, metavar="<file>", help="将上游的指定文件应用到本地 lib/"
    )

    args = parser.parse_args()

    if args.apply:
        # 应用单个文件
        upstream_url = (
            f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/{UPSTREAM_BRANCH}/{args.apply}"
        )
        local_path = os.path.join(LIB_DIR, args.apply)
        try:
            import urllib.request

            with urllib.request.urlopen(upstream_url, timeout=10) as resp:
                content = resp.read().decode("utf-8")
        except Exception as e:
            print(f"❌ 无法获取上游文件: {e}")
            sys.exit(1)

        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 已更新: {args.apply}")
        return

    changes = check_updates(brief=args.brief)

    if not changes:
        print("✅ 上游无更新，本地 lib/ 已是最新")
        return

    # 按类别统计
    high_count = sum(1 for c in changes if not c["low_priority"])
    low_count = sum(1 for c in changes if c["low_priority"])

    print(f"\n📊 发现 {len(changes)} 个文件变更:")
    if high_count:
        print(f"   🔴 源码变更: {high_count} 个")
    if low_count:
        print(f"   🟡 配置/依赖变更: {low_count} 个")
    print()

    # 输出变更列表
    for c in changes:
        status_icon = {"added": "🆕", "modified": "📝", "deleted": "🗑️"}
        icon = status_icon.get(c["status"], "❓")
        priority_tag = " 🟡" if c["low_priority"] else ""
        print(f"  {icon} [{c['status'].upper()}] {c['file']}{priority_tag}")

        if not args.brief and c["status"] != "deleted" and not c["low_priority"]:
            show_diff(c["file"])
            print()

    # 使用提示
    print("\n💡 提示:")
    print("   查看单个文件 diff:  python scripts/utils/check_upstream.py --brief")
    print("   应用单个文件:      python scripts/utils/check_upstream.py --apply <文件路径>")


if __name__ == "__main__":
    main()
