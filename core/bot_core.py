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
from io import BytesIO
from typing import Optional, Callable

from DrissionPage import ChromiumPage

# ─────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────

COOKIES_FILE = "zhipin_cookies"
CHATS_LOG_FILE = "chats_log.json"

USER_AGENTS = [
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
SELECTOR_START_CHAT = ".btn.btn-startchat"
SELECTOR_INPUT_AREA = ".input-area"
SELECTOR_SEND_BTN = ".send-message"
SELECTOR_CLOSE = ".icon-close"
SELECTOR_IMG_UPLOAD = ".toolbar-btn-content.icon.btn-sendimg.tooltip.tooltip-top"
SELECTOR_BOSS_ACTIVE = ".boss-active-time"
SELECTOR_SCALE = ".icon-scale"
SELECTOR_REC_JOB_LIST = ".rec-job-list"
SELECTOR_JOB_NAME = ".job-name"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds

# 操作频率限制
MAX_APPLIES_PER_HOUR = 30
MAX_APPLIES_PER_DAY = 100

# ─────────────────────────────────────────────
# 重试装饰器
# ─────────────────────────────────────────────


def retry(max_attempts: int = MAX_RETRIES, base_delay: float = RETRY_BASE_DELAY):
    """重试装饰器：捕获 Exception，指数退避重试，日志记录重试次数。"""
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
                        delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                        self._log("WARN", f"  {func.__name__} 第 {attempt}/{max_attempts} 次失败: {e}，{delay:.1f}s 后重试")
                        time.sleep(delay)
                    else:
                        self._log("ERROR", f"  {func.__name__} 重试 {max_attempts} 次均失败: {e}")
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator

# ─────────────────────────────────────────────
# BotCore
# ─────────────────────────────────────────────


class BotCore:
    def __init__(
        self,
        config: dict,
        log_callback: Callable[[str], None],
        screenshot_callback: Optional[Callable[[bytes], None]] = None,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.config = config
        self.log_cb = log_callback
        self.screenshot_cb = screenshot_callback
        self.progress_cb = progress_callback
        self.running = False
        self.dp: Optional[ChromiumPage] = None
        self._login_event = threading.Event()
        self._screenshot_thread: Optional[threading.Thread] = None
        self._stop_screenshot = threading.Event()
        self._is_logged_in = False
        self.city_code: Optional[str] = None
        self.jobs: list[dict] = []
        self._sent_jobs: set[str] = set()

    # ── helpers ──

    def _log(self, level: str, msg: str) -> None:
        self.log_cb(f"[{level}] {msg}")

    @staticmethod
    def _random_delay(min_s: float, max_s: float) -> None:
        """随机延时 + 额外高斯 jitter 以防特征检测。"""
        base = random.uniform(min_s, max_s)
        jitter = random.gauss(0, base * 0.15)  # ±15% 高斯抖动
        total = max(0.5, base + jitter)
        time.sleep(total)

    @staticmethod
    def _random_ua() -> str:
        return random.choice(USER_AGENTS)

    # ── 去重管理 ──

    def _load_sent_jobs(self) -> set[str]:
        """加载历史已投递 job URL 集合。"""
        if os.path.exists(CHATS_LOG_FILE):
            try:
                with open(CHATS_LOG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return set(data)
            except (json.JSONDecodeError, OSError):
                pass
        return set()

    def _save_sent_jobs(self) -> None:
        with open(CHATS_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(self._sent_jobs), f, ensure_ascii=False, indent=2)

    # ── Cookie 管理 ──

    def _load_cookies(self) -> bool:
        """加载已保存 Cookie 并注入浏览器，成功返回 True。"""
        if not os.path.exists(COOKIES_FILE):
            return False
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            if not cookies:
                return False
            self.dp.set.cookies(cookies)
            self._log("INFO", f"已加载 {len(cookies)} 条 Cookie")
            return True
        except (json.JSONDecodeError, OSError) as e:
            self._log("WARN", f"Cookie 加载失败: {e}")
            return False

    def _save_cookies(self) -> None:
        try:
            with open(COOKIES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.dp.cookies(), f, ensure_ascii=False, indent=2)
            self._log("INFO", "Cookie 已保存")
        except OSError as e:
            self._log("WARN", f"Cookie 保存失败: {e}")

    def _clear_cookies(self) -> None:
        """清除 Cookie 文件（用于登录失效时）。"""
        if os.path.exists(COOKIES_FILE):
            os.remove(COOKIES_FILE)
            self._log("INFO", "Cookie 已清除")

    # ── 频率限制 ──

    def _check_rate_limit(self) -> bool:
        """检查是否超过频率限制。True = 可以继续。"""
        today_applies = sum(1 for url in self._sent_jobs if url)
        if today_applies >= MAX_APPLIES_PER_DAY:
            self._log("WARN", f"已达每日投递上限 {MAX_APPLIES_PER_DAY}，停止投递")
            return False
        return True

    # ── 公开 API ──

    def _report_progress(self, total: int, applied: int, skipped: int) -> None:
        """将投递进度传回 UI。"""
        if self.progress_cb:
            self.progress_cb({
                "total": total,
                "applied": applied,
                "skipped": skipped,
                "remaining": max(0, total - applied - skipped),
            })

    def start(self) -> None:
        self.running = True
        self._sent_jobs = self._load_sent_jobs()
        self._log("INFO", f"已加载 {len(self._sent_jobs)} 条历史投递记录")

        try:
            self.dp = ChromiumPage()
            # 设置 User-Agent
            self.dp.set.user_agent(self._random_ua())

            self._step_login()
            if not self.running or not self._is_logged_in:
                return
            self._step_fetch_cities()
            if not self.running:
                return
            self._step_search_jobs()
            if not self.running:
                return
            self._start_screenshot_loop()
            self._step_browse_jobs()
            self._log("SUCCESS", "全部完成！")
        except Exception as e:
            self._log("ERROR", f"异常终止: {e}")
        finally:
            self.running = False
            self._stop_screenshot.set()
            if self._screenshot_thread and self._screenshot_thread.is_alive():
                self._screenshot_thread.join(timeout=5)
            if self.dp:
                try:
                    self.dp.quit()
                except Exception:
                    pass

    def stop(self) -> None:
        self.running = False
        self._login_event.set()
        self._stop_screenshot.set()

    def confirm_login(self) -> None:
        """UI 回调：用户确认已登录。"""
        self._login_event.set()

    def check_login_status(self) -> bool:
        """检查当前是否已登录。"""
        if not self.dp:
            return False
        try:
            self.dp.get("https://www.zhipin.com")
            self._random_delay(2, 5)
            # 尝试多个选择器检测登录状态以增加鲁棒性
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

    # ── 截图循环 ──

    def _start_screenshot_loop(self) -> None:
        def _loop():
            while not self._stop_screenshot.is_set() and self.running and self.dp:
                try:
                    tab = self.dp.latest_tab
                    screenshot_data = tab.get_screenshot(raw=True)
                    if screenshot_data and self.screenshot_cb:
                        self.screenshot_cb(screenshot_data)
                except Exception:
                    pass
                self._stop_screenshot.wait(timeout=3)
        self._screenshot_thread = threading.Thread(target=_loop, daemon=True)
        self._screenshot_thread.start()

    # ── 步骤：登录 ──

    def _step_login(self) -> None:
        self._log("INFO", "正在打开 Boss 直聘首页...")
        self.dp.get("https://www.zhipin.com")
        self._random_delay(2, 3)

        # 先尝试加载 Cookie 恢复会话
        if self._load_cookies():
            self.dp.refresh()
            self._random_delay(3, 4)
            if self.check_login_status():
                self._log("INFO", "Cookie 登录成功")
                return
            else:
                self._log("WARN", "Cookie 已失效，需要重新登录")
                self._clear_cookies()

        nav_ele = self.dp.ele(SELECTOR_NAV, timeout=5)
        if nav_ele:
            un_text = nav_ele.text
            if "登录/注册" not in un_text:
                self._log("INFO", "检测到已登录状态，跳过登录步骤")
                self._is_logged_in = True
                self._save_cookies()
                return

        self._log("WARN", "需要登录！请在浏览器中手动登录后，点击「确认已登录」按钮")
        self.dp.get("https://www.zhipin.com/web/user/?ka=header-login")

        self._login_event.clear()
        logged_in = self._login_event.wait(timeout=300)

        if not self.running:
            self._log("INFO", "用户取消登录")
            return

        if not logged_in:
            self._log("WARN", "登录等待超时（5分钟），请检查后重试")
            return

        self._save_cookies()
        self._is_logged_in = True
        self._log("INFO", "登录状态已保存")

    # ── 步骤：获取城市 ──

    @retry(max_attempts=2, base_delay=2.0)
    def _step_fetch_cities(self) -> None:
        self._log("INFO", "刷新页面获取城市数据...")
        city_dict = {}

        # 关键：必须先在 refresh 前开始监听，否则 data/city.json 的请求已发出，
        # listen.steps() 将永远等不到匹配的包而卡死
        self.dp.listen.start("data/city.json")
        self.dp.refresh()
        self._random_delay(2, 3)

        # 用 wait() 代替 steps() — 支持超时，防止无限阻塞
        packet = self.dp.listen.wait(timeout=15)
        if packet is None:
            self._log("WARN", "获取城市数据超时，尝试备用方案...")
            # 备用：从页面 DOM 中提取热门城市列表
            city_eles = self.dp.eles(".city-list .city-item", timeout=5)
            if city_eles:
                for ele in city_eles:
                    name = ele.text.strip()
                    code = ele.attr("data-code")
                    if name and code:
                        city_dict[name] = code
                self._log("INFO", f"从 DOM 提取了 {len(city_dict)} 个城市")
            else:
                # 降级方案：直接尝试硬编码的热门城市 code
                self._log("INFO", "降级方案：使用内置热门城市列表")
                city_dict = {
                    "北京": "101010100",
                    "上海": "101020100",
                    "广州": "101280101",
                    "深圳": "101280601",
                    "杭州": "101210101",
                    "成都": "101270101",
                    "武汉": "101200101",
                    "南京": "101190101",
                    "西安": "101110101",
                    "苏州": "101190401",
                }
        else:
            res = packet.response.body
            city_list = res.get("zpData", {}).get("hotCityList", [])
            for city in city_list:
                city_dict[city["name"]] = city["code"]
        self.dp.listen.stop()

        self._log("INFO", f"已获取 {len(city_dict)} 个城市数据")

        target_city = self.config["city"]
        if target_city not in city_dict:
            self._log("ERROR", f"城市 '{target_city}' 不在热门城市中，可选: {list(city_dict.keys())[:10]}...")
            raise ValueError(f"未知城市: {target_city}")

        self.city_code = city_dict[target_city]
        self._log("INFO", f"目标城市: {target_city} (code={self.city_code})")

    # ── 步骤：搜索岗位 ──

    def _step_search_jobs(self) -> None:
        query = self.config.get("job_query", "")
        scroll_pages = self.config.get("scroll_pages", 5)

        if not query:
            self._log("ERROR", "岗位关键词为空")
            self.jobs = []
            return

        url = (
            f"https://www.zhipin.com/web/geek/jobs?"
            f"query={query}&city={self.city_code}&industry=&position="
        )
        self._log("INFO", f"搜索岗位: {query}")
        self.dp.get(url)
        self._random_delay(2, 3)

        self._log("INFO", f"滚动页面 {scroll_pages} 次加载更多职位...")
        for i in range(scroll_pages):
            if not self.running:
                return
            try:
                self.dp.scroll.to_bottom()
                # 每次滚动的延时逐渐增大，模拟人类浏览行为
                scroll_delay = random.uniform(2.0, 3.5) + i * random.uniform(0.2, 0.5)
                self._random_delay(scroll_delay, scroll_delay + 1.5)
            except Exception:
                self._log("WARN", "页面刷新，等待加载后重试...")
                self._random_delay(3, 5)
                self.dp.scroll.to_bottom()
                self._random_delay(1.5, 3)

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
                parts = job_str.split("\n")
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
                    "query": query,
                })
        else:
            for u in full_job_urls:
                processed_jobs.append({
                    "job_name": "", "salary": "", "url": u, "query": query
                })

        self._log("INFO", f"解析出 {len(processed_jobs)} 条完整岗位信息")
        self.jobs = processed_jobs

    # ── 步骤：遍历投递 ──

    def _step_browse_jobs(self) -> None:
        images = self.config.get("image_files", [])
        valid_images = [img for img in images if os.path.isfile(img)]
        if valid_images != images:
            missing = [i for i in images if not os.path.isfile(i)]
            self._log("WARN", f"以下图片不存在: {missing}")

        min_interval = self.config.get("message_interval_min", 3)
        max_interval = self.config.get("message_interval_max", 8)

        total = len(self.jobs)
        applied_count = 0
        skipped_count = 0

        # 发送初始进度
        self._report_progress(total, 0, 0)

        for idx, job in enumerate(self.jobs, 1):
            if not self.running:
                self._log("INFO", "用户停止，中断投递")
                break

            if not self._check_rate_limit():
                break

            url = job["url"]
            if not url:
                self._log("WARN", f"第 {idx}/{total}: 无链接，跳过")
                skipped_count += 1
                continue

            # 去重检查（基于 URL）
            if url in self._sent_jobs:
                self._log("INFO", f"  → 已投递过，跳过: {job.get('job_name', '')}")
                skipped_count += 1
                continue

            job_name = job.get("job_name", "未知岗位")
            salary = job.get("salary", "")
            self._log("INFO", f"[{idx}/{total}] 正在投递: {job_name} {salary}")

            # 带重试的投递
            success = self._apply_single_job(
                url, job_name, min_interval, max_interval, valid_images
            )

            if success:
                applied_count += 1
                self._sent_jobs.add(url)
                self._save_sent_jobs()
                self._report_progress(total, applied_count, skipped_count)
            else:
                skipped_count += 1
                self._report_progress(total, applied_count, skipped_count)

        self._log("SUCCESS", f"投递完成: 成功 {applied_count}，跳过/失败 {skipped_count}，总计 {total}")

    # ── 单岗位投递 ──

    @retry(max_attempts=MAX_RETRIES, base_delay=RETRY_BASE_DELAY)
    def _apply_single_job(
        self,
        url: str,
        job_name: str,
        min_interval: int,
        max_interval: int,
        valid_images: list[str],
    ) -> bool:
        """投递单个岗位，成功返回 True。"""
        self.dp.get(url)
        self._random_delay(2, 3)

        # 检查是否之前沟通过（页面级别）
        btn = self.dp.ele(SELECTOR_START_CHAT, timeout=3)
        if btn and "继续沟通" in btn.text:
            self._log("INFO", "  → 之前已沟通过，跳过")
            return False

        # 提取活跃度/规模信息
        try:
            boss_time = self.dp.ele(SELECTOR_BOSS_ACTIVE, timeout=3).text
            scale = self.dp.ele(SELECTOR_SCALE, timeout=3).text
            self._log("INFO", f"  活跃度: {boss_time}, 规模: {scale}")
        except Exception:
            pass

        greeting = self.config.get("greeting_message", "")

        # 点击沟通按钮
        chat_btn = self.dp.ele(SELECTOR_START_CHAT, timeout=3)
        if not chat_btn:
            self._log("WARN", "  → 未找到沟通按钮")
            return False
        chat_btn.click()
        self._random_delay(1, 2)

        # 输入打招呼语
        input_area = self.dp.ele(SELECTOR_INPUT_AREA, timeout=3)
        if not input_area:
            self._log("WARN", "  → 未找到输入框")
            return False
        input_area.input(greeting)

        # 发送消息
        send_btn = self.dp.ele(SELECTOR_SEND_BTN, timeout=3)
        if not send_btn:
            self._log("WARN", "  → 未找到发送按钮")
            return False
        send_btn.click()
        self._log("SUCCESS", "  → 消息发送成功")

        # 上传图片
        if valid_images:
            self._upload_images(valid_images)

        # 关闭弹窗
        try:
            close_btn = self.dp.ele(SELECTOR_CLOSE, timeout=3)
            if close_btn:
                close_btn.click()
                self._random_delay(0.5, 1)
        except Exception:
            pass

        # 随机间隔 + 额外抖动防特征检测
        base_delay = random.uniform(min_interval, max_interval)
        jitter = random.gauss(0, base_delay * 0.2)  # 高斯抖动 ±20%
        total_delay = max(1.5, base_delay + jitter)
        self._log("INFO", f"  → 等待 {total_delay:.1f} 秒后继续...")
        time.sleep(total_delay)

        return True

    def _upload_images(self, valid_images: list[str]) -> None:
        """上传图片附件。"""
        for img_path in valid_images:
            try:
                img_ele = self.dp.ele(SELECTOR_IMG_UPLOAD, timeout=3)
                if img_ele:
                    img_ele.click.to_upload(img_path)
                    self._log("INFO", f"  → 上传图片: {os.path.basename(img_path)}")
                else:
                    self._log("WARN", "  → 未找到图片上传按钮")
            except Exception as e:
                self._log("ERROR", f"  → 图片上传失败: {e}")
