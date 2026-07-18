"""
Boss直聘 · 自动投递工具 — Web 服务器

负责：
- FastAPI 入口
- WebSocket 实时日志/截图/进度推送
- 配置 CRUD
- Bot 生命周期管理（同一进程内单例）
"""
import asyncio
import json
import os
import threading
from contextlib import asynccontextmanager
from typing import Optional
from io import BytesIO
import base64

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# 从原项目导入
import sys
sys.path.insert(0, os.path.dirname(__file__))
from bot_core import BotCore
from config import load_config, save_config, reset_config, validate_config

# ── 全局单例 ─────────────────────────────────────────
bot: Optional[BotCore] = None
bot_thread: Optional[threading.Thread] = None

# WebSocket 管理器
log_ws_connections: set[WebSocket] = set()
screenshot_ws_connections: set[WebSocket] = set()
progress_ws_connections: set[WebSocket] = set()


def _broadcast_log(msg: str):
    """向所有已连接的日志 WS 客户端广播。"""
    async def _do():
        dead = set()
        for ws in log_ws_connections:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        log_ws_connections.difference_update(dead)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_do())
    except RuntimeError:
        pass


def _broadcast_screenshot(data: bytes):
    """向所有已连接的截图 WS 客户端广播（base64）。"""
    b64 = base64.b64encode(data).decode("utf-8")
    async def _do():
        dead = set()
        for ws in screenshot_ws_connections:
            try:
                await ws.send_text(b64)
            except Exception:
                dead.add(ws)
        screenshot_ws_connections.difference_update(dead)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_do())
    except RuntimeError:
        pass


def _broadcast_progress(stats: dict):
    """向所有已连接的进度 WS 客户端广播。"""
    async def _do():
        dead = set()
        for ws in progress_ws_connections:
            try:
                await ws.send_json(stats)
            except Exception:
                dead.add(ws)
        progress_ws_connections.difference_update(dead)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_do())
    except RuntimeError:
        pass


# ── 应用生命周期 ───────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时无操作
    yield
    # 关闭时停止 Bot
    global bot, bot_thread
    if bot:
        bot.stop()
        if bot_thread and bot_thread.is_alive():
            bot_thread.join(timeout=5)
        bot = None


app = FastAPI(title="Boss 直聘 · 自动投递", version="2.0", lifespan=lifespan)


# ── API ────────────────────────────────────────

@app.get("/api/config")
def get_config():
    return load_config()


class ConfigBody(BaseModel):
    city: str = "上海"
    job_query: str = ""
    scroll_pages: int = 5
    message_interval_min: int = 3
    message_interval_max: int = 8
    greeting_message: str = ""
    image_files: list[str] = []


@app.post("/api/config")
def update_config(body: ConfigBody):
    cfg = body.model_dump()
    errors = validate_config(cfg)
    if errors:
        return {"ok": False, "errors": errors}
    save_config(cfg)
    return {"ok": True}


class StartBody(BaseModel):
    pass  # 使用当前已保存的配置


@app.post("/api/bot/start")
def start_bot():
    global bot, bot_thread
    if bot and bot.running:
        return {"ok": False, "error": "Bot 已在运行中"}
    cfg = load_config()
    # 关闭旧 bot
    if bot:
        bot.stop()
        if bot_thread and bot_thread.is_alive():
            bot_thread.join(timeout=5)
    bot = BotCore(
        config=cfg,
        log_callback=_broadcast_log,
        screenshot_callback=_broadcast_screenshot,
        progress_callback=_broadcast_progress,
    )
    bot_thread = threading.Thread(target=bot.start, daemon=True)
    bot_thread.start()
    return {"ok": True}


@app.post("/api/bot/stop")
def stop_bot():
    global bot
    if bot:
        bot.stop()
        return {"ok": True}
    return {"ok": False, "error": "Bot 未运行"}


@app.get("/api/bot/status")
def bot_status():
    global bot
    if bot and bot.running:
        return {"running": True}
    return {"running": False}


@app.post("/api/bot/confirm-login")
def confirm_login():
    global bot
    if bot:
        bot.confirm_login()
        return {"ok": True}
    return {"ok": False, "error": "Bot 未启动"}


@app.get("/api/bot/check-login")
def check_login_api():
    global bot
    if bot:
        logged_in = bot.check_login_status()
        return {"logged_in": logged_in}
    return {"logged_in": False}


# ── WebSocket ─────────────────────────────────

@app.websocket("/ws/logs")
async def ws_logs(ws: WebSocket):
    await ws.accept()
    log_ws_connections.add(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        pass
    finally:
        log_ws_connections.discard(ws)


@app.websocket("/ws/screenshot")
async def ws_screenshot(ws: WebSocket):
    await ws.accept()
    screenshot_ws_connections.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        screenshot_ws_connections.discard(ws)


@app.websocket("/ws/progress")
async def ws_progress(ws: WebSocket):
    await ws.accept()
    progress_ws_connections.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        progress_ws_connections.discard(ws)


# ── 静态文件 & SPA 入口 ─────────────────────

@app.get("/")
def index():
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "templates", "index.html")
    )


# ── 启动入口 ──────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=5800,
        reload=True,
        log_level="info"
    )
