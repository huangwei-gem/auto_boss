"""
Boss直聘 · 自动投递 — Web 服务端（多岗位多账号版）

Flask + Flask-SocketIO 单进程架构。
任务调度器依次遍历所有启用的账号×岗位组合，
每个组合启动一个 BotCore 实例运行。
"""
import json
import logging
import os
import sys
import threading
import base64
import time
from typing import Optional

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# ── 路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
CORE_DIR = os.path.join(PROJECT_DIR, "core")
DATA_DIR = os.path.join(PROJECT_DIR, "data")
sys.path.insert(0, CORE_DIR)
os.chdir(BASE_DIR)

# 复制配置和数据文件到 web 工作目录（如果不存在）
import shutil
for fn in ("chats_log.json",):
    src = os.path.join(DATA_DIR, fn)
    dst = os.path.join(BASE_DIR, fn)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)
for fn in ("zhipin_cookies",):
    src = os.path.join(PROJECT_DIR, fn)
    dst = os.path.join(BASE_DIR, fn)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)

# ── 优先用 web_app/config.py（它有 validate_config / flatten_jobs_for_run）──
sys.path.insert(0, BASE_DIR)
from config import load_config, save_config, validate_config, flatten_jobs_for_run
from bot_core import BotCore

# ── Flask 应用 ──
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── 全局状态 ──
_bot: BotCore | None = None
_bot_thread: threading.Thread | None = None
_scheduler_thread: threading.Thread | None = None
_scheduler_stop = threading.Event()
_scheduler_instance: TaskScheduler | None = None  # 存储调度器引用，用于停止
_config = load_config()
_current_task: dict | None = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("boss-web")


# ═══════════════════════════════════════════════════════════
#  任务调度器 — 依次执行每个账号×岗位
# ═══════════════════════════════════════════════════════════

class TaskScheduler:
    """并发执行所有任务，每个任务独享一个 BotCore（独立浏览器实例）。"""

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
        self.log(f"[SCHEDULER] 并发启动 {total} 个任务...")

        socketio.emit("scheduler_status", {
            "running": True,
            "total": total,
            "completed": 0,
            "current": None,
        }, to=self.sid)

        # 并发启动所有任务
        for idx, task in enumerate(self.tasks):
            if self._stop.is_set():
                break

            label = f"{task['account_name']} / {task['query']}({task['city']})"

            bot_config = {
                "city": task["city"],
                "job_query": task["query"],
                "scroll_pages": task["scroll_pages"],
                "greeting_message": task["greeting_message"],
                "image_files": task["image_files"],
                "message_interval_min": task["message_interval_min"],
                "message_interval_max": task["message_interval_max"],
                # 高级过滤（供后续 BotCore 使用）
                "min_salary": task.get("min_salary", 0),
                "max_salary": task.get("max_salary", 0),
                "experience": task.get("experience", ""),
                "education": task.get("education", ""),
                "exclude_companies": task.get("exclude_companies", []),
                "include_keywords": task.get("include_keywords", []),
                # 全局设置（随任务携带）
                "browser": _config.get("browser", {}),
                "anti_detection": _config.get("anti_detection", {}),
                "rate_limit": _config.get("rate_limit", {}),
                "screenshot": _config.get("screenshot", {}),
            }

            runner = BotRunner(bot_config, self.sid, label)
            self._runners.append(runner)

            t = threading.Thread(target=runner.run, daemon=True)
            self._threads.append(t)
            t.start()

            self.log(f"[SCHEDULER] ✓ 已启动 [{idx+1}/{total}] {label}")

        # 等待所有线程完成
        for t in self._threads:
            t.join()

        completed = len([r for r in self._runners if r.done])
        self.log(f"\n[SCHEDULER] 全部完成！{completed}/{total} 个任务")
        socketio.emit("scheduler_status", {
            "running": False,
            "total": total,
            "completed": completed,
            "current": None,
        }, to=self.sid)
        socketio.emit("bot_status", {"running": False}, to=self.sid)


# ═══════════════════════════════════════════════════════════
#  Bot 包装器
# ═══════════════════════════════════════════════════════════

