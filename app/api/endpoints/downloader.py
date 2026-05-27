"""Video/album download endpoints.

Watermark-free download functionality built on HybridCrawler.
"""

import os
import uuid

import yaml
from crawlers.hybrid.hybrid_crawler import HybridCrawler
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from starlette.background import BackgroundTask

from app.api.models import ResponseModel

router = APIRouter()
crawler = HybridCrawler()

config_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "config.yaml",
)
with open(config_path, encoding="utf-8") as f:
    config = yaml.safe_load(f)


def _cleanup_file(path: str) -> None:
    """Clean up temporary files after download.

    Args:
        path: Path to the temporary file to remove.
    """
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


@router.get("/video", summary="Download watermark-free video")
async def download_video(
    request: Request,
    url: str = Query(
        ...,
        example="https://v.douyin.com/L4FJNR3/",
        description="Douyin/TikTok/Bilibili video link",
    ),
):
    """Download watermark-free version of a video.

    Automatically detects the platform (Douyin/TikTok/Bilibili) and returns
    the watermark-free video file. Note: TikTok direct URLs will 403,
    use this endpoint to download.
    """
    try:
        data = await crawler.hybrid_parsing_single_video(url=url, minimal=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse video: {e!s}")

    if data.get("type") != "video":
        raise HTTPException(
            status_code=400, detail="Link is not a video type, use the album download endpoint"
        )

    video_data = data.get("video_data", {})
    # Prefer HQ watermark-free URL
    video_url = (
        video_data.get("nwm_video_url_HQ")
        or video_data.get("nwm_video_url")
        or video_data.get("wm_video_url_HQ")
        or video_data.get("wm_video_url")
    )

    if not video_url:
        raise HTTPException(status_code=500, detail="Failed to get video download URL")

    # TikTok direct URLs return 403, proxy through our server
    # For directly accessible links, redirect instead
    platform = data.get("platform", "unknown")
    video_id = data.get("video_id", str(uuid.uuid4()))

    # Return video info; frontend can use video_url directly
    # If directly accessible, redirect
    if platform == "douyin":
        # Douyin watermark-free links are directly accessible
        return RedirectResponse(url=video_url)
    else:
        # TikTok/Bilibili: stream through proxy
        download_dir = config["server"]["download_path"]
        os.makedirs(download_dir, exist_ok=True)
        ext = ".mp4"
        filename = f"{platform}_{video_id}{ext}"
        filepath = os.path.join(download_dir, filename)

        try:
            import aiofiles
            import httpx

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.tiktok.com/",
            }

            async with httpx.AsyncClient() as client:
                async with client.stream("GET", video_url, headers=headers) as resp:
                    resp.raise_for_status()
                    async with aiofiles.open(filepath, "wb") as f:
                        async for chunk in resp.aiter_bytes():
                            await f.write(chunk)

            return FileResponse(
                path=filepath,
                filename=filename,
                media_type="video/mp4",
                background=BackgroundTask(_cleanup_file, filepath),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"下载视频失败: {e!s}")


@router.get("/images", summary="下载图集图片")
async def download_images(
    request: Request,
    url: str = Query(
        ...,
        example="https://www.douyin.com/note/xxx",
        description="抖音/TikTok 图集链接",
    ),
):
    """
    下载图集中的所有图片（无水印）。

    返回 JSON 格式的图片链接列表，可直接用于下载。
    """
    try:
        data = await crawler.hybrid_parsing_single_video(url=url, minimal=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析图集失败: {e!s}")

    if data.get("type") != "image":
        raise HTTPException(status_code=400, detail="该链接不是图集类型，请使用视频下载接口")

    image_data = data.get("image_data", {})
    image_urls = image_data.get("no_watermark_image_list", [])

    if not image_urls:
        raise HTTPException(status_code=500, detail="无法获取图片下载链接")

    return ResponseModel(
        code=200,
        message=f"获取到 {len(image_urls)} 张图片",
        data={
            "platform": data.get("platform"),
            "video_id": data.get("video_id"),
            "desc": data.get("desc"),
            "image_count": len(image_urls),
            "image_urls": image_urls,
            "author": data.get("author"),
        },
    )


@router.get("/info", summary="获取视频/图集下载信息")
async def get_download_info(
    request: Request,
    url: str = Query(
        ...,
        example="https://v.douyin.com/L4FJNR3/",
        description="视频或图集链接",
    ),
):
    """
    获取视频或图集的下载信息（包含无水印链接列表），不直接下载文件。

    返回数据结构中包含可直接使用的下载链接，方便集成到其他工具中。
    """
    try:
        data = await crawler.hybrid_parsing_single_video(url=url, minimal=True)
        return ResponseModel(code=200, message="获取下载信息成功", data=data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"获取下载信息失败: {e!s}")
