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

# ─────────────────────────────────────────────
# 路径常量
# ─────────────────────────────────────────────

COOKIES_FILE = "zhipin_cookies"
CHATS_LOG_FILE = "chats_log.json"

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

        # 从配置读取参数
        self._load_config_params()

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
        self._retry_max = retry_cfg.get("max_attempts", 3)
        self._retry_base_delay = retry_cfg.get("base_delay", 2.0)
        self._retry_backoff = retry_cfg.get("backoff_factor", 2.0)

        self._min_interval = self.config.get("message_interval_min", 3)
        self._max_interval = self.config.get("message_interval_max", 8)
        self._scroll_pages = self.config.get("scroll_pages", 5)
        self._city = self.config.get("city", "上海")
        self._query = self.config.get("query", "")
        self._greeting_message = self.config.get("greeting_message", "")
        self._image_files = self.config.get("image_files", [])
        self._cookie_file = self.config.get("cookie_file", "zhipin_cookies.json")

    # ── 日志 / 进度 ──

    def _log(self, level: str, msg: str):
        if self.log_cb:
            self.log_cb(f"[{level}] {msg}")

    def _report_progress(self):
        if self.progress_cb:
            self.progress_cb({
                "total": self.total_jobs,
                "applied": self.applied_count,
                "skipped": self.skipped_count,
            })

    # ── 启动 / 停止 ──

    def run(self):
        """Alias for start() 向后兼容。"""
        self.start()

    def start(self):
        self.running = True
        try:
            self._run()
        except Exception as e:
            self._log("ERROR", f"Bot 异常退出: {e}")
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
            self.dp.get("https://www.zhipin.com")
            self._random_delay(2, 5)
            for selector in (SELECTOR_NAV, ".header-login-btn"):
                nav_ele = self.dp.ele(selector, timeout=3)
                if nav_ele:
                    text = nav_ele.text
                    if "登录/注册" not in text:
                        self._is_logged_in = True
                        return True
            return False
        except Exception:
            return False

    # ── 核心运行流程 ──

    def _run(self):
        self._log("INFO", f"🔍 搜索: {self._city} · {self._query}")

        if not self._init_browser():
            return

        if not self._load_cookies() or not self._verify_login():
            self._log("WARN", "Cookie 无效或未登录，等待用户扫码登录...")
            self._log("INFO", "请在浏览器中手动登录，登录后点击「确认登录」按钮继续。")
            if not self._wait_for_login():
                self._log("ERROR", "登录超时，请稍后重试")
                return

        self._save_cookies()

        self._log("INFO", "正在获取岗位列表...")
        self._parse_job_list()

        self._step_browse_jobs()

        self._log("INFO", "✅ 任务完成！")

    def _init_browser(self) -> bool:
        try:
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
        """等待用户手动登录，返回是否登录成功。"""
        if not self._login_event.wait(timeout=self._login_wait_timeout):
            return False
        self._random_delay(2, 5)
        return self.check_login_status()

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
        city_code = self._get_city_id(city) if city else ""
        base = "https://www.zhipin.com/web/geek/job"
        params = []
        if query:
            params.append(f"query={query}")
        if city_code:
            params.append(f"city={city_code}")
        if params:
            return base + "?" + "&".join(params)
        return base

    def _parse_job_list(self):
        self._log("INFO", "正在解析岗位列表...")
        self.dp.get(self._build_search_url(self._query, self._city))
        self._random_delay(3, 6)

        for _ in range(self._scroll_pages):
            if not self.running:
                break
            self.dp.scroll.down(600)
            self._random_delay(1, 3)

        job_url_elements = self.dp.eles(SELECTOR_JOB_NAME)
        full_job_urls = []
        for elem in job_url_elements:
            href = elem.attr("href")
            if href:
                full_job_urls.append(href)

        self._log("INFO", f"共找到 {len(full_job_urls)} 个岗位")

        processed_jobs = []
        rec_list_ele = self.dp.ele(SELECTOR_REC_JOB_LIST, timeout=3)
        if rec_list_ele:
            job_name_list = rec_list_ele.texts()
            for idx, job_str in enumerate(job_name_list):
                parts = job_str.split("\\n")
                if len(parts) < 4:
                    continue
                first_part = parts[0]
                salary_start = len(first_part)
                for marker in ["K", "元/月", "元/天", "薪"]:
                    pos = first_part.find(marker)
                    if pos != -1 and pos < salary_start:
                        salary_start = pos

                job_name = first_part[:salary_start].strip()
                salary = first_part[salary_start:].strip() if salary_start < len(first_part) else ""

                processed_jobs.append({
                    "job_name": job_name,
                    "salary": salary,
                    "experience": parts[1],
                    "education": parts[2],
                    "company_location": parts[3],
                    "url": full_job_urls[idx] if idx < len(full_job_urls) else "",
                    "query": self._query,
                })
        else:
            for u in full_job_urls:
                processed_jobs.append({
                    "job_name": "", "salary": "", "url": u, "query": self._query
                })

        self._log("INFO", f"解析出 {len(processed_jobs)} 条完整岗位信息")
        self.jobs = processed_jobs

    def _get_city_id(self, city_name: str) -> str:
        try:
            self.dp.get("https://www.zhipin.com/web/geek/job")
            self._random_delay(1, 2)
            scale_ele = self.dp.ele(SELECTOR_SCALE, timeout=15)
            if scale_ele:
                scale_ele.click()
                self._random_delay(1, 2)
            city_hot_eles = self.dp.eles(".city-list-hot .city-item")
            for ele in city_hot_eles:
                if city_name in ele.text:
                    city_code = ele.attr("data-code")
                    if city_code:
                        return city_code
            city_all_eles = self.dp.eles(".city-list-all .city-item")
            for ele in city_all_eles:
                if city_name in ele.text:
                    city_code = ele.attr("data-code")
                    if city_code:
                        return city_code
            return ""
        except Exception:
            return ""

    # ── 步骤：遍历投递 ──

    def _step_browse_jobs(self):
        valid_images = [img for img in self._image_files if os.path.isfile(img)]
        if valid_images != self._image_files:
            missing = [i for i in self._image_files if not os.path.isfile(i)]
            self._log("WARN", f"以下图片不存在: {missing}")

        self.total_jobs = len(self.jobs)
        self._report_progress()

        for idx, job in enumerate(self.jobs):
            if not self.running:
                break

            if self._rate_limit_enabled:
                if self.applied_count >= self._max_per_hour:
                    self._log("WARN", f"已达到每小时上限 {self._max_per_hour}，暂停 1 小时")
                    if not self._wait_or_stop(3600):
                        break

            self._log("INFO", f"处理 [{idx+1}/{self.total_jobs}] {job.get('job_name', '未知岗位')}")
            self._random_delay(self._min_interval, self._max_interval)

            if self._is_already_chatted(job):
                self._log("INFO", f"⏭️ 已沟通过: {job.get('job_name', '')}")
                self.skipped_count += 1
                self._report_progress()
                self._save_chat_log(job, skipped=True)
                continue

            success = self._apply_job(job)

            if success:
                self.applied_count += 1
                self._save_chat_log(job, skipped=False)
                self._log("SUCCESS", f"✅ 已投递: {job.get('job_name', '')}")
            else:
                self.skipped_count += 1
                self._log("WARN", f"⏭️ 跳过: {job.get('job_name', '')}")
            self._report_progress()

    @retry(max_attempts=3, base_delay=2.0, backoff_factor=2.0)
    def _apply_job(self, job: dict) -> bool:
        if not self.running:
            return False

        url = job.get("url", "")
        if not url:
            return False

        try:
            self.dp.get(url)
            self._random_delay(2, 5)

            # 点击「立即沟通」或「继续沟通」
            chat_btn = None
            for text in (SELECTOR_START_CHAT_TEXT, SELECTOR_START_CHAT_CONTINUE):
                try:
                    chat_btn = self.dp.ele(f"tag:button@@text():{text}", timeout=3)
                    if chat_btn:
                        break
                except Exception:
                    continue

            if not chat_btn:
                self._log("WARN", "未找到沟通按钮，可能已下架或已沟通")
                return False

            chat_btn.click()
            self._random_delay(2, 4)

            # 找到输入框并发送消息
            msg_input = self.dp.ele(SELECTOR_INPUT_AREA, timeout=5)
            if not msg_input:
                self._log("WARN", "未找到消息输入框")
                return False

            greeting = self._greeting_message or "您好，希望能获得面试机会。"
            msg_input.clear()
            self._random_delay(0.5, 1.5)
            msg_input.input(greeting)
            self._random_delay(1, 2)

            # 如果有图片，上传
            valid_images = [img for img in self._image_files if os.path.isfile(img)]
            for img_path in valid_images:
                try:
                    upload_btn = self.dp.ele("tag:input@@type=file", timeout=3)
                    if upload_btn:
                        upload_btn.input(img_path)
                        self._random_delay(1, 2)
                except Exception:
                    pass

            # 发送
            send_btn = self.dp.ele(SELECTOR_SEND_BTN, timeout=3)
            if send_btn:
                send_btn.click()
                self._random_delay(1, 2)
            else:
                self.dp.run_js("document.querySelector('.send-message')?.click()")
                self._random_delay(1, 2)

            self._mark_chatted(job)
            return True

        except Exception as e:
            self._log("WARN", f"发送消息异常: {e}")
            return False

    # ── 辅助方法 ──

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
        try:
            import shutil as _shutil
            import json as _json
            src = self._cookie_file
            dst = COOKIES_FILE + ".json"
            if src != dst and os.path.exists(src):
                _shutil.copy2(src, dst)
            if os.path.exists(dst):
                with open(dst, "r", encoding="utf-8") as f:
                    cookies = _json.load(f)
                self.dp.set.cookies(cookies)
                self._log("INFO", f"已加载 Cookie: {dst}")
                return True
            return False
        except Exception:
            return False

    def _save_cookies(self):
        try:
            import json as _json
            dst = COOKIES_FILE + ".json"
            cookies = self.dp.cookies()
            with open(dst, "w", encoding="utf-8") as f:
                _json.dump(cookies, f, ensure_ascii=False, indent=2)
            self._log("INFO", f"已保存 Cookie: {dst}")
        except Exception as e:
            self._log("WARN", f"Cookie 保存失败: {e}")

    def _clear_cookies(self):
        if self._clear_cookies_on_failure:
            try:
                dst = COOKIES_FILE + ".json"
                if os.path.exists(dst):
                    os.remove(dst)
                self._log("INFO", "已清除失效 Cookie")
            except Exception:
                pass

    # ── 去重管理 ──

    def _chatted_db_path(self) -> str:
        return "chatted_jobs.json"

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

    def _save_chat_log(self, job: dict, skipped: bool = False):
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
            })
            with open(CHATS_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(logs[-500:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass
