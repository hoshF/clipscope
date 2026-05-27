"""Batch download all videos from a Douyin user's profile.

Usage:
    python download_user_videos.py <user_profile_url>

Example:
    python download_user_videos.py "https://www.douyin.com/user/MS4wLjABAAAA..."

Dependencies:
    Ensure cookies are configured before running:
      1. Export Netscape format cookies to cookies/douyin.txt using Cookie-Editor
      2. Run: python scripts/utils/apply_cookies.py
      Or just run this script directly; it will auto-check and remind you.
"""

import asyncio
import json
import os
import re
import sys
import time

import aiofiles
import httpx

LIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)


def check_cookie_expiry() -> bool:
    """Check if douyin cookies are expired and print warnings.

    Inspects the expires field of each cookie in cookies/douyin.txt.
    Prints warnings if any are expired or expiring within 7 days.

    Returns:
        True if cookies are valid, False if file missing or expired.
    """
    cookie_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies", "douyin.txt")
    if not os.path.exists(cookie_file):
        print("⚠️  Cookie file not found: cookies/douyin.txt")
        print("   Please export Douyin cookies to this file using Cookie-Editor")
        print("   Then run: python scripts/utils/apply_cookies.py\n")
        return False

    now = time.time()
    expired = []
    expiring_soon = []

    with open(cookie_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip #HttpOnly_ prefix
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_") :]

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
        print("❌  Cookies expired! Please update promptly")
        print(f"   Expired: {', '.join(expired)}")
        print("   Update steps:")
        print("     1. Log in to https://www.douyin.com in your browser")
        print("     2. Export Netscape format using Cookie-Editor")
        print("     3. Replace cookies/douyin.txt contents")
        print("     4. Run: python scripts/utils/apply_cookies.py\n")
        return False

    if expiring_soon:
        print(f"⚠️  Critical cookies expiring soon: {', '.join(expiring_soon)}")
        print("   Recommend updating soon\n")

    return True


from crawlers.douyin.web.web_crawler import DouyinWebCrawler
from crawlers.hybrid.hybrid_crawler import HybridCrawler


def extract_sec_user_id(url: str) -> str:
    """Extract sec_user_id from a Douyin user profile URL."""
    # Format: https://www.douyin.com/user/MS4wLjABAAAA...
    match = re.search(r"/user/([^/?]+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"Unable to extract sec_user_id from URL: {url}")


async def download_video(video_url: str, filepath: str, headers: dict) -> bool:
    """Download a single video file."""
    try:
        # Connect directly, no proxy (avoids SOCKS proxy issues)
        transport = httpx.AsyncHTTPTransport(proxy=None, local_address="0.0.0.0")
        async with httpx.AsyncClient(timeout=120.0, transport=transport) as client:
            async with client.stream("GET", video_url, headers=headers) as resp:
                if resp.status_code != 200:
                    print(f"  ⚠️ Download failed, HTTP {resp.status_code}")
                    return False
                async with aiofiles.open(filepath, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        await f.write(chunk)
                return True
    except Exception as e:
        print(f"  ⚠️ Download error: {e}")
        return False


async def main():
    if len(sys.argv) < 2:
        print("Usage: python download_user_videos.py <douyin_user_profile_url>")
        print(
            'Example: python download_user_videos.py "https://www.douyin.com/user/MS4wLjABAAAA..."'
        )
        sys.exit(1)

    if not check_cookie_expiry():
        print("⚠️  Continue? (y/N): ", end="")
        # Non-interactive mode: continue by default
        pass

    url = sys.argv[1]
    sec_user_id = extract_sec_user_id(url)
    print(f"🔍 User sec_user_id: {sec_user_id}")

    output_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "downloads", sec_user_id[:16]
    )
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Download directory: {output_dir}")

    meta = {"sec_user_id": sec_user_id, "url": url, "downloaded_at": time.time()}
    with open(os.path.join(output_dir, "_meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("📄 Metadata saved")

    douyin_crawler = DouyinWebCrawler()
    hybrid_crawler = HybridCrawler()

    print("\n📋 Fetching video list...")
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

            aweme_list = result.get("aweme_list", [])
            all_videos.extend(aweme_list)

            max_cursor = result.get("max_cursor", 0)
            has_more = result.get("has_more", False)

            print(f"  Page {page}: got {len(aweme_list)} videos (total {len(all_videos)})")

            if not aweme_list:
                break

        except Exception as e:
            print(f"  ❌ Failed to fetch page {page}: {e}")
            break

    print(f"\n✅ Total: {len(all_videos)} videos fetched")

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
        desc = video.get("desc", "(no title)")[:40]
        aweme_type = video.get("aweme_type")
        print(f"\n[{idx}/{len(all_videos)}] Video ID: {aweme_id} (type={aweme_type})")
        print(f"  Desc: {desc}")

        is_image = aweme_type in (2, 68)
        ext = ".jpg" if is_image else ".mp4"

        safe_desc = "".join(c for c in desc if c.isalnum() or c in " _-").strip() or "video"
        filename = f"{idx:03d}_{aweme_id}_{safe_desc}{ext}"
        filepath = os.path.join(output_dir, filename)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
            print("  ⏭️ Already exists, skipping")
            skip_count += 1
            continue

        try:
            parsed = await hybrid_crawler.hybrid_parsing_single_video(
                url=f"https://www.douyin.com/video/{aweme_id}",
                minimal=True,
            )

            media_type = parsed.get("type", "video")

            if media_type == "image" or is_image:
                image_data = parsed.get("image_data", {})
                image_urls = image_data.get("no_watermark_image_list", []) or image_data.get(
                    "watermark_image_list", []
                )
                if not image_urls:
                    images = video.get("images", [])
                    image_urls = [
                        img.get("url_list", [None])[0] for img in images if img.get("url_list")
                    ]
                    image_urls = [u for u in image_urls if u]

                if image_urls:
                    img_dir = os.path.join(output_dir, f"{idx:03d}_{aweme_id}")
                    os.makedirs(img_dir, exist_ok=True)
                    dl_ok = 0
                    for ii, img_url in enumerate(image_urls):
                        img_path = os.path.join(img_dir, f"{ii + 1:02d}.jpg")
                        if await download_video(img_url, img_path, headers):
                            dl_ok += 1
                    print(f"  ✅ Album download complete ({dl_ok}/{len(image_urls)} images)")
                    success_count += 1
                else:
                    print("  ❌ Failed to get album download links")
                    fail_count += 1
            else:
                video_data = parsed.get("video_data", {})
                download_url = (
                    video_data.get("nwm_video_url_HQ")
                    or video_data.get("nwm_video_url")
                    or video_data.get("wm_video_url_HQ")
                    or video_data.get("wm_video_url")
                )

                if not download_url:
                    video_info = video.get("video", {}) or {}
                    play_addr = video_info.get("play_addr", {}) or {}
                    url_list = play_addr.get("url_list", [])
                    download_url = url_list[0] if url_list else None

                if not download_url:
                    print("  ❌ Failed to get download URL")
                    fail_count += 1
                    continue

                print("  ⬇️ Downloading...")
                success = await download_video(download_url, filepath, headers)

                if success:
                    size_mb = os.path.getsize(filepath) / 1024 / 1024
                    print(f"  ✅ Download complete ({size_mb:.1f} MB)")
                    success_count += 1
                else:
                    fail_count += 1

            await asyncio.sleep(1.5)  # Rate limit: avoid triggering anti-crawl

        except Exception as e:
            print(f"  ❌ Parse/download failed: {e}")
            fail_count += 1

    print("\n" + "=" * 50)
    print("📊 Download summary")
    print(f"  Total videos: {len(all_videos)}")
    print(f"  ✅ Success: {success_count}")
    print(f"  ❌ Failed: {fail_count}")
    print(f"  ⏭️ Skipped: {skip_count}")
    print(f"  📁 Save path: {output_dir}")
    print("=" * 50)

    try:
        rename_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "scripts", "download", "rename_user_dirs.py"
        )
        print("\n📦 Download complete, running rename script...")
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
            print("✅ Rename script completed successfully")
        else:
            print(f"❌ Rename script returned code {proc.returncode}")
    except Exception as e:
        print(f"❌ Failed to run rename script: {e}")


if __name__ == "__main__":
    asyncio.run(main())
