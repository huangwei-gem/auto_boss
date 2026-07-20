"""配置加载/保存/重置 — 支持多账号多岗位 + 旧单账号格式自动迁移。"""

import json
import os

CONFIG_FILE = "bot_config.json"

DEFAULT_CONFIG = {
    "accounts": [
        {
            "id": "account_1",
            "name": "默认账号",
            "city": "上海",
            "jobs": [{"query": "数据分析", "scroll_pages": 5}],
            "greeting_message": (
                "您好，我是双一流的本科，应聘数据分析岗位。"
                "在校系统学习数据分析相关知识，掌握Excel、基础SQL与数据整理技能，"
                "具备数据思维。做事严谨细心，学习能力强，愿意踏实积累。"
                "十分认可贵公司，希望能获得面试机会。"
            ),
            "image_files": [],
            "cookies_file": "",
        }
    ],
    "message_interval_min": 3,
    "message_interval_max": 8,
    "global_scroll_pages": 5,
}


def _migrate_old_schema(cfg: dict) -> dict:
    """将旧单账号/单岗位/单账号旧字段配置迁移到多账号格式。"""
    if cfg.get("accounts") and isinstance(cfg["accounts"], list) and len(cfg["accounts"]) > 0:
        if isinstance(cfg["accounts"][0], dict) and "id" in cfg["accounts"][0]:
            return cfg
    new_cfg = {**cfg}
    old_keys = ["city", "job_query", "greeting_message", "image_files", "scroll_pages"]
    # 处理单账号旧格式
    if any(k in new_cfg for k in old_keys):
        new_cfg["accounts"] = [
            {
                "id": "account_1",
                "name": "默认账号",
                "city": new_cfg.pop("city", "上海"),
                "jobs": [
                    {
                        "query": new_cfg.pop("job_query", "数据分析"),
                        "scroll_pages": new_cfg.pop("scroll_pages", 5),
                    }
                ],
                "greeting_message": new_cfg.pop(
                    "greeting_message", DEFAULT_CONFIG["accounts"][0]["greeting_message"]
                ),
                "image_files": new_cfg.pop("image_files", []),
                "cookies_file": "",
            }
        ]
    # 处理 accounts 列表但缺少 id 的情况
    elif cfg.get("accounts") and isinstance(cfg["accounts"], list):
        for i, acc in enumerate(cfg["accounts"]):
            if "id" not in acc:
                acc["id"] = f"account_{i + 1}"
            if "jobs" not in acc:
                acc["jobs"] = [{"query": acc.pop("job_query", "数据分析"),
                                "scroll_pages": acc.pop("scroll_pages", 5)}]
    else:
        new_cfg.setdefault("accounts", DEFAULT_CONFIG["accounts"])

    return new_cfg


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg = {**DEFAULT_CONFIG, **saved}
            cfg = _migrate_old_schema(cfg)
            return cfg
        except (json.JSONDecodeError, OSError):
            pass
    return reset_config()


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def reset_config() -> dict:
    save_config(DEFAULT_CONFIG.copy())
    return DEFAULT_CONFIG.copy()
