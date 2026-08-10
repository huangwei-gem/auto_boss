"""
Boss直聘 · 自动投递 — Web 服务端（多岗位多账号版）

Flask + Flask-SocketIO 单进程架构。
任务调度器并发执行所有启用的账号×岗位组合，
每个组合启动一个 BotCore 实例运行。
"""
import json
import logging
import os
import sys
import threading
import base64
import time
import uuid
from typing import Optional

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# ── 路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_DIR)
os.chdir(BASE_DIR)

# 复制配置和数据文件到 web 工作目录（如果不存在）
import shutil
for fn in ("chats_log.json", "zhipin_cookies"):
    src = os.path.join(PROJECT_DIR, "core", fn)
    dst = os.path.join(BASE_DIR, fn)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)

# 复制 dashboard/ 目录
src_dir = os.path.join(PROJECT_DIR, "core", "dashboard")
dst_dir = os.path.join(BASE_DIR, "dashboard")
if os.path.exists(src_dir) and not os.path.exists(dst_dir):
    shutil.copytree(src_dir, dst_dir)

from config import load_config, save_config, validate_config, flatten_jobs_for_run
sys.path.insert(0, os.path.join(PROJECT_DIR, "core"))
from bot_core import BotCore

# ── Flask 应用 ──
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max upload
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── 全局状态 ──
_bot: BotCore | None = None
_bot_thread: threading.Thread | None = None
_scheduler_thread: threading.Thread | None = None
_scheduler_stop = threading.Event()
_scheduler_running = False
_config = load_config()
_current_task: dict | None = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("boss-web")


# ═══════════════════════════════════════════════════════════
#  任务调度器 — 并发执行每个账号×岗位
# ═══════════════════════════════════════════════════════════

class TaskScheduler:
    """按账号顺序执行任务，同一账号的岗位串行执行（Boss直聘限制：一个cookie只能登在一个浏览器）。"""

    def __init__(self, tasks: list[dict], sid: str):
        self.tasks = tasks
        self.sid = sid
        self._stop = threading.Event()
        self._runners: list[BotRunner] = []
        self._threads: list[threading.Thread] = []

    def log(self, msg: str):
        socketio.emit("bot_log", {"message": msg}, to=self.sid)

    def confirm_login(self) -> None:
        """将所有 runner 的 confirm_login 代理到前台。"""
        for runner in self._runners:
            if runner and runner.bot:
                runner.bot.confirm_login()

    def check_login_status(self) -> bool:
        """检查任一 runner 的登录状态。"""
        for runner in self._runners:
            if runner and runner.bot and runner.bot.check_login_status():
                return True
        return False

    def stop(self):
        self._stop.set()
        for runner in self._runners:
            runner.stop()

    def run(self):
        total = len(self.tasks)
        self.log(f"[SCHEDULER] 启动调度，共 {total} 个任务")

        socketio.emit("scheduler_status", {
            "running": True,
            "total": total,
            "completed": 0,
            "current": None,
        }, to=self.sid)

        # 按账号分组，同一账号的任务串行执行（Boss直聘限制：一个cookie只能登在一个浏览器）
        from collections import OrderedDict
        account_groups = OrderedDict()
        for task in self.tasks:
            acc = task["account_name"]
            if acc not in account_groups:
                account_groups[acc] = []
            account_groups[acc].append(task)
        
        self.log(f"[SCHEDULER] 共 {len(account_groups)} 个账号，{total} 个岗位")
        
        completed = 0
        for acc_name, acc_tasks in account_groups.items():
            if self._stop.is_set():
                break
            self.log(f"[SCHEDULER] 开始处理账号「{acc_name}」的 {len(acc_tasks)} 个岗位")
            for task in acc_tasks:
                if self._stop.is_set():
                    break
                label = f"{task['account_name']} / {task['query']}({task['city']})"
                runner = BotRunner(task, self.sid, label)
                self._runners.append(runner)
                self.log(f"[SCHEDULER] 启动: {label}")
                socketio.emit("scheduler_status", {
                    "running": True,
                    "total": total,
                    "completed": completed,
                    "current": label,
                }, to=self.sid)
                runner.run()
                completed += 1

        self.log(f"\n[SCHEDULER] 全部完成！{completed}/{total} 个任务")
        socketio.emit("scheduler_status", {
            "running": False,
            "total": total,
            "completed": completed,
            "current": None,
        }, to=self.sid)


