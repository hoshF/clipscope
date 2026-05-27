"""
抖音用户主页所有视频批量下载工具

使用方式：
    python download_user_videos.py <用户主页URL>
    
示例：
    python download_user_videos.py "https://www.douyin.com/user/MS4wLjABAAAAJI9sVoEAVQU3r8Cp4ubMw3mrhO3aGNNEuM-M-S2oy3PjW5gGM5vYrgAcIsTNzMfh"
    
依赖：
    运行前确保已配置 Cookie：
      1. 用 Cookie-Editor 导出 Netscape 格式 Cookie 到 cookies/douyin.txt
      2. 运行: python scripts/apply_cookies.py
      或直接运行本脚本，会自动检查和提醒
"""

import asyncio
import json
import os
import sys
import re
import time
import httpx
import aiofiles
from datetime import datetime, timezone
import asyncio as _asyncio

# ── 将 lib 加入 Python 路径 ──
LIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)


# ── Cookie 过期检查 ──
def check_cookie_expiry():
    """检查 douyin cookie 是否过期，过期则提醒"""
    cookie_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies", "douyin.txt")
    if not os.path.exists(cookie_file):
        print("⚠️  Cookie 文件不存在: cookies/douyin.txt")
        print("   请先用 Cookie-Editor 导出抖音 Cookie 到该文件")
        print("   然后运行: python scripts/apply_cookies.py\n")
        return False

    now = time.time()
    expired = []
    expiring_soon = []

    with open(cookie_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 去掉 #HttpOnly_ 前缀
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_"):]

            parts = line.split("\t")
            if len(parts) >= 7:
                name = parts[5]
                expiry = int(parts[4]) if parts[4].isdigit() else 0
                if 0 < expiry <= now:
                    expired.append(name)
                elif expiry > now and (expiry - now) / 86400 < 7:
                    if name in ("sessionid", "sid_tt", "__ac_nonce"):
                        expiring_soon.append(name)

    if expired:
        print("❌  Cookie 已过期！请及时更新")
        print(f"   过期项: {', '.join(expired)}")
        print("   更新步骤:")
        print("     1. 浏览器登录 https://www.douyin.com")
        print("     2. 用 Cookie-Editor 导出 Netscape 格式")
        print(f"     3. 替换 cookies/douyin.txt 内容")
        print(f"     4. 运行: python scripts/apply_cookies.py\n")
        return False

    if expiring_soon:
        print(f"⚠️  关键 Cookie 即将过期: {', '.join(expiring_soon)}")
        print(f"   建议尽快更新\n")

    return True

from crawlers.douyin.web.web_crawler import DouyinWebCrawler
from crawlers.hybrid.hybrid_crawler import HybridCrawler


def extract_sec_user_id(url: str) -> str:
    """从抖音用户主页 URL 中提取 sec_user_id"""
    # 格式: https://www.douyin.com/user/MS4wLjABAAAA...
    match = re.search(r"/user/([^/?]+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"无法从 URL 中提取 sec_user_id: {url}")


async def download_video(video_url: str, filepath: str, headers: dict) -> bool:
    """下载单个视频文件"""
    try:
        # 不使用代理，直接连接（避免 SOCKS 代理问题）
        transport = httpx.AsyncHTTPTransport(proxy=None, local_address="0.0.0.0")
        async with httpx.AsyncClient(timeout=120.0, transport=transport) as client:
            async with client.stream("GET", video_url, headers=headers) as resp:
                if resp.status_code != 200:
                    print(f"  ⚠️ 下载失败，HTTP {resp.status_code}")
                    return False
                async with aiofiles.open(filepath, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        await f.write(chunk)
                return True
    except Exception as e:
        print(f"  ⚠️ 下载异常: {e}")
        return False


async def main():
    if len(sys.argv) < 2:
        print("用法: python download_user_videos.py <抖音用户主页URL>")
        print("示例: python download_user_videos.py \"https://www.douyin.com/user/MS4wLjABAAAA...\"")
        sys.exit(1)

    # ── Cookie 过期检查 ──
    if not check_cookie_expiry():
        print("⚠️  是否继续？(y/N): ", end="")
        # 非交互模式默认继续
        pass

    url = sys.argv[1]
    sec_user_id = extract_sec_user_id(url)
    print(f"🔍 用户 sec_user_id: {sec_user_id}")

    # 创建下载目录
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "downloads", sec_user_id[:16])
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 下载目录: {output_dir}")

    # 保存元数据（供后续同步使用）
    meta = {"sec_user_id": sec_user_id, "url": url, "downloaded_at": time.time()}
    with open(os.path.join(output_dir, "_meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"📄 元数据已保存")

    # 初始化爬虫
    douyin_crawler = DouyinWebCrawler()
    hybrid_crawler = HybridCrawler()

    # ── 第一步：获取用户所有视频列表（分页） ──
    print("\n📋 正在获取视频列表...")
    all_videos = []
    max_cursor = 0
    has_more = True
    page = 0

    while has_more:
        page += 1
        try:
            result = await douyin_crawler.fetch_user_post_videos(
                sec_user_id=sec_user_id,
                max_cursor=max_cursor,
                count=20,
            )
            
            # 解析结果
            aweme_list = result.get("aweme_list", [])
            all_videos.extend(aweme_list)
            
            # 更新分页信息
            max_cursor = result.get("max_cursor", 0)
            has_more = result.get("has_more", False)
            
            print(f"  第 {page} 页: 获取到 {len(aweme_list)} 个视频 (累计 {len(all_videos)} 个)")
            
            if not aweme_list:
                break
                
        except Exception as e:
            print(f"  ❌ 获取第 {page} 页失败: {e}")
            break

    print(f"\n✅ 共获取到 {len(all_videos)} 个视频")

    # ── 第二步：解析并下载每个视频 ──
    success_count = 0
    fail_count = 0
    skip_count = 0

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.douyin.com/",
    }

    for idx, video in enumerate(all_videos, 1):
        aweme_id = video.get("aweme_id", "")
        desc = video.get("desc", "无标题")[:40]
        aweme_type = video.get("aweme_type")
        print(f"\n[{idx}/{len(all_videos)}] 视频 ID: {aweme_id} (type={aweme_type})")
        print(f"  描述: {desc}")

        # 判断是否为图集（抖音图集 type=2 或 68）
        is_image = aweme_type in (2, 68)
        ext = ".jpg" if is_image else ".mp4"

        # 跳过已下载的文件
        safe_desc = "".join(c for c in desc if c.isalnum() or c in " _-").strip() or "video"
        filename = f"{idx:03d}_{aweme_id}_{safe_desc}{ext}"
        filepath = os.path.join(output_dir, filename)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
            print(f"  ⏭️ 已存在，跳过")
            skip_count += 1
            continue

        try:
            # 使用混合解析获取无水印链接
            parsed = await hybrid_crawler.hybrid_parsing_single_video(
                url=f"https://www.douyin.com/video/{aweme_id}",
                minimal=True,
            )

            media_type = parsed.get("type", "video")

            if media_type == "image" or is_image:
                # ── 图集：下载所有图片 ──
                image_data = parsed.get("image_data", {})
                image_urls = image_data.get("no_watermark_image_list", []) or image_data.get("watermark_image_list", [])
                if not image_urls:
                    # 从原始数据中提取
                    images = video.get("images", [])
                    image_urls = [img.get("url_list", [None])[0] for img in images if img.get("url_list")]
                    image_urls = [u for u in image_urls if u]

                if image_urls:
                    img_dir = os.path.join(output_dir, f"{idx:03d}_{aweme_id}")
                    os.makedirs(img_dir, exist_ok=True)
                    dl_ok = 0
                    for ii, img_url in enumerate(image_urls):
                        img_path = os.path.join(img_dir, f"{ii+1:02d}.jpg")
                        if await download_video(img_url, img_path, headers):
                            dl_ok += 1
                    print(f"  ✅ 图集下载完成 ({dl_ok}/{len(image_urls)} 张)")
                    success_count += 1
                else:
                    print(f"  ❌ 无法获取图集下载链接")
                    fail_count += 1
            else:
                # ── 视频：获取无水印链接 ──
                video_data = parsed.get("video_data", {})
                download_url = (
                    video_data.get("nwm_video_url_HQ")
                    or video_data.get("nwm_video_url")
                    or video_data.get("wm_video_url_HQ")
                    or video_data.get("wm_video_url")
                )

                if not download_url:
                    # 从原始 aweme_list 数据中提取
                    video_info = video.get("video", {}) or {}
                    play_addr = video_info.get("play_addr", {}) or {}
                    url_list = play_addr.get("url_list", [])
                    download_url = url_list[0] if url_list else None

                if not download_url:
                    print(f"  ❌ 无法获取下载链接")
                    fail_count += 1
                    continue

                print(f"  ⬇️ 正在下载...")
                success = await download_video(download_url, filepath, headers)

                if success:
                    size_mb = os.path.getsize(filepath) / 1024 / 1024
                    print(f"  ✅ 下载完成 ({size_mb:.1f} MB)")
                    success_count += 1
                else:
                    fail_count += 1

            # 适当延时，避免被风控
            await asyncio.sleep(1.5)

        except Exception as e:
            print(f"  ❌ 解析/下载失败: {e}")
            fail_count += 1

    # ── 输出统计 ──
    print("\n" + "=" * 50)
    print("📊 下载统计")
    print(f"  总视频数: {len(all_videos)}")
    print(f"  ✅ 成功: {success_count}")
    print(f"  ❌ 失败: {fail_count}")
    print(f"  ⏭️ 跳过: {skip_count}")
    print(f"  📁 保存路径: {output_dir}")
    print("=" * 50)

    # ── 下载完成后自动运行重命名脚本 ──
    try:
        rename_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "download", "rename_user_dirs.py")
        print("\n📦 下载完成，正在运行重命名脚本 scripts/download/rename_user_dirs.py ...")
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            rename_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if out:
            try:
                print(out.decode().strip())
            except Exception:
                print(out)
        if err:
            try:
                print(err.decode().strip(), file=sys.stderr)
            except Exception:
                print(err, file=sys.stderr)
        if proc.returncode == 0:
            print("✅ 重命名脚本执行成功")
        else:
            print(f"❌ 重命名脚本返回码 {proc.returncode}")
    except Exception as e:
        print(f"❌ 无法执行重命名脚本: {e}")


if __name__ == "__main__":
    asyncio.run(main())

