"""
API 路由聚合

将 lib 中所有 Crawler 路由注册到本项目的 API 下。
"""

from fastapi import APIRouter

from app.api.endpoints.downloader import router as downloader_router

# ── 从 lib 中导入各平台爬虫路由 ──
# 注意: lib 已在 app/main.py 中被加入 sys.path
from app.api.endpoints.parser import router as parser_router
from app.api.endpoints.tracking import router as tracking_router

api_router = APIRouter()

# ── 注册自定义端点 ──
api_router.include_router(parser_router, prefix="/parser", tags=["数据解析"])
api_router.include_router(downloader_router, prefix="/downloader", tags=["文件下载"])
api_router.include_router(tracking_router, prefix="/tracking", tags=["推荐流追踪"])


# ── 直接从 lib 中复用 Douyin_TikTok_Download_API 的原始路由 ──
# 混合解析路由
try:
    from app.api.endpoints.hybrid_parsing import router as hybrid_router

    api_router.include_router(hybrid_router, prefix="/hybrid", tags=["混合解析 (Hybrid-API)"])
except ImportError:
    pass

# 抖音 Web 路由
try:
    from app.api.endpoints.douyin_web import router as douyin_web_router

    api_router.include_router(douyin_web_router, prefix="/douyin/web", tags=["抖音 Web API"])
except ImportError:
    pass

# TikTok Web 路由
try:
    from app.api.endpoints.tiktok_web import router as tiktok_web_router

    api_router.include_router(tiktok_web_router, prefix="/tiktok/web", tags=["TikTok Web API"])
except ImportError:
    pass

# TikTok App 路由
try:
    from app.api.endpoints.tiktok_app import router as tiktok_app_router

    api_router.include_router(tiktok_app_router, prefix="/tiktok/app", tags=["TikTok App API"])
except ImportError:
    pass

# Bilibili Web 路由
try:
    from app.api.endpoints.bilibili_web import router as bilibili_web_router

    api_router.include_router(
        bilibili_web_router, prefix="/bilibili/web", tags=["Bilibili Web API"]
    )
except ImportError:
    pass

# 下载路由
try:
    from app.api.endpoints.download import router as download_router

    api_router.include_router(download_router, tags=["下载 (Download)"])
except ImportError:
    pass

# iOS 快捷指令路由
try:
    from app.api.endpoints.ios_shortcut import router as ios_shortcut_router

    api_router.include_router(ios_shortcut_router, prefix="/ios", tags=["iOS 快捷指令"])
except ImportError:
    pass
