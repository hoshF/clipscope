"""Cookie management utility.

Reads Netscape-format cookie files from cookies/ and updates crawler config.

Usage:
    uv run douyin cookies apply                     # Apply all cookies
    uv run douyin cookies -- --check                # Check expiry only, don't apply
    uv run douyin cookies -- --clear                # Clear cookies from config files
    uv run douyin cookies -- --platform=douyin      # Update Douyin only
"""

import logging
import os
import re
import sys
import time
from datetime import UTC, datetime

from clipscope.utils.crawler_config import CONFIG_OVERRIDE_DIR
from clipscope.utils.paths import COOKIES_DIR, PROJECT_ROOT

logger = logging.getLogger(__name__)

OVERRIDE_DIR = CONFIG_OVERRIDE_DIR

CONFIG_MAP = {
    "douyin": str(OVERRIDE_DIR / "douyin" / "web" / "config.yaml"),
    "tiktok": str(OVERRIDE_DIR / "tiktok" / "web" / "config.yaml"),
}

ROOT = str(PROJECT_ROOT)
COOKIE_DIR = str(COOKIES_DIR)

# Critical cookies (for expiry checking)
CRITICAL_COOKIES = {
    "douyin": ["sessionid", "sid_tt", "ttwid", "__ac_nonce", "__ac_signature"],
    "tiktok": ["sessionid", "ttwid", "msToken"],
}


def parse_netscape_cookies(filepath: str) -> list[dict]:
    """Parse a Netscape-format cookie file.

    Handles #HttpOnly_ prefix, comment lines, tab-separated fields.
    Each returned cookie has name, value, expires, and domain.

    Args:
        filepath: Path to Netscape-format cookie file.

    Returns:
        List of cookie dicts with name, value, expires, domain fields.
        Returns empty list if file does not exist.
    """
    cookies = []
    if not os.path.exists(filepath):
        return cookies

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Strip #HttpOnly_ prefix
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_") :]
            elif line.startswith("#") and not line.startswith("#HttpOnly"):
                continue

            parts = line.split("\t")
            if len(parts) >= 7:
                cookies.append(
                    {
                        "name": parts[5],
                        "value": parts[6],
                        "expires": int(parts[4]) if parts[4].isdigit() else 0,
                        "domain": parts[0],
                    }
                )
    return cookies


def cookies_to_header(cookies: list[dict]) -> str:
    """Convert cookie list to a Cookie header string.

    Deduplicates by keeping the last value for each cookie name.
    Filters out empty-key entries.

    Args:
        cookies: List of cookie dicts from parse_netscape_cookies.

    Returns:
        Cookie string in "key1=value1; key2=value2" format.
    """
    # Deduplicate: keep last value per name
    seen = {}
    for c in cookies:
        seen[c["name"]] = c["value"]
    # Filter empty keys
    seen.pop("", None)
    return "; ".join(f"{k}={v}" for k, v in seen.items())


def update_yaml_cookie(yaml_path: str, cookie_str: str) -> bool:
    """Update the cookie field in a YAML config file.

    Reads the YAML file, updates the cookie field, and writes back.
    Skips if file does not exist.

    Args:
        yaml_path: Path to the YAML config file.
        cookie_str: Cookie string from cookies_to_header.

    Returns:
        True on success, False if file does not exist or write fails.
    """
    if not os.path.exists(yaml_path):
        logger.error("  File not found: %s", yaml_path)
        return False

    with open(yaml_path, encoding="utf-8") as f:
        content = f.read()

    # Replace cookie line — handles both "Cookie: value" and "Cookie:" (empty)
    pattern = re.compile(r"^(      Cookie:).*$", re.MULTILINE)
    if not pattern.search(content):
        logger.warning("  No Cookie field found in %s", os.path.relpath(yaml_path, ROOT))
        return False

    new_content = pattern.sub(rf"\1 {cookie_str}", content)

    if new_content == content:
        logger.info("  Cookie content unchanged")
        return False

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def check_expiry(cookies: list[dict], platform: str) -> list[str]:
    """Check cookie expiry status, return list of warnings."""
    now = time.time()
    warnings = []
    critical = CRITICAL_COOKIES.get(platform, [])

    # Group by name, take the latest
    cookie_map = {}
    for c in cookies:
        if c["expires"] > cookie_map.get(c["name"], {}).get("expires", 0):
            cookie_map[c["name"]] = c

    for name, c in cookie_map.items():
        remaining = c["expires"] - now
        remaining_days = remaining / 86400

        if remaining <= 0:
            tag = "CRITICAL" if name in critical else ""
            warnings.append(
                f"  {tag} [EXPIRED] {name} (since {datetime.fromtimestamp(c['expires'], tz=UTC).strftime('%Y-%m-%d %H:%M')})"
            )
        elif remaining_days < 7:
            tag = "CRITICAL" if name in critical else ""
            warnings.append(f"  {tag} [EXPIRING] {name} ({remaining_days:.0f} days left)")
        elif remaining_days < 30:
            if name in critical:
                warnings.append(f"     [CRITICAL] {name} ({remaining_days:.0f} days left)")

    return warnings


