import os, re

filepath = r"C:\Users\35796\Documents\coding\boss-auto-apply\core\bot_core.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add _login_required_cb in _load_config_params
old = '        self._cookie_file = self.config.get("cookie_file", "zhipin_cookies.json")'
new = '        self._cookie_file = self.config.get("cookie_file", "zhipin_cookies.json")\n        self._login_required_cb = self.config.get("_login_required_callback", None)'
content = content.replace(old, new)

# 2. Find and replace _run() method
# Find the start of _run
idx_run = content.find("    def _run(self):")
if idx_run >= 0:
    # Find the next method or section
    rest = content[idx_run:]
    # Find the next def or section marker
    next_def = rest.find("\n    def ", 30)
    if next_def < 0:
        next_def = rest.find("\n    # ", 30)
    if next_def < 0:
        next_def = len(rest)
    
    old_run = rest[:next_def]
    
    new_run = '''    def _run(self):
        self._log("INFO", "\\U0001f50d \\u641c\\u7d22: " + self._city + " \\u00b7 " + self._query)

        if not self._init_browser():
            return

        # \\u6b65\\u9aa4: \\u68c0\\u67e5\\u767b\\u5f55\\u72b6\\u6001\\uff08\\u53c2\\u8003 mian.py \\u6d41\\u7a0b\\uff09
        if not self._check_and_handle_login():
            return

        # \\u83b7\\u53d6\\u5c97\\u4f4d\\u5217\\u8868
        self._log("INFO", "\\u6b63\\u5728\\u83b7\\u53d6\\u5c97\\u4f4d\\u5217\\u8868...")
        self._parse_job_list()

        # \\u904d\\u5386\\u6295\\u9012
        self._step_browse_jobs()

        self._log("INFO", "\\u2705 \\u4efb\\u52a1\\u5b8c\\u6210\\uff01")

    def _check_and_handle_login(self) -> bool:
        """\\u68c0\\u67e5\\u767b\\u5f55\\u72b6\\u6001\\uff0c\\u5982\\u679c\\u9700\\u8981\\u767b\\u5f55\\u5219\\u6253\\u5f00\\u767b\\u5f55\\u9875\\u9762\\u5e76\\u7b49\\u5f85\\u3002
        \\u53c2\\u8003 mian.py \\u6d41\\u7a0b\\u3002"""
        try:
            self.dp.get("https://www.zhipin.com")
            self._random_delay(2, 3)

            # \\u5148\\u5c1d\\u8bd5\\u52a0\\u8f7d cookie
            if self._load_cookies():
                self.dp.get("https://www.zhipin.com/web/geek/job")
                self._random_delay(2, 3)
                nav_ele = self.dp.ele(".user-nav", timeout=3)
                if nav_ele and "\\u767b\\u5f55/\\u6ce8\\u518c" not in nav_ele.text:
                    self._is_logged_in = True
                    self._log("INFO", "Cookie \\u6709\\u6548\\uff0c\\u5df2\\u767b\\u5f55")
                    self._save_cookies()
                    return True

            # Cookie \\u65e0\\u6548\\u6216\\u4e0d\\u5b58\\u5728\\uff0c\\u9700\\u8981\\u767b\\u5f55
            self._log("WARN", "\\u9700\\u8981\\u767b\\u5f55")
            self._log("INFO", "\\u6b63\\u5728\\u6253\\u5f00\\u767b\\u5f55\\u9875\\u9762...")

            # \\u6253\\u5f00\\u767b\\u5f55\\u9875\\u9762\\uff08\\u53c2\\u8003 mian.py\\uff09
            self.dp.get("https://www.zhipin.com/web/user/?ka=header-login")
            self._random_delay(1, 2)

            # \\u901a\\u77e5\\u524d\\u7aef\\u9700\\u8981\\u767b\\u5f55
            if self._login_required_cb:
                self._login_required_cb()

            self._log("INFO", "\\u8bf7\\u5728\\u6d4f\\u89c8\\u5668\\u4e2d\\u624b\\u52a8\\u767b\\u5f55\\uff0c\\u767b\\u5f55\\u540e\\u70b9\\u51fb\\u300c\\u786e\\u8ba4\\u767b\\u5f55\\u300d\\u6309\\u94ae\\u7ee7\\u7eed\\u3002")

            # \\u7b49\\u5f85\\u7528\\u6237\\u786e\\u8ba4\\u767b\\u5f55
            if not self._wait_for_login():
                self._log("ERROR", "\\u767b\\u5f55\\u8d85\\u65f6\\uff0c\\u8bf7\\u7a0d\\u540e\\u91cd\\u8bd5")
                return False

            # \\u767b\\u5f55\\u6210\\u529f\\uff0c\\u4fdd\\u5b58 cookie
            self._save_cookies()
            self._log("SUCCESS", "\\u767b\\u5f55\\u6210\\u529f")

            # \\u5237\\u65b0\\u9875\\u9762\\u83b7\\u53d6\\u57ce\\u5e02\\u6570\\u636e
            self.dp.refresh()
            self._random_delay(2, 3)

            return True
        except Exception as e:
            self._log("ERROR", "\\u767b\\u5f55\\u68c0\\u67e5\\u5f02\\u5e38: " + str(e))
            return False

    def _check_login_expired(self) -> bool:
        """\\u68c0\\u67e5\\u662f\\u5426\\u767b\\u5f55\\u8fc7\\u671f\\uff08\\u8df3\\u8f6c\\u5230\\u767b\\u5f55\\u9875\\u9762\\u4e86\\uff09\\u3002"""
        try:
            current_url = self.dp.url
            if "passport" in current_url or "login" in current_url:
                self._log("WARN", "\\u68c0\\u6d4b\\u5230\\u767b\\u5f55\\u8fc7\\u671f\\uff0c\\u6b63\\u5728\\u91cd\\u65b0\\u6253\\u5f00\\u767b\\u5f55\\u9875\\u9762...")
                self.dp.get("https://www.zhipin.com/web/user/?ka=header-login")
                self._random_delay(1, 2)
                if self._login_required_cb:
                    self._login_required_cb()
                self._login_event.clear()
                self._log("INFO", "\\u8bf7\\u91cd\\u65b0\\u767b\\u5f55\\u540e\\u70b9\\u51fb\\u300c\\u786e\\u8ba4\\u767b\\u5f55\\u300d\\u6309\\u94ae\\u7ee7\\u7eed")
                if self._wait_for_login():
                    self._save_cookies()
                    self._log("SUCCESS", "\\u91cd\\u65b0\\u767b\\u5f55\\u6210\\u529f")
                    return True
                else:
                    self._log("ERROR", "\\u91cd\\u65b0\\u767b\\u5f55\\u8d85\\u65f6")
                    return False
            return True
        except Exception:
            return True
'''
    content = content.replace(old_run, new_run)
    print("Replaced _run method")
