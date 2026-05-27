"""
Douyin/TikTok/Bilibili 数据爬取 API 服务

基于 Douyin_TikTok_Download_API 爬虫库构建的 FastAPI 应用。
支持抖音、TikTok、Bilibili 视频解析与无水印下载。
"""

import os
import sys
import yaml
import uvicorn

# ── 将 lib (Douyin_TikTok_Download_API) 加入 Python 路径 ──
LIB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router

# ── 加载配置文件 ──
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# ── 创建 FastAPI 应用 ──
app = FastAPI(
    title=config["app"]["title"],
    description=config["app"]["description"],
    version=config["app"]["version"],
    docs_url=config["server"]["docs_url"],
    redoc_url=config["server"]["redoc_url"],
)

# ── CORS 中间件 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──
app.include_router(api_router, prefix="/api")

# ── 静态文件（下载目录 & 看板） ──
download_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "temp")
os.makedirs(download_path, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=download_path), name="downloads")

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", summary="服务状态检查")
async def root():
    return {
        "service": "Douyin/TikTok/Bilibili Crawler API",
        "version": config["app"]["version"],
        "docs": f"{config['server']['docs_url']}",
        "github": "https://github.com/Evil0ctal/Douyin_TikTok_Download_API",
    }


@app.get("/health", summary="健康检查")
async def health_check():
    return {"status": "ok"}


# ── 启动入口 ──
if __name__ == "__main__":
    host = config["server"]["host"]
    port = config["server"]["port"]
    print(f"🚀 服务启动: http://{host}:{port}")
    print(f"📖 API 文档: http://{host}:{port}{config['server']['docs_url']}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
