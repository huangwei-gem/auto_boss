"""配置管理 — 多岗位多账号版（全面设置）

完整配置结构：

全局级:
  browser:
    headless: false          # 是否无头模式
    window_width: 1280       # 浏览器窗口宽度
    window_height: 800       # 浏览器窗口高度
    executable_path: ""      # 自定义 Chrome 路径（空=自动查找）
    user_data_dir: ""        # 用户数据目录（空=临时目录）
  anti_detection:
    user_agent: ""           # 自定义 UA（空=随机）
    max_retries: 3
    retry_base_delay: 2.0
    operation_timeout: 10    # 元素等待超时（秒）
    page_load_timeout: 30    # 页面加载超时（秒）
  rate_limit:
    max_applies_per_hour: 30
    max_applies_per_day: 100
  screenshot:
    enabled: true            # 是否向前端发送截图（关掉可省资源）
    interval: 3.0            # 截图间隔（秒）

账号级（每个账号）:
  name, enabled, cookie_file, image_files,
  message_interval_min, message_interval_max,
  jobs: [...]

岗位级（每个岗位）:
  enabled, city, query, scroll_pages, greeting_message,
  min_salary: 0              # 最低薪资过滤（0=不限）
  max_salary: 0              # 最高薪资过滤（0=不限）
  experience: ""             # 经验要求过滤
  education: ""              # 学历要求过滤
  exclude_companies: []      # 排除公司关键词
  include_keywords: []       # 附加匹配关键词
"""
import json
import os
import copy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "bot_config.json")

DEFAULT_CONFIG = {
    # ── 浏览器设置 ──
    "browser": {
        "headless": False,
        "window_width": 1280,
        "window_height": 800,
        "executable_path": "",
        "user_data_dir": "",
    },
    # ── 反检测设置 ──
    "anti_detection": {
        "user_agent": "",
        "max_retries": 3,
        "retry_base_delay": 2.0,
        "operation_timeout": 10,
        "page_load_timeout": 30,
    },
    # ── 频率限制 ──
    "rate_limit": {
        "max_applies_per_hour": 30,
        "max_applies_per_day": 100,
    },
    # ── 截图设置 ──
    "screenshot": {
        "enabled": True,
        "interval": 3.0,
    },
    # ── 账号列表 ──
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
                    "greeting_message": (
                        "您好，我是双一流的本科，应聘数据分析岗位。"
                        "在校系统学习数据分析相关知识，掌握Excel、基础SQL与数据整理技能，"
                        "具备数据思维。做事严谨细心，学习能力强，愿意踏实积累。"
                        "十分认可贵公司，希望能获得面试机会。"
                    ),
                    "min_salary": 0,
                    "max_salary": 0,
                    "experience": "",
                    "education": "",
                    "exclude_companies": [],
                    "include_keywords": [],
                }
            ],
        }
    ],
}


def _migrate_old_config(old: dict) -> dict:
    """将旧版单岗位配置迁移到新版格式。"""
    new = copy.deepcopy(DEFAULT_CONFIG)
    job = new["accounts"][0]["jobs"][0]
    job["city"] = old.get("city", "上海")
    job["query"] = old.get("job_query", "数据分析")
    job["scroll_pages"] = old.get("scroll_pages", 5)
    job["greeting_message"] = old.get("greeting_message", "")
    acct = new["accounts"][0]
    acct["image_files"] = old.get("image_files", [])
    acct["message_interval_min"] = old.get("message_interval_min", 3)
    acct["message_interval_max"] = old.get("message_interval_max", 8)
    return new


