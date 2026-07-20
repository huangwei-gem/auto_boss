"""
自动投递核心 — 合并版 v2
=========================
- 严格对齐 mian_ref.py 完整投递逻辑
- 多账号多岗位遍历
- 远程 core/bot_core.py 的重试/UA/Cookie/频率限制/城市码容错
"""

import json
import os
import random
import threading
import time
import traceback
from functools import wraps
from typing import Callable, Optional

from DrissionPage import ChromiumPage

# ── 常量 ──────────────────────────────────────────
COOKIES_FILE = "zhipin_cookies"
CHATS_DIR = "chats_log"
MAX_APPLIES_PER_HOUR = 30
MAX_APPLIES_PER_DAY = 100
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0

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

# CSS 选择器（注意：多 class 用空格分隔 — DrissionPage 要求）
SELECTOR_NAV = ".user-nav"
SELECTOR_START_CHAT = ".btn btn-startchat"
SELECTOR_INPUT_AREA = ".input-area"
SELECTOR_SEND_BTN = ".send-message"
SELECTOR_CLOSE = ".icon-close"
SELECTOR_IMG_UPLOAD = ".toolbar-btn-content icon btn-sendimg tooltip tooltip-top"
SELECTOR_JOB_NAME = ".job-name"
SELECTOR_REC_JOB_LIST = ".rec-job-list"
SELECTOR_ACTIVE_TIME = ".boss-active-time"
SELECTOR_SCALE = ".icon-scale"
SELECTOR_JOB_SEC_TEXT = ".job-sec-text"
SELECTOR_SALARY = ".salary"

# ── 已沟通记录 ─────────────────────────────────────

def _ensure_chats_dir():
    if not os.path.exists(CHATS_DIR):
        os.makedirs(CHATS_DIR)


def _chats_file(account_id: str) -> str:
    return os.path.join(CHATS_DIR, f"chats_{account_id}.json")


def _load_chats(account_id: str) -> set:
    _ensure_chats_dir()
    fpath = _chats_file(account_id)
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def _save_chats(account_id: str, names: set):
    _ensure_chats_dir()
    with open(_chats_file(account_id), "w", encoding="utf-8") as f:
        json.dump(sorted(names), f, ensure_ascii=False, indent=2)


# ── 重试装饰器 ─────────────────────────────────────

def retry(max_attempts: int = MAX_RETRIES, base_delay: float = RETRY_BASE_DELAY):
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
                        self._log("WARN",
                            f"  {func.__name__} 第{attempt}/{max_attempts}次失败: {e}，{delay:.1f}s后重试")
                        time.sleep(delay)
                    else:
                        self._log("ERROR",
                            f"  {func.__name__} 重试{max_attempts}次均失败: {e}")
            raise last_exc
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════
#  BotCore
# ═══════════════════════════════════════════════════

