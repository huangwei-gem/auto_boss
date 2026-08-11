import json, os, sys, threading, uuid, shutil, urllib.parse, logging, time
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
    """包装多个任务，同一账号的多个岗位共用同一个浏览器。"""

    def __init__(self, tasks: list, account_name: str, sid: str):
        self.tasks = tasks
        self.account_name = account_name
        self.sid = sid
        self.bot = None
        self.done = False

    def log(self, msg: str):
        try:
            socketio.emit("bot_log", {"message": f"[{self.account_name}] {msg}"}, to=self.sid)
        except Exception:
            pass

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

    def login_required(self):
        """通知前端需要登录。"""
        try:
            socketio.emit("login_required", {
                "account": self.account_name,
                "message": f"[{self.account_name}] 登录已过期，请在浏览器中重新登录后点击「确认登录」"
            }, to=self.sid)
        except Exception:
            pass

    def run(self):
        """运行此账号的所有岗位任务（串行，共用同一个浏览器）。"""
        try:
            if not self.tasks:
                self.log("没有任务")
                self.done = True
                return

            self.log(f"启动账号: {self.account_name} ({len(self.tasks)} 个岗位，共用 1 个浏览器)")

            # 使用第一个任务的配置创建 BotCore
            first_task = self.tasks[0]
            task_config = self._make_task_config(first_task)

            def log_cb(msg):
                self.log(msg)

            def progress_cb(data):
                try:
                    socketio.emit("bot_progress", data, to=self.sid)
                except Exception:
                    pass

            # 创建 BotCore（一个账号一个浏览器实例）
            self.bot = BotCore(
                config=task_config,
                log_callback=log_cb,
                progress_callback=progress_cb,
            )

            # 串行执行所有任务（共用同一个浏览器）
            self.bot.start(tasks=self.tasks)

            self.log(f"账号 {self.account_name} 所有任务完成")
            self.done = True
        except Exception as e:
            self.log(f"错误: {e}")
            import traceback
            self.log(f"详细: {traceback.format_exc()}")
            self.done = True



    def _make_task_config(self, task: dict) -> dict:
        """从 task 创建 BotCore 配置。"""
        import copy
        cfg = copy.deepcopy(task)
        cfg["_login_required_callback"] = self.login_required
        return cfg

class TaskScheduler:
    """按账号顺序执行，同一账号的岗位串行执行（复用同一个浏览器）。"""

    def __init__(self, tasks: list[dict], sid: str):
        self.tasks = tasks
        self.sid = sid
        self._stop = threading.Event()
        self._current_runner = None

    def log(self, msg: str):
        try:
            socketio.emit("bot_log", {"message": msg}, to=self.sid)
        except Exception:
            pass

    def confirm_login(self):
        if self._current_runner:
            self._current_runner.confirm_login()

    def check_login_status(self):
        if self._current_runner:
            return self._current_runner.check_login_status()
        return False

    def stop(self):
        self._stop.set()
        if self._current_runner:
            self._current_runner.stop()

    def run(self, target_sid):
        self.log(f"[SYSTEM] 调度器启动，共 {len(self.tasks)} 个任务")

        # 按账号分组
        account_groups = {}
        for t in self.tasks:
            name = t.get("account_name", "默认")
            if name not in account_groups:
                account_groups[name] = []
            account_groups[name].append(t)

        self.log(f"[SCHEDULER] 共 {len(account_groups)} 个账号：{list(account_groups.keys())}")
        total_count = len(self.tasks)
        completed_count = 0

        for acc_name, acc_tasks in account_groups.items():
            if self._stop.is_set():
                self.log(f"[SCHEDULER] 已被中断")
                break

            self.log(f"[SCHEDULER] 处理账号：{acc_name}（{len(acc_tasks)} 个岗位，共用 1 个浏览器）")

            # 一个账号创建一个 BotRunner，共用同一个浏览器
            runner = BotRunner(acc_tasks, acc_name, self.sid)
            self._current_runner = runner

            # 同步执行（串行）
            runner.run()

            # 等待完成
            while not runner.done and not self._stop.is_set():
                time.sleep(0.5)

            completed_count += len(acc_tasks)
            self.log(f"[SCHEDULER] ✓ 账号 {acc_name} 已完成（{len(acc_tasks)} 个岗位）")

            socketio.emit("scheduler_status", {
                "running": True,
                "total": total_count,
                "completed": completed_count,
                "current": None,
            }, to=self.sid)

            self._current_runner = None

        self.log(f"[SCHEDULER] 全部完成！{completed_count}/{total_count} 个任务")
        socketio.emit("scheduler_status", {
            "running": False,
            "total": total_count,
            "completed": completed_count,
            "current": None,
        }, to=self.sid)


# ── Routes ──

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
                "greeting_message": DEFAULT_GREETING,
            }],
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


