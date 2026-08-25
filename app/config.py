"""配置管理 — 多岗位多账号版 + AI 智能解析

完整配置结构（所有字段均可通过 Web UI 调整）：
{
  "browser": { ... },
  "login": { ... },
  "rate_limit": { ... },
  "retry": { ... },
  "ai": {
    "enabled": false,
    "api_key": "",
    "api_base": "https://apihub.agnes-ai.com/v1",
    "model": "agnes-2.5-flash",
    "match_threshold": 70
  },
  "resume": {
    "school": "",
    "major": "",
    "degree": "",
    "skills": [],
    "experience": "",
    "target_position": "",
    "self_intro": ""
  },
  "accounts": [ ... ]
}
"""
import json
import os
import copy

# app/ 目录；数据文件统一放在 app/data/
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(DATA_DIR, "bot_config.json")

DEFAULT_GREETING = (
    "您好，我是双一流的本科，应聘数据分析岗位。在校系统学习数据分析相关知识，"
    "掌握Excel、基础SQL与数据整理技能，具备数据思维。做事严谨细心，学习能力强，"
    "愿意踏实积累。十分认可贵公司，希望能获得面试机会。"
)

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
    "ai": {
        "enabled": False,
        "api_key": "",
        "api_base": "https://apihub.agnes-ai.com/v1",
        "model": "agnes-2.5-flash",
        "match_threshold": 70,
        "providers": [
            {
                "name": "Agnes",
                "api_key": "",
                "api_base": "https://apihub.agnes-ai.com/v1",
                "model": "agnes-2.5-flash",
                "timeout": 30
            }
        ]
    },
    "resume": {
        "school": "",
        "major": "",
        "degree": "",
        "skills": [],
        "experience": "",
        "target_position": "",
        "self_intro": "",
    },
    "accounts": [
        {
            "name": "主账号",
            "enabled": True,
            "cookie_file": "zhipin_cookies.json",
            "image_files": [],
            "message_interval_min": 3,
            "message_interval_max": 8,
            "jobs": [
                {
                    "enabled": True,
                    "city": "上海",
                    "query": "数据分析",
                    "scroll_pages": 5,
                    "greeting_message": DEFAULT_GREETING,
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
    new["accounts"] = []
    job = {
        "enabled": True,
        "city": old.get("city", "上海"),
        "query": old.get("job_query", "数据分析"),
        "scroll_pages": old.get("scroll_pages", 5),
        "greeting_message": old.get("greeting_message", DEFAULT_GREETING),
    }
    account = {
        "name": "主账号",
        "enabled": True,
        "cookie_file": "zhipin_cookies.json",
        "image_files": old.get("image_files", []),
        "message_interval_min": old.get("message_interval_min", 3),
        "message_interval_max": old.get("message_interval_max", 8),
        "jobs": [job],
    }
    new["accounts"].append(account)
    return new


def load_config() -> dict:
    """加载配置，自动填充缺失字段（包括 AI 和简历字段）。"""
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

    # 新版但缺少顶层字段 -> 合并默认值
    merged = copy.deepcopy(DEFAULT_CONFIG)
    if isinstance(saved, dict):
        _fill_defaults(saved, merged)
        merged = saved

    # 确保每个 job 都有 greeting_message 默认值
    for acc in merged.get("accounts", []):
        acc.setdefault("image_files", [])
        acc.setdefault("message_interval_min", 3)
        acc.setdefault("message_interval_max", 8)
        for job in acc.get("jobs", []):
            job.setdefault("greeting_message", DEFAULT_GREETING)
            job.setdefault("scroll_pages", 5)
            job.setdefault("city", "上海")
            job.setdefault("enabled", True)

    # 确保 AI 和 resume 字段存在
    merged.setdefault("ai", copy.deepcopy(DEFAULT_CONFIG["ai"]))
    merged.setdefault("resume", copy.deepcopy(DEFAULT_CONFIG["resume"]))

    # 迁移旧版 AI 配置：如果 providers 为空但顶层有 api_key，自动迁移到 providers[0]
    ai = merged.get("ai", {})
    if not ai.get("providers") and ai.get("api_key"):
        ai["providers"] = [{
            "name": ai.get("name", "默认"),
            "api_key": ai.get("api_key", ""),
            "api_base": ai.get("api_base", "https://apihub.agnes-ai.com/v1"),
            "model": ai.get("model", "agnes-2.5-flash"),
            "timeout": 30,
        }]

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

    browser = cfg.get("browser", {})
    if isinstance(browser, dict):
        if not isinstance(browser.get("page_load_timeout", 30), (int, float)):
            errors.append("browser.page_load_timeout 必须是数字")

    rl = cfg.get("rate_limit", {})
    if isinstance(rl, dict):
        for k in ("max_per_hour", "max_per_day"):
            v = rl.get(k, 0)
            if not isinstance(v, (int, float)) or v < 0:
                errors.append(f"rate_limit.{k} 必须是非负数")

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
                "city": job.get("city", "上海"),
                "query": job.get("query", ""),
                "scroll_pages": job.get("scroll_pages", 5),
                "greeting_message": job.get("greeting_message", DEFAULT_GREETING),
                "cookie_file": acc.get("cookie_file", "zhipin_cookies.json"),
                "image_files": job.get("image_files", []),
                "message_interval_min": acc.get("message_interval_min", 3),
                "message_interval_max": acc.get("message_interval_max", 8),
                "browser": cfg.get("browser", {}),
                "login": cfg.get("login", {}),
                "rate_limit": cfg.get("rate_limit", {}),
                "retry": cfg.get("retry", {}),
                "ai": cfg.get("ai", {}),
                "resume": cfg.get("resume", {}),
            })
    return tasks
