"""配置管理 — 多岗位多账号版（完整参数版）

完整配置结构（所有字段均可通过 Web UI 调整）：
{
  "browser": {
    "headless": false,
    "viewport_width": 1280,
    "viewport_height": 800,
    "page_load_timeout": 30,
    "custom_user_agent": "",
    "proxy": ""
  },
  "login": {
    "wait_timeout": 300,
    "clear_cookies_on_failure": true
  },
  "rate_limit": {
    "enabled": true,
    "max_per_hour": 30,
    "max_per_day": 100
  },
  "retry": {
    "max_attempts": 3,
    "base_delay": 2.0,
    "backoff_factor": 2.0
  },
  "screenshot": {
    "enabled": true,
    "interval": 3.0
  },
  "accounts": [
    {
      "name": "主账号",
      "enabled": true,
      "cookie_file": "zhipin_cookies.json",
      "image_files": ["..."],
      "message_interval_min": 3,
      "message_interval_max": 8,
      "jobs": [
        {
          "enabled": true,
          "city": "上海",
          "query": "数据分析",
          "scroll_pages": 5,
          "greeting_message": "您好..."
        }
      ]
    }
  ]
}
"""
import json
import os
import copy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "bot_config.json")

DEFAULT_CONFIG = {
    "browser": {
        "headless": False,
        "viewport_width": 1280,
        "viewport_height": 800,
        "page_load_timeout": 30,
        "custom_user_agent": "",
        "proxy": "",
    },
    "login": {
        "wait_timeout": 300,
        "clear_cookies_on_failure": True,
    },
    "rate_limit": {
        "enabled": True,
        "max_per_hour": 30,
        "max_per_day": 100,
    },
    "retry": {
        "max_attempts": 3,
        "base_delay": 2.0,
        "backoff_factor": 2.0,
    },
    "screenshot": {
        "enabled": True,
        "interval": 3.0,
    },
    "accounts": [
        {
            "name": "主账号",
            "enabled": True,
            "cookie_file": "zhipin_cookies.json",
            "image_files": [
                "dashboard/看板1.png",
                "dashboard/看板2.png",
                "dashboard/看板3.png",
            ],
            "message_interval_min": 3,
            "message_interval_max": 8,
            "jobs": [
                {
                    "enabled": True,
                    "city": "上海",
                    "query": "AI产品经理",
                    "scroll_pages": 5,
                    "greeting_message": (
                        "您好，我有AI产品落地经验，熟悉大模型应用与产品化。"
                        "能独立完成需求分析、原型设计、PRD撰写， "
                        "对用户增长与数据驱动有深入理解。"
                        "希望能获得面试机会，详细聊聊我的AI项目经验。"
                    ),
                },
                {
                    "enabled": True,
                    "city": "北京",
                    "query": "大模型应用开发",
                    "scroll_pages": 5,
                    "greeting_message": (
                        "您好，我熟悉大模型API调用与Prompt工程，"
                        "有基于LangChain/LLM的应用开发经验，"
                        "能独立完成AI产品从原型到上线的全流程。"
                        "希望能获得面试机会，贡献我的AI技术能力。"
                    ),
                },
            ],
        }
    ],
}


def _fill_defaults(target: dict, default: dict) -> dict:
    """递归填充缺失的默认值（不覆盖已存在的键）。"""
    for key, val in default.items():
        if key not in target:
            target[key] = copy.deepcopy(val)
        elif isinstance(val, dict) and isinstance(target[key], dict):
            _fill_defaults(target[key], val)
    return target


