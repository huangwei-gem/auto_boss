"""
Boss直聘 · 自动投递 — Web 服务端（多岗位多账号版）

Flask + Flask-SocketIO 单进程架构。
任务调度器按账号顺序串行执行（Boss直聘限制：一个cookie只能登在一个浏览器），
同一账号的多个岗位依次执行，不同账号可并行。
"""
import json
import logging
import os
import sys
import threading
import base64
import time
import uuid
import shutil
import mimetypes
from typing import Optional
from collections import OrderedDict

from flask import Flask, render_template, request, jsonify, send_file, abort
from flask_socketio import SocketIO, emit

# ── 路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_DIR)
os.chdir(BASE_DIR)

from config import load_config, save_config, validate_config, flatten_jobs_for_run
sys.path.insert(0, os.path.join(PROJECT_DIR, "core"))
from bot_core import BotCore

# ── Flask 应用 ──
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max upload
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── 全局状态 ──
_bot = None
_bot_thread = None
_scheduler_thread = None
_scheduler_stop = threading.Event()
_scheduler_running = False
_config = load_config()
_current_task = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("boss-web")


# ═══════════════════════════════════════════════════════════
#  BotRunner — 包装一个 BotCore 实例
# ═══════════════════════════════════════════════════════════

class BotRunner:
    """包装一个 BotCore 实例，在独立线程中运行。"""

    def __init__(self, bot_config: dict, sid: str, label: str):
        self.bot_config = bot_config
        self.sid = sid
        self.label = label
        self.bot = None
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
                progress_callback=None,
            )
            socketio.emit("scheduler_status", {
                "running": True,
                "current": {
                    "account": self.label.split(" / ")[0],
                    "query": self.label.split(" / ")[1] if " / " in self.label else self.label,
                    "city": ""
                },
            }, to=self.sid)
            self.bot.start()
            self.done = True
            self.log("已完成")
        except Exception as e:
            self.log(f"错误: {e}")
            import traceback
            self.log(f"详细: {traceback.format_exc()}")
            self.done = True


# ═══════════════════════════════════════════════════════════
#  TaskScheduler — 按账号顺序执行任务
# ═══════════════════════════════════════════════════════════

class TaskScheduler:
    """按账号顺序执行任务，同一账号的岗位串行执行。"""

    def __init__(self, tasks: list[dict], sid: str):
        self.tasks = tasks
        self.sid = sid
        self._stop = threading.Event()
        self._runners = []

    def log(self, msg: str):
        socketio.emit("bot_log", {"message": msg}, to=self.sid)

    def confirm_login(self):
        for runner in self._runners:
            if runner and runner.bot:
                runner.bot.confirm_login()

    def check_login_status(self):
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
            "running": True, "total": total, "completed": 0, "current": None,
        }, to=self.sid)

        # 按账号分组，同一账号的任务串行执行
        account_groups = OrderedDict()
        for task in self.tasks:
            acc = task["account_name"]
            if acc not in account_groups:
                account_groups[acc] = []
            account_groups[acc].append(task)

        completed = 0
        for acc_name, acc_tasks in account_groups.items():
            if self._stop.is_set():
                break
            for task in acc_tasks:
                if self._stop.is_set():
                    break
                label = f"{task['account_name']} / {task['query']}({task['city']})"
                runner = BotRunner(task, self.sid, label)
                self._runners.append(runner)

                self.log(f"[SCHEDULER] 启动 [{completed+1}/{total}] {label}")
                runner.run()
                completed += 1

                # 等待任务完成后再启动下一个（同一账号串行）
                runner.done = False
                # 简单轮询等待
                while not runner.done and not self._stop.is_set():
                    time.sleep(0.5)

                socketio.emit("scheduler_status", {
                    "running": not self._stop.is_set(),
                    "total": total,
                    "completed": completed,
                    "current": None if self._stop.is_set() else {"account": task["account_name"], "query": task["query"], "city": task["city"]},
                }, to=self.sid)

        self.log(f"[SCHEDULER] 全部完成！{completed}/{total} 个任务")
        socketio.emit("scheduler_status", {
            "running": False, "total": total, "completed": completed, "current": None,
        }, to=self.sid)


# ═══════════════════════════════════════════════════════════
#  Routes — 页面
# ═══════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ═══════════════════════════════════════════════════════════
#  Routes — 配置 API
# ═══════════════════════════════════════════════════════════

@app.route("/api/config", methods=["GET"])
def api_get_config():
    global _config
    return jsonify({"status": "ok", "config": _config})


