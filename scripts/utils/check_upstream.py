"""Check upstream repository update script.

Compares the local lib/ (from Evil0ctal/Douyin_TikTok_Download_API)
with the latest upstream code, filtering meaningful changes.

Usage:
    python scripts/utils/check_upstream.py                   # Check updates and show summary
    python scripts/utils/check_upstream.py --brief            # Show only changed file list
    python scripts/utils/check_upstream.py --apply <file>     # Apply single upstream file locally
    python scripts/utils/check_upstream.py --apply-all        # Apply all upstream changes
    python scripts/utils/check_upstream.py --auto             # Apply all changes (no prompt)
"""

import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORT))

from scripts.utils.paths import LIB_DIR, PROJECT_ROOT

UPSTREAM_REPO = "Evil0ctal/Douyin_TikTok_Download_API"
UPSTREAM_BRANCH = "main"

ROOT = str(PROJECT_ROOT)
LIB_DIR = str(LIB_DIR)

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
    """Determine if a file should be ignored (filter out noise)."""
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


def compute_blob_sha(filepath: str) -> str:
    """Compute the Git blob SHA1 hash for a local file.

    Git blob hash = sha1("blob {size}\\0{content}").
    This matches the SHA returned by GitHub's Git Trees API,
    allowing hash-based comparison without downloading files.
    """
    with open(filepath, "rb") as f:
        content = f.read()
    blob = f"blob {len(content)}\0".encode() + content
    return hashlib.sha1(blob).hexdigest()


