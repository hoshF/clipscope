"""
Cookie 应用工具

从 cookies/ 目录下的 Netscape 格式 cookie 文件读取并更新到爬虫配置中。

用法:
    python scripts/apply_cookies.py              # 应用所有 cookie
    python scripts/apply_cookies.py --check      # 仅检查过期状态，不应用
    python scripts/apply_cookies.py --platform douyin  # 仅更新抖音
"""

import os
import re
import sys
import time
from datetime import UTC, datetime

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 配置文件路径映射
CONFIG_MAP = {
    "douyin": os.path.join(ROOT, "lib", "crawlers", "douyin", "web", "config.yaml"),
    "tiktok": os.path.join(ROOT, "lib", "crawlers", "tiktok", "web", "config.yaml"),
}

# Cookie 文件路径
COOKIE_DIR = os.path.join(ROOT, "cookies")

# 关键 Cookie（用于过期判断）
CRITICAL_COOKIES = {
    "douyin": ["sessionid", "sid_tt", "ttwid", "__ac_nonce", "__ac_signature"],
    "tiktok": ["sessionid", "ttwid", "msToken"],
}


def parse_netscape_cookies(filepath: str) -> list[dict]:
    """解析 Netscape 格式的 cookie 文件。

    处理 #HttpOnly_ 前缀、注释行和制表符分隔的字段。
    每个返回值包含 name、value、expires 和 domain。

    Args:
        filepath: Netscape 格式 cookie 文件路径。

    Returns:
        cookie 字典列表，每个字典包含 name、value、expires、domain 字段。
        文件不存在或为空时返回空列表。
    """
    cookies = []
    if not os.path.exists(filepath):
        return cookies

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # 去掉 #HttpOnly_ 前缀
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
    """将 cookie 列表转换为请求头 Cookie 字符串。

    自动去重：同名 cookie 保留最后一个值。
    过滤空 key 的条目。

    Args:
        cookies: parse_netscape_cookies 返回的 cookie 字典列表。

    Returns:
        "key1=value1; key2=value2" 格式的 Cookie 字符串。
    """
    # 去重：保留最后一个同名 cookie
    seen = {}
    for c in cookies:
        seen[c["name"]] = c["value"]
    # 过滤空 key
    seen.pop("", None)
    return "; ".join(f"{k}={v}" for k, v in seen.items())


def update_yaml_cookie(yaml_path: str, cookie_str: str) -> bool:
    """更新 YAML 配置文件中的 Cookie 字段。

    读取 YAML 文件，更新 cookie 字段并写回。
    如果文件不存在则跳过。

    Args:
        yaml_path: YAML 配置文件路径。
        cookie_str: cookies_to_header 生成的 Cookie 字符串。

    Returns:
        True 表示更新成功，False 表示文件不存在或写入失败。
    """
    if not os.path.exists(yaml_path):
        print(f"  ❌ 文件不存在: {yaml_path}")
        return False

    with open(yaml_path, encoding="utf-8") as f:
        content = f.read()

    # 替换 Cookie 行
    pattern = re.compile(r"^(      Cookie: ).*$", re.MULTILINE)
    if not pattern.search(content):
        pattern = re.compile(r"^(      Cookie: ).*", re.MULTILINE)

    new_content = pattern.sub(rf"\1{cookie_str}", content)

    if new_content == content:
        print("  ⚠️  Cookie 内容无变化")
        return False

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def check_expiry(cookies: list[dict], platform: str) -> list[str]:
    """检查 cookie 过期状态，返回警告信息列表"""
    now = time.time()
    warnings = []
    critical = CRITICAL_COOKIES.get(platform, [])

    # 按名称分组取最新的
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
    """打印 cookie 概要"""
    now = time.time()
    total = len(cookies)
    expired = sum(1 for c in cookies if 0 < c["expires"] <= now)
    critical_names = CRITICAL_COOKIES.get(platform, [])

    print(f"\n📊 {platform.upper()} Cookie 统计:")
    print(f"   总数: {total} | 已过期: {expired}")

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
