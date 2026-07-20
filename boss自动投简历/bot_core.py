"""
自动投递核心 — 严格遵循 mian_ref.py 逻辑 + 多账号多岗位 + 连通性测试。

mian_ref.py 原始流程（完整复现）：
  1. ChromiumPage() → 打开 zhipin.com → .user-nav 检测登录
  2. 需要登录则跳转登录页 → 手动登录 → 保存 cookies
  3. 刷新 → listen.start("data/city.json") → 提取 hotCityList → 城市 code 映射
  4. 按 city + job query 搜索 → scroll.to_bottom() × scroll_pages（带 try/except 容错）
  5. .job-name → attr("href") 提取岗位 URL
  6. .rec-job-list.texts() 获取岗位信息 → split("\\n") 解析 parts
  7. salary_markers 智能分离职位名和薪资（K / 元/月 / 元/天 / 薪）
  8. 逐个访问岗位详情页 → 提取 boss-active-time / icon-scale / job-sec-text / .salary
  9. 检测 .btn.btn-startchat
     - 文本含"继续沟通" → 跳过（已沟通过）
     - 文本含"打招呼" → 点击沟通
  10. 输入招呼语 → 点击发送 → .icon-close 关闭聊天窗
  11. 重新点击 btn-startchat → 上传图片（click.to_upload）
  12. 随机间隔 3-8 秒 → 下一个岗位
  13. 切换账号 → 继续
"""

import json
import os
import random
import time
import threading
import traceback

from DrissionPage import ChromiumPage

# ── 调用记录文件 ──────────────────────────────────
CHATS_DIR = "chats_log"


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


# ═══════════════════════════════════════════════════
#  BotCore
# ═══════════════════════════════════════════════════

