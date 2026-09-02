"""跨平台浏览器启动器

解决 DrissionPage 在 macOS 上的兼容性问题：
- Windows: 直接使用 ChromiumPage（正常）
- macOS: 手动启动 Chrome + Chromium 类连接（绕过 bug）

DrissionPage 在 macOS arm64 上的 bug：
启动 Chrome 后，从 /json/version 获取的 browser_id 与实际 WebSocket URL 不匹配，
导致 WebSocket 握手返回 404。
"""
import os
import sys
import time
import json
import subprocess
import platform
import shutil
import socket
import tempfile
import logging
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

logger = logging.getLogger("browser_launcher")

# 平台检测
_IS_MACOS = platform.system().lower() == "darwin"
_IS_WINDOWS = platform.system().lower() == "windows"


def _find_chrome_path() -> str:
    """自动查找 Chrome/Chromium 可执行文件路径（跨平台）"""
    if _IS_MACOS:
        mac_paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
        ]
        for p in mac_paths:
            if os.path.isfile(p):
                return p
        # 尝试 which
        for name in ('google-chrome', 'chromium', 'chrome'):
            path = shutil.which(name)
            if path:
                return path

    elif _IS_WINDOWS:
        win_paths = [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%PROGRAMFILES%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe'),
        ]
        for p in win_paths:
            if os.path.isfile(p):
                return p
        path = shutil.which('chrome') or shutil.which('chrome.exe')
        if path:
            return path

    else:  # Linux
        for name in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'):
            path = shutil.which(name)
            if path:
                return path

    return ""


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """检查端口是否开放"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def _wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    """等待端口开放"""
    start = time.time()
    while time.time() - start < timeout:
        if _is_port_open(host, port):
            return True
        time.sleep(0.5)
    return False


def _get_ws_url(host: str, port: int, retries: int = 5) -> str:
    """从 /json/version 获取 WebSocket URL"""
    for attempt in range(retries):
        try:
            resp = urlopen(f'http://{host}:{port}/json/version', timeout=3)
            data = json.loads(resp.read())
            ws_url = data.get('webSocketDebuggerUrl', '')
            if ws_url:
                return ws_url
        except (URLError, OSError, json.JSONDecodeError) as e:
            logger.debug(f"获取 ws_url 第{attempt+1}次失败: {e}")
            time.sleep(1)
    return ""


class BrowserInstance:
    """浏览器实例封装

    提供统一的 API，屏蔽 Windows/macOS 差异。
    暴露 ChromiumPage 或 tab 的常用方法。
    """

    def __init__(self, chrome_page=None, chromium=None, tab=None, process=None):
        self._page = chrome_page      # Windows: ChromiumPage
        self._chromium = chromium     # macOS: Chromium
        self._tab = tab               # macOS: 当前 tab
        self._process = process       # macOS: Chrome 子进程

    def _get_active(self):
        """返回当前活动的页面对象"""
        if self._page is not None:
            return self._page
        return self._tab

    # ── 常用方法代理 ──

    def ele(self, selector, timeout=None):
        obj = self._get_active()
        if timeout is not None:
            return obj.ele(selector, timeout=timeout)
        return obj.ele(selector)

    def eles(self, selector, timeout=None):
        obj = self._get_active()
        if timeout is not None:
            return obj.eles(selector, timeout=timeout)
        return obj.eles(selector)

    def get(self, url):
        return self._get_active().get(url)

    @property
    def url(self):
        return self._get_active().url

    @property
    def title(self):
        return self._get_active().title

    @property
    def scroll(self):
        return self._get_active().scroll

    def run_js(self, script, *args):
        return self._get_active().run_js(script, *args)

    @property
    def set(self):
        return self._get_active().set

    def cookies(self, as_dict=False):
        return self._get_active().cookies(as_dict=as_dict)

    @property
    def listen(self):
        return self._get_active().listen

    def refresh(self):
        return self._get_active().refresh()

    def close_current_tab(self):
        if self._page is not None:
            self._page.close_current_tab()
        elif self._tab is not None:
            self._tab.close()

    def quit(self):
        """关闭浏览器"""
        try:
            if self._page is not None:
                self._page.quit()
            elif self._chromium is not None:
                self._chromium.quit()
        except Exception as e:
            logger.warning(f"关闭浏览器异常: {e}")
        finally:
            # 确保子进程被终止
            if self._process is not None:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass

    @property
    def current_tab(self):
        """返回当前 tab（macOS 模式下可用）"""
        return self._tab

    @property
    def browser(self):
        """返回浏览器对象（macOS 模式下可用）"""
        return self._chromium

    def new_tab(self, url=""):
        """新建 tab（macOS 模式下可用）"""
        if self._chromium is not None:
            return self._chromium.new_tab(url)
        elif self._page is not None:
            return self._page.new_tab(url)
        return None


def launch_browser(
    headless: bool = False,
    user_agent: str = "",
    proxy: str = "",
    viewport_width: int = 1280,
    viewport_height: int = 800,
    port: int = 0,
    chrome_path: str = "",
) -> BrowserInstance:
    """启动浏览器（跨平台）

    Args:
        headless: 是否无头模式
        user_agent: 自定义 User-Agent
        proxy: 代理地址
        viewport_width: 视口宽度
        viewport_height: 视口高度
        port: 调试端口（0 表示自动选择）
        chrome_path: Chrome 路径（空则自动检测）

    Returns:
        BrowserInstance: 浏览器实例
    """
    if not chrome_path:
        chrome_path = _find_chrome_path()

    if not chrome_path or not os.path.isfile(chrome_path):
        raise FileNotFoundError(
            f"未找到 Chrome/Chromium。请安装 Google Chrome 或手动指定路径。\n"
            f"当前平台: {platform.system()} {platform.machine()}"
        )

    logger.info(f"Chrome 路径: {chrome_path}")

    if _IS_MACOS:
        return _launch_macos(
            chrome_path=chrome_path,
            headless=headless,
            user_agent=user_agent,
            proxy=proxy,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            port=port or _find_free_port(),
        )
    else:
        return _launch_windows(
            chrome_path=chrome_path,
            headless=headless,
            user_agent=user_agent,
            proxy=proxy,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )


def _find_free_port() -> int:
    """找一个空闲端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def _launch_macos(
    chrome_path: str,
    headless: bool,
    user_agent: str,
    proxy: str,
    viewport_width: int,
    viewport_height: int,
    port: int,
) -> BrowserInstance:
    """macOS 启动 Chrome（手动启动 + Chromium 连接）"""

    # 构建启动参数
    user_data_dir = os.path.join(
        tempfile.gettempdir(), f"boss_bot_chrome_{port}"
    )
    os.makedirs(user_data_dir, exist_ok=True)

    args = [
        f'--remote-debugging-port={port}',
        '--no-sandbox',
        '--disable-gpu',
        '--disable-dev-shm-usage',
        '--disable-extensions',
        '--disable-background-networking',
        f'--user-data-dir={user_data_dir}',
        '--remote-allow-origins=*',  # 允许所有来源（Chrome 111+ 需要）
        f'--window-size={viewport_width},{viewport_height}',
    ]

    if headless:
        args.append('--headless=new')

    if user_agent:
        args.append(f'--user-agent={user_agent}')

    if proxy:
        args.append(f'--proxy-server={proxy}')

    logger.info(f"macOS: 启动 Chrome (port={port})...")
    logger.debug(f"启动参数: {args}")

    # 启动 Chrome 子进程
    proc = subprocess.Popen(
        [chrome_path] + args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 等待 Chrome 就绪
    if not _wait_for_port('127.0.0.1', port, timeout=15):
        proc.kill()
        raise RuntimeError(
            f"Chrome 启动失败（端口 {port} 未响应）。\n"
            f"请检查 Chrome 版本是否兼容。"
        )

    # 获取 WebSocket URL
    ws_url = _get_ws_url('127.0.0.1', port)
    if not ws_url:
        proc.kill()
        raise RuntimeError("无法获取 Chrome WebSocket URL")

    logger.info(f"Chrome WebSocket: {ws_url}")

    # 连接
    from DrissionPage._base.chromium import Chromium
    from DrissionPage import ChromiumOptions

    co = ChromiumOptions()
    co.ws_address = ws_url

    try:
        chromium = Chromium(co)
    except Exception as e:
        proc.kill()
        raise RuntimeError(f"连接 Chrome 失败: {e}")

    # 创建初始 tab
    tab = chromium.new_tab()

    logger.info(f"macOS: Chrome 连接成功 (PID={proc.pid})")

    return BrowserInstance(chromium=chromium, tab=tab, process=proc)


def _launch_windows(
    chrome_path: str,
    headless: bool,
    user_agent: str,
    proxy: str,
    viewport_width: int,
    viewport_height: int,
) -> BrowserInstance:
    """Windows 启动 Chrome（使用原生 ChromiumPage）"""

    from DrissionPage import ChromiumPage, ChromiumOptions

    co = ChromiumOptions()
    co.set_browser_path(chrome_path)
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument(f'--window-size={viewport_width},{viewport_height}')

    if headless:
        co.set_argument('--headless=new')

    if user_agent:
        co.set_user_agent(user_agent)

    if proxy:
        co.set_proxy(proxy)

    page = ChromiumPage(co)
    logger.info("Windows: ChromiumPage 启动成功")

    return BrowserInstance(chrome_page=page)
