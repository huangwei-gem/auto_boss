"""结构化日志系统 — 支持文件持久化、分级、按类别/时间检索

日志文件位置: app/data/logs/
- bot_YYYY-MM-DD.log  — 每日运行日志
- error_YYYY-MM-DD.log — 错误日志（单独保存，方便排查）
- ai_YYYY-MM-DD.log   — AI 分析日志
- browser_YYYY-MM-DD.log — 浏览器操作日志
"""
import os
import json
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, List
from pathlib import Path

# 日志目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(DATA_DIR, "logs")

# 确保日志目录存在
os.makedirs(LOG_DIR, exist_ok=True)

# 日志级别
LEVEL_DEBUG = "DEBUG"
LEVEL_INFO = "INFO"
LEVEL_WARN = "WARN"
LEVEL_ERROR = "ERROR"
LEVEL_SUCCESS = "SUCCESS"

# 日志类别
CATEGORY_SYSTEM = "SYSTEM"
CATEGORY_BOT = "BOT"
CATEGORY_AI = "AI"
CATEGORY_BROWSER = "BROWSER"
CATEGORY_LOGIN = "LOGIN"
CATEGORY_SCHEDULER = "SCHEDULER"
CATEGORY_SERVER = "SERVER"


class StructuredLogger:
    """结构化日志记录器 — 同时输出到文件和控制台"""

    def __init__(self):
        self._callbacks: List[Callable] = []
        self._lock = threading.Lock()
        self._setup_python_logging()

    def _setup_python_logging(self):
        """配置 Python 标准 logging 模块"""
        self._logger = logging.getLogger("auto_boss")
        self._logger.setLevel(logging.DEBUG)

        # 控制台 handler
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        self._logger.addHandler(console)

        # 文件 handler — 每日日志
        log_file = self._get_log_file("bot")
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        self._logger.addHandler(file_handler)

        # 错误文件 handler
        error_file = self._get_log_file("error")
        error_handler = logging.FileHandler(error_file, encoding="utf-8")
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        self._logger.addHandler(error_handler)

    def _get_log_file(self, prefix: str) -> str:
        """获取当日日志文件路径"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(LOG_DIR, f"{prefix}_{date_str}.log")

    def _write_structured(self, category: str, level: str, message: str, extra: dict = None):
        """写入结构化 JSON 日志（用于 API 检索）"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "level": level,
            "message": message,
        }
        if extra:
            entry["extra"] = extra

        # 写入结构化日志文件
        structured_file = os.path.join(LOG_DIR, f"structured_{datetime.now().strftime('%Y-%m-%d')}.jsonl")
        with self._lock:
            with open(structured_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log(self, category: str, level: str, message: str, extra: dict = None):
        """记录一条日志"""
        # 写入结构化日志
        self._write_structured(category, level, message, extra)

        # 同时输出到标准日志
        log_msg = f"[{category}] {message}"
        if level == LEVEL_ERROR:
            self._logger.error(log_msg)
        elif level == LEVEL_WARN:
            self._logger.warning(log_msg)
        elif level == LEVEL_SUCCESS:
            self._logger.info(f"[SUCCESS] {log_msg}")
        elif level == LEVEL_DEBUG:
            self._logger.debug(log_msg)
        else:
            self._logger.info(log_msg)

        # 通知回调（用于 Socket.IO 推送）
        for cb in self._callbacks:
            try:
                cb(category, level, message, extra)
            except Exception:
                pass

    def debug(self, category: str, message: str, extra: dict = None):
        self.log(category, LEVEL_DEBUG, message, extra)

    def info(self, category: str, message: str, extra: dict = None):
        self.log(category, LEVEL_INFO, message, extra)

    def warn(self, category: str, message: str, extra: dict = None):
        self.log(category, LEVEL_WARN, message, extra)

    def error(self, category: str, message: str, extra: dict = None):
        self.log(category, LEVEL_ERROR, message, extra)

    def success(self, category: str, message: str, extra: dict = None):
        self.log(category, LEVEL_SUCCESS, message, extra)

    def add_callback(self, callback: Callable):
        """添加日志回调（如 Socket.IO 推送）"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable):
        self._callbacks.remove(callback)

    # ── 日志检索 API ──

    def query_logs(
        self,
        category: str = None,
        level: str = None,
        search: str = None,
        start_time: str = None,
        end_time: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """检索日志"""
        results = []
        structured_file = os.path.join(LOG_DIR, f"structured_{datetime.now().strftime('%Y-%m-%d')}.jsonl")

        if not os.path.exists(structured_file):
            return {"total": 0, "results": [], "offset": offset, "limit": limit}

        with self._lock:
            with open(structured_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # 过滤
                    if category and entry.get("category") != category:
                        continue
                    if level and entry.get("level") != level:
                        continue
                    if search and search.lower() not in entry.get("message", "").lower():
                        continue
                    if start_time and entry.get("timestamp", "") < start_time:
                        continue
                    if end_time and entry.get("timestamp", "") > end_time:
                        continue

                    results.append(entry)

        # 分页
        total = len(results)
        results = results[offset:offset + limit]

        return {
            "total": total,
            "results": results,
            "offset": offset,
            "limit": limit,
        }

    def get_error_summary(self, hours: int = 24) -> dict:
        """获取错误摘要"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        errors = self.query_logs(level=LEVEL_ERROR, start_time=cutoff, limit=1000)

        # 按类别分组统计
        by_category = {}
        for entry in errors["results"]:
            cat = entry.get("category", "UNKNOWN")
            by_category[cat] = by_category.get(cat, 0) + 1

        return {
            "total_errors": errors["total"],
            "by_category": by_category,
            "recent_errors": errors["results"][:10],
        }

    def clear_old_logs(self, days: int = 7):
        """清理超过指定天数的日志"""
        cutoff = datetime.now() - timedelta(days=days)
        removed = 0
        for fn in os.listdir(LOG_DIR):
            filepath = os.path.join(LOG_DIR, fn)
            if os.path.isfile(filepath):
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                if mtime < cutoff:
                    os.remove(filepath)
                    removed += 1
        return removed


# 全局单例（命名为 log_mgr 避免与标准库 logging.Logger 冲突）
log_mgr = StructuredLogger()
