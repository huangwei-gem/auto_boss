import json, os, sys, threading, uuid, shutil, urllib.parse, logging, time
from typing import Optional
from flask import Flask, render_template, request, jsonify, send_file, abort
from flask_socketio import SocketIO, emit

# app/ 目录结构：app/server.py, app/config.py, app/bot_core.py 同级
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")          # 所有运行时数据
STATIC_DIR = os.path.join(BASE_DIR, "static")      # 静态资源
DASHBOARD_DIR = os.path.join(STATIC_DIR, "dashboard")  # 作品图片
# 把 app/ 加到 path，这样 from config / from bot_core 能直接 import
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from config import load_config, save_config, validate_config, flatten_jobs_for_run, DEFAULT_GREETING
from bot_core import BotCore

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.urandom(24).hex()
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

_scheduler_lock = threading.Lock()
_scheduler_thread = None
_scheduler_stop = threading.Event()
_scheduler_run_id = 0
_scheduler_running = False
_bot = None
_config = None

def _ensure_config():
    """确保 _config 已初始化。"""
    global _config
    if _config is None:
        _config = load_config()
    return _config

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
    _ensure_config()
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
        data = request.get_json(silent=True) or {}
        idx = len(_config["accounts"])
        cookie_file = data.get("cookie_file", "zhipin_cookies.json")
        # 验证 cookie 文件是否存在，如果不存在则使用默认值
        cookie_path = os.path.join(DATA_DIR, cookie_file)
        if not os.path.isfile(cookie_path):
            cookie_file = "zhipin_cookies.json"
        _config["accounts"].append({
            "name": f"账号{idx + 1}",
            "enabled": True,
            "cookie_file": cookie_file,
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
        data = request.get_json(silent=True) or {}
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
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    uploaded = []
    for f in files:
        if f and f.filename:
            filename = uuid.uuid4().hex[:8] + "_" + f.filename
            save_path = os.path.join(DASHBOARD_DIR, filename)
            f.save(save_path)
            uploaded.append(f"dashboard/{filename}")
    return jsonify({"status": "ok", "files": uploaded})


@app.route("/api/upload/cookie", methods=["POST"])
def api_upload_cookie():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    safe_name = os.path.basename(f.filename)
    if not safe_name.endswith(".json"):
        safe_name += ".json"
    save_path = os.path.join(DATA_DIR, safe_name)
    f.save(save_path)
    return jsonify({"status": "ok", "filename": safe_name})


@app.route("/api/images/delete", methods=["POST"])
def api_delete_image():
    """删除图片文件（支持单张删除、批量指定删除、全部删除）。"""
    data = request.get_json() or {}
    path = data.get("path", "")
    # 兼容旧版：如果 path 是 dashboard/ 开头的，加上 static/dashboard 目录
    if path and not os.path.isabs(path):
        test_path = os.path.join(DASHBOARD_DIR, path)
        if os.path.exists(test_path):
            path = test_path
        # 也尝试直接用 dashboard 目录下的文件名
        elif "/" not in path and "\\" not in path:
            test_path2 = os.path.join(DASHBOARD_DIR, path)
            if os.path.exists(test_path2):
                path = test_path2
    delete_all = data.get("delete_all", False)
    delete_paths = data.get("paths", [])
    dashboard_dir = DASHBOARD_DIR
    
    # 批量删除所有图片
    if delete_all:
        if os.path.exists(dashboard_dir):
            deleted = 0
            for fn in os.listdir(dashboard_dir):
                fp = os.path.join(dashboard_dir, fn)
                if os.path.isfile(fp) and fn.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
                    try:
                        os.remove(fp)
                        deleted += 1
                    except Exception:
                        pass
            return jsonify({"status": "ok", "deleted": deleted})
        return jsonify({"status": "ok", "deleted": 0})
    
    # 批量删除指定路径列表
    if delete_paths:
        deleted = 0
        for p in delete_paths:
            p = urllib.parse.unquote(p)
            basename = os.path.basename(p)
            if os.path.exists(dashboard_dir):
                for fn in os.listdir(dashboard_dir):
                    if fn == basename or fn == p.replace('dashboard/', '').replace('dashboard\\', ''):
                        fp = os.path.join(dashboard_dir, fn)
                        if os.path.isfile(fp):
                            try:
                                os.remove(fp)
                                deleted += 1
                            except Exception:
                                pass
        return jsonify({"status": "ok", "deleted": deleted})
    
    # 单个删除
    if not path:
        return jsonify({"status": "error", "message": "path 不能为空"}), 400
    path = urllib.parse.unquote(path)
    basename = os.path.basename(path)
    clean_name = basename.replace("dashboard/", "").replace("dashboard\\", "")
    # 尝试精确匹配文件名
    if os.path.exists(dashboard_dir):
        for fn in os.listdir(dashboard_dir):
            if fn == clean_name or fn == basename:
                filepath = os.path.join(dashboard_dir, fn)
                if os.path.isfile(filepath):
                    try:
                        os.remove(filepath)
                        return jsonify({"status": "ok"})
                    except Exception as e:
                        return jsonify({"status": "error", "message": str(e)}), 500
        # 精确匹配失败时，尝试模糊匹配（忽略大小写和特殊字符）
        import re as _re
        clean_key = _re.sub(r"[\s_\-]", "", clean_name.lower())
        for fn in os.listdir(dashboard_dir):
            fn_key = _re.sub(r"[\s_\-]", "", fn.lower())
            if fn_key == clean_key or clean_key in fn_key or fn_key in clean_key:
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



@app.route("/api/advanced", methods=["GET", "POST"])
def api_advanced():
    """获取或保存高级设置。"""
    global _config
    if request.method == "GET":
        cfg = load_config()
        return jsonify({
            "status": "ok",
            "browser": cfg.get("browser", {}),
            "login": cfg.get("login", {}),
            "rate_limit": cfg.get("rate_limit", {}),
            "retry": cfg.get("retry", {}),
            "message_interval_min": cfg.get("accounts", [{}])[0].get("message_interval_min", 3) if cfg.get("accounts") else 3,
            "message_interval_max": cfg.get("accounts", [{}])[0].get("message_interval_max", 8) if cfg.get("accounts") else 8,
        })
    try:
        data = request.get_json() or {}
        cfg = load_config()
        if "browser" in data:
            cfg["browser"] = {**cfg.get("browser", {}), **data["browser"]}
        if "login" in data:
            cfg["login"] = {**cfg.get("login", {}), **data["login"]}
        if "rate_limit" in data:
            cfg["rate_limit"] = {**cfg.get("rate_limit", {}), **data["rate_limit"]}
        if "retry" in data:
            cfg["retry"] = {**cfg.get("retry", {}), **data["retry"]}
        # 消息间隔保存到每个账号
        for acc in cfg.get("accounts", []):
            if "message_interval_min" in data:
                acc["message_interval_min"] = int(data["message_interval_min"])
            if "message_interval_max" in data:
                acc["message_interval_max"] = int(data["message_interval_max"])
        save_config(cfg)
        _config = cfg
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


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


@app.route("/api/cities", methods=["GET"])
def api_cities():
    """返回支持的城市列表（硬编码 + 运行时捕获 + 文件缓存）"""
    from bot_core import CITY_CODES
    cities = set(CITY_CODES.keys())

    # 从运行时捕获的数据中添加
    if _bot and hasattr(_bot, '_city_dict') and _bot._city_dict:
        cities.update(_bot._city_dict.keys())

    # 从文件缓存中添加
    city_file = os.path.join(DATA_DIR, "city_dict.json")
    if os.path.exists(city_file):
        try:
            import json
            with open(city_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    cities.update(data.keys())
        except Exception:
            pass

    return jsonify({"status": "ok", "cities": sorted(cities)})


@app.route("/api/images/list", methods=["GET"])
def api_images_list():
    if not os.path.exists(DASHBOARD_DIR):
        os.makedirs(DASHBOARD_DIR, exist_ok=True)
    images = []
    for fn in sorted(os.listdir(DASHBOARD_DIR), reverse=True):
        fp = os.path.join(DASHBOARD_DIR, fn)
        if os.path.isfile(fp) and fn.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
            images.append(f"dashboard/{fn}")
    return jsonify({"status": "ok", "images": images})


@app.route("/dashboard/<path:filename>")
def serve_dashboard(filename):
    full_path = os.path.join(DASHBOARD_DIR, filename)
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
        safe_name = os.path.basename(f.filename) if f.filename else "zhipin_cookies.json"
        dst = os.path.join(DATA_DIR, safe_name)
        with open(dst, "w", encoding="utf-8") as out:
            out.write(content_data)
        return jsonify({"status": "ok", "filename": safe_name})
    except json.JSONDecodeError:
        return jsonify({"status": "error", "message": "无效的 JSON 格式"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cookies/list", methods=["GET"])
def api_cookies_list():
    """列出可用的 Cookie 文件。"""
    cookies = []
    for fn in os.listdir(DATA_DIR):
        if fn.endswith(".json") and (fn != "bot_config.json" and fn != "chats_log.json" and fn != "chatted_jobs.json"):
            cookies.append(fn)
    return jsonify({"status": "ok", "cookies": cookies})


@app.route("/api/cookies/delete", methods=["POST"])
def api_delete_cookie():
    """删除 Cookie 文件。"""
    data = request.get_json() or {}
    filename = data.get("filename", "")
    if not filename:
        return jsonify({"status": "error", "message": "filename 不能为空"}), 400
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        os.remove(filepath)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "文件不存在"}), 404

# ── SocketIO ──

@socketio.on("start_all")
def on_start_all(data=None):
    global _scheduler_thread, _scheduler_stop, _bot, _scheduler_running, _config, _scheduler_run_id

    sid = request.sid

    # Stop old scheduler if running
    if _scheduler_running:
        emit("bot_log", {"message": "[SYSTEM] 正在停止旧调度器..."})
        _scheduler_stop.set()
        if _bot:
            try:
                _bot.stop()
            except Exception:
                pass
            _bot = None
        if _scheduler_thread and _scheduler_thread.is_alive():
            _scheduler_thread.join(timeout=10)
        _scheduler_thread = None
        _scheduler_running = False
        _scheduler_stop.clear()
        time.sleep(1)
        logger.info("已停止旧调度器线程，重新启动")

    _config = load_config()
    tasks = flatten_jobs_for_run(_config)
    if not tasks:
        emit("bot_log", {"message": "[SYSTEM] 没有启用的任务（请检查账号和岗位的 enabled 状态）"})
        return

    _scheduler_run_id += 1
    my_run_id = _scheduler_run_id

    emit("bot_log", {"message": f"[SYSTEM] 调度器启动，共 {len(tasks)} 个任务"})
    emit("bot_status", {"running": True})
    emit("scheduler_status", {"running": True, "total": len(tasks), "completed": 0, "current": None})

    _scheduler_stop.clear()
    _scheduler_running = True
    scheduler = TaskScheduler(tasks, sid)
    _bot = scheduler

    def _run_scheduler(run_id):
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
            # Only clear running flag if this is still the current run
            if run_id == _scheduler_run_id:
                _scheduler_running = False
                _scheduler_thread = None
                try:
                    socketio.emit("bot_status", {"running": False}, to=sid)
                    socketio.emit("scheduler_status", {"running": False}, to=sid)
                except Exception:
                    pass

    t = threading.Thread(target=_run_scheduler, args=(my_run_id,), daemon=True)
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


@socketio.on("stop_login_modal")
def on_stop_login_modal():
    """关闭登录弹窗。"""
    emit("close_login_modal")



# ── AI 分析器实例 ──

_ai_analyzer = None

def _get_ai_analyzer():
    """获取或初始化 AI 分析器。"""
    global _ai_analyzer
    cfg = load_config()
    ai_cfg = cfg.get("ai", {})
    resume_cfg = cfg.get("resume", {})
    if _ai_analyzer is None:
        from ai_analyzer import AIAnalyzer
        _ai_analyzer = AIAnalyzer(
            api_key=ai_cfg.get("api_key", ""),
            api_base=ai_cfg.get("api_base", "https://apihub.agnes-ai.com/v1"),
            model=ai_cfg.get("model", "agnes-2.5-flash"),
            match_threshold=ai_cfg.get("match_threshold", 70),
            log_callback=lambda msg: logger.info(msg),
        )
    # 更新简历
    _ai_analyzer.set_resume(resume_cfg)
    return _ai_analyzer


# ── Resume API ──

@app.route("/api/resume", methods=["GET"])
def api_get_resume():
    """获取简历信息。"""
    cfg = load_config()
    return jsonify({"status": "ok", "resume": cfg.get("resume", {})})


@app.route("/api/resume", methods=["PUT", "POST"])
def api_save_resume():
    """保存简历信息。"""
    global _config
    try:
        data = request.get_json() or {}
        cfg = load_config()
        cfg["resume"] = {
            "school": data.get("school", ""),
            "major": data.get("major", ""),
            "degree": data.get("degree", ""),
            "skills": data.get("skills", []),
            "experience": data.get("experience", ""),
            "target_position": data.get("target_position", ""),
            "self_intro": data.get("self_intro", ""),
        }
        save_config(cfg)
        _config = cfg
        # 重置 AI 分析器，下次使用新简历
        global _ai_analyzer
        _ai_analyzer = None
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── AI Config API ──

@app.route("/api/ai/config", methods=["GET"])
def api_get_ai_config():
    """获取 AI 配置。"""
    cfg = load_config()
    return jsonify({"status": "ok", "ai": cfg.get("ai", {})})


@app.route("/api/ai/config", methods=["PUT", "POST"])
def api_save_ai_config():
    """保存 AI 配置。"""
    global _config, _ai_analyzer
    try:
        data = request.get_json() or {}
        cfg = load_config()
        cfg["ai"] = {
            "enabled": data.get("enabled", False),
            "api_key": data.get("api_key", ""),
            "api_base": data.get("api_base", "https://apihub.agnes-ai.com/v1"),
            "model": data.get("model", "agnes-2.5-flash"),
            "match_threshold": int(data.get("match_threshold", 70)),
        }
        save_config(cfg)
        _config = cfg
        # 重置 AI 分析器
        _ai_analyzer = None
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── AI Analysis API ──

@app.route("/api/ai/analyze", methods=["POST"])
def api_ai_analyze():
    """分析单个岗位。"""
    try:
        data = request.get_json() or {}
        job = data.get("job", {})
        if not job:
            return jsonify({"status": "error", "message": "job 不能为空"}), 400
        analyzer = _get_ai_analyzer()
        if not analyzer.api_key:
            return jsonify({"status": "error", "message": "AI API Key 未配置"}), 400
        result = analyzer.analyze_job(job)
        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        logger.exception("AI 分析失败")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ai/analyze-batch", methods=["POST"])
def api_ai_analyze_batch():
    """批量分析岗位。"""
    try:
        data = request.get_json() or {}
        jobs = data.get("jobs", [])
        if not jobs:
            return jsonify({"status": "error", "message": "jobs 不能为空"}), 400
        analyzer = _get_ai_analyzer()
        if not analyzer.api_key:
            return jsonify({"status": "error", "message": "AI API Key 未配置"}), 400
        results = analyzer.analyze_batch(jobs)
        return jsonify({"status": "ok", "results": results})
    except Exception as e:
        logger.exception("AI 批量分析失败")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ai/cache", methods=["GET"])
def api_ai_cache():
    """查看 AI 分析缓存状态。"""
    try:
        import os
        cache_file = os.path.join(DATA_DIR, "ai_cache.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            return jsonify({"status": "ok", "cache": cache, "count": len(cache)})
        return jsonify({"status": "ok", "cache": {}, "count": 0})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ai/cache/clear", methods=["POST"])
def api_ai_cache_clear():
    """清空 AI 分析缓存。"""
    try:
        analyzer = _get_ai_analyzer()
        analyzer.clear_cache()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ai/stats", methods=["GET"])
def api_ai_stats():
    """获取 AI 分析统计。"""
    try:
        analyzer = _get_ai_analyzer()
        stats = analyzer.get_stats()
        return jsonify({"status": "ok", "stats": stats})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── AI 提示词管理 ──

@app.route("/api/ai/prompts", methods=["GET"])
def api_ai_prompts_get():
    """获取当前 AI 提示词。"""
    try:
        prompts = _config.get("ai", {}).get("prompts", {})
        # 如果没有自定义提示词，返回默认模板
        if not prompts:
            from ai_analyzer import AIAnalyzer
            prompts = {
                "system": "你是 Boss直聘智能投递助手的岗位匹配分析专家。你的任务是分析招聘岗位与求职者简历的匹配程度，给出评分和详细理由。请按 JSON 格式返回结果。",
                "user": (
                    "【求职者简历】\n"
                    "教育背景：{school} {major} {degree}\n"
                    "技能：{skills}\n"
                    "工作经验：{experience}\n"
                    "求职意向：{target_position}\n\n"
                    "【招聘岗位】\n"
                    "岗位名称：{job_name}\n"
                    "薪资：{salary}\n"
                    "岗位描述：{description}\n"
                    "任职要求：{requirements}\n"
                    "公司：{company}\n\n"
                    "请分析匹配度，按以下 JSON 格式返回（不要包含其他内容）：\n"
                    '{\n  "score": 0-100,\n  "is_match": true/false,\n'
                    '  "reason": "匹配分析简要说明",\n'
                    '  "strengths": ["优势1", "优势2"],\n'
                    '  "weaknesses": ["劣势1", "劣势2"],\n'
                    '  "suggested_greeting": "基于岗位要求生成的个性化打招呼消息"\n}'
                ),
            }
        return jsonify({"status": "ok", "prompts": prompts})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ai/prompts", methods=["PUT"])
def api_ai_prompts_put():
    """保存 AI 提示词。"""
    global _config
    try:
        data = request.get_json(silent=True) or {}
        prompts = data.get("prompts", {})
        if not isinstance(prompts, dict):
            return jsonify({"status": "error", "message": "prompts 必须是对象"}), 400
        _config.setdefault("ai", {})["prompts"] = prompts
        save_config(_config)
        # 同步更新分析器的提示词
        global _bot
        if _bot and hasattr(_bot, '_ai_analyzer') and _bot._ai_analyzer:
            _bot._ai_analyzer.set_prompts(prompts)
        return jsonify({"status": "ok", "prompts": prompts})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/excel/files", methods=["GET"])
def api_excel_files():
    """获取 Excel 分析文件列表。"""
    try:
        from excel_exporter import get_analysis_files
        files = get_analysis_files()
        return jsonify({"status": "ok", "files": files})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/excel/download", methods=["GET"])
def api_excel_download():
    """下载指定 Excel 文件。"""
    try:
        from flask import send_file
        filename = request.args.get("filename", "")
        if not filename or "/" in filename or "\\" in filename:
            return jsonify({"status": "error", "message": "无效文件名"}), 400
        filepath = os.path.join(DATA_DIR, "jd_analysis", filename)
        if not os.path.exists(filepath):
            return jsonify({"status": "error", "message": "文件不存在"}), 404
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    print("  Boss 直聘 · 自动投递  Web 版（多岗位多账号）")
    print("  启动地址: http://127.0.0.1:5000")
    print("  " + "=" * 40)
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)




