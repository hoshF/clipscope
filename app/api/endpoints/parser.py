"""Video/album data parsing endpoints.

Clean parsing API built on HybridCrawler.
Supports single and batch parsing for Douyin, TikTok, and Bilibili.
"""

import asyncio
import re

from crawlers.hybrid.hybrid_crawler import HybridCrawler
from fastapi import APIRouter, HTTPException, Query, Request

from app.api.models import ErrorResponse, ResponseModel

router = APIRouter()
crawler = HybridCrawler()


def extract_urls(text: str) -> list[str]:
    """Extract all possible video/sharing URLs from text.

    Args:
        text: Raw text that may contain sharing links.

    Returns:
        List of extracted URLs, or empty list if none found.
    """
    url_pattern = re.compile(r"https?://[^\s,，、\n\r]+")
    return url_pattern.findall(text)


@router.get("/video", summary="Parse single video/album")
async def parse_video(
    request: Request,
    url: str = Query(
        ...,
        example="https://v.douyin.com/L4FJNR3/",
        description="Douyin/TikTok/Bilibili video or album link",
    ),
    minimal: bool = Query(
        True,
        description="Return minimal data (True=minimal, False=full)",
    ),
):
    """Parse a single video or album.

    - **url**: Douyin/TikTok/Bilibili sharing link
    - **minimal**: Returns only key fields when True, full data when False

    **Supported formats:**
    - Douyin: `https://v.douyin.com/xxx/`, `https://www.douyin.com/video/xxx`
    - TikTok: `https://www.tiktok.com/@user/video/xxx`, `https://www.tiktok.com/t/xxx/`
    - Bilibili: `https://www.bilibili.com/video/BVxxx`, `https://b23.tv/xxx`
    """
    try:
        data = await crawler.hybrid_parsing_single_video(url=url, minimal=minimal)
        return ResponseModel(code=200, message="Parsed successfully", data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                code=500, message=f"Parse failed: {e!s}", detail={"url": url}
            ).model_dump(),
        )


@router.post("/batch", summary="Batch parse multiple videos/albums")
async def parse_batch(
    request: Request,
    urls: list[str] = Query(
        ...,
        example=[
            "https://v.douyin.com/L4FJNR3/",
            "https://www.tiktok.com/@taylorswift/video/7359655005701311786",
        ],
        description="List of video URLs, supports Douyin/TikTok/Bilibili mixed",
    ),
    minimal: bool = Query(
        True,
        description="Return minimal data",
    ),
    max_concurrent: int = Query(
        5,
        description="Maximum concurrent requests",
        ge=1,
        le=20,
    ),
):
    """Batch parse multiple videos/albums (supports mixed platforms).

    - **urls**: List of video URLs (max 30)
    - **minimal**: Return minimal data when True
    - **max_concurrent**: Maximum concurrent requests (1-20)
    """
    if len(urls) > 30:
        raise HTTPException(status_code=400, detail="Maximum 30 URLs per batch")

    semaphore = asyncio.Semaphore(max_concurrent)

    async def parse_one(url: str) -> dict:
        async with semaphore:
            try:
                data = await crawler.hybrid_parsing_single_video(url=url, minimal=minimal)
                return {"url": url, "success": True, "data": data}
            except Exception as e:
                return {"url": url, "success": False, "error": str(e)}

    tasks = [parse_one(url) for url in urls]
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r["success"])
    failed_count = sum(1 for r in results if not r["success"])

    return ResponseModel(
        code=200,
        message=f"Batch parse complete: {success_count} succeeded, {failed_count} failed",
        data={
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
            "results": results,
        },
    )


@router.get("/extract", summary="Extract and parse links from text")
async def parse_from_text(
    request: Request,
    text: str = Query(
        ...,
        example="7.43 pda:/ 让你记住我 https://v.douyin.com/L5pbfdP/ 复制打开抖音",
        description="Text containing sharing links (supports multiple mixed)",
    ),
    minimal: bool = Query(True),
    max_concurrent: int = Query(5, ge=1, le=20),
):
    """Auto-extract all links from text and parse them in batch.

    Supports extracting links from Douyin share text, TikTok share text,
    or directly pasting multiple links.
    """
    extracted_urls = extract_urls(text)
    if not extracted_urls:
        raise HTTPException(status_code=400, detail="未从文本中提取到有效链接")

    # 去重
    extracted_urls = list(dict.fromkeys(extracted_urls))

    if len(extracted_urls) > 30:
        extracted_urls = extracted_urls[:30]

    semaphore = asyncio.Semaphore(max_concurrent)

    async def parse_one(url: str) -> dict:
        async with semaphore:
            try:
                data = await crawler.hybrid_parsing_single_video(url=url, minimal=minimal)
                return {"url": url, "success": True, "data": data}
            except Exception as e:
                return {"url": url, "success": False, "error": str(e)}

    tasks = [parse_one(url) for url in extracted_urls]
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r["success"])
    failed_count = sum(1 for r in results if not r["success"])

    return ResponseModel(
        code=200,
        message=f"提取到 {len(extracted_urls)} 个链接，解析完成: 成功 {success_count}, 失败 {failed_count}",
        data={
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
            "extracted_urls": extracted_urls,
            "results": results,
        },
    )
