"""
视频/图集下载接口

基于 HybridCrawler 实现的无水印下载功能。
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

# 加载配置
config_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "config.yaml",
)
with open(config_path, encoding="utf-8") as f:
    config = yaml.safe_load(f)


def _cleanup_file(path: str) -> None:
    """下载完成后清理临时文件。

    Args:
        path: 要清理的临时文件路径。
    """
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


@router.get("/video", summary="下载无水印视频")
async def download_video(
    request: Request,
    url: str = Query(
        ...,
        example="https://v.douyin.com/L4FJNR3/",
        description="抖音/TikTok/Bilibili 视频链接",
    ),
):
    """
    下载指定视频的无水印版本。

    自动识别平台（抖音/TikTok/B站），返回无水印视频文件。
    注意：TikTok 视频链接需通过本接口下载，直接访问会 403。
    """
    try:
        # 解析视频数据
        data = await crawler.hybrid_parsing_single_video(url=url, minimal=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析视频失败: {e!s}")

    if data.get("type") != "video":
        raise HTTPException(status_code=400, detail="该链接不是视频类型，请使用图集下载接口")

    video_data = data.get("video_data", {})
    # 优先使用无水印高清链接
    video_url = (
        video_data.get("nwm_video_url_HQ")
        or video_data.get("nwm_video_url")
        or video_data.get("wm_video_url_HQ")
        or video_data.get("wm_video_url")
    )

    if not video_url:
        raise HTTPException(status_code=500, detail="无法获取视频下载链接")

    # 对于 TikTok，视频直链会 403，重定向到下载接口
    # 但对于可直接访问的链接，直接重定向
    platform = data.get("platform", "unknown")
    video_id = data.get("video_id", str(uuid.uuid4()))

    # 返回视频信息，前端或客户端可以用 video_url 自行处理
    # 如果是可直接访问的链接，返回重定向
    if platform == "douyin":
        # 抖音无水印链接可以直接访问
        return RedirectResponse(url=video_url)
    else:
        # TikTok/B站 通过流式代理下载
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
