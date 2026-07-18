"""
Boss直聘 · 自动投递 — Web 服务端

Flask + Flask-SocketIO 单进程架构。
BotCore 在后台线程运行，通过 SocketIO 发射日志/截图/进度。
"""
import json
import logging
import os
import sys
import threading
import base64

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# ── 路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)       # boss自动投简历/
sys.path.insert(0, PROJECT_DIR)

# 把 bot_core config 放在 web_app 目录
os.chdir(BASE_DIR)

# 复制配置和数据文件到 web 工作目录（如果不存在）
import shutil
for fn in ("bot_config.json", "chats_log.json", "zhipin_cookies"):
    src = os.path.join(PROJECT_DIR, "boss自动投简历", fn)
    dst = os.path.join(BASE_DIR, fn)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)

# 复制 数据分析看板/ 目录
src_dir = os.path.join(PROJECT_DIR, "boss自动投简历", "数据分析看板")
dst_dir = os.path.join(BASE_DIR, "数据分析看板")
if os.path.exists(src_dir) and not os.path.exists(dst_dir):
    shutil.copytree(src_dir, dst_dir)

from config import load_config, save_config, validate_config
sys.path.insert(0, os.path.join(PROJECT_DIR, "boss自动投简历"))
from bot_core import BotCore

# ── Flask 应用 ──
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── 全局状态 ──
_bot: BotCore | None = None
_bot_thread: threading.Thread | None = None
_config = load_config()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("boss-web")


# ═══════════════════════════════════════════════════════════
#  Bot wrapper — 将回调桥接到 SocketIO
# ═══════════════════════════════════════════════════════════

class BotRunner:
    """包装 BotCore，将回调重定向到 SocketIO。"""

    def __init__(self, config: dict, sid: str):
        self.config = config
        self.sid = sid
        self.bot: BotCore | None = None

    def log_cb(self, msg: str):
        socketio.emit("bot_log", {"message": msg}, to=self.sid)

    def screenshot_cb(self, data: bytes):
        b64 = base64.b64encode(data).decode("utf-8")
        socketio.emit("bot_screenshot", {"image": b64}, to=self.sid)

    def progress_cb(self, stats: dict):
        socketio.emit("bot_progress", stats, to=self.sid)

    def run(self):
        try:
            self.bot = BotCore(
                config=self.config,
                log_callback=self.log_cb,
                screenshot_callback=self.screenshot_cb,
                progress_callback=self.progress_cb,
            )
            self.bot.start()
        except Exception as e:
            self.log_cb(f"[SYSTEM] Bot 异常退出: {e}")
        finally:
            self.bot = None
            socketio.emit("bot_status", {"running": False}, to=self.sid)

    def stop(self):
        if self.bot:
            self.bot.stop()

    def confirm_login(self):
        if self.bot:
            self.bot.confirm_login()

    def check_login_status(self) -> bool:
        if self.bot:
            return self.bot.check_login_status()
        return False


# ═══════════════════════════════════════════════════════════
#  路由
# ═══════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(_config)


@app.route("/api/config", methods=["PUT"])
def api_save_config():
    global _config
    data = request.get_json(force=True)
    errors = validate_config(data)
    if errors:
        return jsonify({"status": "error", "errors": errors}), 400
    _config.update(data)
    save_config(_config)
    return jsonify({"status": "ok", "config": _config})


@app.route("/api/images", methods=["GET"])
def api_list_images():
    """列出 available 图片附件。"""
    img_dir = os.path.join(BASE_DIR, "数据分析看板")
    files = []
    if os.path.exists(img_dir):
        for f in sorted(os.listdir(img_dir)):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                files.append(f)
    return jsonify(files)


@app.route("/api/status")
def api_status():
    """当前 bot 运行状态。"""
    running = _bot_thread is not None and _bot_thread.is_alive()
    return jsonify({"running": running})


# ═══════════════════════════════════════════════════════════
#  SocketIO 事件
# ═══════════════════════════════════════════════════════════

@socketio.on("connect")
def on_connect():
    logger.info(f"Client connected: {request.sid}")


@socketio.on("disconnect")
def on_disconnect():
    logger.info(f"Client disconnected: {request.sid}")


@socketio.on("start_bot")
def on_start_bot(data):
    global _bot, _bot_thread

    if _bot_thread and _bot_thread.is_alive():
        emit("bot_log", {"message": "[SYSTEM] Bot 已在运行中"})
        return

    # 合并当前配置
    cfg = _config.copy()
    if data:
        cfg.update(data)

    runner = BotRunner(cfg, request.sid)
    _bot = runner

    emit("bot_status", {"running": True})
    emit("bot_log", {"message": "[SYSTEM] Bot 启动中..."})

    _bot_thread = threading.Thread(target=runner.run, daemon=True)
    _bot_thread.start()


@socketio.on("stop_bot")
def on_stop_bot():
    global _bot
    if _bot:
        _bot.stop()
        emit("bot_log", {"message": "[SYSTEM] 正在停止 Bot..."})
    else:
        emit("bot_log", {"message": "[SYSTEM] Bot 未运行"})


@socketio.on("confirm_login")
def on_confirm_login():
    global _bot
    if _bot:
        _bot.confirm_login()
        emit("bot_log", {"message": "[LOGIN] 用户确认已登录，继续执行..."})
    else:
        emit("bot_log", {"message": "[LOGIN] Bot 未运行，请先启动"})


@socketio.on("check_login")
def on_check_login():
    global _bot
    if _bot:
        ok = _bot.check_login_status()
        emit("bot_login_status", {"logged_in": ok})
    else:
        emit("bot_login_status", {"logged_in": False})


# ═══════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"  Boss 直聘 · 自动投递  Web 版")
    print(f"  启动地址: http://127.0.0.1:5000")
    print(f"  工作目录: {BASE_DIR}")
    print(f"  {'='*40}")
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)
