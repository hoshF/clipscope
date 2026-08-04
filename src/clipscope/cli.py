#!/usr/bin/env python3
"""Unified CLI entry point for the ClipScope toolkit.

Usage:
    uv run douyin sync [--dry-run]
    uv run douyin grab <url> <target_dir>
    uv run douyin track add <url>
    uv run douyin track list
    uv run douyin track remove <sec_user_id>
    uv run douyin feed [--loop] [--interval N]
    uv run douyin comments <url> [options]
    uv run douyin cookies apply
    uv run douyin config
    uv run douyin logs [clean|prune]
"""

from __future__ import annotations

import asyncio
import os
import sys


def _err(msg: str) -> None:
    sys.stderr.write(f"\u274c {msg}\n")


def cmd_sync(args: list[str]) -> None:
    from clipscope.collector.sync import main, parse_args

    parsed = parse_args(args)
    asyncio.run(main(parsed))


def cmd_grab(args: list[str]) -> None:
    from clipscope.collector.grab import main

    sys.argv = ["grab", *args]
    asyncio.run(main())


def cmd_track(args: list[str]) -> None:
    from clipscope.collector.track import main

    sys.argv = ["track", *args]
    main()


def cmd_feed(args: list[str]) -> None:
    from clipscope.collector.feed import main, parse_args

    parsed = parse_args(args)
    asyncio.run(main(parsed))


def cmd_comments(args: list[str]) -> None:
    from clipscope.collector.comments import main

    sys.argv = ["comments", *args]
    asyncio.run(main())


def cmd_cookies(args: list[str]) -> None:
    from clipscope.utils.apply_cookies import main

    sys.argv = ["cookies", *args]
    main()


def cmd_config(_: list[str]) -> None:
    print("""Config Architecture
===================
  config.yaml                                  ClipScope app settings
  cookies/douyin.txt                           Douyin cookies (Netscape format)
  cookies/tiktok.txt                           TikTok cookies
  src/clipscope/crawler/douyin/web/config.yaml  Douyin crawler config
  src/clipscope/crawler/bilibili/web/config.yaml Bilibili crawler config

Cookie Management
==================
  1. Export cookies from browser -> cookies/douyin.txt
  2. Run: uv run douyin cookies apply

  Commands:
    uv run douyin cookies apply              Apply cookies from files
    uv run douyin cookies -- --check         Check expiry only
    uv run douyin cookies -- --clear         Clear cookies from configs
    uv run douyin cookies -- --platform=tiktok  Single platform
""")


def cmd_logs(args: list[str]) -> None:
    from pathlib import Path as _Path

    from clipscope.utils.paths import PROJECT_ROOT as PROOT

    log_dir = _Path(str(PROOT)) / "data" / "logs"

    if not log_dir.is_dir():
        print("No log directory found at data/logs/")
        return

    if args and args[0] == "clean":
        import glob

        empty = glob.glob(str(log_dir / "*.log"))
        empty = [f for f in empty if os.path.getsize(f) == 0]
        if not empty:
            print("No empty log files to clean")
            return
        for f in empty:
            os.remove(f)
            print(f"  removed: {os.path.basename(f)}")
        print(f"\nRemoved {len(empty)} empty log files")
        return

    if args and args[0] == "prune":
        days = int(args[1]) if len(args) > 1 else 30
        import glob
        import time

        cutoff = time.time() - days * 86400
        pruned = 0
        for f in glob.glob(str(log_dir / "*.log")):
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
                pruned += 1
        print(f"Removed {pruned} log files older than {days} days")
        return

    import glob

    files = sorted(glob.glob(str(log_dir / "*.log")))
    total = len(files)
    total_size = sum(os.path.getsize(f) for f in files)
    empty_count = sum(1 for f in files if os.path.getsize(f) == 0)
    print(f"data/logs/ - {total} files, {_fmt_size(total_size)}")
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


def print_help() -> None:
    print("""ClipScope CLI
Usage: uv run douyin <command> [options]

Commands:
  sync [--dry-run]                    Incremental sync download
  grab <url> <dir>                    Download images/video from a single post
  track add <url>                     Add a user to tracking
  track list                          List tracked users
  track remove <sec_user_id>          Remove a user from tracking
  feed [--loop] [--interval N]        Feed collector (scheduled task)
  comments <url> [options]            Comment collection
  cookies apply                       Apply cookies from files
  cookies -- --check                  Check cookie expiry
  cookies -- --clear                  Clear cookies from configs
  config                              Show config structure guide
  logs [clean|prune]                  Log management (status / clean / prune)

Run 'uv run douyin <command> --help' for detailed help on each command.
""")


def main() -> None:
    from clipscope.utils.logging import setup_logging

    setup_logging()

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print_help()
        return

    cmd = sys.argv[1]
    cmd_args = sys.argv[2:]

    dispatch = {
        "sync": cmd_sync,
        "grab": cmd_grab,
        "track": cmd_track,
        "feed": cmd_feed,
        "comments": cmd_comments,
        "cookies": cmd_cookies,
        "config": cmd_config,
        "logs": cmd_logs,
    }

    if cmd in dispatch:
        dispatch[cmd](cmd_args)
    else:
        _err(f"Unknown command: {cmd}\n")
        print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