# ═══════════════════════════════════════════════════════════
#  单任务运行器
# ═══════════════════════════════════════════════════════════

class BotRunner:
    """包装一个 BotCore 实例，在独立线程中运行。"""

    def __init__(self, bot_config: dict, sid: str, label: str):
        self.bot_config = bot_config
        self.sid = sid
        self.label = label
        self.bot: BotCore | None = None
        self.done = False

    def log(self, msg: str):
        socketio.emit("bot_log", {"message": f"[{self.label}] {msg}"}, to=self.sid)

    def stop(self):
        if self.bot:
            try:
                self.bot.stop()
            except Exception:
                pass

    def confirm_login(self):
        if self.bot:
            try:
                self.bot.confirm_login()
            except Exception:
                pass

    def check_login_status(self):
        if self.bot:
            try:
                return self.bot.check_login_status()
            except Exception:
                pass
        return False

    def run(self):
        try:
            self.log("启动中...")
            self.bot = BotCore(
                self.bot_config,
                log_callback=self.log,
                screenshot_callback=None,
                progress_callback=None,
            )
            socketio.emit("scheduler_status", {
                "running": True,
                "current": {"account": self.label.split(" / ")[0], "query": self.label.split(" / ")[1] if " / " in self.label else self.label, "city": ""},
            }, to=self.sid)
            self.bot.start()
            self.done = True
            self.log("已完成")
        except Exception as e:
            self.log(f"错误: {e}")
            self.done = True


# ═══════════════════════════════════════════════════════════
#  HTTP API — 配置管理
# ═══════════════════════════════════════════════════════════

@app.route("/api/config", methods=["GET"])
def api_get_config():
    global _config
    return jsonify(_config)


@app.route("/api/config", methods=["PUT"])
def api_put_config():
    global _config
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "无效的配置数据"}), 400
    errors = validate_config(data)
    if errors:
        return jsonify({"status": "error", "message": "校验失败", "errors": errors}), 400
    _config = data
    save_config(_config)
    return jsonify({"status": "ok"})


@app.route("/api/config/accounts", methods=["POST"])
def api_add_account():
    global _config
    accounts = _config.get("accounts", [])
    accounts.append({
        "name": f"账号{len(accounts)+1}",
        "enabled": True,
        "cookie_file": "zhipin_cookies.json",
        "image_files": [],
        "message_interval_min": 3,
        "message_interval_max": 8,
        "jobs": [
            {
                "enabled": True,
                "city": "上海",
                "query": "AI产品经理",
                "scroll_pages": 5,
                "greeting_message": "您好，希望能获得面试机会。"
            }
        ]
    })
    _config["accounts"] = accounts
    save_config(_config)
    return jsonify({"status": "ok", "accounts": accounts})


@app.route("/api/config/accounts/<int:idx>", methods=["DELETE"])
def api_delete_account(idx):
    global _config
    accounts = _config.get("accounts", [])
    if idx < 0 or idx >= len(accounts):
        return jsonify({"status": "error", "message": "索引越界"}), 404
    accounts.pop(idx)
    _config["accounts"] = accounts
    save_config(_config)
    return jsonify({"status": "ok", "accounts": accounts})


# ═══════════════════════════════════════════════════════════
#  HTTP API — 文件上传
# ═══════════════════════════════════════════════════════════

DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard")
os.makedirs(DASHBOARD_DIR, exist_ok=True)


