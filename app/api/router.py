"""API route aggregation.

Registers all Crawler routes from lib into this project's API.
"""

from fastapi import APIRouter

from app.api.endpoints.downloader import router as downloader_router
from app.api.endpoints.parser import router as parser_router
from app.api.endpoints.tracking import router as tracking_router

api_router = APIRouter()

api_router.include_router(parser_router, prefix="/parser", tags=["Data Parsing"])
api_router.include_router(downloader_router, prefix="/downloader", tags=["File Download"])
api_router.include_router(tracking_router, prefix="/tracking", tags=["Feed Tracking"])


# lib routes (optional, depends on which crawlers are installed)
try:
    from app.api.endpoints.hybrid_parsing import router as hybrid_router

    api_router.include_router(hybrid_router, prefix="/hybrid", tags=["Hybrid Parsing"])
except ImportError:
    pass

try:
    from app.api.endpoints.douyin_web import router as douyin_web_router

    api_router.include_router(douyin_web_router, prefix="/douyin/web", tags=["Douyin Web API"])
except ImportError:
    pass

try:
    from app.api.endpoints.tiktok_web import router as tiktok_web_router

    api_router.include_router(tiktok_web_router, prefix="/tiktok/web", tags=["TikTok Web API"])
except ImportError:
    pass

try:
    from app.api.endpoints.tiktok_app import router as tiktok_app_router

    api_router.include_router(tiktok_app_router, prefix="/tiktok/app", tags=["TikTok App API"])
except ImportError:
    pass

try:
    from app.api.endpoints.bilibili_web import router as bilibili_web_router

    api_router.include_router(
        bilibili_web_router, prefix="/bilibili/web", tags=["Bilibili Web API"]
    )
except ImportError:
    pass

try:
    from app.api.endpoints.download import router as download_router

    api_router.include_router(download_router, tags=["Download"])
except ImportError:
    pass

try:
    from app.api.endpoints.ios_shortcut import router as ios_shortcut_router

    api_router.include_router(ios_shortcut_router, prefix="/ios", tags=["iOS Shortcuts"])
except ImportError:
    pass