def fetch_upstream_tree() -> dict:
    """
    Fetch upstream file tree with blob SHA hashes via GitHub API.

    Returns {file_path: {"sha": str, "url": str}} mapping.
    Uses blob SHA for efficient comparison — no need to download each file.
    """
    import urllib.request

    api_url = (
        f"https://api.github.com/repos/{UPSTREAM_REPO}/git/trees/{UPSTREAM_BRANCH}?recursive=1"
    )

    req = urllib.request.Request(api_url, headers={"User-Agent": "check-upstream/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"❌ Failed to fetch upstream repo info: {e}")
        print(f"   Please verify that {UPSTREAM_REPO} exists and is accessible")
        sys.exit(1)

    files = {}
    for item in data.get("tree", []):
        if item["type"] == "blob" and not should_ignore(item["path"]):
            files[item["path"]] = {
                "sha": item["sha"],
                "url": (
                    f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/{UPSTREAM_BRANCH}/{item['path']}"
                ),
            }
    return files


def get_local_file_hashes() -> dict:
    """Get blob SHA hashes for all local lib/ files.

    Returns {relative_path: blob_sha} mapping.
    """
    local_hashes = {}
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
            local_hashes[rel_path] = compute_blob_sha(str(fpath))
        except Exception:
            pass  # binary files

    return local_hashes


def fetch_upstream_content(file_path: str) -> str | None:
    """Download a single file from upstream."""
    import urllib.request

    url = f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/{UPSTREAM_BRANCH}/{file_path}"
    req = urllib.request.Request(url, headers={"User-Agent": "check-upstream/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"  ⚠️  Failed to fetch upstream {file_path}: {e}")
        return None


def check_updates() -> list:
    """
    Check upstream updates using blob SHA comparison (fast, no content download).

    Each element: {"file": str, "status": "added"|"modified"|"deleted",
                   "low_priority": bool, "sha": str}
    """
    print(f"🔍 Checking upstream updates: {UPSTREAM_REPO} @ {UPSTREAM_BRANCH}")
    print()

    upstream_files = fetch_upstream_tree()
    local_hashes = get_local_file_hashes()

    changes = []

    # Check for new or modified upstream files (using blob SHA)
    for fpath, info in upstream_files.items():
        upstream_sha = info["sha"]
        if fpath not in local_hashes:
            changes.append(
                {
                    "file": fpath,
                    "status": "added",
                    "low_priority": is_low_priority(fpath),
                    "sha": upstream_sha,
                }
            )
        elif local_hashes[fpath] != upstream_sha:
            changes.append(
                {
                    "file": fpath,
                    "status": "modified",
                    "low_priority": is_low_priority(fpath),
                    "sha": upstream_sha,
                }
            )

    # Check for files deleted upstream but still present locally
    for fpath in local_hashes:
        if fpath not in upstream_files:
            changes.append(
                {
                    "file": fpath,
                    "status": "deleted",
                    "low_priority": is_low_priority(fpath),
                    "sha": None,
                }
            )

    # Sort: low priority items last
    changes.sort(key=lambda x: (x["low_priority"], x["file"]))

    return changes


def apply_upstream_file(file_path: str) -> bool:
    """Download and apply a single upstream file to local lib/.

    Returns True on success, False on failure.
    """
    content = fetch_upstream_content(file_path)
    if content is None:
        return False

    local_path = os.path.join(LIB_DIR, file_path)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def print_changes(changes: list):
    """Print a clean summary of changes."""
    if not changes:
        print("✅ 上游无更新，本地 lib/ 已是最新")
        return

    high_count = sum(1 for c in changes if not c["low_priority"])
    low_count = sum(1 for c in changes if c["low_priority"])

    print(f"\n📊 发现 {len(changes)} 个文件变更:")
    if high_count:
        print(f"   🔴 源码变更: {high_count} 个")
    if low_count:
        print(f"   🟡 配置/依赖变更: {low_count} 个")
    print()

    status_icon = {"added": "🆕", "modified": "📝", "deleted": "🗑️"}
    for c in changes:
        icon = status_icon.get(c["status"], "❓")
        priority_tag = " 🟡" if c["low_priority"] else ""
        print(f"  {icon} [{c['status'].upper()}] {c['file']}{priority_tag}")

    print()


def apply_all(changes: list, yes: bool = False) -> int:
    """Apply all upstream changes.

    Args:
        changes: List of changes from check_updates().
        yes: Skip confirmation prompt if True.

    Returns:
        Number of successfully applied files.
    """
    if not changes:
        print("✅ 没有需要更新的文件")
        return 0

    print(f"📦 准备更新 {len(changes)} 个文件:")
    for c in changes:
        tag = " 🟡" if c["low_priority"] else ""
        print(f"   {c['file']}{tag}")
    print()

    if not yes:
        try:
            response = input("❓ 确认应用以上变更? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            response = "n"
        if response != "y":
            print("⏭️  已取消")
            return 0

    success = 0
    for c in changes:
        if c["status"] == "deleted":
            # File deleted upstream — leave it alone (don't delete local data)
            print(f"  ⏭️  [DELETED] {c['file']} (上游已删除，本地保留)")
            continue

        if apply_upstream_file(c["file"]):
            print(f"  ✅ [{'ADDED' if c['status'] == 'added' else 'UPDATED'}] {c['file']}")
            success += 1
        else:
            print(f"  ❌ [FAILED] {c['file']}")

    # Summary
    high_count = sum(1 for c in changes if not c["low_priority"])
    low_count = sum(1 for c in changes if c["low_priority"])
    print(f"\n📊 更新完成: {success}/{len(changes)} 个文件成功")
    if high_count:
        print(
            f"   🔴 源码: {sum(1 for c in changes if not c['low_priority'] and c['status'] != 'deleted')} 个"
        )
    if low_count:
        print(
            f"   🟡 配置: {sum(1 for c in changes if c['low_priority'] and c['status'] != 'deleted')} 个"
        )

    return success


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="检查上游仓库更新并同步到本地 lib/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s                     # 检查更新并显示变更\n"
            "  %(prog)s --brief             # 仅列出变更文件\n"
            "  %(prog)s --apply <file>      # 应用单个文件\n"
            "  %(prog)s --apply-all         # 批量应用所有变更（需确认）\n"
            "  %(prog)s --auto              # 一键应用所有变更（无提示）\n"
        ),
    )
    parser.add_argument("--brief", action="store_true", help="仅列出变更文件，不显示详细 diff")
    parser.add_argument(
        "--apply", type=str, metavar="<file>", help="将上游的指定文件应用到本地 lib/"
    )
    parser.add_argument("--apply-all", action="store_true", help="批量应用所有上游变更（需确认）")
    parser.add_argument(
        "--yes", "-y", action="store_true", help="跳过确认提示（配合 --apply-all 使用）"
    )
    parser.add_argument("--auto", action="store_true", help="一键更新: 等同于 --apply-all --yes")

    args = parser.parse_args()

    # --auto is shorthand for --apply-all --yes
    if args.auto:
        args.apply_all = True
        args.yes = True

    # --apply <file>: apply a single file
    if args.apply:
        print(f"📥 正在从上游获取: {args.apply}")
        if apply_upstream_file(args.apply):
            print(f"✅ 已更新: {args.apply}")
        else:
            print(f"❌ 更新失败: {args.apply}")
            sys.exit(1)
        return

    # Check for updates
    changes = check_updates()

    if not changes:
        print("✅ 上游无更新，本地 lib/ 已是最新")
        return

    # --apply-all or --auto: apply all changes
    if args.apply_all:
        print_changes(changes)
        apply_all(changes, yes=args.yes)
        return

    # Default: just show changes
    print_changes(changes)

    # Usage tips
    print("💡 提示:")
    if any(not c["low_priority"] for c in changes):
        print("   应用所有变更:  python scripts/utils/check_upstream.py --apply-all")
        print("   一键更新:      python scripts/utils/check_upstream.py --auto")
    print("   查看单个文件:   python scripts/utils/check_upstream.py --apply <文件路径>")


if __name__ == "__main__":
    main()