@app.route("/api/upload/images", methods=["POST"])
def api_upload_images():
    """上传作品图片，支持多文件。"""
    if "files" not in request.files:
        return jsonify({"status": "error", "message": "没有上传文件"}), 400

    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"status": "error", "message": "文件为空"}), 400

    uploaded = []
    for f in files:
        if f.filename == "":
            continue
        # 安全处理文件名：添加 UUID 前缀防止重名覆盖
        _, ext = os.path.splitext(f.filename)
        safe_name = f"{uuid.uuid4().hex[:8]}_{f.filename}"
        save_path = os.path.join(DASHBOARD_DIR, safe_name)
        f.save(save_path)
        uploaded.append(f"dashboard/{safe_name}")

    logger.info(f"上传了 {len(uploaded)} 张图片: {uploaded}")
    return jsonify({"status": "ok", "files": uploaded})


@app.route("/api/upload/cookie", methods=["POST"])
def api_upload_cookie():
    """上传 Cookie 文件。"""
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "没有上传文件"}), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({"status": "error", "message": "文件为空"}), 400

    # 用原文件名保存
    save_path = os.path.join(BASE_DIR, f.filename)
    f.save(save_path)

    logger.info(f"上传了 Cookie 文件: {f.filename}")
    return jsonify({"status": "ok", "filename": f.filename})


@app.route("/api/images/list", methods=["GET"])
def api_list_images():
    """列出 dashboard 目录下所有图片。"""
    images = []
    if os.path.exists(DASHBOARD_DIR):
        for fn in sorted(os.listdir(DASHBOARD_DIR)):
            if fn.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
                images.append(f"dashboard/{fn}")
    return jsonify({"status": "ok", "images": images})


# ═══════════════════════════════════════════════════════════
#  HTTP API — 仪表盘/统计
# ═══════════════════════════════════════════════════════════

@app.route("/api/images/delete", methods=["POST"])
def api_delete_image():
    """删除上传的作品图片。"""
    data = request.get_json()
    if not data or "filename" not in data:
        return jsonify({"status": "error", "message": "缺少文件名"}), 400
    
    filename = data["filename"]
    if not filename.startswith("dashboard/"):
        return jsonify({"status": "error", "message": "非法文件路径"}), 400
    
    relative_path = filename.replace("dashboard/", "", 1)
    if ".." in relative_path or "/" in relative_path or "\\" in relative_path:
        return jsonify({"status": "error", "message": "非法文件名"}), 400
    
    file_path = os.path.join(DASHBOARD_DIR, relative_path)
    if os.path.exists(file_path):
        os.remove(file_path)
        logger.info(f"删除图片: {file_path}")
        return jsonify({"status": "ok", "message": "已删除"})
    else:
        return jsonify({"status": "error", "message": "文件不存在"}), 404


@app.route("/api/scheduler/reset", methods=["POST"])
def api_reset_scheduler():
    """重置调度器状态（前端用来解除卡死状态）。"""
    global _scheduler_running, _scheduler_thread, _scheduler_stop, _bot, _bot_thread
    _scheduler_running = False
    _scheduler_stop.set()
    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=1)
    _scheduler_thread = None
    if _bot_thread and _bot_thread.is_alive():
        _bot_thread.join(timeout=1)
    _bot_thread = None
    _bot = None
    logger.info("调度器状态已重置")
    return jsonify({"status": "ok"})




@app.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify({
        "total": 0,
        "applied": 0,
        "skipped": 0,
    })


# ═══════════════════════════════════════════════════════════
#  页面路由
# ═══════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ═══════════════════════════════════════════════════════════
#  SocketIO 事件
# ═══════════════════════════════════════════════════════════

@socketio.on("connect")
def on_connect():
    logger.info(f"Client connected: {request.sid}")


@socketio.on("disconnect")
def on_disconnect():
    logger.info(f"Client disconnected: {request.sid}")


