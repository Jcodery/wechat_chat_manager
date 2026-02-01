"""
WeChat Chat Manager - FastAPI Application

Main entry point for the WeChat Chat Manager API.
Provides REST endpoints for authentication, WeChat management,
and chat extraction/hiding functionality.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pathlib import Path

app = FastAPI(
    title="微信聊天记录管理",
    description="WeChat Chat Manager - Secure chat extraction and hiding tool",
    version="1.0.0",
)

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Frontend directory
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Only mount static files if frontend directory exists
if FRONTEND_DIR.exists():
    # Mount static files
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    # Mount css and js for relative paths in index.html
    if (FRONTEND_DIR / "css").exists():
        app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    if (FRONTEND_DIR / "js").exists():
        app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")


@app.get("/")
async def root():
    """Serve the frontend index.html"""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "WeChat Chat Manager API", "docs": "/docs"}


@app.get("/api/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}


# Include routers
from wechat_manager.api.routes import auth, wechat, contacts, mode_a, search, export

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(wechat.router, prefix="/api/wechat", tags=["wechat"])
app.include_router(contacts.router, prefix="/api/contacts", tags=["contacts"])
app.include_router(mode_a.router, prefix="/api/mode-a", tags=["mode-a"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