@app.route("/api/config/accounts/<int:acc_idx>/jobs", methods=["POST"])
def api_add_job(acc_idx):
    global _config
    try:
        data = request.get_json() or {}
        if 0 <= acc_idx < len(_config["accounts"]):
            _config["accounts"][acc_idx].setdefault("jobs", [])
            _config["accounts"][acc_idx]["jobs"].append({
                "enabled": True,
                "city": data.get("city", "上海"),
                "query": data.get("query", "数据分析"),
                "scroll_pages": int(data.get("scroll_pages", 5)),
                "greeting_message": data.get("greeting_message", DEFAULT_GREETING),
            })
            save_config(_config)
            return jsonify({"status": "ok", "jobs": _config["accounts"][acc_idx]["jobs"]})
        return jsonify({"status": "error", "message": "账号索引越界"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/config/accounts/<int:acc_idx>/jobs/<int:job_idx>", methods=["PUT", "DELETE"])
def api_update_job(acc_idx, job_idx):
    global _config
    try:
        if not (0 <= acc_idx < len(_config["accounts"])):
            return jsonify({"status": "error", "message": "账号索引越界"}), 404
        acc = _config["accounts"][acc_idx]
        if not (0 <= job_idx < len(acc.get("jobs", []))):
            return jsonify({"status": "error", "message": "岗位索引越界"}), 404
        if request.method == "DELETE":
            del acc["jobs"][job_idx]
            save_config(_config)
            return jsonify({"status": "ok", "jobs": acc["jobs"]})
        # PUT
        data = request.get_json() or {}
        for key in ("enabled", "city", "query", "scroll_pages", "greeting_message"):
            if key in data:
                acc["jobs"][job_idx][key] = data[key]
        save_config(_config)
        return jsonify({"status": "ok", "jobs": acc["jobs"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Image / Upload API ──

@app.route("/api/upload/images", methods=["POST"])
def api_upload_images():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    dashboard_dir = os.path.join(BASE_DIR, "dashboard")
    os.makedirs(dashboard_dir, exist_ok=True)
    uploaded = []
    for f in files:
        if f and f.filename:
            filename = uuid.uuid4().hex[:8] + "_" + f.filename
            save_path = os.path.join(dashboard_dir, filename)
            f.save(save_path)
            uploaded.append(f"dashboard/{filename}")
    return jsonify({"status": "ok", "files": uploaded})


@app.route("/api/upload/cookie", methods=["POST"])
def api_upload_cookie():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    save_path = os.path.join(BASE_DIR, "zhipin_cookies.json")
    f.save(save_path)
    return jsonify({"status": "ok", "filename": "zhipin_cookies.json"})


@app.route("/api/images/delete", methods=["POST"])
def api_delete_image():
    """删除图片文件。"""
    data = request.get_json() or {}
    path = data.get("path", "")
    delete_all = data.get("delete_all", False)
    if not path and not delete_all:
        return jsonify({"status": "error", "message": "path 不能为空或需要 delete_all=True"}), 400
    dashboard_dir = os.path.join(BASE_DIR, "dashboard")
    
    # 批量删除所有图片
    if delete_all:
        if os.path.exists(dashboard_dir):
            deleted = 0
            for fn in os.listdir(dashboard_dir):
                fp = os.path.join(dashboard_dir, fn)
                if os.path.isfile(fp):
                    try:
                        os.remove(fp)
                        deleted += 1
                    except Exception:
                        pass
            return jsonify({"status": "ok", "deleted": deleted})
        return jsonify({"status": "ok", "deleted": 0})
    
    # 单个删除 - 支持完整路径或文件名
    basename = os.path.basename(path)
    # 也尝试去除可能的 dashboard/ 前缀
    clean_name = basename.replace("dashboard/", "").replace("dashboard\\", "")
    if os.path.exists(dashboard_dir):
        for fn in os.listdir(dashboard_dir):
            if clean_name == fn or basename == fn:
                filepath = os.path.join(dashboard_dir, fn)
                if os.path.isfile(filepath):
                    try:
                        os.remove(filepath)
                        return jsonify({"status": "ok"})
                    except Exception as e:
                        return jsonify({"status": "error", "message": str(e)}), 500
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
                try:
                    _bot.stop()
                except Exception:
                    pass
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
            "thread_alive": _scheduler_thread is not None and _scheduler_thread.is_alive() if _scheduler_thread else False,
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





@app.route("/api/cookies/upload", methods=["POST"])
def api_upload_cookies():
    """上传 Cookie 文件。"""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    try:
        content_data = f.read().decode("utf-8")
        json.loads(content_data)  # 验证 JSON 格式
        dst = os.path.join(BASE_DIR, "zhipin_cookies.json")
        with open(dst, "w", encoding="utf-8") as out:
            out.write(content_data)
        return jsonify({"status": "ok", "filename": "zhipin_cookies.json"})
    except json.JSONDecodeError:
        return jsonify({"status": "error", "message": "无效的 JSON 格式"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cookies/list", methods=["GET"])
def api_cookies_list():
    """列出可用的 Cookie 文件。"""
    cookies = []
    for fn in os.listdir(BASE_DIR):
        if fn.endswith(".json") and "cookie" in fn.lower():
            cookies.append(fn)
    return jsonify({"status": "ok", "cookies": cookies})


@app.route("/api/cookies/delete", methods=["POST"])
def api_delete_cookie():
    """删除 Cookie 文件。"""
    data = request.get_json() or {}
    filename = data.get("filename", "")
    if not filename:
        return jsonify({"status": "error", "message": "filename 不能为空"}), 400
    filepath = os.path.join(BASE_DIR, filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        os.remove(filepath)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "文件不存在"}), 404

# ── SocketIO ──

@socketio.on("start_all")
def on_start_all(data=None):
    global _scheduler_thread, _scheduler_stop, _bot, _scheduler_running, _config

    sid = request.sid

    with _scheduler_lock:
        if _scheduler_running:
            emit("bot_log", {"message": "[SYSTEM] 调度器已在运行中，正在停止旧调度器..."})
            _scheduler_stop.set()
            if _bot:
                try:
                    _bot.stop()
                except Exception:
                    pass
                _bot = None
            if _scheduler_thread and _scheduler_thread.is_alive():
                _scheduler_thread.join(timeout=5)
            _scheduler_thread = None
            _scheduler_running = False
            _scheduler_stop.clear()
            import time
            time.sleep(1)
            logger.info("已停止旧调度器线程，重新启动")

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