@socketio.on("start_all")
def on_start_all(data=None):
    """启动所有启用的账号×岗位任务。"""
    global _scheduler_thread, _scheduler_stop, _bot, _scheduler_running

    # 如果标记为运行中但线程已死，重置状态
    if _scheduler_running:
        if _scheduler_thread and _scheduler_thread.is_alive():
            emit("bot_log", {"message": "[SYSTEM] 调度器已在运行中"})
            return
        else:
            # 线程已死，重置状态
            _scheduler_running = False
            _scheduler_thread = None
            _bot = None
            logger.info("检测到调度器线程已结束，重置状态")

    # 展开任务
    tasks = flatten_jobs_for_run(_config)
    if not tasks:
        emit("bot_log", {"message": "[SYSTEM] 没有启用的任务（请检查账号和岗位的 enabled 状态）"})
        return

    emit("bot_log", {"message": f"[SYSTEM] 调度器启动，共 {len(tasks)} 个任务"})
    emit("bot_status", {"running": True})
    emit("scheduler_status", {"running": True})

    _scheduler_stop.clear()
    _scheduler_running = True
    scheduler = TaskScheduler(tasks, request.sid)
    _bot = scheduler

    def _run_scheduler():
        global _scheduler_running
        try:
            scheduler.run()
        finally:
            _scheduler_running = False
            _scheduler_thread = None
            emit("bot_status", {"running": False}, to=request.sid)

    _scheduler_thread = threading.Thread(target=_run_scheduler, daemon=True)
    _scheduler_thread.start()


@socketio.on("stop_all")
def on_stop_all():
    """停止调度器。"""
    global _scheduler_stop, _scheduler_thread, _bot, _scheduler_running
    _scheduler_stop.set()
    _scheduler_running = False
    if _bot:
        try:
            _bot.stop()
        except Exception:
            pass
    # Wait briefly for scheduler thread to finish
    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=3)
    _scheduler_thread = None
    emit("bot_log", {"message": "[SYSTEM] 正在停止调度器..."})
    emit("bot_status", {"running": False})
    emit("scheduler_status", {"running": False}, to=request.sid)


@socketio.on("start_bot")
def on_start_bot(data):
    """兼容旧版：单任务快速启动。"""
    global _bot, _bot_thread

    if _bot_thread and _bot_thread.is_alive():
        emit("bot_log", {"message": "[SYSTEM] Bot 已在运行中"})
        return

    tasks = flatten_jobs_for_run(_config)
    if not tasks:
        emit("bot_log", {"message": "[SYSTEM] 没有启用的任务"})
        return

    task_idx = 0
    if data and "task_index" in data:
        task_idx = data["task_index"]
    if task_idx >= len(tasks):
        emit("bot_log", {"message": f"[SYSTEM] 任务索引 {task_idx} 超出范围"})
        return

    task = tasks[task_idx]


    label = f"{task['account_name']} / {task['query']}({task['city']})"
    runner = BotRunner(task, request.sid, label)
    _bot = runner

    emit("bot_status", {"running": True})
    emit("bot_log", {"message": f"[SYSTEM] Bot 启动: {label}"})

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
    global _scheduler_stop, _bot
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
#  Static file serving for dashboard images
# ═══════════════════════════════════════════════════════════

# Dashboards images are served from /dashboard/ path
# Flask automatically serves static files from the 'static' folder
# We need to serve the dashboard directory as well
import mimetypes

@app.route("/dashboard/<path:filename>")
def serve_dashboard(filename):
    return app.send_static_file_or_404(os.path.join("dashboard", filename))

# Helper to send static file or 404
def send_static_file_or_404(filepath):
    full_path = os.path.join(BASE_DIR, filepath)
    if os.path.exists(full_path) and os.path.isfile(full_path):
        from flask import send_file
        return send_file(full_path)
    from flask import abort
    return abort(404)

app.send_static_file_or_404 = staticmethod(send_static_file_or_404)


# ═══════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"  Boss 直聘 · 自动投递  Web 版（多岗位多账号）")
    print(f"  启动地址: http://127.0.0.1:5000")
    print(f"  {'='*40}")
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)