def _migrate_old_config(old: dict) -> dict:
    """将旧版单岗位配置迁移到新版完整配置格式。"""
    new = copy.deepcopy(DEFAULT_CONFIG)
    # 清空 accounts 然后用旧数据填充
    new["accounts"] = []
    job = {
        "enabled": True,
        "city": old.get("city", "长沙"),
        "query": old.get("job_query", "数据分析"),
        "scroll_pages": old.get("scroll_pages", 5),
        "greeting_message": old.get("greeting_message", ""),
    }
    account = {
        "name": "主账号",
        "enabled": True,
        "cookie_file": "zhipin_cookies.json",
        "image_files": old.get("image_files", [
            "dashboard/看板1.png",
            "dashboard/看板2.png",
            "dashboard/看板3.png",
        ]),
        "message_interval_min": old.get("message_interval_min", 3),
        "message_interval_max": old.get("message_interval_max", 8),
        "jobs": [job],
    }
    new["accounts"].append(account)
    return new


def load_config() -> dict:
    """加载配置，自动填充缺失字段。"""
    if not os.path.exists(CONFIG_FILE):
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(DEFAULT_CONFIG)

    # 检测旧版格式（没有 accounts 但有 job_query）
    if isinstance(saved, dict) and "job_query" in saved:
        saved = _migrate_old_config(saved)

    # 新版但缺少顶层字段 → 合并默认值
    merged = copy.deepcopy(DEFAULT_CONFIG)
    if isinstance(saved, dict):
        _fill_defaults(saved, merged)
        merged = saved
    return merged


def save_config(cfg: dict) -> None:
    """保存配置到文件。"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def validate_config(cfg: dict) -> list:
    """校验配置，返回错误列表（空 = 校验通过）。"""
    errors = []
    if not isinstance(cfg, dict):
        errors.append("配置必须是一个对象")
        return errors

    # browser
    browser = cfg.get("browser", {})
    if isinstance(browser, dict):
        if not isinstance(browser.get("page_load_timeout", 30), (int, float)):
            errors.append("browser.page_load_timeout 必须是数字")

    # rate_limit
    rl = cfg.get("rate_limit", {})
    if isinstance(rl, dict):
        for k in ("max_per_hour", "max_per_day"):
            v = rl.get(k, 0)
            if not isinstance(v, (int, float)) or v < 0:
                errors.append(f"rate_limit.{k} 必须是非负数")

    # accounts
    accounts = cfg.get("accounts", [])
    if not isinstance(accounts, list) or not accounts:
        errors.append("至少需要一个账号配置")
        return errors

    for ai, acc in enumerate(accounts):
        if not isinstance(acc, dict):
            errors.append(f"账号 #{ai} 必须是一个对象")
            continue
        jobs = acc.get("jobs", [])
        if not isinstance(jobs, list) or not jobs:
            errors.append(f"账号「{acc.get('name', ai)}」至少需要一个岗位")
        for ji, job in enumerate(jobs):
            if not isinstance(job, dict):
                errors.append(f"岗位 #{ji} 必须是一个对象")

    return errors


def flatten_jobs_for_run(cfg: dict) -> list[dict]:
    """将配置展平为任务列表，每个任务为一个 (账号, 岗位) 组合。"""
    tasks = []
    for acc in cfg.get("accounts", []):
        if not acc.get("enabled", True):
            continue
        for job in acc.get("jobs", []):
            if not job.get("enabled", True):
                continue
            tasks.append({
                "account_name": acc.get("name", ""),
                "city": job.get("city", "长沙"),
                "query": job.get("query", ""),
                "scroll_pages": job.get("scroll_pages", 5),
                "greeting_message": job.get("greeting_message", ""),
                "cookie_file": acc.get("cookie_file", "zhipin_cookies.json"),
                "image_files": acc.get("image_files", []),
                "message_interval_min": acc.get("message_interval_min", 3),
                "message_interval_max": acc.get("message_interval_max", 8),
                # 引用全局参数
                "browser": cfg.get("browser", {}),
                "login": cfg.get("login", {}),
                "rate_limit": cfg.get("rate_limit", {}),
                "retry": cfg.get("retry", {}),
                "screenshot": cfg.get("screenshot", {}),
            })
    return tasks
