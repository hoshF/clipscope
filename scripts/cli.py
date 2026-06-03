#!/usr/bin/env python3
"""Unified CLI entry point for the social-archive-douyin toolkit.

Usage:
    uv run douyin sync [--dry-run]
    uv run douyin feed [--loop] [--interval N]
    uv run douyin comments <url> [--max-posts N] [--max-comments N] [--no-replies] [--resume]
    uv run douyin analyze fan-portrait <user>
    uv run douyin analyze social-graph <user>
    uv run douyin analyze identity <user>
    uv run douyin analyze commenter-value <user> [--top N]
    uv run douyin analyze recommend-portrait
    uv run douyin upstream check
    uv run douyin upstream update
    uv run douyin upstream apply <file>
    uv run douyin cookies apply
"""

from __future__ import annotations

import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)


def _run_script(script_path: str, args: list[str] | None = None) -> None:
    """Run a script via subprocess, forwarding stdout/stderr.

    Args:
        script_path: Relative path from scripts/ (e.g. "download/sync_downloads.py").
        args: Additional arguments to pass to the script.
    """
    full_path = os.path.join(SCRIPTS_DIR, script_path)
    if not os.path.exists(full_path):
        print(f"❌ Script not found: {full_path}", file=sys.stderr)
        sys.exit(1)

    cmd = [sys.executable, full_path] + (args or [])
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    sys.exit(result.returncode)


def cmd_sync(args: list[str]) -> None:
    """Incremental sync download: check and fetch new videos."""
    _run_script("download/sync_downloads.py", args)


def cmd_feed(args: list[str]) -> None:
    """Recommendation feed collector (scheduled task)."""
    _run_script("collect/feed_collector.py", args)


def cmd_comments(args: list[str]) -> None:
    """Full comment collection for a Douyin user."""
    _run_script("collect/collect_comments.py", args)


def cmd_analyze_fan_portrait(args: list[str]) -> None:
    """Fan portrait analysis (comment-based)."""
    _run_script("analyze/analyze_fan_portrait.py", args)


def cmd_analyze_social_graph(args: list[str]) -> None:
    """Social graph analysis from comment interactions."""
    _run_script("analyze/analyze_social_graph.py", args)


def cmd_analyze_identity(args: list[str]) -> None:
    """Identity mining from comments and post descriptions."""
    _run_script("analyze/analyze_identity_mining.py", args)


def cmd_analyze_commenter_value(args: list[str]) -> None:
    """Commenter value assessment tool."""
    _run_script("analyze/analyze_commenter_value.py", args)


def cmd_analyze_recommend_portrait(_: list[str]) -> None:
    """Recommendation feed profile inference."""
    _run_script("analyze/analyze_recommend_portrait.py")


def cmd_upstream_check(_: list[str]) -> None:
    """Check upstream repository for updates."""
    _run_script("utils/check_upstream.py", ["--brief"])


def cmd_upstream_update(_: list[str]) -> None:
    """Update local lib/ from upstream (auto mode)."""
    _run_script("utils/check_upstream.py", ["--auto"])


def cmd_logs(args: list[str]) -> None:
    """Log management: show status, clean empty logs."""
    log_dir = os.path.join(PROJECT_ROOT, "data", "logs")

    if not os.path.isdir(log_dir):
        print("📂 No log directory found at data/logs/")
        return

    if args and args[0] == "clean":
        # Clean empty logs
        import glob

        empty = glob.glob(os.path.join(log_dir, "*.log"))
        empty = [f for f in empty if os.path.getsize(f) == 0]
        if not empty:
            print("✅ No empty log files to clean")
            return
        for f in empty:
            os.remove(f)
            print(f"  🗑️  removed: {os.path.basename(f)}")
        print(f"\n✅ Removed {len(empty)} empty log files")
        return

    if args and args[0] == "prune":
        # Remove logs older than N days
        days = int(args[1]) if len(args) > 1 else 30
        import glob
        import time

        cutoff = time.time() - days * 86400
        pruned = 0
        for f in glob.glob(os.path.join(log_dir, "*.log")):
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
                pruned += 1
        print(f"✅ Removed {pruned} log files older than {days} days")
        return

    # Default: show status
    import glob

    files = sorted(glob.glob(os.path.join(log_dir, "*.log")))
    total = len(files)
    total_size = sum(os.path.getsize(f) for f in files)
    empty_count = sum(1 for f in files if os.path.getsize(f) == 0)
    print(f"📂 data/logs/  —  {total} files, {_fmt_size(total_size)}")
    print(f"   Empty: {empty_count}  |  With content: {total - empty_count}")
    print()
    if files:
        for f in files[-10:]:
            size = os.path.getsize(f)
            mtime = os.path.basename(f).replace(".log", "").replace("-", ":")
            label = " (empty)" if size == 0 else ""
            print(f"   {mtime}  {_fmt_size(size)}{label}")
        if len(files) > 10:
            print(f"   ... ({len(files) - 10} older files hidden)")
    print()
    print("Commands:")
    print("  uv run douyin logs clean      Remove empty log files")
    print("  uv run douyin logs prune [N]  Remove logs older than N days (default: 30)")


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.0f}KB"
    return f"{size / 1024 / 1024:.1f}MB"


