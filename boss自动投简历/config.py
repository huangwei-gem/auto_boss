"""
配置管理模块

职责：
- 加载/保存扁平化的单账号配置
- 校验
"""
import json
import os

CONFIG_FILE = "bot_config.json"

DEFAULT_CONFIG = {
    "city": "上海",
    "job_query": "数据分析",
    "scroll_pages": 5,
    "message_interval_min": 3,
    "message_interval_max": 8,
    "greeting_message": (
        "您好，我是双一流的本科，应聘数据分析岗位。"
        "在校系统学习数据分析相关知识，掌握Excel、基础SQL与数据整理技能，"
        "具备数据思维。做事严谨细心，学习能力强，愿意踏实积累。"
        "十分认可贵公司，希望能获得面试机会。"
    ),
    "image_files": [
        "数据分析看板/看板1.png",
        "数据分析看板/看板2.png",
        "数据分析看板/看板3.png",
    ],
}


def load_config() -> dict:
    """加载配置文件，缺失字段用默认值补充。"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 合并：用 saved 覆盖 DEFAULT_CONFIG
            cfg = {**DEFAULT_CONFIG, **saved}
            return cfg
        except (json.JSONDecodeError, OSError):
            pass
    return reset_config()


def save_config(cfg: dict) -> None:
    """保存配置到文件。"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def reset_config() -> dict:
    """重置为默认配置并保存。"""
    save_config(DEFAULT_CONFIG.copy())
    return DEFAULT_CONFIG.copy()


def validate_config(cfg: dict) -> list[str]:
    """校验配置，返回错误信息列表（空列表代表无错误）。"""
    errors = []
    if not cfg.get("city", "").strip():
        errors.append("城市不能为空")
    if not cfg.get("job_query", "").strip():
        errors.append("岗位关键词不能为空")
    if cfg.get("scroll_pages", 5) < 1:
        errors.append("滚动页数至少为 1")
    min_iv = cfg.get("message_interval_min", 3)
    max_iv = cfg.get("message_interval_max", 8)
    if min_iv < 1:
        errors.append("最小发送间隔不能小于 1 秒")
    if max_iv < min_iv:
        errors.append("最大发送间隔不能小于最小发送间隔")
    if not cfg.get("greeting_message", "").strip():
        errors.append("打招呼语不能为空")
    return errors