class BotCore:
    """Boss 直聘自动投递核心。

    Config 格式（来自 config.py）:
      {
        "accounts": [
          {
            "id": "account_1",
            "name": "账号1",
            "city": "上海",
            "jobs": [{"query": "数据分析", "scroll_pages": 5}, ...],
            "greeting_message": "...",
            "image_files": ["path1.png", ...],
            "cookies_file": "",
          },
        ],
        "message_interval_min": 3,
        "message_interval_max": 8,
        "global_scroll_pages": 5,
      }
    """

    def __init__(self, config: dict, log_callback, screenshot_callback=None):
        self.config = config
        self.log_cb = log_callback
        self.screenshot_cb = screenshot_callback

        self.dp: ChromiumPage = None
        self.running = False
        self._lock = threading.Lock()
        self._progress = {"current": 0, "total": 0, "text": ""}
        self._stop_screenshot = threading.Event()
        self._screenshot_thread: threading.Thread = None

        # 按账号加载已沟通过的公司
        self.chatted_companies: set = set()

    # ── 日志代理 ─────────────────────────────────

    def _log(self, level: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        try:
            self.log_cb(f"[{level}] {ts} {msg}")
        except Exception:
            pass

    # ── 进度 ─────────────────────────────────────

    def get_progress(self) -> dict:
        with self._lock:
            return dict(self._progress)

    def _update_progress(self, cur: int, total: int, text: str = ""):
        with self._lock:
            self._progress = {"current": cur, "total": total, "text": text}

    # ── 截图循环 ─────────────────────────────────

    def _start_screenshot_loop(self) -> None:
        if self._screenshot_thread and self._screenshot_thread.is_alive():
            return
        self._stop_screenshot.clear()
        self._screenshot_thread = threading.Thread(
            target=self._screenshot_loop, daemon=True
        )
        self._screenshot_thread.start()

    def _screenshot_loop(self) -> None:
        while not self._stop_screenshot.is_set():
            try:
                if self.dp and hasattr(self.dp, 'tabs') and self.dp.tabs:
                    for tab in self.dp.tabs:
                        try:
                            b64 = tab.run_js(
                                "document.body ? "
                                "'data:image/png;base64,' + arguments[0].toDataURL('image/png').split(',')[1]"
                                " : ''",
                                tab.run_js(
                                    "document.querySelector('canvas')||document.createElement('canvas')")
                            )
                            if b64 and self.screenshot_cb:
                                self.screenshot_cb(b64)
                            break
                        except Exception:
                            continue
            except Exception:
                pass
            self._stop_screenshot.wait(1.5)

    def _stop_screenshot_loop(self) -> None:
        self._stop_screenshot.set()
        if self._screenshot_thread:
            self._screenshot_thread.join(timeout=3)

    # ── 等待辅助 ─────────────────────────────────

    @staticmethod
    def _wait(sec: float):
        time.sleep(sec)

    # ═══════════════════════════════════════════════
    #  登录检测（严格对齐 mian_ref.py）
    # ═══════════════════════════════════════════════

    def ensure_login(self, account: dict) -> bool:
        """
        mian_ref.py 登录逻辑完整复现：
          1. 访问 zhipin.com
          2. .user-nav 取文本
          3. 含"登录/注册" → 跳登录页 → 手动登录 → 保存 cookies
          4. 否则 → 已登录
        """
        try:
            if self.dp is None:
                self.dp = ChromiumPage()
            self.dp.get("https://www.zhipin.com")
            self._wait(2)

            nav_el = self.dp.ele(".user-nav", timeout=8)
            if nav_el is None:
                self._log("WARN", "未找到 .user-nav 元素")
                return False

            un_text = nav_el.text
            self._log("INFO", f"登录检测: .user-nav → {un_text[:30]}...")

            if "登录/注册" in un_text:
                self._log("WARN", "需要登录，跳转登录页...")
                self.dp.get("https://www.zhipin.com/web/user/?ka=header-login")
                # 触发手动登录（由 GUI 用户完成）
                self._log("WAIT", "请在浏览器中手动登录，然后在 GUI 中点击「确认已登录」")
                return False  # 返回 False 表示需要登录
            else:
                self._log("OK", "已登录状态")
                return True

        except Exception as e:
            self._log("ERROR", f"登录检测异常: {e}")
            return False

    def confirm_login(self) -> bool:
        """确认登录完成并保存 cookies。"""
        try:
            with open("zhipin_cookies", "w", encoding="utf-8") as f:
                json.dump(self.dp.cookies(), f)
            self._log("OK", "登录状态已保存 (zhipin_cookies)")
            return True
        except Exception as e:
            self._log("ERROR", f"保存 cookies 失败: {e}")
            return False

    # ═══════════════════════════════════════════════
    #  城市码获取（严格对齐 mian_ref.py）
    # ═══════════════════════════════════════════════

    def _fetch_city_code(self, city_name: str) -> str:
        """
        mian_ref.py 城市码获取：
          1. dp.refresh()
          2. listen.start("data/city.json")
          3. 获取数据包 → res["zpData"]["hotCityList"]
          4. 建立 name → code 映射
        """
        try:
            self.dp.refresh()
            self._wait(2)
            self.dp.listen.start("data/city.json")

            city_dict = {}
            for packet in self.dp.listen.steps():
                res = packet.response.body
                city_list = res.get("zpData", {}).get("hotCityList", [])
                for c in city_list:
                    city_dict[c["name"]] = c["code"]
                break  # 只取第一个数据包

            code = city_dict.get(city_name, "")
            if not code:
                self._log("WARN", f"城市 [{city_name}] 未在热门城市列表中找到")
                self._log("INFO", f"支持的热门城市: {list(city_dict.keys())[:10]}...")
            else:
                self._log("OK", f"城市 [{city_name}] → code={code}")
            return code
        except Exception as e:
            self._log("ERROR", f"获取城市码失败: {e}")
            return ""

    # ═══════════════════════════════════════════════
    #  搜索岗位（严格对齐 mian_ref.py）
    # ═══════════════════════════════════════════════

    def _search_jobs(self, city_code: str, job_query: str, scroll_pages: int) -> list:
        """
        mian_ref.py 搜索逻辑：
          1. 访问
             https://www.zhipin.com/web/geek/jobs?query={job}&city={code}
          2. scroll.to_bottom() × scroll_pages（带 try/except）
          3. .job-name → attr("href")
          4. .rec-job-list.texts() → split() → 解析
          5. salary_markers 分离职位名和薪资
        """
        try:
            url = (f"https://www.zhipin.com/web/geek/jobs?"
                   f"query={job_query}&city={city_code}&industry=&position=")
            self.dp.get(url)
            self._wait(2)

            # ── 滚动加载 ──
            for _ in range(scroll_pages):
                try:
                    self.dp.scroll.to_bottom()
                    self._wait(2)
                except Exception:
                    self._log("WARN", "页面刷新，等待后重试滚动...")
                    self._wait(3)
                    try:
                        self.dp.scroll.to_bottom()
                        self._wait(2)
                    except Exception:
                        break

            # ── 提取 URL ──
            job_url_elements = self.dp.eles(".job-name")
            full_urls = []
            for elem in job_url_elements:
                href = elem.attr("href")
                if href:
                    full_urls.append(href)

            self._log("INFO", f"找到 {len(full_urls)} 个岗位链接")

            # ── 提取岗位列表文本 ──
            job_name_list = self.dp.ele(".rec-job-list").texts()
            if not job_name_list:
                self._log("WARN", ".rec-job-list.texts() 为空，尝试回退方案")
                return []

            # ── 解析（严格对齐 mian_ref.py） ──
            jobs = []
            for i, job_str in enumerate(job_name_list):
                parts = job_str.split('\n')
                if len(parts) < 4:
                    continue

                first_part = parts[0]
                salary_markers = ["K", "元/月", "元/天", "薪"]
                salary_start = len(first_part)
                for marker in salary_markers:
                    idx = first_part.find(marker)
                    if idx != -1 and idx < salary_start:
                        salary_start = idx

                job_info = {
                    "job_name": first_part[:salary_start].strip() if salary_start < len(
                        first_part) else first_part,
                    "salary": first_part[salary_start:].strip() if salary_start < len(
                        first_part) else "",
                    "experience": parts[1],
                    "education": parts[2],
                    "company_location": parts[3],
                    "raw": job_str,
                    "url": full_urls[i] if i < len(full_urls) else "",
                }
                jobs.append(job_info)

            self._log("OK", f"解析到 {len(jobs)} 个岗位")
            return jobs

        except Exception as e:
            self._log("ERROR", f"搜索岗位异常: {e}")
            return []

    # ═══════════════════════════════════════════════
    #  投递单岗位（严格对齐 mian_ref.py）
    # ═══════════════════════════════════════════════

    def _deliver_single_job(self, job: dict, greeting: str, image_paths: list,
                            account_id: str) -> bool:
        """
        mian_ref.py 投递逻辑完整复现：
          1. 访问岗位 URL
          2. 提取 boss-active-time / icon-scale / job-sec-text / .salary
          3. 检测 .btn.btn-startchat
             - 含"继续沟通" → 跳过
             - 含"打招呼" → 点击沟通
          4. 输入招呼语 → 点击发送
          5. .icon-close 关闭聊天窗
          6. 重新点击 btn-startchat → 上传图片（click.to_upload）
        """
        url = job.get("url", "")
        if not url:
            return False

        job_name = job.get("job_name", "未知岗位")
        self._log("INFO", f"  → 访问: {job_name}")
        self.dp.get(url)
        self._wait(2)

        # ── 提取岗位详情（mian_ref.py 独有） ──
        try:
            boss_active = self.dp.ele(".boss-active-time", timeout=3)
            self._log("INFO", f"    活跃度: {boss_active.text}")
        except Exception:
            self._log("INFO", "    活跃度: 未知")

        try:
            scale = self.dp.ele(".icon-scale", timeout=2)
            self._log("INFO", f"    公司规模: {scale.text}")
        except Exception:
            pass

        try:
            desc = self.dp.ele(".job-sec-text", timeout=2)
            desc_short = desc.text[:80] + "..." if len(desc.text) > 80 else desc.text
            self._log("INFO", f"    描述: {desc_short}")
        except Exception:
            pass

        try:
            sal = self.dp.ele(".salary", timeout=2)
            self._log("INFO", f"    薪资: {sal.text}")
        except Exception:
            pass

        # ── 检测沟通按钮 ──
        try:
            chat_btn = self.dp.ele(".btn btn-startchat", timeout=5)
            if chat_btn is None:
                self._log("WARN", "    未找到沟通按钮，跳过")
                return False

            btn_text = chat_btn.text
            self._log("INFO", f"    按钮文本: {btn_text}")

            if "继续沟通" in btn_text:
                self._log("INFO", "    → 已沟通过，跳过")
                return False

            if "打招呼" not in btn_text:
                self._log("WARN", f"    按钮不是打招呼({btn_text})，跳过")
                return False

            # ── 点击沟通 ──
            chat_btn.click()
            self._wait(1.5)

        except Exception as e:
            self._log("WARN", f"    沟通按钮检测异常: {e}")
            return False

        # ── 输入招呼语 → 发送 ──
        try:
            input_area = self.dp.ele(".input-area", timeout=5)
            if input_area:
                input_area.input(greeting)
                self._wait(0.5)
                send_btn = self.dp.ele(".send-message", timeout=3)
                if send_btn:
                    send_btn.click()
                    self._log("OK", f"    ✓ 消息已发送")
                else:
                    self._log("WARN", "    未找到发送按钮")
            else:
                self._log("WARN", "    未找到输入框")
        except Exception as e:
            self._log("WARN", f"    发送消息异常: {e}")

        self._wait(1)

        # ── 关闭聊天窗（mian_ref.py: .icon-close） ──
        try:
            close_btn = self.dp.ele(".icon-close", timeout=3)
            if close_btn:
                close_btn.click()
                self._wait(1)
                self._log("INFO", "    → 关闭聊天窗")
        except Exception:
            self._log("INFO", "    → 未找到关闭按钮（可能已自动关闭）")

        self._wait(0.5)

        # ── 重新打开 → 上传图片（mian_ref.py: click.to_upload） ──
        if image_paths:
            try:
                # 重新点击沟通
                chat_btn2 = self.dp.ele(".btn btn-startchat", timeout=5)
                if chat_btn2:
                    chat_btn2.click()
                    self._wait(1.5)

                for img_path in image_paths:
                    if not os.path.exists(img_path):
                        self._log("WARN", f"    图片不存在: {img_path}")
                        continue
                    try:
                        # mian_ref.py 用 .click.to_upload()
                        upload_el = self.dp.ele(
                            ".toolbar-btn-content.icon.btn-sendimg.tooltip.tooltip-top",
                            timeout=3
                        )
                        if upload_el:
                            upload_el.click.to_upload(img_path)
                            self._wait(1)
                            self._log("OK", f"    ✓ 上传: {os.path.basename(img_path)}")
                        else:
                            self._log("WARN", "    未找到上传按钮")
                    except Exception as e:
                        self._log("WARN", f"    上传图片异常: {e}")

            except Exception as e:
                self._log("WARN", f"    图片上传流程异常: {e}")

        self._log("OK", f"    ✓ {job_name} 投递完成")
        return True

    # ═══════════════════════════════════════════════
    #  连通性测试
    # ═══════════════════════════════════════════════

    def test_connectivity(self, account: dict) -> dict:
        """测试某账号的连通性（打开页面、检测登录、获取城市码、搜索岗位数）。"""
        result = {"success": False, "login_ok": False, "city_ok": False,
                  "job_count": 0, "message": ""}
        try:
            self._log("HEADER", f"═══ 连通性测试: {account.get('name', '未知')} ═══")

            if self.dp is None:
                self.dp = ChromiumPage()

            # 登录检测
            self.dp.get("https://www.zhipin.com")
            self._wait(2)
            nav_el = self.dp.ele(".user-nav", timeout=8)
            if nav_el and "登录/注册" not in nav_el.text:
                result["login_ok"] = True
                self._log("OK", "✓ 已登录")
            else:
                result["message"] = "未登录，请先登录"
                self._log("WARN", "✗ 未登录")
                return result

            # 城市码
            city = account.get("city", "上海")
            code = self._fetch_city_code(city)
            if code:
                result["city_ok"] = True
            else:
                result["message"] = f"城市 [{city}] 码获取失败"
                return result

            # 搜索岗位
            jobs = self._search_jobs(code,
                                     account.get("jobs", [{"query": "数据分析"}])[0].get("query", "数据分析"),
                                     2)
            result["job_count"] = len(jobs)
            result["success"] = True
            result["message"] = f"连通正常，找到 {len(jobs)} 个岗位"
            self._log("OK", f"✓ 连通正常，找到 {len(jobs)} 个岗位")

        except Exception as e:
            result["message"] = f"异常: {e}"
            self._log("ERROR", f"连通性测试异常: {e}")
        finally:
            self._update_progress(0, 0, "")
        return result

    # ═══════════════════════════════════════════════
    #  主运行流程
    # ═══════════════════════════════════════════════

    def run(self):
        """遍历所有账号 → 每个账号的多岗位 → 执行投递。"""
        self.running = True
        self._start_screenshot_loop()

        accounts = self.config.get("accounts", [])
        interval_min = self.config.get("message_interval_min", 3)
        interval_max = self.config.get("message_interval_max", 8)
        global_scroll = self.config.get("global_scroll_pages", 5)

        completed = 0
        total_deliveries = 0

        try:
            self._log("HEADER", "╔══════════════════════════════════╗")
            self._log("HEADER", "║   Boss 直聘 · 自动投递开始      ║")
            self._log("HEADER", "╚══════════════════════════════════╝")

            for acc_idx, account in enumerate(accounts):
                if not self.running:
                    break

                acc_id = account.get("id", f"account_{acc_idx + 1}")
                acc_name = account.get("name", f"账号{acc_idx + 1}")
                city = account.get("city", "上海")
                greeting = account.get("greeting_message",
                                       DEFAULT_GREETING)
                images = account.get("image_files", [])
                jobs_list = account.get("jobs", [{"query": "数据分析"}])

                self._log("HEADER", f"───── 账号 {acc_idx + 1}/{len(accounts)}: {acc_name} [{city}] ─────")

                # 加载该账号的已沟通历史
                self.chatted_companies = _load_chats(acc_id)

                # ── 登录检测 ──
                if not self.ensure_login(account):
                    self._log("WARN", "  需要手动登录，跳过此账号")
                    continue

                # ── 获取城市码 ──
                city_code = self._fetch_city_code(city)
                if not city_code:
                    self._log("ERROR", f"  城市 [{city}] 码获取失败，跳过此账号")
                    continue

                # ── 遍历多岗位 ──
                for job_idx, job_def in enumerate(jobs_list):
                    if not self.running:
                        break

                    job_query = job_def.get("query", "")
                    scroll_cnt = job_def.get("scroll_pages", global_scroll)
                    if not job_query:
                        continue

                    self._log("HEADER", f"  ─── 岗位 {job_idx + 1}/{len(jobs_list)}: {job_query} ───")

                    # 搜索
                    jobs = self._search_jobs(city_code, job_query, scroll_cnt)
                    if not jobs:
                        self._log("WARN", "  未找到岗位")
                        continue

                    total_cnt = len(jobs)
                    total_deliveries += total_cnt

                    for i, job in enumerate(jobs):
                        if not self.running:
                            break

                        job_name = job.get("job_name", "未知")
                        self._log("INFO", f"    [{i + 1}/{total_cnt}] {job_name}")
                        self._update_progress(i + 1, total_cnt,
                                              f"{acc_name} › {job_query} › {i + 1}/{total_cnt}")

                        # 去重
                        if job_name in self.chatted_companies:
                            self._log("INFO", "    → 历史已沟通，跳过")
                            completed += 1
                            continue

                        # 投递
                        success = self._deliver_single_job(job, greeting, images, acc_id)
                        if success:
                            completed += 1
                            self.chatted_companies.add(job_name)
                            _save_chats(acc_id, self.chatted_companies)

                        # 随机间隔
                        if self.running:
                            delay = random.randint(interval_min, interval_max)
                            self._log("INFO", f"    → 等待 {delay}s...")
                            self._wait(delay)

            self._log("HEADER", f"═════ 完成! 共投递 {completed} 次 ═════")

        except Exception as e:
            self._log("ERROR", f"运行异常: {e}\n{traceback.format_exc()}")
        finally:
            self.running = False
            self._update_progress(0, 0, "已停止")
            self._stop_screenshot_loop()

    # ── 停止 ──

    def stop(self):
        self.running = False
        self._log("WARN", "⏹ 停止信号已发送...")


DEFAULT_GREETING = (
    "您好，我是双一流的本科，应聘数据分析岗位。"
    "在校系统学习数据分析相关知识，掌握Excel、基础SQL与数据整理技能，"
    "具备数据思维。做事严谨细心，学习能力强，愿意踏实积累。"
    "十分认可贵公司，希望能获得面试机会。"
)
