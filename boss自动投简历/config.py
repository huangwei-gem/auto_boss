import json
import os

CONFIG_FILE = "bot_config.json"

DEFAULT_CONFIG = {
    "accounts": [
        {
            "id": "account_1",
            "name": "账号1",
            "city": "上海",
            "jobs": [
                {"query": "数据分析", "scroll_pages": 5}
            ],
            "greeting_message": (
                "您好，我是双一流的本科，应聘数据分析岗位。"
                "在校系统学习数据分析相关知识，掌握Excel、基础SQL与数据整理技能，"
                "具备数据思维。做事严谨细心，学习能力强，愿意踏实积累。"
                "十分认可贵公司，希望能获得面试机会。"
            ),
            "image_files": []
        }
    ],
    "message_interval_min": 3,
    "message_interval_max": 8,
    "global_scroll_pages": 5
}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg = {**DEFAULT_CONFIG, **saved}
            # Ensure accounts is always a list
            if "accounts" not in cfg or not isinstance(cfg["accounts"], list):
                cfg["accounts"] = DEFAULT_CONFIG["accounts"]
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


def validate_image_files(paths: list) -> list:
    result = []
    for p in paths:
        if os.path.isfile(p):
            result.append(p)
        else:
            result.append(p)
    return result
