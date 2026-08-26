"""
Boss直聘自动投递核心逻辑

职责：
- 浏览器自动化（登录、搜索、投递）
- 反爬策略（随机间隔、User-Agent）
- 去重管理（持久化已投递记录）
- 重试与容错
"""
import json
import os
import random
import time
import threading
from functools import wraps
from typing import Optional, Callable

from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage.errors import PageDisconnectedError

# ─────────────────────────────────────────────
# 路径常量
# ─────────────────────────────────────────────
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_APP_DIR, "data")
COOKIES_FILE = "zhipin_cookies"
CHATS_LOG_FILE = os.path.join(DATA_DIR, "chats_log.json")

# ─────────────────────────────────────────────
# 文件日志
# ─────────────────────────────────────────────
import logging
LOG_FILE = os.path.join(DATA_DIR, "bot.log")
os.makedirs(DATA_DIR, exist_ok=True)
_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
_file_logger = logging.getLogger("bot_file")
_file_logger.setLevel(logging.INFO)
_file_logger.addHandler(_file_handler)
_file_logger.propagate = False

# 默认 User-Agent 列表
FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# CSS 选择器常量
SELECTOR_NAV = ".user-nav"
SELECTOR_START_CHAT_TEXT = "立即沟通"
SELECTOR_START_CHAT_CONTINUE = "继续沟通"
SELECTOR_INPUT_AREA = ".input-area"
SELECTOR_SEND_BTN = ".send-message"
SELECTOR_CLOSE = ".icon-close"
SELECTOR_BOSS_ACTIVE = ".boss-active-time"
SELECTOR_SCALE = ".icon-scale"
SELECTOR_REC_JOB_LIST = ".rec-job-list"
SELECTOR_JOB_NAME = ".job-name"

# 默认打招呼语模板（当任务和岗位都未设置时使用）
DEFAULT_GREETING = "您好，我是双一流的本科，应聘数据分析岗位。在校系统学习数据分析相关知识，掌握Excel、基础SQL与数据整理技能，具备数据思维。做事严谨细心，学习能力强，愿意踏实积累。十分认可贵公司，希望能获得面试机会。"

# 热门城市编码映射（Boss直聘使用）
CITY_CODES = {
    "北京": "101010100", "上海": "101020100", "广州": "101280100",
    "深圳": "101280600", "杭州": "101210100", "成都": "101270100",
    "南京": "101190100", "武汉": "101200100", "西安": "101110100",
    "重庆": "101040100", "长沙": "101250100", "苏州": "101190400",
    "天津": "101030100", "郑州": "101180100", "东莞": "101281600",
    "青岛": "101120200", "沈阳": "101070100", "宁波": "101210400",
    "昆明": "101290100", "大连": "101070200", "厦门": "101230200",
    "合肥": "101220100", "佛山": "101280300", "福州": "101230100",
    "哈尔滨": "101050100", "济南": "101120100", "温州": "101210700",
    "长春": "101060100", "石家庄": "101090100", "常州": "101191100",
    "泉州": "101230500", "南宁": "101300100", "贵阳": "101260100",
    "南昌": "101240100", "太原": "101100100", "烟台": "101120500",
    "嘉兴": "101210300", "南通": "101190500", "金华": "101210900",
    "珠海": "101280700", "惠州": "101280300", "徐州": "101190800",
    "海口": "101310100", "乌鲁木齐": "101130100", "绍兴": "101210500",
    "中山": "101281700", "台州": "101210600", "兰州": "101160100",
}

# ─────────────────────────────────────────────
# 重试装饰器
# ─────────────────────────────────────────────

