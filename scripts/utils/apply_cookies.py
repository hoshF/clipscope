"""Cookie management utility.

Reads Netscape-format cookie files from cookies/ and updates crawler config.

Usage:
    python scripts/utils/apply_cookies.py              # Apply all cookies
    python scripts/utils/apply_cookies.py --check      # Check expiry only, don't apply
    python scripts/utils/apply_cookies.py --platform douyin  # Update Douyin only
"""

import os
import re
import sys
import time
from datetime import UTC, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_MAP = {
    "douyin": os.path.join(ROOT, "lib", "crawlers", "douyin", "web", "config.yaml"),
    "tiktok": os.path.join(ROOT, "lib", "crawlers", "tiktok", "web", "config.yaml"),
}

COOKIE_DIR = os.path.join(ROOT, "cookies")

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
        print(f"  ❌ File not found: {yaml_path}")
        return False

    with open(yaml_path, encoding="utf-8") as f:
        content = f.read()

    # Replace cookie line
    pattern = re.compile(r"^(      Cookie: ).*$", re.MULTILINE)
    if not pattern.search(content):
        pattern = re.compile(r"^(      Cookie: ).*", re.MULTILINE)

    new_content = pattern.sub(rf"\1{cookie_str}", content)

    if new_content == content:
        print("  ⚠️  Cookie content unchanged")
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
            tag = "⚠️ 关键" if name in critical else "  "
            warnings.append(
                f"  {tag} [已过期] {name} (过期于 {datetime.fromtimestamp(c['expires'], tz=UTC).strftime('%Y-%m-%d %H:%M')})"
            )
        elif remaining_days < 7:
            tag = "⚠️ 关键" if name in critical else "  "
            warnings.append(f"  {tag} [即将过期] {name} (剩余 {remaining_days:.0f} 天)")
        elif remaining_days < 30:
            if name in critical:
                warnings.append(f"     [关键] {name} (剩余 {remaining_days:.0f} 天)")

    return warnings


def print_cookie_summary(cookies: list[dict], platform: str):
    """Print cookie summary."""
    now = time.time()
    total = len(cookies)
    expired = sum(1 for c in cookies if 0 < c["expires"] <= now)
    critical_names = CRITICAL_COOKIES.get(platform, [])

    print(f"\n📊 {platform.upper()} Cookie stats:")
    print(f"   Total: {total} | Expired: {expired}")

    # 关键 cookie 状态
    cookie_map = {}
    for c in cookies:
        if c["expires"] > cookie_map.get(c["name"], {}).get("expires", 0):
            cookie_map[c["name"]] = c

    for name in critical_names:
        if name in cookie_map:
            c = cookie_map[name]
            remaining = c["expires"] - now
            status = "✅" if remaining > 86400 * 7 else ("⚠️" if remaining > 0 else "❌")
            exp_str = datetime.fromtimestamp(c["expires"], tz=UTC).strftime("%m/%d")
            print(f"   {status} {name}: 有效期至 {exp_str}")
        else:
            print(f"   ❌ {name}: 未找到")


def main():
    # 解析参数
    args = sys.argv[1:]
    check_only = "--check" in args
    platform_filter = None
    for a in args:
        if a.startswith("--platform="):
            platform_filter = a.split("=", 1)[1]

    platforms = [platform_filter] if platform_filter else ["douyin", "tiktok"]

    all_warnings = []
    any_updated = False

    for platform in platforms:
        cookie_file = os.path.join(COOKIE_DIR, f"{platform}.txt")
        yaml_file = CONFIG_MAP.get(platform)

        if not os.path.exists(cookie_file):
            print(f"\n⚠️ Cookie 文件不存在: {cookie_file}")
            continue

        print(f"\n{'=' * 50}")
        print(f"🔍 正在处理: {platform.upper()}")
        print(f"{'=' * 50}")

        cookies = parse_netscape_cookies(cookie_file)
        if not cookies:
            print("  ⚠️  未找到有效 cookie")
            continue

        print_cookie_summary(cookies, platform)

        # 检查过期
        warnings = check_expiry(cookies, platform)
        all_warnings.extend(warnings)

        if check_only:
            continue

        # 应用到配置
        cookie_str = cookies_to_header(cookies)
        print(f"\n  Cookie 长度: {len(cookie_str)} 字符")

        updated = update_yaml_cookie(yaml_file, cookie_str)
        if updated:
            print(f"  ✅ 已更新: {os.path.relpath(yaml_file, ROOT)}")
            any_updated = True
        else:
            print("  💤 无需更新")

    # ── 输出警告汇总 ──
    critical_warnings = [w for w in all_warnings if "关键" in w]
    other_warnings = [w for w in all_warnings if "关键" not in w]

    if critical_warnings:
        print(f"\n{'=' * 50}")
        print("⚠️  Cookie 过期警告")
        print("=" * 50)
        for w in critical_warnings:
            print(w)
        print("\n请及时更新 Cookie：")
        print("  1. 在浏览器中登录抖音/TikTok")
        print("  2. 用 Cookie-Editor 扩展导出 Netscape 格式")
        print("  3. 替换 cookies/ 目录下对应的 .txt 文件")
        print("  4. 运行: python scripts/apply_cookies.py")

    if other_warnings:
        for w in other_warnings:
            print(w)

    if not any_updated and not check_only:
        print("\n💡 使用 --check 参数可仅检查过期状态")

    return 1 if critical_warnings else 0


if __name__ == "__main__":
    sys.exit(main())