def cmd_upstream_apply(args: list[str]) -> None:
    """Apply a specific upstream file to local lib/."""
    _run_script("utils/check_upstream.py", ["--apply"] + (args or []))


def cmd_cookies(args: list[str]) -> None:
    """Cookie management: apply, check, or clear."""
    _run_script("utils/apply_cookies.py", args)


def cmd_config(_: list[str]) -> None:
    """Show config file locations and management guide."""
    print("""Config Architecture
===================
  config.yaml                        Our app settings (API, crawler defaults)
  cookies/douyin.txt                 Douyin cookies (Netscape format)
  cookies/tiktok.txt                 TikTok cookies
  lib/crawlers/douyin/web/config.yaml   Douyin crawler config (auto-updated)
  lib/crawlers/bilibili/web/config.yaml  Bilibili crawler config

Cookie Management
==================
  1. Export cookies from browser → cookies/douyin.txt
  2. Run: uv run douyin cookies apply

  Commands:
    uv run douyin cookies apply              Apply cookies from files
    uv run douyin cookies -- --check         Check expiry only
    uv run douyin cookies -- --clear         Clear cookies from configs
    uv run douyin cookies -- --platform=tiktok  Single platform
""")


def print_help() -> None:
    """Print the main help message."""
    print("""social-archive-douyin CLI
Usage: uv run douyin <command> [options]

Commands:
  sync [--dry-run]                    Incremental sync download
  feed [--loop] [--interval N]        Feed collector (scheduled task)

  comments <url> [options]            Comment collection

  analyze fan-portrait <user>         Fan portrait analysis
  analyze social-graph <user>         Social graph analysis
  analyze identity <user>             Identity mining
  analyze commenter-value <user>      Commenter value assessment
  analyze recommend-portrait          Recommendation profile inference

  upstream check                      Check upstream updates
  upstream update                     Apply all upstream changes
  upstream apply <file>               Apply single upstream file

  cookies apply                       Apply cookies from files
  cookies --check                     Check cookie expiry
  cookies --clear                     Clear cookies from configs

  config                              Show config structure guide

  logs [clean|prune]                  Log management (status / clean / prune)

Run 'uv run douyin <command> --help' for detailed help on each command.
""")


def main() -> None:
    """CLI entry point - dispatches to the appropriate subcommand."""
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print_help()
        return

    cmd = sys.argv[1]
    cmd_args = sys.argv[2:]

    # Commands that need sub-subcommand parsing
    if cmd == "analyze":
        if not cmd_args or cmd_args[0] in ("-h", "--help"):
            print("""analyze subcommands:
  fan-portrait <user>         Fan portrait analysis
  social-graph <user>         Social graph analysis
  identity <user>             Identity mining
  commenter-value <user>      Commenter value assessment
  recommend-portrait          Recommendation profile inference
""")
            return
        sub_cmd = cmd_args[0]
        sub_args = cmd_args[1:]
        dispatch_analyze(sub_cmd, sub_args)
    elif cmd == "upstream":
        if not cmd_args or cmd_args[0] in ("-h", "--help"):
            print("""upstream subcommands:
  check            Check upstream updates
  update           Apply all upstream changes
  apply <file>     Apply single upstream file
""")
            return
        sub_cmd = cmd_args[0]
        sub_args = cmd_args[1:]
        dispatch_upstream(sub_cmd, sub_args)
    else:
        dispatch_top(cmd, cmd_args)


def dispatch_top(cmd: str, args: list[str]) -> None:
    """Dispatch top-level commands."""
    dispatch = {
        "sync": cmd_sync,
        "feed": cmd_feed,
        "comments": cmd_comments,
        "cookies": cmd_cookies,
        "config": cmd_config,
        "logs": cmd_logs,
    }
    if cmd in dispatch:
        dispatch[cmd](args)
    else:
        print(f"❌ Unknown command: {cmd}\n", file=sys.stderr)
        print_help()
        sys.exit(1)


def dispatch_analyze(cmd: str, args: list[str]) -> None:
    """Dispatch analyze subcommands."""
    dispatch = {
        "fan-portrait": cmd_analyze_fan_portrait,
        "social-graph": cmd_analyze_social_graph,
        "identity": cmd_analyze_identity,
        "commenter-value": cmd_analyze_commenter_value,
        "recommend-portrait": cmd_analyze_recommend_portrait,
    }
    if cmd in dispatch:
        dispatch[cmd](args)
    else:
        print(f"❌ Unknown analyze subcommand: {cmd}\n", file=sys.stderr)
        sys.exit(1)


def dispatch_upstream(cmd: str, args: list[str]) -> None:
    """Dispatch upstream subcommands."""
    dispatch = {
        "check": cmd_upstream_check,
        "update": cmd_upstream_update,
        "apply": cmd_upstream_apply,
    }
    if cmd in dispatch:
        dispatch[cmd](args)
    else:
        print(f"❌ Unknown upstream subcommand: {cmd}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
