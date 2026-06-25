"""Bootstrap or update the upstream crawler engine in lib/."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORT))

from scripts.utils.paths import LIB_DIR


UPSTREAM_URL = "https://github.com/Evil0ctal/Douyin_TikTok_Download_API.git"


def run(cmd: list[str]) -> None:
    """Run a command and fail fast."""
    subprocess.run(cmd, check=True)


def main() -> int:
    args = sys.argv[1:]
    update = "--update" in args

    if LIB_DIR.exists():
        if not (LIB_DIR / ".git").exists():
            if update:
                print(f"lib/ already exists but is not a Git checkout: {LIB_DIR}")
                print("Move it aside or remove it before using --update.")
                return 1
            print("lib/ already exists; leaving the local crawler engine in place.")
            return 0
        if update:
            print("Updating upstream crawler engine in lib/...")
            run(["git", "-C", str(LIB_DIR), "pull", "--ff-only"])
        else:
            print("lib/ already exists. Use --update to pull latest upstream changes.")
        return 0

    print(f"Cloning upstream crawler engine into {LIB_DIR}...")
    run(["git", "clone", UPSTREAM_URL, str(LIB_DIR)])
    print("Done. Run `uv run douyin cookies apply` after exporting cookies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