class BotRunner:
    """包装 BotCore，将回调桥接到 SocketIO。"""

    def __init__(self, config: dict, sid: str, label: str = ""):
        self.config = config
        self.sid = sid
        self.label = label
        self.bot: BotCore | None = None
        self.done = False

    def _prefix(self, msg: str) -> str:
        if self.label:
            return f"[{self.label}] {msg}"
        return msg

    def log_cb(self, msg: str):
        socketio.emit("bot_log", {"message": self._prefix(msg)}, to=self.sid)

    def screenshot_cb(self, data: bytes):
        b64 = base64.b64encode(data).decode("utf-8")
        socketio.emit("bot_screenshot", {"image": b64, "label": self.label}, to=self.sid)

    def progress_cb(self, stats: dict):
        socketio.emit("bot_progress", {**stats, "label": self.label}, to=self.sid)

    def run(self):
        # 构建完整配置（任务级 + 全局设置）
        full_config = dict(self.config)
        # 合并全局设置
        full_config.setdefault("browser", _config.get("browser", {}))
        full_config.setdefault("anti_detection", _config.get("anti_detection", {}))
        full_config.setdefault("rate_limit", _config.get("rate_limit", {}))
        full_config.setdefault("screenshot", _config.get("screenshot", {}))

        try:
            self.bot = BotCore(
                config=full_config,
                log_callback=self.log_cb,
                screenshot_callback=self.screenshot_cb,
                progress_callback=self.progress_cb,
            )
            self.bot.start()
        except Exception as e:
            self.log_cb(f"[SYSTEM] Bot 异常退出: {e}")
        finally:
            self.bot = None
            self.done = True

    def confirm_login(self) -> None:
        """代理到 BotCore.confirm_login()"""
        if self.bot:
            self.bot.confirm_login()

    def check_login_status(self) -> bool:
        """代理到 BotCore.check_login_status()"""
        if self.bot:
            return self.bot.check_login_status()
        return False

    def stop(self):
        if self.bot:
            self.bot.stop()
            self.bot = None


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
    _config = data
    save_config(_config)
    return jsonify({"status": "ok", "config": _config})


@app.route("/api/config/accounts", methods=["POST"])
def api_add_account():
    """添加新账号（空模板）。"""
    global _config
    new_account = {
        "name": f"账号{len(_config.get('accounts', [])) + 1}",
        "enabled": True,
        "cookie_file": f"zhipin_cookies_{len(_config.get('accounts', [])) + 1}.json",
        "image_files": [],
        "message_interval_min": 3,
        "message_interval_max": 8,
        "jobs": [{
            "enabled": True,
            "city": "上海",
            "query": "",
            "scroll_pages": 5,
            "greeting_message": "您好，希望能获得面试机会。",
        }],
    }
    _config.setdefault("accounts", []).append(new_account)
    save_config(_config)
    return jsonify({"status": "ok", "accounts": _config["accounts"]})


@app.route("/api/config/accounts/<int:ai>", methods=["DELETE"])
def api_delete_account(ai):
    """删除账号。"""
    global _config
    accs = _config.get("accounts", [])
    if 0 <= ai < len(accs):
        accs.pop(ai)
        save_config(_config)
        return jsonify({"status": "ok", "accounts": accs})
    return jsonify({"status": "error", "errors": ["账号索引无效"]}), 400


@app.route("/api/config/accounts/<int:ai>/jobs", methods=["POST"])
def api_add_job(ai):
    """为指定账号添加岗位。"""
    global _config
    accs = _config.get("accounts", [])
    if not (0 <= ai < len(accs)):
        return jsonify({"status": "error", "errors": ["账号索引无效"]}), 400
    new_job = {
        "enabled": True,
        "city": "上海",
        "query": "",
        "scroll_pages": 5,
        "greeting_message": "您好，希望能获得面试机会。",
        "min_salary": 0,
        "max_salary": 0,
        "experience": "",
        "education": "",
        "exclude_companies": [],
        "include_keywords": [],
    }
    accs[ai].setdefault("jobs", []).append(new_job)
    save_config(_config)
    return jsonify({"status": "ok", "accounts": accs})


@app.route("/api/config/accounts/<int:ai>/jobs/<int:ji>", methods=["DELETE"])
def api_delete_job(ai, ji):
    """删除岗位。"""
    global _config
    accs = _config.get("accounts", [])
    if 0 <= ai < len(accs):
        jobs = accs[ai].get("jobs", [])
        if 0 <= ji < len(jobs):
            jobs.pop(ji)
            save_config(_config)
            return jsonify({"status": "ok", "accounts": accs})
    return jsonify({"status": "error", "errors": ["索引无效"]}), 400


