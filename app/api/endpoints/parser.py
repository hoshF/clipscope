"""
视频/图集数据解析接口

基于 HybridCrawler 实现的简洁解析 API。
支持抖音、TikTok、Bilibili 的单条/批量解析。
"""

import re
import asyncio
from typing import List, Optional

from fastapi import APIRouter, Query, Request, HTTPException
from app.api.models import ResponseModel, ErrorResponse

from crawlers.hybrid.hybrid_crawler import HybridCrawler

router = APIRouter()
crawler = HybridCrawler()


def extract_urls(text: str) -> List[str]:
    """从文本中提取所有可能的视频/分享链接"""
    # 匹配常见 URL
    url_pattern = re.compile(
        r"https?://[^\s,，、\n\r]+"
    )
    return url_pattern.findall(text)


@router.get("/video", summary="解析单个视频/图集")
async def parse_video(
    request: Request,
    url: str = Query(
        ...,
        example="https://v.douyin.com/L4FJNR3/",
        description="抖音/TikTok/Bilibili 视频或图集链接",
    ),
    minimal: bool = Query(
        True,
        description="是否只返回精简数据（True=精简, False=完整）",
    ),
):
    """
    解析单个视频或图集的数据。

    - **url**: 抖音/TikTok/Bilibili 分享链接
    - **minimal**: 为 True 时只返回关键字段，为 False 时返回原始完整数据

    **支持格式：**
    - 抖音: `https://v.douyin.com/xxx/`、`https://www.douyin.com/video/xxx`
    - TikTok: `https://www.tiktok.com/@user/video/xxx`、`https://www.tiktok.com/t/xxx/`
    - B站: `https://www.bilibili.com/video/BVxxx`、`https://b23.tv/xxx`
    """
    try:
        data = await crawler.hybrid_parsing_single_video(url=url, minimal=minimal)
        return ResponseModel(code=200, message="解析成功", data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(code=500, message=f"解析失败: {str(e)}", detail={"url": url}).model_dump(),
        )


@router.post("/batch", summary="批量解析多个视频/图集")
async def parse_batch(
    request: Request,
    urls: List[str] = Query(
        ...,
        example=[
            "https://v.douyin.com/L4FJNR3/",
            "https://www.tiktok.com/@taylorswift/video/7359655005701311786",
        ],
        description="视频链接列表，支持抖音/TikTok/B站混合",
    ),
    minimal: bool = Query(
        True,
        description="是否只返回精简数据",
    ),
    max_concurrent: int = Query(
        5,
        description="最大并发数",
        ge=1,
        le=20,
    ),
):
    """
    批量解析多个视频/图集（支持混合平台）。

    - **urls**: 视频链接列表（最多 30 个）
    - **minimal**: 为 True 时只返回关键字段
    - **max_concurrent**: 最大并发请求数（1-20）
    """
    if len(urls) > 30:
        raise HTTPException(status_code=400, detail="一次最多解析 30 个链接")

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
        message=f"批量解析完成: 成功 {success_count}, 失败 {failed_count}",
        data={
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
            "results": results,
        },
    )


@router.get("/extract", summary="从文本中提取链接并解析")
async def parse_from_text(
    request: Request,
    text: str = Query(
        ...,
        example="7.43 pda:/ 让你记住我 https://v.douyin.com/L5pbfdP/ 复制打开抖音",
        description="包含分享链接的文本内容（支持多条混合）",
    ),
    minimal: bool = Query(True),
    max_concurrent: int = Query(5, ge=1, le=20),
):
    """
    从文本中自动提取所有链接并批量解析。

    支持从抖音分享口令、TikTok 分享文本中提取链接，
    也支持直接粘贴多条链接混合解析。
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