def print_cookie_summary(cookies: list[dict], platform: str):
    """Print cookie summary."""
    now = time.time()
    total = len(cookies)
    expired = sum(1 for c in cookies if 0 < c["expires"] <= now)
    critical_names = CRITICAL_COOKIES.get(platform, [])

    logger.info("%s Cookie stats:", platform.upper())
    logger.info("   Total: %d | Expired: %d", total, expired)

    cookie_map = {}
    for c in cookies:
        if c["expires"] > cookie_map.get(c["name"], {}).get("expires", 0):
            cookie_map[c["name"]] = c

    for name in critical_names:
        if name in cookie_map:
            c = cookie_map[name]
            remaining = c["expires"] - now
            status = "valid" if remaining > 86400 * 7 else ("expiring" if remaining > 0 else "expired")
            exp_str = datetime.fromtimestamp(c["expires"], tz=UTC).strftime("%m/%d")
            logger.info("   %s %s: expires %s", status, name, exp_str)
        else:
            logger.warning("   %s: not found", name)


def clear_cookies(platform: str) -> bool:
    yaml_file = CONFIG_MAP.get(platform)
    if not yaml_file or not os.path.exists(yaml_file):
        logger.error("  Config not found: %s", yaml_file)
        return False

    with open(yaml_file, encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(r"^(      Cookie:).*$", re.MULTILINE)
    if not pattern.search(content):
        logger.warning("  No Cookie field found in %s config", platform)
        return False

    new_content = pattern.sub(r"\1", content)
    with open(yaml_file, "w", encoding="utf-8") as f:
        f.write(new_content)
    logger.info("  Cleared Cookie in %s", os.path.relpath(yaml_file, ROOT))
    return True


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    clear_mode = "--clear" in args
    platform_filter = None
    for a in args:
        if a.startswith("--platform="):
            platform_filter = a.split("=", 1)[1]

    platforms = [platform_filter] if platform_filter else ["douyin", "tiktok"]

    if clear_mode:
        logger.info("Clearing cookies from config files...")
        for platform in platforms:
            clear_cookies(platform)
        logger.info("Done. Run 'uv run douyin cookies apply' to restore from cookies/*.txt")
        return 0

    all_warnings = []
    any_updated = False

    for platform in platforms:
        cookie_file = os.path.join(COOKIE_DIR, f"{platform}.txt")
        yaml_file = CONFIG_MAP.get(platform)

        if not os.path.exists(cookie_file):
            logger.warning("Cookie file not found: %s", cookie_file)
            continue

        logger.info("=" * 50)
        logger.info("Processing: %s", platform.upper())
        logger.info("=" * 50)

        cookies = parse_netscape_cookies(cookie_file)
        if not cookies:
            logger.warning("  No valid cookies found")
            continue

        print_cookie_summary(cookies, platform)
        warnings = check_expiry(cookies, platform)
        all_warnings.extend(warnings)

        if check_only:
            continue

        cookie_str = cookies_to_header(cookies)
        logger.info("  Cookie length: %d chars", len(cookie_str))

        updated = update_yaml_cookie(yaml_file, cookie_str)
        if updated:
            logger.info("  Updated: %s", os.path.relpath(yaml_file, ROOT))
            any_updated = True
        else:
            logger.info("  No update needed")

    critical_warnings = [w for w in all_warnings if "CRITICAL" in w]
    other_warnings = [w for w in all_warnings if "CRITICAL" not in w]

    if critical_warnings:
        logger.warning("=" * 50)
        logger.warning("Cookie expiry warnings")
        logger.warning("=" * 50)
        for w in critical_warnings:
            logger.warning(w)
        logger.warning("Please update your cookies:")
        logger.warning("  1. Log in to Douyin/TikTok in a browser")
        logger.warning("  2. Export cookies in Netscape format with Cookie-Editor")
        logger.warning("  3. Replace the corresponding .txt files in cookies/")
        logger.warning("  4. Run: uv run douyin cookies apply")

    if other_warnings:
        for w in other_warnings:
            logger.info(w)

    if not any_updated and not check_only:
        logger.info("Use --check to check expiry without applying")

    return 1 if critical_warnings else 0


if __name__ == "__main__":
    sys.exit(main())