def load_config() -> dict:
    """加载配置，自动迁移旧版格式。"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 检测旧版格式（有 job_query 但没有 accounts）
            if "job_query" in saved and "accounts" not in saved:
                saved = _migrate_old_config(saved)
                save_config(saved)
            return _deep_defaults(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return copy.deepcopy(DEFAULT_CONFIG)


def _deep_defaults(cfg: dict) -> dict:
    """用默认值补充缺失的嵌套字段（保留顶层全局设置）。"""
    result = copy.deepcopy(DEFAULT_CONFIG)

    # 合并全局设置
    for section in ("browser", "anti_detection", "rate_limit", "screenshot"):
        if section in cfg and isinstance(cfg[section], dict):
            result[section].update(cfg[section])

    # 合并 accounts
    if "accounts" in cfg and cfg["accounts"]:
        result["accounts"] = []
        for i, acct in enumerate(cfg["accounts"]):
            default_acct = copy.deepcopy(DEFAULT_CONFIG["accounts"][0])
            # 复制顶层账号字段
            for k in default_acct:
                if k == "jobs":
                    continue
                if k in acct:
                    default_acct[k] = acct[k]
            # 合并 jobs
            if "jobs" in acct and acct["jobs"]:
                default_job = copy.deepcopy(DEFAULT_CONFIG["accounts"][0]["jobs"][0])
                merged_jobs = []
                for job in acct["jobs"]:
                    mj = copy.deepcopy(default_job)
                    for k in mj:
                        if k in job:
                            mj[k] = job[k]
                    merged_jobs.append(mj)
                default_acct["jobs"] = merged_jobs
            result["accounts"].append(default_acct)

    return result


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def validate_config(cfg: dict) -> list[str]:
    """校验配置，返回错误信息列表。"""
    errors = []
    accounts = cfg.get("accounts", [])
    if not accounts:
        errors.append("至少需要一个账号配置")
        return errors

    for i, acct in enumerate(accounts):
        jobs = acct.get("jobs", [])
        if not jobs:
            errors.append(f"账号「{acct.get('name', f'账号{i+1}')}」至少需要一个岗位")
        for j, job in enumerate(jobs):
            name = f"账号「{acct.get('name', f'账号{i+1}')}」/岗位{j+1}"
            if not job.get("city", "").strip():
                errors.append(f"{name}：城市不能为空")
            if not job.get("query", "").strip():
                errors.append(f"{name}：岗位关键词不能为空")
            if job.get("scroll_pages", 5) < 1:
                errors.append(f"{name}：滚动页数至少为 1")
            if not job.get("greeting_message", "").strip():
                errors.append(f"{name}：打招呼语不能为空")
        min_iv = acct.get("message_interval_min", 3)
        max_iv = acct.get("message_interval_max", 8)
        if min_iv < 1:
            errors.append(f"账号「{acct.get('name', f'账号{i+1}')}」：最小发送间隔不能小于 1 秒")
        if max_iv < min_iv:
            errors.append(f"账号「{acct.get('name', f'账号{i+1}')}」：最大发送间隔不能小于最小发送间隔")

    # 全局校验
    rl = cfg.get("rate_limit", {})
    if rl.get("max_applies_per_hour", 30) < 1:
        errors.append("每小时最多投递数不能小于 1")
    if rl.get("max_applies_per_day", 100) < 1:
        errors.append("每天最多投递数不能小于 1")

    return errors


def flatten_jobs_for_run(cfg: dict) -> list[dict]:
    """展开为扁平的任务列表，携带所有全局和账号级参数。"""
    tasks = []
    for ai, acct in enumerate(cfg.get("accounts", [])):
        if not acct.get("enabled", True):
            continue
        for ji, job in enumerate(acct.get("jobs", [])):
            if not job.get("enabled", True):
                continue
            tasks.append({
                "account_index": ai,
                "job_index": ji,
                "account_name": acct.get("name", f"账号{ai+1}"),
                "city": job.get("city", ""),
                "query": job.get("query", ""),
                "scroll_pages": job.get("scroll_pages", 5),
                "greeting_message": job.get("greeting_message", ""),
                "cookie_file": acct.get("cookie_file", "zhipin_cookies.json"),
                "image_files": acct.get("image_files", []),
                "message_interval_min": acct.get("message_interval_min", 3),
                "message_interval_max": acct.get("message_interval_max", 8),
                # 岗位额外过滤条件
                "min_salary": job.get("min_salary", 0),
                "max_salary": job.get("max_salary", 0),
                "experience": job.get("experience", ""),
                "education": job.get("education", ""),
                "exclude_companies": job.get("exclude_companies", []),
                "include_keywords": job.get("include_keywords", []),
                # 全局设置（每个任务携带一份）
                "browser": cfg.get("browser", DEFAULT_CONFIG["browser"]),
                "anti_detection": cfg.get("anti_detection", DEFAULT_CONFIG["anti_detection"]),
                "rate_limit": cfg.get("rate_limit", DEFAULT_CONFIG["rate_limit"]),
                "screenshot": cfg.get("screenshot", DEFAULT_CONFIG["screenshot"]),
            })
    return tasks
