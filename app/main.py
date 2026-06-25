"""ClipScope API Service

FastAPI application built on the Douyin_TikTok_Download_API crawler library.
Supports Douyin, TikTok, and Bilibili video/album parsing and watermark-free downloads.
"""

import os
import sys

import uvicorn
import yaml

from scripts.utils.paths import CONFIG_PATH, LIB_DIR, TEMP_DIR

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router

with open(CONFIG_PATH, encoding="utf-8") as f:
    config = yaml.safe_load(f)

app = FastAPI(
    title=config["app"]["title"],
    description=config["app"]["description"],
    version=config["app"]["version"],
    docs_url=config["server"]["docs_url"],
    redoc_url=config["server"]["redoc_url"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

download_path = str(TEMP_DIR)
os.makedirs(download_path, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=download_path), name="downloads")

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", summary="Service status check")
async def root() -> dict:
    """Return basic service info including version and documentation URL.

    Returns:
        dict: Service name, version, and docs link.
    """
    return {
        "service": "ClipScope API",
        "version": config["app"]["version"],
        "docs": f"{config['server']['docs_url']}",
        "github": "https://github.com/Evil0ctal/Douyin_TikTok_Download_API",
    }


@app.get("/health", summary="Health check")
async def health_check() -> dict:
    """Health check endpoint for monitoring service availability.

    Returns:
        dict: {"status": "ok"}.
    """
    return {"status": "ok"}


if __name__ == "__main__":
    host = config["server"]["host"]
    port = config["server"]["port"]
    print(f"🚀 Server running: http://{host}:{port}")
    print(f"📖 API docs: http://{host}:{port}{config['server']['docs_url']}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
