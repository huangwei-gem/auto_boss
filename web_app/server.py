import json, os, sys, threading, uuid, shutil, urllib.parse, logging
from typing import Optional
from flask import Flask, render_template, request, jsonify, send_file, abort
from flask_socketio import SocketIO, emit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_DIR)
os.chdir(BASE_DIR)

from config import load_config, save_config, validate_config, flatten_jobs_for_run, DEFAULT_GREETING
sys.path.insert(0, os.path.join(PROJECT_DIR, "core"))
from bot_core import BotCore

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

_scheduler_lock = threading.Lock()
_scheduler_thread = None
_scheduler_stop = threading.Event()
_scheduler_running = False
_bot = None
_config = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("boss-web")


class BotRunner:
    def __init__(self, bot_config: dict, sid: str, label: str):
        self.bot_config = bot_config
        self.sid = sid
        self.label = label
        self.bot = None
        self.done = False

    def log(self, msg: str):
        try:
            socketio.emit("bot_log", {"message": f"[{self.label}] {msg}"}, to=self.sid)
        except Exception:
            pass

    def stop(self):
        if self.bot:
            try: self.bot.stop()
            except Exception: pass

    def confirm_login(self):
        if self.bot:
            try: self.bot.confirm_login()
            except Exception: pass

    def check_login_status(self):
        if self.bot:
            try: return self.bot.check_login_status()
            except Exception: pass
        return False

    def run(self):
        try:
            self.log("启动中...")
            self.bot = BotCore(self.bot_config, log_callback=self.log, progress_callback=None)
            label_parts = self.label.split(" / ")
            socketio.emit("scheduler_status", {
                "running": True,
                "current": {
                    "account": label_parts[0] if len(label_parts) > 0 else self.label,
                    "query": label_parts[1] if len(label_parts) > 1 else "",
                    "city": "",
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


class TaskScheduler:
    def __init__(self, tasks: list[dict], sid: str):
        self.tasks = tasks
        self.sid = sid
        self._stop = threading.Event()
        self._runners = []

    def log(self, msg: str):
        try:
            socketio.emit("bot_log", {"message": msg}, to=self.sid)
        except Exception: pass

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

    def run(self, target_sid):
        self.log(f"[SYSTEM] 调度器启动，共 {len(self.tasks)} 个任务")
        self.log(f"[SCHEDULER] 并发启动 {len(self.tasks)} 个任务...")
        self._runners = []
        for i, task in enumerate(self.tasks):
            if self._stop.is_set():
                self.log(f"[SCHEDULER] 已停止")
                return
            label = f"{task.get('account_name', '')} / {task.get('query', '')}"
            runner = BotRunner(task, target_sid, label)
            self._runners.append(runner)
            t = threading.Thread(target=runner.run, daemon=True)
            t.start()
            self.log(f"[SCHEDULER] ✓ 已启动 [{i+1}/{len(self.tasks)}] {label}")
        self.log(f"[SCHEDULER] 全部完成！{len(self.tasks)}/{len(self.tasks)} 个任务")


@app.route("/")
def index():
    return render_template("index.html")


# ── Config API ──

@app.route("/api/config", methods=["GET"])
def api_get_config():
    global _config
    _config = load_config()
    return jsonify({"status": "ok", "config": _config})


@app.route("/api/config", methods=["POST", "PUT"])
def api_put_config():
    global _config
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求体为空"}), 400
        new_cfg = data.get("config") if isinstance(data.get("config"), dict) else data
        if not isinstance(new_cfg, dict):
            return jsonify({"status": "error", "message": "config 字段必须是对象"}), 400
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
                "greeting_message": DEFAULT_GREETING
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
        if 0 <= idx < len(_config["accounts"]):
            del _config["accounts"][idx]
            save_config(_config)
            return jsonify({"status": "ok", "accounts": _config["accounts"]})
        return jsonify({"status": "error", "message": "索引越界"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/config/accounts/<int:aidx>/jobs", methods=["POST"])
def api_add_job(aidx):
    global _config
    try:
        if 0 <= aidx < len(_config["accounts"]):
            job = {
                "enabled": True,
                "city": "上海",
                "query": "数据分析",
                "scroll_pages": 5,
                "greeting_message": DEFAULT_GREETING
            }
            _config["accounts"][aidx].setdefault("jobs", []).append(job)
            save_config(_config)
            return jsonify({"status": "ok", "jobs": _config["accounts"][aidx]["jobs"]})
        return jsonify({"status": "error", "message": "索引越界"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/config/accounts/<int:aidx>/jobs/<int:jidx>", methods=["DELETE"])
def api_delete_job(aidx, jidx):
    global _config
    try:
        if 0 <= aidx < len(_config["accounts"]):
            acc = _config["accounts"][aidx]
            if 0 <= jidx < len(acc.get("jobs", [])):
                del acc["jobs"][jidx]
                save_config(_config)
                return jsonify({"status": "ok", "jobs": acc["jobs"]})
        return jsonify({"status": "error", "message": "索引越界"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Upload API ──

@app.route("/api/upload/images", methods=["POST"])
def api_upload_image():
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
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    save_path = os.path.join(BASE_DIR, "zhipin_cookies.json")
    f.save(save_path)
    return jsonify({"status": "ok", "filename": "zhipin_cookies.json", "path": "zhipin_cookies.json"})


@app.route("/api/images/delete", methods=["POST"])
def api_delete_image():
    """删除作品图片文件。"""
    data = request.get_json()
    path = (data.get("path") or data.get("filename") or data.get("name") or "") if data else ""
    if not path:
        return jsonify({"status": "error", "message": "缺少文件路径"}), 400
    path = urllib.parse.unquote(path)
    path = path.lstrip("/")
    dashboard_dir = os.path.join(BASE_DIR, "dashboard")
    basename = os.path.basename(path)
    # 尝试: 直接搜索 basename
    if os.path.exists(dashboard_dir):
        for fn in os.listdir(dashboard_dir):
            if basename == fn:
                filepath = os.path.join(dashboard_dir, fn)
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    return jsonify({"status": "ok"})
        # 模糊匹配
        for fn in os.listdir(dashboard_dir):
            if basename in fn or fn in basename:
                filepath = os.path.join(dashboard_dir, fn)
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "文件不存在"}), 404


@app.route("/api/upload/greeting", methods=["POST"])
def api_upload_greeting():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    content = f.read().decode("utf-8").strip()
    return jsonify({"status": "ok", "greeting": content})


# ── Scheduler Status ──

@app.route("/api/scheduler/reset", methods=["POST"])
def api_scheduler_reset():
    global _scheduler_running, _scheduler_thread, _bot
    with _scheduler_lock:
        if _scheduler_thread and _scheduler_thread.is_alive():
            _scheduler_stop.set()
            if _bot:
                try: _bot.stop()
                except Exception: pass
            _scheduler_thread.join(timeout=5)
        _scheduler_running = False
        _scheduler_thread = None
        _bot = None
        _scheduler_stop.clear()
    return jsonify({"status": "ok"})


@app.route("/api/scheduler/status", methods=["GET"])
def api_scheduler_status():
    with _scheduler_lock:
        return jsonify({
            "status": "ok",
            "running": _scheduler_running,
            "thread_alive": _scheduler_thread is not None and _scheduler_thread.is_alive() if _scheduler_thread else False
        })


@app.route("/api/default/greeting", methods=["GET"])
def api_default_greeting():
    return jsonify({"status": "ok", "greeting": DEFAULT_GREETING})


@app.route("/api/images/list", methods=["GET"])
def api_images_list():
    dashboard_dir = os.path.join(BASE_DIR, "dashboard")
    if not os.path.exists(dashboard_dir):
        os.makedirs(dashboard_dir, exist_ok=True)
    images = []
    for fn in sorted(os.listdir(dashboard_dir), reverse=True):
        fp = os.path.join(dashboard_dir, fn)
        if os.path.isfile(fp) and fn.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
            images.append(f"dashboard/{fn}")
    return jsonify({"status": "ok", "images": images})


@app.route("/dashboard/<path:filename>")
def serve_dashboard(filename):
    full_path = os.path.join(BASE_DIR, "dashboard", filename)
    if os.path.exists(full_path) and os.path.isfile(full_path):
        return send_file(full_path)
    return abort(404)


# ── SocketIO ──

@socketio.on("start_all")
def on_start_all(data=None):
    global _scheduler_thread, _scheduler_stop, _bot, _scheduler_running, _config

    # 获取当前 socket session id
    sid = request.sid

    with _scheduler_lock:
        if _scheduler_thread and _scheduler_thread.is_alive():
            _scheduler_stop.set()
            if _bot:
                try: _bot.stop()
                except Exception: pass
                _bot = None
            _scheduler_thread.join(timeout=5)
            _scheduler_thread = None
            _scheduler_running = False
            _scheduler_stop.clear()
            logger.info("已停止旧调度器线程，重新启动")
        else:
            _scheduler_running = False
            _scheduler_thread = None
            _bot = None
            _scheduler_stop.clear()

    _config = load_config()
    tasks = flatten_jobs_for_run(_config)
    if not tasks:
        emit("bot_log", {"message": "[SYSTEM] 没有启用的任务（请检查账号和岗位的 enabled 状态）"})
        return

    emit("bot_log", {"message": f"[SYSTEM] 调度器启动，共 {len(tasks)} 个任务"})
    emit("bot_status", {"running": True})
    emit("scheduler_status", {"running": True, "total": len(tasks), "completed": 0, "current": None})

    _scheduler_stop.clear()
    with _scheduler_lock:
        _scheduler_running = True
        scheduler = TaskScheduler(tasks, sid)
        _bot = scheduler

    def _run_scheduler():
        global _scheduler_running, _scheduler_thread
        try:
            scheduler.run(sid)
        except Exception as e:
            logger.error(f"调度器异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            try:
                socketio.emit("bot_log", {"message": f"[SYSTEM] 调度器异常: {e}"}, to=sid)
            except Exception:
                pass
        finally:
            with _scheduler_lock:
                _scheduler_running = False
                _scheduler_thread = None
            try:
                socketio.emit("bot_status", {"running": False}, to=sid)
                socketio.emit("scheduler_status", {"running": False}, to=sid)
            except Exception:
                pass

    t = threading.Thread(target=_run_scheduler, daemon=True)
    with _scheduler_lock:
        _scheduler_thread = t
    t.start()


@socketio.on("stop_all")
def on_stop_all():
    global _scheduler_stop, _scheduler_thread, _bot, _scheduler_running
    with _scheduler_lock:
        _scheduler_stop.set()
        _scheduler_running = False
        if _bot:
            try: _bot.stop()
            except Exception: pass
        if _scheduler_thread and _scheduler_thread.is_alive():
            _scheduler_thread.join(timeout=3)
        _scheduler_thread = None
    try:
        emit("bot_log", {"message": "[SYSTEM] 正在停止调度器..."})
        emit("bot_status", {"running": False})
        emit("scheduler_status", {"running": False})
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


if __name__ == "__main__":
    print("  Boss 直聘 · 自动投递  Web 版（多岗位多账号）")
    print("  启动地址: http://127.0.0.1:5000")
    print("  " + "=" * 40)
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)