@app.route("/api/images", methods=["GET"])
def api_list_images():
    """列出可用图片附件。"""
    img_dir = os.path.join(BASE_DIR, "dashboard")
    files = []
    if os.path.exists(img_dir):
        for f in sorted(os.listdir(img_dir)):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                files.append(f)
    return jsonify(files)


@app.route("/api/status")
def api_status():
    """当前运行状态。"""
    global _scheduler_thread
    running = _scheduler_thread is not None and _scheduler_thread.is_alive()
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


@socketio.on("start_all")
def on_start_all(data=None):
    """启动所有启用的账号×岗位任务。"""
    global _scheduler_thread, _scheduler_stop, _bot, _scheduler_instance

    # 如果有旧的调度器线程卡住，先尝试停止
    if _scheduler_thread and _scheduler_thread.is_alive():
        emit("bot_log", {"message": "[SYSTEM] 检测到旧调度器仍在运行，正在停止旧调度器..."})
        if _scheduler_instance:
            _scheduler_instance.stop()
        _scheduler_thread.join(timeout=10)
        _scheduler_thread = None
        _scheduler_instance = None
        emit("bot_log", {"message": "[SYSTEM] 旧调度器已停止"})

    # 展开任务
    tasks = flatten_jobs_for_run(_config)
    if not tasks:
        emit("bot_log", {"message": "[SYSTEM] 没有启用的任务（请检查账号和岗位的 enabled 状态）"})
        return

    emit("bot_log", {"message": f"[SYSTEM] 调度器启动，共 {len(tasks)} 个任务"})
    emit("bot_status", {"running": True})

    _scheduler_stop.clear()
    scheduler = TaskScheduler(tasks, request.sid)
    _scheduler_instance = scheduler
    _bot = scheduler  # 使 confirm_login / check_login 能到达当前 BotCore

    def _run_scheduler():
        scheduler.run()
        global _scheduler_thread, _scheduler_instance
        _scheduler_thread = None
        _scheduler_instance = None

    _scheduler_thread = threading.Thread(target=_run_scheduler, daemon=True)
    _scheduler_thread.start()


@socketio.on("stop_all")
def on_stop_all():
    """停止调度器。"""
    global _scheduler_stop, _scheduler_instance
    _scheduler_stop.set()
    # 停止调度器实例（会停止所有 BotRunner）
    if _scheduler_instance:
        _scheduler_instance.stop()
        emit("bot_log", {"message": "[SYSTEM] 正在停止调度器..."})
    else:
        emit("bot_log", {"message": "[SYSTEM] 调度器未运行"})
    emit("bot_status", {"running": False})
    emit("scheduler_status", {"running": False})


@socketio.on("start_bot")
def on_start_bot(data):
    """
    兼容旧版：单任务快速启动。
    如果 data 中有 account/job 索引则跑特定任务，
    否则使用配置中的第一个启用的任务。
    """
    global _bot, _bot_thread, _scheduler_thread

    if _bot_thread and _bot_thread.is_alive():
        emit("bot_log", {"message": "[SYSTEM] Bot 已在运行中，先停止旧的..."})
        _bot_thread = None

    if _scheduler_thread and _scheduler_thread.is_alive():
        emit("bot_log", {"message": "[SYSTEM] 调度器正在运行，请先停止调度器"})
        return

    tasks = flatten_jobs_for_run(_config)
    if not tasks:
        emit("bot_log", {"message": "[SYSTEM] 没有启用的任务"})
        return

    # 选择任务
    task_idx = 0
    if data and "task_index" in data:
        task_idx = data["task_index"]
    if task_idx >= len(tasks):
        emit("bot_log", {"message": f"[SYSTEM] 任务索引 {task_idx} 超出范围"})
        return

    task = tasks[task_idx]

    bot_config = {
        "city": task["city"],
        "job_query": task["query"],
        "scroll_pages": task["scroll_pages"],
        "greeting_message": task["greeting_message"],
        "image_files": task["image_files"],
        "message_interval_min": task["message_interval_min"],
        "message_interval_max": task["message_interval_max"],
        "browser": _config.get("browser", {}),
        "anti_detection": _config.get("anti_detection", {}),
        "rate_limit": _config.get("rate_limit", {}),
        "screenshot": _config.get("screenshot", {}),
    }

    label = f"{task['account_name']} / {task['query']}({task['city']})"
    runner = BotRunner(bot_config, request.sid, label)
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
#  入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"  Boss 直聘 · 自动投递  Web 版（多岗位多账号）")
    print(f"  启动地址: http://127.0.0.1:5000")
    print(f"  {'='*40}")
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)