def retry(max_attempts: int = 3, base_delay: float = 2.0, backoff_factor: float = 2.0):
    """重试装饰器：捕获 Exception，指数退避重试。"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt < max_attempts:
                        delay = base_delay * (backoff_factor ** (attempt - 1)) + random.uniform(0, 1)
                        self._log("WARN", f"重试 {attempt}/{max_attempts}: {e}，等待 {delay:.1f}s")
                        time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# BotCore
# ─────────────────────────────────────────────

class BotCore:
    """Boss直聘自动投递机器人核心类。"""

    def __init__(
        self,
        config: dict,
        log_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
    ):
        self.config = config
        self.log_cb = log_callback
        self.progress_cb = progress_callback

        # 运行状态
        self.running = False
        self._is_logged_in = False
        self._login_event = threading.Event()

        # 统计
        self.applied_count = 0
        self.skipped_count = 0
        self.total_jobs = 0

        # 浏览器实例
        self.dp: Optional[ChromiumPage] = None

        # 城市字典（从API捕获）
        self._city_dict = {}

        # 当前任务参数
        self._query = ""
        self._city = "上海"
        self._scroll_pages = 5
        self._greeting_message = ""
        self._image_files = []
        self._min_interval = 3
        self._max_interval = 8
        self._cookie_file = "zhipin_cookies.json"
        self._login_required_cb = None

        # 岗位列表
        self.jobs = []

        # 岗位级别自定义打招呼语 {job_url: greeting_text}
        self._custom_greetings = {}

        # 投递队列锁（防止并发操作浏览器）
        self._apply_lock = threading.Lock()

        # 从配置读取参数
        self._load_config_params()
        self._load_city_dict()
        self._tasks = [self.config]

    def _load_config_params(self):
        """从 config 读取所有可调参数。"""
        browser_cfg = self.config.get("browser", {})
        self._headless = browser_cfg.get("headless", False)
        self._viewport_width = browser_cfg.get("viewport_width", 1280)
        self._viewport_height = browser_cfg.get("viewport_height", 800)
        self._page_load_timeout = browser_cfg.get("page_load_timeout", 30)
        self._custom_user_agent = browser_cfg.get("custom_user_agent", "")
        self._proxy = browser_cfg.get("proxy", "")

        login_cfg = self.config.get("login", {})
        self._login_wait_timeout = login_cfg.get("wait_timeout", 300)
        self._clear_cookies_on_failure = login_cfg.get("clear_cookies_on_failure", True)

        rl_cfg = self.config.get("rate_limit", {})
        self._rate_limit_enabled = rl_cfg.get("enabled", True)
        self._max_per_hour = rl_cfg.get("max_per_hour", 30)
        self._max_per_day = rl_cfg.get("max_per_day", 100)

        retry_cfg = self.config.get("retry", {})
        self._retry_max_attempts = retry_cfg.get("max_attempts", 3)
        self._retry_base_delay = retry_cfg.get("base_delay", 2.0)
        self._retry_backoff_factor = retry_cfg.get("backoff_factor", 2.0)

        ai_cfg = self.config.get("ai", {})
        self._ai_enabled = ai_cfg.get("enabled", False)
        self._ai_api_key = ai_cfg.get("api_key", "")
        self._ai_api_base = ai_cfg.get("api_base", "https://apihub.agnes-ai.com/v1")
        self._ai_model = ai_cfg.get("model", "agnes-2.5-flash")
        self._ai_threshold = ai_cfg.get("match_threshold", 70)
        self._ai_cfg = ai_cfg
        self._resume_cfg = self.config.get("resume", {})
        self._ai_analyzer = None

        # 从 config 中读取 _login_required_callback（由 BotRunner 传入）
        self._login_required_cb = self.config.get("_login_required_callback", None)

        self._query = self.config.get("query", "")
        self._city = self.config.get("city", "上海")
        self._scroll_pages = self.config.get("scroll_pages", 5)
        self._greeting_message = self.config.get("greeting_message", "")
        self._image_files = self.config.get("image_files", [])
        self._min_interval = self.config.get("message_interval_min", 3)
        self._max_interval = self.config.get("message_interval_max", 8)
        self._cookie_file = self.config.get("cookie_file", "zhipin_cookies.json")

    def _log(self, level: str, msg: str):
        """统一日志输出。"""
        if self.log_cb:
            self.log_cb(f"[{level}] {msg}")
        # 同时写入文件日志
        try:
            _file_logger.info(f"[{self.account_name}] [{level}] {msg}")
        except Exception:
            pass

    def _report_progress(self):
        if self.progress_cb:
            self.progress_cb({
                "applied": self.applied_count,
                "skipped": self.skipped_count,
                "total": self.total_jobs,
            })

    def set_custom_greetings(self, custom_greetings: dict):
        """设置岗位级别自定义打招呼语。
        Args:
            custom_greetings: {job_url: greeting_text} 字典
        """
        self._custom_greetings = custom_greetings or {}
        self._log("INFO", f"已设置 {len(self._custom_greetings)} 个岗位的自定义打招呼语")

    def get_job_list(self, task_idx=0):
        """获取指定任务的岗位列表（预览用，不投递）。
        Returns:
            list: 岗位列表，每个岗位包含 job_name, url, company_location 等字段
        """
        if not self._init_browser():
            return []
        if not self._check_and_handle_login():
            return []
        task = self._tasks[task_idx] if task_idx < len(self._tasks) else self._tasks[0]
        self._query = task.get("query", "")
        self._city = task.get("city", "上海")
        self._scroll_pages = task.get("scroll_pages", 5)
        self._cookie_file = task.get("cookie_file", "zhipin_cookies.json")
        self._log("INFO", f"🔍 预览搜索: {self._city} · {self._query}")
        self.running = True  # _parse_job_list 需要 running=True
        self._parse_job_list()
        return list(self.jobs)

    # ── 兼容旧接口 ──

    def run(self):
        """Alias for start() 向后兼容。"""
        self.start()

    def start(self, tasks=None):
        """启动机器人。
        Args:
            tasks: 可选，多任务列表。如果为 None，使用默认配置中的单个任务。
        """
        self.running = True
        try:
            self._run(tasks)
        except Exception as e:
            self._log("ERROR", f"Bot 异常退出: {e}")
            import traceback
            self._log("ERROR", traceback.format_exc())
        finally:
            self.running = False
            if self.dp:
                try:
                    self.dp.quit()
                except Exception:
                    pass

    def stop(self):
        self.running = False

    def confirm_login(self) -> None:
        self._login_event.set()

    def check_login_status(self) -> bool:
        if not self.dp:
            return False
        try:
            # 先检查当前页面，避免导航到新页面改变上下文
            for selector in (SELECTOR_NAV, ".header-login-btn", ".user-nav"):
                nav_ele = self.dp.ele(selector, timeout=3)
                if nav_ele:
                    text = nav_ele.text
                    if "登录/注册" not in text and text.strip():
                        self._is_logged_in = True
                        return True
            # 尝试检查 URL 是否包含登录页路径
            try:
                current_url = self.dp.url
                if current_url and "passport" not in current_url and "login" not in current_url:
                    # 当前页面不是登录页，但没找到导航元素，可能是页面还在加载
                    return True
            except Exception:
                pass
            # 如果当前页面没有找到导航元素，再导航到首页检查
            self.dp.get("https://www.zhipin.com")
            self._random_delay(2, 5)
            for selector in (SELECTOR_NAV, ".header-login-btn", ".user-nav"):
                nav_ele = self.dp.ele(selector, timeout=3)
                if nav_ele:
                    text = nav_ele.text
                    if "登录/注册" not in text and text.strip():
                        self._is_logged_in = True
                        return True
            return False
        except Exception:
            return False

    def _run(self, tasks=None):
        """运行任务。如果传入 tasks ，则为多任务模式（共用浏览器）。"""
        if tasks is not None:
            self._tasks = tasks

        if not self._init_browser():
            return

        if not self._check_and_handle_login():
            return

        for task_idx, task in enumerate(self._tasks):
            if not self.running:
                break

            self._log("INFO", f"━━━ 任务 [{task_idx+1}/{len(self._tasks)}] {task.get('query', '')} @ {task.get('city', '')} ━━━")

            self._query = task.get("query", "")
            self._city = task.get("city", "上海")
            self._scroll_pages = task.get("scroll_pages", 5)
            self._greeting_message = task.get("greeting_message", "")
            self._image_files = task.get("image_files", [])
            self._min_interval = task.get("message_interval_min", 3)
            self._max_interval = task.get("message_interval_max", 8)
            self._cookie_file = task.get("cookie_file", "zhipin_cookies.json")
            # Issue 6 fix: 从 task 中读取 _login_required_callback
            self._login_required_cb = task.get("_login_required_callback", self._login_required_cb)

            # AI 配置随任务刷新
            task_ai = task.get("ai", {}) or {}
            self._ai_enabled = task_ai.get("enabled", self._ai_enabled)
            self._ai_api_key = task_ai.get("api_key", self._ai_api_key)
            self._ai_api_base = task_ai.get("api_base", self._ai_api_base)
            self._ai_model = task_ai.get("model", self._ai_model)
            self._ai_threshold = task_ai.get("match_threshold", self._ai_threshold)
            self._resume_cfg = task.get("resume", self._resume_cfg) or {}
            self._ai_analyzer = None

            self._log("INFO", f"🔍 搜索: {self._city} · {self._query}")

            self._log("INFO", "正在获取岗位列表...")
            self._parse_job_list()

            if self.jobs:
                self._step_browse_jobs()
            else:
                self._log("WARN", "没有找到岗位，跳过此任务")

        self._log("INFO", "✅ 任务完成！")

    def _check_and_handle_login(self) -> bool:
        """检查登录状态，参考 mian.py 流程。"""
        orig_cwd = os.getcwd()
        try:
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
            if os.path.exists(data_dir):
                os.chdir(data_dir)

            self.dp.get("https://www.zhipin.com")
            self._random_delay(2, 3)

            nav_ele = self.dp.ele(SELECTOR_NAV, timeout=5)
            if nav_ele:
                nav_text = nav_ele.text
                if "登录/注册" in nav_text:
                    self._log("WARN", "需要登录")
                    if self._load_cookies():
                        self.dp.get("https://www.zhipin.com")
                        self._random_delay(2, 3)
                        nav_ele2 = self.dp.ele(SELECTOR_NAV, timeout=3)
                        if nav_ele2 and "登录/注册" not in nav_ele2.text:
                            self._is_logged_in = True
                            self._log("INFO", "Cookie 有效，已登录")
                            self._save_cookies()
                        else:
                            self._clear_cookies()
                            self.dp.get("https://www.zhipin.com/web/user/?ka=header-login")
                            self._random_delay(1, 2)
                            if self._login_required_cb:
                                self._login_required_cb()
                            self._log("INFO", "请手动登录，登录后点击「确认登录」")
                            if not self._wait_for_login():
                                self._log("ERROR", "登录超时")
                                return False
                            self._save_cookies()
                            self._log("SUCCESS", "登录成功")
                    else:
                        self.dp.get("https://www.zhipin.com/web/user/?ka=header-login")
                        self._random_delay(1, 2)
                        if self._login_required_cb:
                            self._login_required_cb()
                        self._log("INFO", "请手动登录，登录后点击「确认登录」")
                        if not self._wait_for_login():
                            self._log("ERROR", "登录超时")
                            return False
                        self._save_cookies()
                        self._log("SUCCESS", "登录成功")
                else:
                    self._is_logged_in = True
                    self._log("INFO", "已登录状态")
            else:
                self._log("WARN", "需要登录")
                self.dp.get("https://www.zhipin.com/web/user/?ka=header-login")
                self._random_delay(1, 2)
                if self._login_required_cb:
                    self._login_required_cb()
                self._log("INFO", "请手动登录，登录后点击「确认登录」")
                if not self._wait_for_login():
                    self._log("ERROR", "登录超时")
                    return False
                self._save_cookies()
                self._log("SUCCESS", "登录成功")

            self._log("INFO", "正在获取城市数据...")
            self._capture_city_data()
            return True
        except Exception as e:
            self._log("ERROR", "登录检查异常: " + str(e))
            import traceback
            self._log("ERROR", traceback.format_exc())
            return False
        finally:
            os.chdir(orig_cwd)

    def _capture_city_data(self):
        """捕获城市数据（参考 mian.py：监听 city.json 数据包）。"""
        try:
            self.dp.listen.start("data/city.json")
            self.dp.refresh()
            self._random_delay(2, 4)
            for packet in self.dp.listen.steps(timeout=10):
                res = packet.response.body
                if isinstance(res, dict) and "zpData" in res:
                    city_list = res["zpData"].get("hotCityList", [])
                    for city in city_list:
                        if isinstance(city, dict):
                            name = city.get("name", "")
                            code = city.get("code", "")
                            self._city_dict[name] = code
                            self._log("INFO", f"城市: {name} -> {code}")
                    if self._city_dict:
                        self._log("SUCCESS", f"已获取 {len(self._city_dict)} 个城市数据")
                        self._save_city_dict()
                    break
        except Exception as e:
            self._log("WARN", f"城市数据捕获异常: {e}")

    def _save_city_dict(self):
        """保存城市数据到文件，供前端下拉列表使用。"""
        try:
            import json
            city_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "city_dict.json")
            with open(city_file, "w", encoding="utf-8") as f:
                json.dump(self._city_dict, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_city_dict(self):
        """从文件加载之前捕获的城市数据。"""
        try:
            import json
            city_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "city_dict.json")
            if os.path.exists(city_file):
                with open(city_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._city_dict.update(data)
                        self._log("INFO", f"已加载 {len(self._city_dict)} 个城市数据(文件)")
        except Exception:
            pass


    def _check_login_expired(self) -> bool:
        """验证登录状态，检查当前页面是否被重定向到登录页。"""
        try:
            current_url = self.dp.url
            # 检查 URL 是否包含登录相关的路径
            is_suspicious = "passport" in current_url or "login" in current_url or not current_url
            if is_suspicious:
                self._log("WARN", "检测到登录过期，需要重新登录")
                self.dp.get("https://www.zhipin.com/web/user/?ka=header-login")
                self._random_delay(1, 2)
                if self._login_required_cb:
                    self._login_required_cb()
                self._log("INFO", "已打开登录页面，请在浏览器中完成登录")
                # 给用户一些时间登录，不阻塞等待
                self._log("INFO", "等待登录确认...")
                if not self._wait_for_login():
                    self._log("ERROR", "登录超时")
                    return False
                self._save_cookies()
                self._log("SUCCESS", "登录成功")
            return True
        except Exception as e:
            self._log("WARN", "登录检查异常: " + str(e))
            import traceback
            self._log("WARN", traceback.format_exc())
            return False

    def _init_browser(self) -> bool:
        """初始化浏览器。如果已经初始化则复用。"""
        try:
            if self.dp is not None:
                return True  # 复用已有浏览器
            co = ChromiumOptions()
            co.set_argument("--no-sandbox")
            co.set_argument("--disable-gpu")
            if self._headless:
                co.set_argument("--headless=new")
            if self._custom_user_agent:
                co.set_user_agent(self._custom_user_agent)
            else:
                co.set_user_agent(random.choice(FALLBACK_USER_AGENTS))
            if self._proxy:
                co.set_proxy(self._proxy)
            co.set_timeouts(base=self._page_load_timeout)
            self.dp = ChromiumPage(co)
            self._log("INFO", "浏览器已启动")
            return True
        except Exception as e:
            self._log("ERROR", f"浏览器启动失败: {e}")
            return False

    def _wait_for_login(self) -> bool:
        """等待用户手动登录。"""
        if not self._login_event.wait(timeout=self._login_wait_timeout):
            return False
        self._random_delay(2, 5)
        return self.check_login_status()

    def _is_login_page(self) -> bool:
        """检查当前页面是否是登录页。"""
        try:
            current_url = self.dp.url
            return "passport" in current_url or "login" in current_url
        except Exception:
            return False

    def _verify_login(self) -> bool:
        try:
            self.dp.get("https://www.zhipin.com/web/geek/job")
            self._random_delay(2, 4)
            for selector in (SELECTOR_NAV, ".header-login-btn"):
                nav_ele = self.dp.ele(selector, timeout=3)
                if nav_ele:
                    text = nav_ele.text
                    if "登录/注册" not in text and "我的" in text:
                        self._is_logged_in = True
                        return True
            return False
        except Exception:
            return False

    def _build_search_url(self, query: str, city: str) -> str:
        """构建搜索 URL（参考 mian.py 格式）。"""
        city_code = self._get_city_id(city) if city else ""
        self._log("INFO", f"城市: {city}, 编码: {city_code}")
        if city_code:
            return f"https://www.zhipin.com/web/geek/jobs?query={query}&city={city_code}&industry=&position="
        else:
            return f"https://www.zhipin.com/web/geek/jobs?query={query}&industry=&position="

    def _parse_job_list(self):
        """解析岗位列表（参考 mian.py 流程）。"""
        self._log("INFO", "正在解析岗位列表...")

        search_url = self._build_search_url(self._query, self._city)
        self._log("INFO", f"访问搜索页面: {search_url}")
        self.dp.get(search_url)
        self._random_delay(3, 6)

        self._log("INFO", f"开始滚动 {self._scroll_pages} 次...")
        for i in range(self._scroll_pages):
            if not self.running:
                break
            try:
                self.dp.scroll.to_bottom()
                self._random_delay(1, 3)
                self._log("INFO", f"已滚动 {i+1}/{self._scroll_pages} 次")
            except Exception:
                self._log("WARN", "页面被刷新，等待页面加载完成后重试...")
                self._random_delay(2, 4)
                try:
                    self.dp.scroll.to_bottom()
                    self._random_delay(1, 3)
                except Exception:
                    pass

        job_url_elements = self.dp.eles(SELECTOR_JOB_NAME)
        full_job_urls = []
        for elem in job_url_elements:
            href = elem.attr("href")
            if href:
                if href.startswith("/"):
                    href = "https://www.zhipin.com" + href
                full_job_urls.append(href)

        self._log("INFO", f"共找到 {len(full_job_urls)} 个岗位链接")

        processed_jobs = []
        rec_list_ele = self.dp.ele(SELECTOR_REC_JOB_LIST, timeout=3)
        if rec_list_ele:
            job_name_list = rec_list_ele.texts()
            self._log("INFO", f"从 rec-job-list 解析出 {len(job_name_list)} 条文本")
            for idx, job_str in enumerate(job_name_list):
                parts = job_str.split("\n")
                if len(parts) < 4:
                    continue
                first_part = parts[0]
                salary_start = len(first_part)
                for marker in ["K", "元/月", "元/天", "薪"]:
                    m_idx = first_part.find(marker)
                    if m_idx != -1 and m_idx < salary_start:
                        salary_start = m_idx
                job_name = first_part[:salary_start].strip() if salary_start < len(first_part) else first_part
                salary = first_part[salary_start:].strip() if salary_start < len(first_part) else ""
                processed_jobs.append({
                    "job_name": job_name,
                    "salary": salary,
                    "experience": parts[1] if len(parts) > 1 else "",
                    "education": parts[2] if len(parts) > 2 else "",
                    "company_location": parts[3] if len(parts) > 3 else "",
                    "url": full_job_urls[idx] if idx < len(full_job_urls) else "",
                    "query": self._query,
                })
        else:
            self._log("INFO", "未找到 rec-job-list，直接使用链接")
            for u in full_job_urls:
                processed_jobs.append({
                    "job_name": "", "salary": "", "url": u, "query": self._query
                })

        self._log("INFO", f"解析出 {len(processed_jobs)} 条岗位信息")
        self.jobs = processed_jobs

        # 为每个岗位附加已保存的自定义打招呼语（用于预览回显）
        for job in self.jobs:
            url = job.get("url", "")
            if url and url in getattr(self, "_custom_greetings", {}):
                job["custom_greeting"] = self._custom_greetings[url]

    def _get_city_id(self, city_name: str) -> str:
        """获取城市编码。优先使用 API 捕获数据，再使用硬编码映射。"""
        if self._city_dict and city_name in self._city_dict:
            code = self._city_dict[city_name]
            self._log("INFO", f"城市 {city_name} 编码 (API): {code}")
            return str(code)
        if city_name in CITY_CODES:
            self._log("INFO", f"城市 {city_name} 编码 (硬编码): {CITY_CODES[city_name]}")
            return CITY_CODES[city_name]
        self._log("WARN", f"未找到城市 {city_name} 的编码")
        return ""


    def _resolve_images(self) -> list:
        """解析作品图片路径。只使用配置的 image_files，不自动扫描 dashboard 目录。"""
        import glob
        # app/static/dashboard 是作品图目录
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
        dashboard_dir = os.path.join(static_dir, "dashboard")
        os.makedirs(dashboard_dir, exist_ok=True)

        resolved = []

        # 只使用配置的 image_files
        if self._image_files:
            for img in self._image_files:
                if isinstance(img, str):
                    if img.startswith("dashboard/") or img.startswith("dashboard\\"):
                        full_path = os.path.join(static_dir, img.replace("\\", "/"))
                    elif os.path.isabs(img):
                        full_path = img
                    else:
                        full_path = os.path.join(dashboard_dir, img)
                    if os.path.isfile(full_path):
                        resolved.append(full_path)
                    else:
                        self._log("WARN", f"配置图片不存在: {full_path}")

        # 兜底：扫描 dashboard 目录
        if not resolved:
            for ext in ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp"]:
                for f in glob.glob(os.path.join(dashboard_dir, ext)):
                    resolved.append(f)

        final_resolved = list(dict.fromkeys(resolved))
        if final_resolved:
            self._log("INFO", f"共准备 {len(final_resolved)} 张作品图片")
        else:
            self._log("WARN", "没有作品图片")
        return final_resolved
        return final_resolved



    def _init_ai(self):
        """初始化 AI 分析器（懒加载）。支持多 AI 容灾链。"""
        if self._ai_analyzer is not None:
            return self._ai_analyzer
        if not self._ai_enabled:
            return None
        try:
            # 优先使用多 AI 容灾链
            providers = self._ai_cfg.get("providers", [])
            if providers:
                from ai_analyzer_chain import AIAnalyzerChain
                self._ai_analyzer = AIAnalyzerChain(
                    providers=providers,
                    match_threshold=self._ai_threshold,
                    log_callback=lambda msg: self._log("INFO", msg),
                )
            else:
                # 单 AI 模式（向后兼容）
                from ai_analyzer import AIAnalyzer
                self._ai_analyzer = AIAnalyzer(
                    api_key=self._ai_api_key,
                    api_base=self._ai_api_base,
                    model=self._ai_model,
                    match_threshold=self._ai_threshold,
                    log_callback=lambda msg: self._log("INFO", msg),
                )
            self._ai_analyzer.set_resume(self._resume_cfg)
            self._log("INFO", f"🤖 AI 智能解析已启用（模型: {self._ai_model}，阈值: {self._ai_threshold}）")
            return self._ai_analyzer
        except Exception as e:
            self._log("WARN", f"AI 分析器初始化失败（降级为普通投递）: {e}")
            return None

    def _analyze_job_with_ai(self, job: dict):
        """用 AI 分析岗位匹配度。返回匹配结果 dict，未启用时返回 None。"""
        analyzer = self._init_ai()
        if not analyzer:
            return None
        ai_job = {
            "job_name": job.get("job_name", ""),
            "salary": job.get("salary", ""),
            "description": job.get("description", job.get("job_desc", "")),
            "requirements": job.get("requirements", ""),
            "company": job.get("company", ""),
            "url": job.get("url", ""),
        }
        try:
            result = analyzer.analyze_job(ai_job)
            score = result.get("score", 50)
            is_match = result.get("is_match", True)
            self._log("INFO", f"🤖 AI 匹配度: {score}/100 —— {result.get('reason', '')[:80]}")
            return result if (is_match and score >= self._ai_threshold) else None
        except Exception as e:
            self._log("WARN", f"AI 分析异常，按通过处理: {e}")
            return None

    def _step_browse_jobs(self):
        """遍历岗位列表并投递。"""
        # 先解析图片
        resolved_images = self._resolve_images()
        self._image_files = resolved_images
        self._log("INFO", f"最终准备发送 {len(self._image_files)} 张作品图片")

        self.total_jobs = len(self.jobs)
        self._report_progress()

        for idx, job in enumerate(self.jobs):
            if not self.running:
                break
            if self._rate_limit_enabled and self.applied_count >= self._max_per_hour:
                self._log("WARN", f"已达到每小时上限 {self._max_per_hour}，暂停 1 小时")
                if not self._wait_or_stop(3600):
                    break
            self._log("INFO", f"处理 [{idx+1}/{self.total_jobs}] {job.get('job_name', '未知岗位')}")
            self._random_delay(self._min_interval, self._max_interval)
            # AI 智能匹配：不达标的岗位直接跳过
            has_ai = self._ai_enabled and (self._ai_api_key or self._ai_cfg.get("providers", []))
            if has_ai:
                ai_result = self._analyze_job_with_ai(job)
                if ai_result is None and self._init_ai() is not None:
                    self._log("WARN", f"🤖 AI 判定不匹配，跳过: {job.get('job_name', '')}")
                    self.skipped_count += 1
                    self._save_chat_log(job, skipped=True)
                    self._report_progress()
                    continue
                if ai_result and ai_result.get("suggested_greeting"):
                    self._greeting_message = ai_result["suggested_greeting"]
            else:
                ai_result = None
            if self._is_already_chatted(job):
                self._log("INFO", f"⏭️ 已沟通过: {job.get('job_name', '')}")
                self.skipped_count += 1
                self._report_progress()
                self._save_chat_log(job, skipped=True)
                continue
            if not self._check_login_expired():
                break
            try:
                success = self._apply_job(job)
                if success:
                    self.applied_count += 1
                    self._save_chat_log(job, skipped=False, ai_result=ai_result)
                    self._log("SUCCESS", f"✅ 已投递: {job.get('job_name', '')}")
                else:
                    self.skipped_count += 1
                    self._log("WARN", f"⏭️ 跳过: {job.get('job_name', '')}")
            except PageDisconnectedError:
                self._log("WARN", "页面连接断开，尝试恢复...")
                if self._handle_disconnect():
                    try:
                        success = self._apply_job(job)
                        if success:
                            self.applied_count += 1
                            self._save_chat_log(job, skipped=False)
                            self._log("SUCCESS", f"✅ 已投递: {job.get('job_name', '')}")
                        else:
                            self.skipped_count += 1
                    except Exception as e2:
                        self._log("WARN", f"重试投递异常: {e2}")
                        self.skipped_count += 1
                else:
                    self._log("ERROR", "无法恢复连接，终止任务")
                    break
            self._report_progress()


    def _handle_disconnect(self) -> bool:
        """处理页面断开连接，尝试恢复。"""
        try:
            self._log("WARN", "开始处理页面断开，尝试恢复浏览器...")
            # 1. 先尝试轻量级恢复：导航到 about:blank 重置页面连接
            if self.dp:
                try:
                    self.dp.get('about:blank')
                    self._random_delay(1, 2)
                    _ = self.dp.url
                    self._log("INFO", "轻量级恢复（about:blank）成功")
                    return True
                except Exception:
                    self._log("WARN", "轻量级恢复失败，尝试重初始化浏览器...")

            # 2. 安全释放旧的浏览器实例
            if self.dp:
                try:
                    self.dp.quit()
                except Exception as e:
                    self._log("WARN", f"退出旧浏览器时异常（可忽略）: {e}")
                finally:
                    self.dp = None
            # 3. 等待浏览器进程完全释放
            self._random_delay(3, 6)
            # 4. 重新初始化浏览器
            if not self._init_browser():
                self._log("ERROR", "重新初始化浏览器失败")
                return False
            self._log("INFO", "浏览器重新初始化成功")
            # 5. 重新加载 cookie 并检查登录
            self._load_cookies()
            self._random_delay(2, 4)
            # 导航到首页检查登录状态
            for _ in range(3):
                try:
                    self.dp.get("https://www.zhipin.com")
                    self._random_delay(2, 3)
                    _ = self.dp.url
                    break
                except Exception:
                    self._random_delay(2, 3)
            # 检查登录状态
            if self.check_login_status():
                self._log("INFO", "页面断开后重新登录成功")
                return True
            # 即使 check_login_status 返回 False，也尝试继续（可能是页面还没加载完）
            # 再导航到首页确认一次
            try:
                self.dp.get("https://www.zhipin.com")
                self._random_delay(2, 3)
                self._log("INFO", "页面断开后恢复成功，继续执行")
            except Exception as e:
                self._log("WARN", f"恢复后导航到首页失败: {e}")
            return True
        except Exception as e:
            self._log("ERROR", f"处理页面断开异常: {e}")
            import traceback
            self._log("ERROR", traceback.format_exc())
            return False
    def _apply_job(self, job: dict, _disconnect_retry: int = 0) -> bool:
        """
        投递一个岗位。
        严格参考源文件 mian.py 流程。
        """
        # 使用锁防止并发操作浏览器
        with self._apply_lock:
            return self._apply_job_inner(job, _disconnect_retry)

    def _apply_job_inner(self, job: dict, _disconnect_retry: int = 0) -> bool:
        """实际投递逻辑（内部方法）。"""
        if not self.running:
            return False
        url = job.get("url", "")
        if not url:
            return False

        # 如果页面已断开，先尝试恢复
        if _disconnect_retry == 0:
            try:
                _ = self.dp.url
            except PageDisconnectedError:
                self._log("WARN", "页面已断开，尝试恢复...")
                if self._handle_disconnect():
                    _disconnect_retry = 1
                else:
                    return False
            except Exception:
                pass

        try:
            # ── 1. 导航到岗位详情页（新开 tab） ──
            # 先检查页面是否连接，已断开则尝试恢复
            try:
                _ = self.dp.url
            except PageDisconnectedError:
                self._log("WARN", "导航前页面已断开，尝试恢复...")
                if not self._handle_disconnect():
                    return False
            except Exception:
                pass

            for _retry in range(3):
                try:
                    self._log("INFO", f"[v2] 导航到: {url}")
                    # 使用 JavaScript 在当前标签页导航（DrissionPage 4.x 的 get() 会打开新标签页）
                    self.dp.run_js(f"window.location.href = '{url}'")
                    self._random_delay(3, 6)
                    self._log("INFO", f"[v2] 导航后URL: {self.dp.url}")
                    break
                except PageDisconnectedError:
                    self._log("WARN", "页面连接断开，尝试恢复...")
                    if not self._handle_disconnect():
                        return False
                    continue
                except Exception as _e:
                    self._log("WARN", f"页面加载重试: {_e}")
                    self._random_delay(2, 4)
            else:
                self._log("WARN", "页面加载失败，跳过此岗位")
                return False

            # 检查是否被重定向到登录页
            try:
                current_url = self.dp.url
                if "passport" in current_url or "login" in current_url:
                    self._log("WARN", "访问岗位详情时被重定向到登录页")
                    if self._login_required_cb:
                        self._login_required_cb()
                    self._log("INFO", "请重新登录，登录后点击「确认登录」")
                    if not self._wait_for_login():
                        self._log("ERROR", "登录超时")
                        return False
                    self._save_cookies()
                    self._log("SUCCESS", "登录成功")
                    try:
                        self.dp.get(url)
                        self._random_delay(3, 6)
                    except PageDisconnectedError:
                        return False
            except PageDisconnectedError:
                self._log("WARN", "页面断开")
                return False

            # ── 2. 查找沟通按钮（严格参考源文件 .btn btn-startchat） ──
            # 先检查是否已沟通过（源文件：if dp.ele(".btn btn-startchat").text in "继续沟通"）
            chat_btn = self._find_chat_button(timeout=8)
            if chat_btn is None:
                self._log("WARN", "未找到沟通按钮")
                return False

            btn_text = chat_btn.text
            if "继续沟通" in btn_text:
                self._log("INFO", "之前已经沟通过，不需要再沟通")
                self._mark_chatted(job)
                return True

            # ── 3. 获取信息（参考源文件） ──
            try:
                boss_active = self.dp.ele(".boss-active-time", timeout=3).text
                self._log("INFO", "上线状态: " + boss_active[:50])
            except Exception:
                pass
            try:
                company_scale = self.dp.ele(".icon-scale", timeout=3).text
                self._log("INFO", "公司规模: " + company_scale[:50])
            except Exception:
                pass
            try:
                job_desc = self.dp.ele(".job-sec-text", timeout=3).text
                self._log("INFO", "岗位描述: " + job_desc[:100] + "...")
            except Exception:
                pass
            try:
                salary = self.dp.ele(".salary", timeout=3).text
                self._log("INFO", "薪资: " + salary[:50])
            except Exception:
                pass

            # ── 4. 点击立即沟通（严格参考源文件：dp.ele(".btn btn-startchat").click()） ──
            self._log("INFO", f"[v2] 开始点击沟通按钮... URL: {self.dp.url}")
            chat_btn = self.dp.ele(".btn btn-startchat", timeout=5)
            if not chat_btn:
                self._log("WARN", f"[v2] 未找到沟通按钮! URL: {self.dp.url}")
                # 检查页面上有没有其他按钮
                try:
                    all_btns = self.dp.eles("tag:button") + self.dp.eles(".btn")
                    self._log("INFO", f"[v2] 页面上的按钮数量: {len(all_btns)}")
                    for i, b in enumerate(all_btns[:10]):
                        btext = (b.text or "")[:30]
                        bclass = b.attr("class") or ""
                        self._log("INFO", f"  btn[{i}]: class={bclass} text={btext}")
                except Exception as dbg_e:
                    self._log("WARN", f"[v2] 获取按钮失败: {dbg_e}")
                return False
            self._log("INFO", f"[v2] 找到沟通按钮，文本: {chat_btn.text}")
            chat_btn.click()
            self._log("INFO", "[v2] 已点击沟通按钮，等待输入框...")

            # ── 5. 输入消息（严格参考源文件：dp.ele(".input-area").input(message)） ──
            # 优先级：岗位自定义打招呼语 > 任务级打招呼语 > 默认模板
            custom_greeting = self._custom_greetings.get(job.get("url"), "")
            greeting = custom_greeting or self._greeting_message or DEFAULT_GREETING
            self._log("INFO", f"[v2] 打招呼语来源: {'岗位自定义' if custom_greeting else ('任务级' if self._greeting_message else '默认模板')}")
            input_area = self.dp.ele(".input-area", timeout=10)
            if not input_area:
                self._log("WARN", f"[v2] 未找到输入框! 当前URL: {self.dp.url}")
                # 打印页面上所有input/textarea元素帮助调试
                try:
                    inputs = self.dp.eles("tag:input") + self.dp.eles("tag:textarea") + self.dp.eles("[contenteditable]")
                    self._log("INFO", f"[v2] 页面上的输入元素: {len(inputs)} 个")
                    for i, inp in enumerate(inputs[:5]):
                        self._log("INFO", f"  输入{i}: tag={inp.tag} class={inp.attr('class')} type={inp.attr('type')}")
                except Exception as dbg_e:
                    self._log("WARN", f"[v2] 获取输入元素失败: {dbg_e}")
                return False
            self._log("INFO", "[v2] 找到输入框，输入消息...")
            input_area.input(greeting)
            self._log("INFO", "[v2] 消息已输入")

            # ── 6. 点击发送（严格参考源文件：dp.ele(".send-message").click()） ──
            self.dp.ele(".send-message").click()
            self._random_delay(1, 2)

            # 发送后检测页面是否断开
            try:
                _ = self.dp.url
            except PageDisconnectedError:
                self._log("WARN", "发送消息后页面连接断开，但消息可能已发送成功")
                self._mark_chatted(job)
                return True

            # ── 7. 发送图片（在发送消息之后） ──
            self._send_images_after_message()

            # ── 清理状态 ──
            try:
                close_btn = self.dp.ele(".icon-close", timeout=2)
                if close_btn:
                    close_btn.click()
                    self._random_delay(1, 2)
            except Exception:
                pass

            # ── 关闭当前 tab，回到列表页 ──
            try:
                self.dp.close_current_tab()
                self._random_delay(1, 2)
            except Exception:
                pass

        except PageDisconnectedError:
            self._log("WARN", "投递过程中页面连接断开")
            if _disconnect_retry < 1 and self._handle_disconnect():
                self._log("INFO", "页面连接已恢复，重新投递")
                return self._apply_job(job, _disconnect_retry=_disconnect_retry + 1)
            else:
                self._mark_chatted(job)
                return True
        except Exception as e:
            self._log("WARN", "发送消息异常: " + str(e))
            import traceback
            self._log("WARN", traceback.format_exc())
            return False

    def _send_images_after_message(self):
        """
        在发送消息之后上传图片。
        先检查聊天窗口是否打开，然后使用 click.to_upload() 方式上传图片。
        参考源文件 mian.py 的上传流程。
        """
        if not self._image_files:
            return

        # 参考源文件流程：先关闭当前聊天窗口，再重新打开
        try:
            close_btn = self.dp.ele(".icon-close", timeout=2)
            if close_btn:
                close_btn.click()
                self._random_delay(1, 2)
        except Exception:
            pass

        # 检查聊天窗口是否打开，未打开则重新打开
        input_area = None
        try:
            input_area = self.dp.ele(".input-area", timeout=3)
        except Exception:
            pass

        if not input_area:
            self._log("INFO", "聊天窗口未打开，尝试重新打开...")
            chat_btn = self._find_chat_button(timeout=5)
            if chat_btn:
                try:
                    chat_btn.click()
                    self._random_delay(1, 2)
                except Exception as e:
                    self._log("WARN", f"重新打开聊天窗口失败: {e}")
                    return
            else:
                self._log("WARN", "未找到沟通按钮，无法上传图片")
                return

        # 上传图片 - 去重后依次上传，使用 click.to_upload() 方式
        seen = set()
        for img_path in self._image_files:
            if img_path in seen:
                continue
            seen.add(img_path)
            if os.path.isfile(img_path):
                abs_path = os.path.abspath(img_path)
                uploaded = self._upload_image(abs_path)
                if uploaded:
                    self._log("INFO", "已上传图片: " + os.path.basename(img_path))
                else:
                    self._log("WARN", "上传图片失败: " + os.path.basename(img_path))
                self._random_delay(1, 2)

    def _find_chat_button(self, timeout=5):
        """
        查找沟通按钮。
        严格参考源文件 mian.py：dp.ele(".btn btn-startchat")
        """
        import time as _time
        _time.sleep(1)

        # 严格参考源文件：.btn btn-startchat（DrissionPage AND 语法）
        try:
            btn = self.dp.ele(".btn btn-startchat", timeout=timeout)
            if btn:
                return btn
        except Exception:
            pass

        # 备选：文本匹配
        for chat_text in ("立即沟通", "继续沟通"):
            try:
                btn = self.dp.ele(f"text:{chat_text}", timeout=2)
                if btn:
                    return btn
            except Exception:
                pass

        return None

    def _upload_image(self, img_path):
        """
        上传单张图片。
        严格参考源文件 mian.py：
        dp.ele(".toolbar-btn-content icon btn-sendimg tooltip tooltip-top").click.to_upload(路径)
        """
        if not os.path.isfile(img_path):
            self._log("WARN", f"上传图片文件不存在: {img_path}")
            return False

        abs_path = os.path.abspath(img_path)

        # 严格参考源文件：.toolbar-btn-content icon btn-sendimg tooltip tooltip-top
        try:
            btn = self.dp.ele(".toolbar-btn-content icon btn-sendimg tooltip tooltip-top", timeout=5)
            if btn:
                btn.click.to_upload(abs_path)
                self._random_delay(2, 3)
                self._log("INFO", f"已上传图片: {os.path.basename(img_path)}")
                return True
        except Exception:
            pass

        # 备选：直接找 input[type=file]
        try:
            file_input = self.dp.ele("tag:input@@type=file", timeout=3)
            if file_input:
                file_input.input(abs_path)
                self._random_delay(1, 2)
                self._log("INFO", f"已上传图片(文件框): {os.path.basename(img_path)}")
                return True
        except Exception:
            pass

        self._log("WARN", f"上传图片失败: {os.path.basename(img_path)}")
        return False

    def _random_delay(self, min_sec: float, max_sec: float):
        if not self.running:
            return
        time.sleep(random.uniform(min_sec, max_sec))

    def _wait_or_stop(self, seconds: float) -> bool:
        interval = 5
        for _ in range(int(seconds / interval)):
            if not self.running:
                return False
            time.sleep(interval)
        return self.running

    # ── Cookie 管理 ──

    def _load_cookies(self) -> bool:
        """加载 Cookie，优先使用 app/data 目录下的文件。"""
        try:
            import json as _json
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
            cookie_name = self._cookie_file if self._cookie_file else "zhipin_cookies.json"
            paths_to_try = []
            if not os.path.isabs(cookie_name):
                paths_to_try.append(os.path.join(data_dir, cookie_name))
            else:
                paths_to_try.append(cookie_name)
            if cookie_name != "zhipin_cookies.json":
                paths_to_try.append(os.path.join(data_dir, "zhipin_cookies.json"))
            else:
                paths_to_try.append(os.path.join(data_dir, "zhipin_cookies.json"))
            loaded = False
            for p in paths_to_try:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        cookies = _json.load(f)
                    self.dp.set.cookies(cookies)
                    self._log("INFO", f"已加载 Cookie: {p}")
                    loaded = True
                    break
            if not loaded:
                self._log("WARN", "未找到 Cookie 文件")
            return loaded
        except Exception as e:
            self._log("WARN", f"Cookie 加载失败: {e}")
            return False

    def _save_cookies(self):
        """保存 Cookie 到 app/data 目录。"""
        try:
            import json as _json
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
            cookie_name = self._cookie_file if self._cookie_file else "zhipin_cookies.json"
            dst = os.path.join(data_dir, cookie_name)
            cookies = self.dp.cookies()
            with open(dst, "w", encoding="utf-8") as f:
                _json.dump(cookies, f, ensure_ascii=False, indent=2)
            self._log("INFO", f"已保存 Cookie: {dst}")
            fallback = os.path.join(data_dir, "zhipin_cookies.json")
            if dst != fallback:
                import shutil
                shutil.copy2(dst, fallback)
        except Exception as e:
            self._log("WARN", f"Cookie 保存失败: {e}")

    def _clear_cookies(self):
        if self._clear_cookies_on_failure:
            try:
                cookie_name = self._cookie_file if self._cookie_file else "zhipin_cookies.json"
                if not os.path.isabs(cookie_name):
                    dst = os.path.join(DATA_DIR, cookie_name)
                else:
                    dst = cookie_name
                if os.path.exists(dst):
                    os.remove(dst)
                self._log("INFO", f"已清除失效 Cookie: {dst}")
            except Exception:
                pass

    # ── 去重管理 ──

    def _chatted_db_path(self) -> str:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        return os.path.join(data_dir, "chatted_jobs.json")

    def _load_chatted(self) -> set:
        try:
            if os.path.exists(self._chatted_db_path()):
                with open(self._chatted_db_path(), "r") as f:
                    return set(json.load(f))
        except Exception:
            pass
        return set()

    def _save_chatted(self, urls: set):
        try:
            with open(self._chatted_db_path(), "w") as f:
                json.dump(list(urls), f)
        except Exception:
            pass

    def _is_already_chatted(self, job: dict) -> bool:
        url = job.get("url", "")
        return url in self._load_chatted()

    def _mark_chatted(self, job: dict):
        url = job.get("url", "")
        if url:
            chatted = self._load_chatted()
            chatted.add(url)
            self._save_chatted(chatted)

    # ── 聊天日志 ──

    def _save_chat_log(self, job: dict, skipped: bool = False, ai_result: dict = None):
        try:
            logs = []
            if os.path.exists(CHATS_LOG_FILE):
                with open(CHATS_LOG_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            logs.append({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "job_name": job.get("job_name", ""),
                "company": job.get("company_location", ""),
                "salary": job.get("salary", ""),
                "query": self._query,
                "city": self._city,
                "skipped": skipped,
                "ai_score": ai_result.get("score", "") if ai_result else "",
                "ai_reason": ai_result.get("reason", "") if ai_result else "",
            })
            with open(CHATS_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(logs[-500:], f, ensure_ascii=False, indent=2)
            # 同步保存到 Excel
            try:
                from excel_exporter import save_jd_analysis
                save_jd_analysis(job, ai_result, skipped, self._query, self._city)
            except Exception:
                pass
        except Exception:
            pass