class BotCore:
    """Boss 直聘自动投递核心 — 多账号多岗位 + mian_ref.py 逻辑对齐。"""

    def __init__(self, config: dict,
                 log_callback: Callable,
                 screenshot_callback: Optional[Callable] = None,
                 progress_callback: Optional[Callable] = None):
        self.config = config
        self.log_cb = log_callback
        self.screenshot_cb = screenshot_callback
        self.progress_cb = progress_callback

        self.dp: Optional[ChromiumPage] = None
        self.running = False
        self._lock = threading.Lock()
        self._stop_screenshot = threading.Event()
        self._screenshot_thread: Optional[threading.Thread] = None
        self._login_event = threading.Event()
        self._is_logged_in = False
        self.chatted_companies: set = set()

    # ── 日志 + 进度 ─────────────────────────────────

    def _log(self, level: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log_cb(f"[{level}] {ts} {msg}")

    def _update_progress(self, cur: int, total: int, text: str = ""):
        if self.progress_cb:
            self.progress_cb(cur, total, text)

    @staticmethod
    def _wait(sec: float):
        time.sleep(sec)

    @staticmethod
    def _random_delay(min_s: float, max_s: float):
        """随机延时 + 高斯抖动防特征检测。"""
        base = random.uniform(min_s, max_s)
        jitter = random.gauss(0, base * 0.15)
        time.sleep(max(0.5, base + jitter))

    @staticmethod
    def _random_ua() -> str:
        return random.choice(USER_AGENTS)

    # ── 浏览器启动 ─────────────────────────────────

    def _ensure_browser(self):
        if self.dp is None:
            self._log("INFO", "启动浏览器…")
            self.dp = ChromiumPage()
            self.dp.set.user_agent(self._random_ua())

    # ── Cookie 管理 ────────────────────────────────

    def _load_cookies(self) -> bool:
        if not os.path.exists(COOKIES_FILE):
            return False
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            if not cookies:
                return False
            self.dp.set.cookies(cookies)
            self._log("INFO", f"加载了 {len(cookies)} 条 Cookie")
            return True
        except Exception as e:
            self._log("WARN", f"Cookie 加载失败: {e}")
            return False

    def _save_cookies(self) -> None:
        try:
            with open(COOKIES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.dp.cookies(), f, ensure_ascii=False, indent=2)
            self._log("INFO", "Cookie 已保存")
        except Exception as e:
            self._log("WARN", f"Cookie 保存失败: {e}")

    def _clear_cookies(self) -> None:
        if os.path.exists(COOKIES_FILE):
            os.remove(COOKIES_FILE)
            self._log("INFO", "Cookie 已清除")

    # ── 截图循环 ─────────────────────────────────

    def _start_screenshot_loop(self):
        if self._screenshot_thread and self._screenshot_thread.is_alive():
            return
        self._stop_screenshot.clear()
        self._screenshot_thread = threading.Thread(target=self._screenshot_loop, daemon=True)
        self._screenshot_thread.start()

    def _screenshot_loop(self):
        while not self._stop_screenshot.is_set():
            try:
                if self.dp and self.dp.tabs:
                    for tab in self.dp.tabs:
                        try:
                            b64 = tab.run_js(
                                "document.body ? "
                                "'data:image/png;base64,' + arguments[0].toDataURL('image/png').split(',')[1]"
                                " : ''",
                                tab.run_js("document.querySelector('canvas')||document.createElement('canvas')")
                            )
                            if b64 and self.screenshot_cb:
                                self.screenshot_cb(b64)
                            break
                        except Exception:
                            continue
            except Exception:
                pass
            self._stop_screenshot.wait(1.5)

    def _stop_screenshot_loop(self):
        self._stop_screenshot.set()
        if self._screenshot_thread:
            self._screenshot_thread.join(timeout=3)

    # ═══════════════════════════════════════════════
    #  登录检测 — 对齐 mian_ref.py + Cookie 恢复
    # ═══════════════════════════════════════════════

    def ensure_login(self) -> bool:
        """mian_ref.py 流程 + Cookie 恢复。"""
        try:
            self._ensure_browser()
            self.dp.get("https://www.zhipin.com")
            self._random_delay(2, 3)

            # 先尝试 Cookie 恢复
            if self._load_cookies():
                self.dp.refresh()
                self._random_delay(2, 3)
                if self._check_logged_in():
                    self._log("OK", "Cookie 登录成功")
                    self._is_logged_in = True
                    return True
                else:
                    self._log("WARN", "Cookie 已失效，需要重新登录")
                    self._clear_cookies()

            un_text = self.dp.ele(SELECTOR_NAV, timeout=10).text
            self._log("INFO", f"登录检测: 「{un_text[:30]}…」")

            if "登录/注册" in un_text:
                self._log("WARN", "需要登录，跳转登录页…")
                self.dp.get("https://www.zhipin.com/web/user/?ka=header-login")
                self._log("WARN", "请在浏览器手动登录，后在 GUI 点击「确认已登录」")
                return False
            else:
                self._log("OK", "已登录")
                self._is_logged_in = True
                self._save_cookies()
                return True
        except Exception as e:
            self._log("ERROR", f"登录检测异常: {e}")
            return False

    def _check_logged_in(self) -> bool:
        """检查当前是否已登录。"""
        try:
            nav_ele = self.dp.ele(SELECTOR_NAV, timeout=5)
            if nav_ele and "登录/注册" not in nav_ele.text:
                return True
            return False
        except Exception:
            return False

    def confirm_login(self):
        """UI 回调：用户确认已手动登录。"""
        self._login_event.set()

    def check_login_status(self) -> bool:
        return self._check_logged_in()

    # ═══════════════════════════════════════════════
    #  获取城市码 — 对齐 mian_ref.py + 超时降级
    # ═══════════════════════════════════════════════

    @retry(max_attempts=2, base_delay=2.0)
    def fetch_city_code(self, city: str) -> Optional[str]:
        """mian_ref.py + timeout 保护 + DOM 降级 + 硬编码降级。"""
        try:
            self._ensure_browser()
            self._log("INFO", f"获取城市 [{city}] 编码…")

            city_dict = {}
            # 关键：先 listen 再 refresh
            self.dp.listen.start("data/city.json")
            self.dp.refresh()
            self._random_delay(2, 3)

            packet = self.dp.listen.wait(timeout=15)
            if packet is None:
                self._log("WARN", "城市数据请求超时，尝试 DOM 提取…")
                # 降级 1: DOM
                city_eles = self.dp.eles(".city-list .city-item", timeout=5)
                if city_eles:
                    for ele in city_eles:
                        name = ele.text.strip()
                        code = ele.attr("data-code")
                        if name and code:
                            city_dict[name] = code
                if not city_dict:
                    # 降级 2: 硬编码
                    self._log("INFO", "使用内置热门城市列表")
                    city_dict = {
                        "北京": "101010100", "上海": "101020100",
                        "广州": "101280101", "深圳": "101280601",
                        "杭州": "101210101", "成都": "101270101",
                        "武汉": "101200101", "南京": "101190101",
                        "西安": "101110101", "苏州": "101190401",
                    }
            else:
                res = packet.response.body
                city_list = res.get("zpData", {}).get("hotCityList", [])
                for c in city_list:
                    city_dict[c["name"]] = c["code"]

            self.dp.listen.stop()

            if city in city_dict:
                self._log("OK", f"城市 [{city}] 编码: {city_dict[city]}")
                return city_dict[city]
            else:
                self._log("ERROR", f"未找到 [{city}]，可用: {list(city_dict.keys())}")
                return None
        except Exception as e:
            self._log("ERROR", f"获取城市码异常: {e}")
            return None

    # ═══════════════════════════════════════════════
    #  搜索岗位 — 对齐 mian_ref.py
    # ═══════════════════════════════════════════════

    def search_jobs(self, city_code: str, query: str, scroll_pages: int = 5) -> list:
        """mian_ref.py 搜索 + 薪资分离。"""
        self._ensure_browser()
        url = f"https://www.zhipin.com/web/geek/jobs?query={query}&city={city_code}"
        self._log("INFO", f"搜索岗位: {url}")
        self.dp.get(url)
        self._random_delay(2, 3)

        for i in range(scroll_pages):
            try:
                self.dp.scroll.to_bottom()
                delay = random.uniform(2.0, 3.5) + i * random.uniform(0.2, 0.5)
                self._random_delay(delay, delay + 1.5)
                self._log("INFO", f"  滚动 #{i + 1}/{scroll_pages}")
            except Exception:
                self._log("WARN", "  页面刷新，等待后重试…")
                self._random_delay(3, 5)
                try:
                    self.dp.scroll.to_bottom()
                    self._random_delay(1.5, 3)
                except Exception:
                    pass

        url_eles = self.dp.eles(SELECTOR_JOB_NAME)
        full_urls = [e.attr("href") for e in url_eles if e.attr("href")]
        self._log("INFO", f"  提取到 {len(full_urls)} 个 URL")

        processed_jobs = []
        rec_eles = self.dp.ele(SELECTOR_REC_JOB_LIST, timeout=3)
        if rec_eles:
            texts = rec_eles.texts()
            for i, s in enumerate(texts):
                parts = s.split("\n")
                if len(parts) < 4:
                    continue
                first_part = parts[0]
                markers = ["K", "元/月", "元/天", "薪"]
                split_pos = len(first_part)
                for m in markers:
                    p = first_part.find(m)
                    if p != -1 and p < split_pos:
                        split_pos = p
                name = first_part[:split_pos].strip() if split_pos < len(first_part) else first_part
                salary = first_part[split_pos:].strip() if split_pos < len(first_part) else ""
                processed_jobs.append({
                    "job_name": name, "salary": salary,
                    "experience": parts[1], "education": parts[2],
                    "company_location": parts[3],
                    "url": full_urls[i] if i < len(full_urls) else "",
                })
        else:
            for u in full_urls:
                processed_jobs.append({"job_name": "", "salary": "", "url": u})

        self._log("OK", f"找到 {len(processed_jobs)} 个岗位")
        return processed_jobs

    # ═══════════════════════════════════════════════
    #  投递单岗位 — 严格对齐 mian_ref.py
    # ═══════════════════════════════════════════════

    @retry(max_attempts=MAX_RETRIES, base_delay=RETRY_BASE_DELAY)
    def deliver_single_job(self, job: dict, greeting: str,
                           image_paths: list, account_id: str) -> bool:
        """
        mian_ref.py 完整流程：
          1. dp.get(url) → 检查"继续沟通" → 提取信息
          2. dp.get(url) → 点击沟通 → 输入 → 发送
          3. .icon-close 关闭
          4. 再次点击 btn-startchat
          5. 上传图片 (click.to_upload)
        """
        url = job.get("url", "")
        if not url:
            return False
        job_name = job.get("job_name", "未知")
        self._log("INFO", f"  → 访问: {job_name}")

        # ── 各选择器都加大 timeout ──
        # 第 1 次访问：检查 & 提取
        self.dp.get(url)
        self._random_delay(3, 5)

        chat_btn = self.dp.ele(SELECTOR_START_CHAT, timeout=8)
        if chat_btn:
            btn_text = chat_btn.text
            self._log("INFO", f"    按钮: 「{btn_text[:15]}」")
            if "继续沟通" in btn_text:
                self._log("INFO", "    → 已沟通过，跳过")
                return False

        # 提取详情
        try:
            bt = self.dp.ele(SELECTOR_ACTIVE_TIME, timeout=3)
            self._log("INFO", f"    活跃度: {bt.text}")
        except Exception:
            pass
        try:
            sc = self.dp.ele(SELECTOR_SCALE, timeout=3)
            self._log("INFO", f"    公司规模: {sc.text}")
        except Exception:
            pass
        try:
            ds = self.dp.ele(SELECTOR_JOB_SEC_TEXT, timeout=3)
            self._log("INFO", f"    描述: {ds.text[:50]}…")
        except Exception:
            pass

        # 第 2 次访问：沟通
        self.dp.get(url)
        self._random_delay(2, 3)

        chat_btn = self.dp.ele(SELECTOR_START_CHAT, timeout=8)
        if not chat_btn:
            self._log("WARN", "    未找到沟通按钮")
            return False
        btn_text = chat_btn.text
        if "继续沟通" in btn_text:
            self._log("INFO", "    → 已沟通过（第2次检查），跳过")
            return False
        if "打招呼" not in btn_text and "沟通" not in btn_text:
            self._log("WARN", f"    按钮文本异常「{btn_text}」，跳过")
            return False

        chat_btn.click()
        self._random_delay(1, 2)

        input_area = self.dp.ele(SELECTOR_INPUT_AREA, timeout=5)
        if not input_area:
            self._log("WARN", "    未找到输入框")
            return False
        input_area.input(greeting)
        self._wait(0.5)

        send_btn = self.dp.ele(SELECTOR_SEND_BTN, timeout=3)
        if send_btn:
            send_btn.click()
            self._wait(1)
            self._log("OK", "    ✅ 消息已发送")
        else:
            self._log("WARN", "    未找到发送按钮，尝试 Enter")
            try:
                self.dp.run_js(
                    "document.querySelector('.input-area')"
                    "?.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter'}))"
                )
                self._wait(1)
            except Exception:
                pass

        # 关闭聊天窗
        try:
            close_btn = self.dp.ele(SELECTOR_CLOSE, timeout=3)
            if close_btn:
                close_btn.click()
                self._wait(1)
                self._log("INFO", "    → 已关闭聊天窗")
        except Exception:
            pass

        # 上传图片
        if image_paths:
            self._wait(1)
            try:
                cb2 = self.dp.ele(SELECTOR_START_CHAT, timeout=5)
                if cb2:
                    cb2.click()
                    self._random_delay(1, 2)
                    self._log("INFO", "    → 重新打开聊天，准备传图")
            except Exception:
                self._log("WARN", "    无法重新打开聊天")

            for img_path in image_paths:
                if not os.path.exists(img_path):
                    self._log("WARN", f"    图片不存在: {img_path}")
                    continue
                try:
                    self.dp.ele(SELECTOR_IMG_UPLOAD, timeout=3).click.to_upload(img_path)
                    self._wait(1.5)
                    self._log("OK", f"    ✅ 已上传: {os.path.basename(img_path)}")
                except Exception as e:
                    self._log("WARN", f"    上传失败 {os.path.basename(img_path)}: {e}")

        company = job.get("company_location", job_name)
        self.chatted_companies.add(company)
        self._log("OK", f"    ✅ 完成: {job_name}")
        return True

    # ═══════════════════════════════════════════════
    #  连通性测试
    # ═══════════════════════════════════════════════

    def test_connectivity(self, account_id: str) -> dict:
        result = {"success": False, "message": "", "cookies_valid": False}
        try:
            self._ensure_browser()
            self.dp.get("https://www.zhipin.com")
            self._random_delay(2, 3)

            acc = None
            for a in self.config.get("accounts", []):
                if a["id"] == account_id:
                    acc = a
                    break
            if acc and acc.get("cookies_file") and os.path.exists(acc["cookies_file"]):
                try:
                    with open(acc["cookies_file"], "r", encoding="utf-8") as f:
                        self.dp.set.cookies(json.load(f))
                    self.dp.get("https://www.zhipin.com")
                    self._random_delay(2, 3)
                except Exception as e:
                    result["message"] = f"Cookie 加载失败: {e}"
                    return result

            nav = self.dp.ele(SELECTOR_NAV, timeout=10)
            if nav and "登录/注册" in nav.text:
                result["message"] = "❌ Cookie 无效，需重新登录"
                result["cookies_valid"] = False
            else:
                result["message"] = "✅ Cookie 有效"
                result["cookies_valid"] = True
            result["success"] = True
            return result
        except Exception as e:
            result["message"] = f"测试异常: {e}"
            return result

    # ═══════════════════════════════════════════════
    #  主执行
    # ═══════════════════════════════════════════════

    def run(self):
        if self.running:
            self._log("WARN", "已在运行中")
            return
        self.running = True
        self._start_screenshot_loop()
        try:
            accounts = self.config.get("accounts", [])
            interval_min = self.config.get("message_interval_min", 3)
            interval_max = self.config.get("message_interval_max", 8)
            global_scroll = self.config.get("global_scroll_pages", 5)

            if not accounts:
                self._log("ERROR", "没有配置账号")
                return

            logged_in = self.ensure_login()
            if not logged_in:
                self.running = False
                self._stop_screenshot_loop()
                return

            self._run_all_accounts(accounts, interval_min, interval_max, global_scroll)

        except Exception as e:
            self._log("ERROR", f"异常: {e}\n{traceback.format_exc()}")
        finally:
            self.running = False
            self._update_progress(0, 0, "已停止")
            self._stop_screenshot_loop()

    def run_all(self, accounts: list, interval_min: int, interval_max: int, global_scroll: int):
        self.running = True
        self._start_screenshot_loop()
        try:
            self._run_all_accounts(accounts, interval_min, interval_max, global_scroll)
        except Exception as e:
            self._log("ERROR", f"异常: {e}\n{traceback.format_exc()}")
        finally:
            self.running = False
            self._update_progress(0, 0, "已停止")
            self._stop_screenshot_loop()

    def _run_all_accounts(self, accounts: list, interval_min: int, interval_max: int, global_scroll: int):
        completed = 0
        for acc in accounts:
            if not self.running:
                break
            acc_id = acc.get("id", "")
            acc_name = acc.get("name", acc_id)
            city = acc.get("city", "上海")
            jobs_list = acc.get("jobs", [{"query": "数据分析", "scroll_pages": 5}])
            greeting = acc.get("greeting_message", "您好，应聘该岗位。")
            images = acc.get("image_files", [])
            self.chatted_companies = _load_chats(acc_id)

            self._log("HEADER", f"═══ 账号: {acc_name} ═══")
            self._update_progress(0, 0, f"{acc_name} 准备…")

            code = self.fetch_city_code(city)
            if not code:
                continue

            for jd in jobs_list:
                if not self.running:
                    break
                q = jd.get("query", "")
                sc = jd.get("scroll_pages", global_scroll)
                if not q:
                    continue
                self._log("HEADER", f"  ─── 岗位: {q} ───")
                jobs = self.search_jobs(code, q, sc)
                if not jobs:
                    continue

                for i, job in enumerate(jobs):
                    if not self.running:
                        break
                    jn = job.get("job_name", "未知")
                    self._log("INFO", f"    [{i+1}/{len(jobs)}] {jn}")
                    self._update_progress(i + 1, len(jobs), f"{acc_name} › {q} › {i+1}/{len(jobs)}")

                    company = job.get("company_location", jn)
                    if company in self.chatted_companies:
                        self._log("INFO", "    → 已沟通，跳过")
                        completed += 1
                        continue

                    ok = self.deliver_single_job(job, greeting, images, acc_id)
                    if ok:
                        completed += 1
                        self.chatted_companies.add(company)
                        _save_chats(acc_id, self.chatted_companies)

                    if self.running:
                        delay = random.randint(interval_min, interval_max)
                        self._log("INFO", f"    → 等待 {delay}s…")
                        self._wait(delay)

        self._log("HEADER", f"═════ 完成! 共投递 {completed} 次 ═════")

    def stop(self):
        self.running = False
        self._login_event.set()
        self._stop_screenshot_loop()
        self._log("INFO", "已请求停止")

    def close(self):
        self.stop()
        if self.dp:
            try:
                self.dp.quit()
            except Exception:
                pass
