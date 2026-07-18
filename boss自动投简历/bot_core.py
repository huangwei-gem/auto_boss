import json
import os
import random
import time
import threading
from io import BytesIO
from DrissionPage import ChromiumPage


class BotCore:
    def __init__(self, config: dict, log_callback, screenshot_callback=None):
        self.config = config
        self.log_cb = log_callback
        self.screenshot_cb = screenshot_callback
        self.running = False
        self.dp = None
        self._login_event = threading.Event()
        self._screenshot_thread = None
        self._stop_screenshot = threading.Event()
        self._is_logged_in = False

    # ---- logging helper ----

    def _log(self, level: str, msg: str) -> None:
        self.log_cb(f"[{level}] {msg}")

    # ---- public API ----

    def start(self) -> None:
        self.running = True
        self.dp = ChromiumPage()
        try:
            self._step_login()
            if not self.running:
                return
            if not self._is_logged_in:
                self._log("ERROR", "未检测到登录状态，终止投递")
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
        """Called from UI after user confirms they've logged in."""
        self._login_event.set()

    def check_login_status(self) -> bool:
        """Check if currently logged in by looking at page nav."""
        if not self.dp:
            return False
        try:
            self.dp.get("https://www.zhipin.com")
            self.dp.wait(2)
            nav_ele = self.dp.ele(".user-nav", timeout=3)
            if nav_ele:
                text = nav_ele.text
                if "登录/注册" not in text:
                    self._is_logged_in = True
                    return True
            return False
        except Exception:
            return False

    def _start_screenshot_loop(self) -> None:
        """Background thread that takes screenshots periodically."""
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

    # ---- steps ----

    def _step_login(self) -> None:
        self._log("INFO", "正在打开 Boss 直聘首页...")
        self.dp.get("https://www.zhipin.com")
        self.dp.wait(2)

        nav_ele = self.dp.ele(".user-nav", timeout=3)
        if nav_ele:
            un_text = nav_ele.text
            if "登录/注册" not in un_text:
                self._log("INFO", "检测到已登录状态，跳过登录步骤")
                self._is_logged_in = True
                return

        self._log("WARN", "需要登录！请在浏览器中手动登录后，点击「确认已登录」按钮")
        self.dp.get("https://www.zhipin.com/web/user/?ka=header-login")

        self._login_event.clear()
        self._login_event.wait(timeout=300)

        if not self.running:
            self._log("INFO", "用户取消登录")
            return

        with open("zhipin_cookies", "w", encoding="utf-8") as f:
            json.dump(self.dp.cookies(), f)
        self._is_logged_in = True
        self._log("INFO", "登录状态已保存")

    def _step_fetch_cities(self) -> None:
        self._log("INFO", "刷新页面获取城市数据...")
        self.dp.refresh()
        self.dp.wait(2)

        city_dict = {}
        self.dp.listen.start("data/city.json")
        for packet in self.dp.listen.steps():
            res = packet.response.body
            city_list = res.get("zpData", {}).get("hotCityList", [])
            for city in city_list:
                city_dict[city["name"]] = city["code"]
            break
        self.dp.listen.stop()

        self._log("INFO", f"已获取 {len(city_dict)} 个城市数据")

        target_city = self.config["city"]
        if target_city not in city_dict:
            self._log("ERROR", f"城市 '{target_city}' 不在热门城市中，可选: {list(city_dict.keys())[:10]}...")
            raise ValueError(f"Unknown city: {target_city}")

        self.city_code = city_dict[target_city]
        self._log("INFO", f"目标城市: {target_city} (code={self.city_code})")

    def _step_search_jobs(self) -> None:
        jobs_config = self.config.get("jobs", [])
        all_jobs = []

        for job_cfg in jobs_config:
            query = job_cfg.get("query", "")
            if not query:
                continue

            scroll_pages = job_cfg.get("scroll_pages", self.config.get("scroll_pages", 5))
            url = f"https://www.zhipin.com/web/geek/jobs?query={query}&city={self.city_code}&industry=&position="
            self._log("INFO", f"搜索岗位: {query}, URL: {url}")
            self.dp.get(url)
            self.dp.wait(2)

            self._log("INFO", f"滚动页面 {scroll_pages} 次加载更多职位...")
            for i in range(scroll_pages):
                if not self.running:
                    return
                try:
                    self.dp.scroll.to_bottom()
                    self.dp.wait(2)
                except Exception:
                    self._log("WARN", "页面刷新，等待加载后重试...")
                    self.dp.wait(3)
                    self.dp.scroll.to_bottom()
                    self.dp.wait(2)

            job_url_elements = self.dp.eles(".job-name")
            full_job_urls = []
            for elem in job_url_elements:
                href = elem.attr("href")
                if href:
                    full_job_urls.append(href)

            self._log("INFO", f"共找到 {len(full_job_urls)} 个岗位 (关键词: {query})")

            processed_jobs = []
            rec_list_ele = self.dp.ele(".rec-job-list", timeout=3)
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
                    processed_jobs.append({"job_name": "", "salary": "", "url": u, "query": query})

            self._log("INFO", f"解析出 {len(processed_jobs)} 条完整岗位信息 (关键词: {query})")
            all_jobs.extend(processed_jobs)

        self.jobs = all_jobs
        self._log("INFO", f"共收集到 {len(all_jobs)} 条岗位 (所有关键词)")

    def _step_browse_jobs(self) -> None:
        chats_log = self._load_chats_log()
        images = self.config.get("image_files", [])
        valid_images = [img for img in images if os.path.isfile(img)]
        if valid_images != images:
            missing = [i for i in images if not os.path.isfile(i)]
            self._log("WARN", f"以下图片不存在: {missing}")

        min_interval = self.config.get("message_interval_min", 3)
        max_interval = self.config.get("message_interval_max", 8)

        total = len(self.jobs)
        for idx, job in enumerate(self.jobs, 1):
            if not self.running:
                self._log("INFO", "用户停止，中断投递")
                break

            url = job["url"]
            if not url:
                self._log("WARN", f"第 {idx}/{total}: 无链接，跳过")
                continue

            job_name = job.get("job_name", "未知岗位")
            salary = job.get("salary", "")
            query = job.get("query", "")
            self._log("INFO", f"[{idx}/{total}] 正在投递 ({query}): {job_name} {salary}")

            self.dp.get(url)
            self.dp.wait(2)

            btn = self.dp.ele(".btn.btn-startchat", timeout=3)
            if btn and btn.text == "继续沟通":
                self._log("INFO", "  → 之前已沟通过，跳过")
                continue

            try:
                boss_time = self.dp.ele(".boss-active-time", timeout=3).text
                scale = self.dp.ele(".icon-scale", timeout=3).text
                self._log("INFO", f"  活跃度: {boss_time}, 规模: {scale}")
            except Exception:
                pass

            greeting = self.config.get("greeting_message", "")
            try:
                chat_btn = self.dp.ele(".btn.btn-startchat", timeout=3)
                if chat_btn:
                    chat_btn.click()
                    self.dp.wait(1)

                    input_area = self.dp.ele(".input-area", timeout=3)
                    if input_area:
                        input_area.input(greeting)
                        send_btn = self.dp.ele(".send-message", timeout=3)
                        if send_btn:
                            send_btn.click()
                            self._log("SUCCESS", "  → 消息发送成功")
                        else:
                            self._log("WARN", "  → 未找到发送按钮")
                    else:
                        self._log("WARN", "  → 未找到输入框")
                else:
                    self._log("WARN", "  → 未找到沟通按钮")
            except Exception as e:
                self._log("ERROR", f"  → 发送失败: {e}")

            if valid_images:
                try:
                    for img_path in valid_images:
                        img_ele = self.dp.ele(
                            ".toolbar-btn-content.icon.btn-sendimg.tooltip.tooltip-top", timeout=3
                        )
                        if img_ele:
                            img_ele.click.to_upload(img_path)
                            self._log("INFO", f"  → 上传图片: {os.path.basename(img_path)}")
                        else:
                            self._log("WARN", "  → 未找到图片上传按钮")
                except Exception as e:
                    self._log("ERROR", f"  → 图片上传失败: {e}")

            try:
                close_btn = self.dp.ele(".icon-close", timeout=3)
                if close_btn:
                    close_btn.click()
            except Exception:
                pass

            company = job.get("company_location", "").split()[0] if job.get("company_location") else ""
            if company:
                chats_log.add(company)
                self._save_chats_log(chats_log)

            delay = random.uniform(min_interval, max_interval)
            self._log("INFO", f"  → 等待 {delay:.1f} 秒后继续...")
            time.sleep(delay)

    # ---- dedup helper ----

    def _load_chats_log(self) -> set:
        if os.path.exists("chats_log.json"):
            try:
                with open("chats_log.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                return set(data)
            except (json.JSONDecodeError, OSError):
                pass
        return set()

    def _save_chats_log(self, chats: set) -> None:
        with open("chats_log.json", "w", encoding="utf-8") as f:
            json.dump(list(chats), f, ensure_ascii=False)