@app.route("/api/config", methods=["PUT"])
def api_put_config():
    global _config
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求体为空"}), 400
        if not isinstance(data.get("config"), dict):
            return jsonify({"status": "error", "message": "config 字段必须是对象"}), 400

        new_cfg = data["config"]
        errors = validate_config(new_cfg)
        if errors:
            return jsonify({"status": "error", "message": "；".join(errors)}), 400

        _config = new_cfg
        save_config(_config)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.exception("保存配置失败")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/config/accounts", methods=["POST"])
def api_add_account():
    global _config
    try:
        idx = len(_config["accounts"])
        _config["accounts"].append({
            "name": f"账号{idx + 1}",
            "enabled": True,
            "cookie_file": "zhipin_cookies.json",
            "image_files": [],
            "message_interval_min": 3,
            "message_interval_max": 8,
            "jobs": [{
                "enabled": True,
                "city": "上海",
                "query": "数据分析",
                "scroll_pages": 5,
                "greeting_message": "您好，我是双一流的本科，应聘数据分析岗位。在校系统学习数据分析相关知识，掌握Excel、基础SQL与数据整理技能，具备数据思维。做事严谨细心，学习能力强，愿意踏实积累。十分认可贵公司，希望能获得面试机会。"
            }]
        })
        save_config(_config)
        return jsonify({"status": "ok", "accounts": _config["accounts"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/config/accounts/<int:idx>", methods=["DELETE"])
def api_delete_account(idx):
    global _config
    try:
        accounts = _config.get("accounts", [])
        if idx < 0 or idx >= len(accounts):
            return jsonify({"status": "error", "message": "账号索引无效"}), 400
        accounts.pop(idx)
        save_config(_config)
        return jsonify({"status": "ok", "accounts": accounts})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/config/accounts/<int:aidx>/jobs", methods=["POST"])
def api_add_job(aidx):
    global _config
    try:
        accounts = _config.get("accounts", [])
        if aidx < 0 or aidx >= len(accounts):
            return jsonify({"status": "error", "message": "账号索引无效"}), 400
        data = request.get_json() or {}
        job = {
            "enabled": True,
            "city": data.get("city", "上海"),
            "query": data.get("query", "数据分析"),
            "scroll_pages": data.get("scroll_pages", 5),
            "greeting_message": data.get("greeting_message", "您好，我是双一流的本科，应聘数据分析岗位。在校系统学习数据分析相关知识，掌握Excel、基础SQL与数据整理技能，具备数据思维。做事严谨细心，学习能力强，愿意踏实积累。十分认可贵公司，希望能获得面试机会。"),
        }
        accounts[aidx]["jobs"].append(job)
        save_config(_config)
        return jsonify({"status": "ok", "jobs": accounts[aidx]["jobs"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/config/accounts/<int:aidx>/jobs/<int:jidx>", methods=["DELETE"])
def api_delete_job(aidx, jidx):
    global _config
    try:
        accounts = _config.get("accounts", [])
        if aidx < 0 or aidx >= len(accounts):
            return jsonify({"status": "error", "message": "账号索引无效"}), 400
        jobs = accounts[aidx].get("jobs", [])
        if jidx < 0 or jidx >= len(jobs):
            return jsonify({"status": "error", "message": "岗位索引无效"}), 400
        jobs.pop(jidx)
        save_config(_config)
        return jsonify({"status": "ok", "jobs": jobs})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ═══════════════════════════════════════════════════════════
#  Routes — 文件上传 / 删除
# ═══════════════════════════════════════════════════════════

@app.route("/api/upload/image", methods=["POST"])
@app.route("/api/upload/images", methods=["POST"])
def api_upload_image():
    """上传作品图片到 dashboard/ 目录，返回文件名列表。"""
    dashboard_dir = os.path.join(BASE_DIR, "dashboard")
    os.makedirs(dashboard_dir, exist_ok=True)
    files = request.files.getlist("files")
    if not files:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    uploaded = []
    for f in files:
        if f.filename:
            safe_name = f"{uuid.uuid4().hex[:8]}_{f.filename}"
            save_path = os.path.join(dashboard_dir, safe_name)
            f.save(save_path)
            uploaded.append(f"dashboard/{safe_name}")
    return jsonify({"status": "ok", "images": uploaded, "files": uploaded})


@app.route("/api/upload/cookie", methods=["POST"])
def api_upload_cookie():
    """上传 Cookie 文件到工作目录。"""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    save_path = os.path.join(BASE_DIR, "zhipin_cookies.json")
    f.save(save_path)
    return jsonify({"status": "ok", "filename": "zhipin_cookies.json", "path": "zhipin_cookies.json"})


@app.route("/api/delete/image", methods=["POST"])
@app.route("/api/images/delete", methods=["POST"])
def api_delete_image():
    """删除作品图片文件。"""
    data = request.get_json()
    path = (data.get("path") or data.get("filename") or "") if data else ""
    if not path:
        return jsonify({"status": "error", "message": "缺少文件路径"}), 400
    full_path = os.path.join(BASE_DIR, path)
    if os.path.exists(full_path) and os.path.isfile(full_path):
        os.remove(full_path)
        return jsonify({"status": "ok"})
    # Try matching by basename
    basename = os.path.basename(path)
    dashboard_dir = os.path.join(BASE_DIR, "dashboard")
    if os.path.exists(dashboard_dir):
        for fn in os.listdir(dashboard_dir):
            if fn == basename:
                os.remove(os.path.join(dashboard_dir, fn))
                return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "文件不存在"}), 404


@app.route("/api/upload/greeting", methods=["POST"])
def api_upload_greeting():
    """上传打招呼模板文件。"""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    content = f.read().decode("utf-8").strip()
    return jsonify({"status": "ok", "greeting": content})


# ═══════════════════════════════════════════════════════════
#  Routes — 调度器状态
# ═══════════════════════════════════════════════════════════

@app.route("/api/scheduler/reset", methods=["POST"])
def api_scheduler_reset():
    """重置调度器状态。"""
    global _scheduler_running, _scheduler_thread, _bot, _bot_thread
    _scheduler_running = False
    _scheduler_thread = None
    _bot = None
    _bot_thread = None
    _scheduler_stop.clear()
    return jsonify({"status": "ok"})


# ═══════════════════════════════════════════════════════════
#  SocketIO — 调度器控制
# ═══════════════════════════════════════════════════════════

@socketio.on("start_all")
def on_start_all(data=None):
    """启动所有启用的账号×岗位任务。"""
    global _scheduler_thread, _scheduler_stop, _bot, _scheduler_running

    # 如果标记为运行中但线程已死，先重置
    if _scheduler_running:
        if _scheduler_thread and _scheduler_thread.is_alive():
            emit("bot_log", {"message": "[SYSTEM] 调度器已在运行中"})
            return
        else:
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
    emit("scheduler_status", {"running": True, "total": len(tasks), "completed": 0, "current": None})

    _scheduler_stop.clear()
    _scheduler_running = True
    scheduler = TaskScheduler(tasks, request.sid)
    _bot = scheduler

    def _run_scheduler():
        global _scheduler_running, _scheduler_thread
        try:
            scheduler.run()
        except Exception as e:
            logger.error(f"调度器异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            try:
                emit("bot_log", {"message": f"[SYSTEM] 调度器异常: {e}"}, to=request.sid)
            except Exception:
                pass
        finally:
            _scheduler_running = False
            _scheduler_thread = None
            try:
                emit("bot_status", {"running": False}, to=request.sid)
            except Exception:
                pass

    _scheduler_thread = threading.Thread(target=_run_scheduler, daemon=True)
    _scheduler_thread.start()


@socketio.on("stop_all")
def on_stop_all():
    """停止所有任务。"""
    global _scheduler_stop, _scheduler_thread, _bot, _scheduler_running
    _scheduler_stop.set()
    _scheduler_running = False
    if _bot:
        try:
            _bot.stop()
        except Exception:
            pass
    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=3)
    _scheduler_thread = None
    try:
        emit("bot_log", {"message": "[SYSTEM] 正在停止调度器..."})
        emit("bot_status", {"running": False})
        emit("scheduler_status", {"running": False}, to=request.sid)
    except Exception:
        pass


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
#  Static file serving
# ═══════════════════════════════════════════════════════════

@app.route("/dashboard/<path:filename>")
def serve_dashboard(filename):
    full_path = os.path.join(BASE_DIR, "dashboard", filename)
    if os.path.exists(full_path) and os.path.isfile(full_path):
        return send_file(full_path)
    return abort(404)


@app.route("/api/images/list", methods=["GET"])
def api_images_list():
    """列出所有作品图片。"""
    dashboard_dir = os.path.join(BASE_DIR, "dashboard")
    if not os.path.exists(dashboard_dir):
        os.makedirs(dashboard_dir, exist_ok=True)
    images = []
    for fn in sorted(os.listdir(dashboard_dir), reverse=True):
        fp = os.path.join(dashboard_dir, fn)
        if os.path.isfile(fp) and fn.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
            images.append(f"dashboard/{fn}")
    return jsonify({"status": "ok", "images": images})


if __name__ == "__main__":
    print("  Boss 直聘 · 自动投递  Web 版（多岗位多账号）")
    print("  启动地址: http://127.0.0.1:5000")
    print("  " + "=" * 40)
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)
