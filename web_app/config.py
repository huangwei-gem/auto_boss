"""配置管理 — 多岗位多账号版

新格式：
{
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

# 配置在 web_app 下
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "bot_config.json")

DEFAULT_CONFIG = {
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
                    "query": "数据分析",
                    "scroll_pages": 5,
                    "greeting_message": (
                        "您好，我是双一流的本科，应聘数据分析岗位。"
                        "在校系统学习数据分析相关知识，掌握Excel、基础SQL与数据整理技能，"
                        "具备数据思维。做事严谨细心，学习能力强，愿意踏实积累。"
                        "十分认可贵公司，希望能获得面试机会。"
                    ),
                }
            ],
        }
    ]
}


def _migrate_old_config(old: dict) -> dict:
    """将旧版单岗位配置迁移到新版多账号格式。"""
    new = {"accounts": []}
    job = {
        "enabled": True,
        "city": old.get("city", "上海"),
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
    """加载配置，自动迁移旧版格式。"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 检测旧版格式（有 job_query 但没有 accounts）
            if "job_query" in saved and "accounts" not in saved:
                saved = _migrate_old_config(saved)
                # 保存迁移后的配置
                save_config(saved)
            return _deep_defaults(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return copy.deepcopy(DEFAULT_CONFIG)


def _deep_defaults(cfg: dict) -> dict:
    """用默认值补充缺失的嵌套字段。"""
    result = copy.deepcopy(DEFAULT_CONFIG)

    if "accounts" not in cfg or not cfg["accounts"]:
        return result

    result["accounts"] = []
    for i, acct in enumerate(cfg["accounts"]):
        default_acct = copy.deepcopy(DEFAULT_CONFIG["accounts"][0])
        for k in default_acct:
            if k == "jobs":
                continue
            if k in acct:
                default_acct[k] = acct[k]
        # 合并 jobs
        if "jobs" in acct and acct["jobs"]:
            default_job = copy.deepcopy(DEFAULT_CONFIG["accounts"][0]["jobs"][0])
            merged_jobs = []
            for j, job in enumerate(acct["jobs"]):
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

    return errors


def flatten_jobs_for_run(cfg: dict) -> list[dict]:
    """展开为扁平的任务列表：[{account_index, job_index, account_name, ...}, ...]"""
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
            })
    return tasks
