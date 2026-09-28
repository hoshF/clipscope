"""yt-dlp backed downloader for platforms ClipScope's crawlers do not cover.

Handles YouTube and Bilibili single-video downloads by delegating to yt-dlp,
which resolves formats, DASH audio/video streams, merging, and cookies.

Usage:
    from clipscope.collector.downloader import detect_platform, resolve_cookies, download

    platform = detect_platform(url)
    if platform:
        download(url, target_dir, resolve_cookies(platform))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from clipscope.utils.paths import COOKIES_DIR

logger = logging.getLogger(__name__)

YOUTUBE = "youtube"
BILIBILI = "bilibili"
YTDLP_PLATFORMS = (YOUTUBE, BILIBILI)

_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_BILIBILI_HOSTS = ("bilibili.com", "b23.tv")

DEFAULT_BROWSER = "chrome"


@dataclass(frozen=True)
class CookiePlan:
    """Cookie sources for a download, in priority order.

    Attributes:
        file: Path to a Netscape-format cookie file, if one exists.
        browser: Browser to read cookies from when no file is available.
    """

    file: str | None = None
    browser: str | None = None


def _hostname(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.hostname:
        parsed = urlparse(f"//{url}")
    return parsed.hostname or ""


def _matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def detect_platform(url: str) -> str | None:
    """Identify which yt-dlp platform a URL belongs to.

    Args:
        url: Video URL pasted by the user.

    Returns:
        "youtube" or "bilibili" for supported platforms, None otherwise.
    """
    host = _hostname(url).lower()
    if _matches(host, _YOUTUBE_HOSTS):
        return YOUTUBE
    if _matches(host, _BILIBILI_HOSTS):
        return BILIBILI
    return None


def resolve_cookies(platform: str, cookies_dir: str | None = None) -> CookiePlan:
    """Resolve a cookie plan: cookies/<platform>.txt, else browser, else none.

    Args:
        platform: Platform name, e.g. "youtube".
        cookies_dir: Override for the cookies directory (mainly for tests).

    Returns:
        A CookiePlan describing which cookie source to use.
    """
    base = Path(cookies_dir) if cookies_dir else COOKIES_DIR
    cookie_file = base / f"{platform}.txt"
    if cookie_file.is_file():
        return CookiePlan(file=str(cookie_file))
    return CookiePlan(browser=DEFAULT_BROWSER)


def build_ydl_opts(plan: CookiePlan, target_dir: str) -> dict:
    """Build the yt-dlp option dict for a single-video download.

    Args:
        plan: Cookie source selection.
        target_dir: Directory the merged video is written to.

    Returns:
        Options dict for yt_dlp.YoutubeDL.
    """
    opts: dict = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "paths": {"home": str(target_dir)},
        "outtmpl": "%(title)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if plan.file:
        opts["cookiefile"] = plan.file
    elif plan.browser:
        opts["cookiesfrombrowser"] = (plan.browser,)
    return opts


def grab_ytdlp(url: str, target_dir: str, ydl_factory=None) -> bool | None:
    """Download a URL through yt-dlp when it belongs to a supported platform.

    Args:
        url: Video URL.
        target_dir: Directory to write the merged video into.
        ydl_factory: yt_dlp.YoutubeDL replacement, for tests.

    Returns:
        None when the URL is not a yt-dlp platform, otherwise True on
        success and False on failure.
    """
    platform = detect_platform(url)
    if platform is None:
        return None
    logger.info("Downloading %s via yt-dlp: %s", platform, url)
    return download(url, target_dir, resolve_cookies(platform), ydl_factory=ydl_factory)


def _open_ydl(plan: CookiePlan, target_dir: str, ydl_factory):
    """Build a yt-dlp client and force its lazy cookie load to happen now.

    yt-dlp extracts cookies only when ``cookiejar`` is first accessed, which
    would otherwise happen mid-download and be indistinguishable from a
    download error. Touching it here isolates cookie problems.
    """
    ydl = ydl_factory(build_ydl_opts(plan, target_dir))
    _ = ydl.cookiejar
    return ydl


def download(
    url: str,
    target_dir: str,
    plan: CookiePlan,
    ydl_factory=None,
) -> bool:
    """Download a single video into target_dir.

    yt-dlp loads cookies lazily, on first access to its cookie jar. That load
    is forced before downloading, so a cookie failure means the browser
    cookies could not be read and only then does it fall back to a cookieless
    attempt. Download-time errors (bot checks, network) are reported as-is so
    real login state is never discarded.

    Args:
        url: Video URL.
        target_dir: Directory to write the merged video into.
        plan: Cookie source selection.
        ydl_factory: yt_dlp.YoutubeDL replacement, for tests.

    Returns:
        True if the download succeeded, False otherwise.
    """
    if ydl_factory is None:
        from yt_dlp import YoutubeDL

        ydl_factory = YoutubeDL

    try:
        ydl = _open_ydl(plan, target_dir, ydl_factory)
    except Exception as e:
        if not (plan.browser and not plan.file):
            logger.error("%s", e)
            return False
        logger.warning("Browser cookies unavailable (%s); retrying without cookies", e)
        try:
            ydl = _open_ydl(CookiePlan(), target_dir, ydl_factory)
        except Exception as retry_error:
            logger.error("%s", retry_error)
            return False

    try:
        with ydl:
            ydl.download([url])
        return True
    except Exception as e:
        logger.error("%s", e)
        return False
