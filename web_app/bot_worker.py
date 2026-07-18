"""
BotWorker — 后台异步线程封装 BotCore

通过 asyncio 队列将 BotCore 的回调（日志、截图、进度）桥接到
FastAPI WebSocket。启动时在主线程用 threading 运行 BotCore，
回调垫片将消息塞入 asyncio 队列，WebSocket 发送循环从队列消费。
"""
import asyncio
import json
import os
import sys
import threading
import time
from typing import Callable, Optional

# 使 bot_core 可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from bot_core import BotCore


class BotWorker:
    """在后台线程中运行 BotCore，通过 asyncio.Queue 桥接回调。"""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._bot: Optional[BotCore] = None
        self._running = False

        # asyncio 队列 — WebSocket 发送循环从这消费
        self.log_queue: asyncio.Queue = asyncio.Queue()
        self.screenshot_queue: asyncio.Queue = asyncio.Queue()
        self.progress_queue: asyncio.Queue = asyncio.Queue()
        self.login_queue: asyncio.Queue = asyncio.Queue()

        # 登录确认事件（跨线程）
        self._login_event = threading.Event()
        self._login_confirmed = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, config: dict) -> None:
        """启动 BotCore 后台线程。"""
        if self._running:
            raise RuntimeError("Bot 已在运行中")

        self._running = True
        self._login_confirmed = False

        def _run():
            try:
                bot = BotCore(
                    config=config,
                    log_callback=self._log_cb,
                    screenshot_callback=self._screenshot_cb,
                    progress_callback=self._progress_cb,
                )
                self._bot = bot

                # 替换登录步骤为异步通知模式
                original_step = bot._step_login
                bot._step_login = lambda: self._async_login(bot)

                bot.start()
            except Exception as e:
                self._put_log(f"[ERROR] Bot 异常: {e}")
            finally:
                self._running = False
                self._bot = None
                self._put_log("[INFO] Bot 已停止")

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._bot:
            self._bot.stop()
        self._running = False
        self._login_event.set()

    def confirm_login(self) -> None:
        self._login_confirmed = True
        self._login_event.set()

    # ── 回调垫片（在 BotCore 线程中调用） ──

    def _put_log(self, msg: str) -> None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(
                    self.log_queue.put_nowait, {"type": "log", "msg": msg, "ts": time.time()}
                )
        except RuntimeError:
            pass  # 没有事件循环就丢弃

    def _log_cb(self, msg: str) -> None:
        self._put_log(msg)

    def _screenshot_cb(self, data: bytes) -> None:
        import base64
        b64 = base64.b64encode(data).decode("utf-8")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(
                    self.screenshot_queue.put_nowait,
                    {"type": "screenshot", "data": f"data:image/png;base64,{b64}"}
                )
        except RuntimeError:
            pass

    def _progress_cb(self, data: dict) -> None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(
                    self.progress_queue.put_nowait, {"type": "progress", **data}
                )
        except RuntimeError:
            pass

    # ── 异步登录流程 ──

    def _async_login(self, bot: BotCore):
        """替代 _step_login：先尝试 Cookie，否则通知前端扫码。"""
        # 先尝试 Cookie
        if bot._load_cookies():
            bot.dp.refresh()
            time.sleep(3)
            if bot.check_login_status():
                bot._log("INFO", "Cookie 登录成功")
                return
            bot._log("WARN", "Cookie 已失效，重新登录")
            bot._clear_cookies()

        # 检测当前是否已登录
        nav_ele = bot.dp.ele(".user-nav", timeout=5)
        if nav_ele and "登录/注册" not in nav_ele.text:
            bot._log("INFO", "检测到已登录状态")
            bot._is_logged_in = True
            bot._save_cookies()
            return

        # 通知前端需要扫码
        bot._log("WARN", "请在浏览器中扫码登录 Boss 直聘，然后点击「确认已登录」")
        bot.dp.get("https://www.zhipin.com/web/user/?ka=header-login")

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(
                    self.login_queue.put_nowait, {"type": "login_required"}
                )
        except RuntimeError:
            pass

        # 等待用户确认
        self._login_event.clear()
        self._login_confirmed = False
        logged_in = self._login_event.wait(timeout=300)

        if not bot.running:
            bot._log("INFO", "用户取消登录")
            return
        if not logged_in:
            bot._log("WARN", "登录等待超时（5分钟）")
            return

        bot._save_cookies()
        bot._is_logged_in = True
        bot._log("INFO", "登录成功")