else:
    print("_run method not found")

# 3. Update _step_browse_jobs to add login expiration check
idx_sbj = content.find("    def _step_browse_jobs(self):")
if idx_sbj >= 0:
    old_sbj = content[idx_sbj:]
    # Find the next method
    next_def = old_sbj.find("\n    def ", 40)
    if next_def < 0:
        next_def = old_sbj.find("\n    # ", 40)
    if next_def < 0:
        next_def = len(old_sbj)
    old_sbj_method = old_sbj[:next_def]
    
    # Add _check_login_expired call before applying
    new_sbj = old_sbj_method.replace(
        "            success = self._apply_job(job)",
        "            # check login expired\n            if not self._check_login_expired():\n                break\n\n            success = self._apply_job(job)"
    )
    content = content.replace(old_sbj_method, new_sbj)
    print("Updated _step_browse_jobs")
else:
    print("_step_browse_jobs not found")

# 4. Update _apply_job to match mian.py flow
idx_aj = content.find("    def _apply_job(self, job: dict) -> bool:")
if idx_aj >= 0:
    old_aj = content[idx_aj:]
    # Find the next method
    next_def = old_aj.find("\n    def ", 40)
    if next_def < 0:
        next_def = old_aj.find("\n    # ", 40)
    if next_def < 0:
        next_def = len(old_aj)
    old_aj_method = old_aj[:next_def]
    
    new_aj = '''    @retry(max_attempts=3, base_delay=2.0, backoff_factor=2.0)
    def _apply_job(self, job: dict) -> bool:
        """\\u6295\\u9012\\u5c97\\u4f4d\\uff08\\u53c2\\u8003 mian.py \\u6d41\\u7a0b\\uff09\\u3002
        \\u6d41\\u7a0b: \\u8bbf\\u95ee\\u5c97\\u4f4d -> \\u68c0\\u67e5\\u662f\\u5426\\u5df2\\u6c9f\\u901a -> \\u70b9\\u51fb\\u7acb\\u5373\\u6c9f\\u901a -> \\u8f93\\u5165\\u6d88\\u606f -> \\u53d1\\u9001 -> \\u5173\\u95ed -> \\u91cd\\u65b0\\u6253\\u5f00 -> \\u4e0a\\u4f20\\u56fe\\u7247"""
        if not self.running:
            return False

        url = job.get("url", "")
        if not url:
            return False

        try:
            self.dp.get(url)
            self._random_delay(2, 5)

            # \\u68c0\\u67e5\\u6309\\u94ae\\u72b6\\u6001\\uff08\\u53c2\\u8003 mian.py\\uff09
            # \\u5982\\u679c\\u6309\\u94ae\\u662f"\\u7ee7\\u7eed\\u6c9f\\u901a"\\uff0c\\u8bf4\\u660e\\u4e4b\\u524d\\u5df2\\u7ecf\\u6c9f\\u901a\\u8fc7
            chat_btn = self.dp.ele(".btn.btn-startchat", timeout=5)
            if chat_btn:
                btn_text = chat_btn.text
                if "\\u7ee7\\u7eed\\u6c9f\\u901a" in btn_text:
                    self._log("INFO", "\\u4e4b\\u524d\\u5df2\\u7ecf\\u6c9f\\u901a\\u8fc7\\uff0c\\u4e0d\\u9700\\u8981\\u518d\\u6c9f\\u901a")
                    self._mark_chatted(job)
                    return True
            else:
                self._log("WARN", "\\u672a\\u627e\\u5230\\u6c9f\\u901a\\u6309\\u94ae\\uff0c\\u53ef\\u80fd\\u5df2\\u4e0b\\u67b6\\u6216\\u5df2\\u6c9f\\u901a")
                return False

            # \\u70b9\\u51fb\\u300c\\u7acb\\u5373\\u6c9f\\u901a\\u300d
            chat_btn.click()
            self._random_delay(2, 4)

            # \\u627e\\u5230\\u8f93\\u5165\\u6846\\u5e76\\u53d1\\u9001\\u6d88\\u606f
            msg_input = self.dp.ele(".input-area", timeout=5)
            if not msg_input:
                self._log("WARN", "\\u672a\\u627e\\u5230\\u6d88\\u606f\\u8f93\\u5165\\u6846")
                return False

            greeting = self._greeting_message or "\\u60a8\\u597d\\uff0c\\u5e0c\\u671b\\u80fd\\u83b7\\u5f97\\u9762\\u8bd5\\u673a\\u4f1a\\u3002"
            msg_input.clear()
            self._random_delay(0.5, 1.5)
            msg_input.input(greeting)
            self._random_delay(1, 2)

            # \\u53d1\\u9001\\u6d88\\u606f
            send_btn = self.dp.ele(".send-message", timeout=3)
            if send_btn:
                send_btn.click()
                self._random_delay(1, 2)
            else:
                self.dp.run_js("document.querySelector('.send-message')?.click()")
                self._random_delay(1, 2)

            # \\u5982\\u679c\\u6709\\u56fe\\u7247\\uff0c\\u6309 mian.py \\u6d41\\u7a0b\\uff1a\\u5173\\u95ed -> \\u91cd\\u65b0\\u6253\\u5f00 -> \\u4e0a\\u4f20\\u56fe\\u7247
            if self._image_files:
                self._random_delay(1, 2)

                # \\u5173\\u95ed\\u804a\\u5929\\u7a97\\u53e3
                try:
                    close_btn = self.dp.ele(".icon-close", timeout=3)
                    if close_btn:
                        close_btn.click()
                        self._random_delay(1, 2)
                except Exception:
                    pass

                # \\u70b9\\u51fb\\u300c\\u7ee7\\u7eed\\u6c9f\\u901a\\u300d\\u91cd\\u65b0\\u6253\\u5f00\\u804a\\u5929
                try:
                    continue_btn = self.dp.ele(".btn.btn-startchat", timeout=5)
                    if continue_btn and "\\u7ee7\\u7eed\\u6c9f\\u901a" in continue_btn.text:
                        continue_btn.click()
                        self._random_delay(1, 2)
                except Exception:
                    pass

                # \\u4e0a\\u4f20\\u56fe\\u7247
                for img_path in self._image_files:
                    if os.path.isfile(img_path):
                        try:
                            upload_trigger = self.dp.ele(".toolbar-btn-content", timeout=3)
                            if upload_trigger:
                                upload_trigger.click.to_upload(img_path)
                                self._random_delay(1, 2)
                            else:
                                upload_btn = self.dp.ele("tag:input@@type=file", timeout=3)
                                if upload_btn:
                                    upload_btn.input(img_path)
                                    self._random_delay(1, 2)
                        except Exception:
                            self._log("WARN", "\\u4e0a\\u4f20\\u56fe\\u7247\\u5931\\u8d25: " + str(img_path))

            self._mark_chatted(job)
            return True

        except Exception as e:
            self._log("WARN", "\\u53d1\\u9001\\u6d88\\u606f\\u5f02\\u5e38: " + str(e))
            return False
'''
    content = content.replace(old_aj_method, new_aj)
    print("Replaced _apply_job method")
else:
    print("_apply_job not found")

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Done! Updated bot_core.py")
