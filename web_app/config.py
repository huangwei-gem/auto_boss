"""配置管理 — 移植自原桌面版 config.py"""
import json
import os

# 配置在 web_app 下，实际指向项目根目录的 bot_config.json
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "boss自动投简历", "bot_config.json")

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
    """加载配置，缺失字段用默认值补充。"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return {**DEFAULT_CONFIG, **saved}
        except (json.JSONDecodeError, OSError):
            pass
    return {**DEFAULT_CONFIG}


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def validate_config(cfg: dict) -> list[str]:
    """校验配置，返回错误信息列表。"""
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
