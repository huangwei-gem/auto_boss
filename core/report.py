"""AI 投递周报 — 聚合投递/值守日志并生成中文周报正文。

读取 web_app/chats_log.json 与 reply_log.json，按天聚合指标，
再调用 AI 生成 300 字以内的周报。旧版日志头部混有纯 URL 字符串，
聚合时只保留 dict 条目。
"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from ai_analyzer import AIAnalyzer, DEFAULT_API_BASE, DEFAULT_MODEL

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def _resolve_log(fname: str) -> str:
    for base in (os.path.join(_BASE_DIR, "web_app"), _BASE_DIR):
        p = os.path.join(base, fname)
        if os.path.exists(p):
            return p
    return os.path.join(_BASE_DIR, "web_app", fname)


def _parse_time(t_str) -> Optional[datetime]:
    if not isinstance(t_str, str):
        return None
    s = t_str.strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _load_entries(fname: str, since: datetime, until: datetime) -> list:
    path = _resolve_log(fname)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for e in data:
        if not isinstance(e, dict):
            continue
        t = _parse_time(e.get("time"))
        if t and since <= t <= until:
            out.append(e)
    return out


def aggregate_weekly_stats(days: int = 7) -> dict:
    """聚合最近 days 天的投递/值守统计。"""
    until = datetime.now()
    since = until - timedelta(days=days)
    chats = _load_entries("chats_log.json", since, until)
    replies = _load_entries("reply_log.json", since, until)

    applied = 0
    skipped = 0
    skip_reasons = {}
    scores = []
    hr_active = 0
    daily = {}
    for e in chats:
        day = (e.get("time") or "")[:10]
        if day:
            daily[day] = daily.get(day, 0) + 1
        score = e.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            scores.append(score)
        if e.get("hr_active"):
            hr_active += 1
        if e.get("skipped"):
            skipped += 1
            reason = e.get("skip_reason") or "unknown"
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
        else:
            applied += 1

    top_skip = sorted(skip_reasons.items(), key=lambda x: x[1], reverse=True)
    daily_trend = [{"date": d, "count": daily[d]} for d in sorted(daily)]

    return {
        "period": f"{since:%Y-%m-%d} ~ {until:%Y-%m-%d}",
        "days": days,
        "total": len(chats),
        "applied": applied,
        "skipped": skipped,
        "skip_reasons": [{"reason": k, "count": v} for k, v in top_skip],
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "hr_active": hr_active,
        "daily_trend": daily_trend,
        "reply_total": len(replies),
        "reply_sent": sum(1 for r in replies if r.get("sent")),
    }


def _build_report_prompt(stats: dict) -> list:
    reasons = stats.get("skip_reasons") or []
    reason_lines = "\n".join(f"- {r['reason']}: {r['count']} 次" for r in reasons) or "- 无"
    trend = stats.get("daily_trend") or []
    trend_lines = "\n".join(f"- {t['date']}: {t['count']} 条" for t in trend) or "- 无数据"
    avg_score = stats.get("avg_score")
    user_msg = (
        f"统计周期：{stats['period']}（共 {stats['days']} 天）\n"
        f"投递日志条目：{stats['total']}\n"
        f"成功投递：{stats['applied']}\n"
        f"已跳过：{stats['skipped']}\n"
        f"跳过原因分布：\n{reason_lines}\n"
        f"平均匹配分：{avg_score if avg_score is not None else '无数据'}\n"
        f"检测到活跃 HR 次数：{stats['hr_active']}\n"
        f"每日投递趋势：\n{trend_lines}\n"
        f"AI 值守回复：总 {stats['reply_total']}，已发送 {stats['reply_sent']}"
    )
    system_msg = (
        "你是 Boss直聘自动投递助手的投递数据分析专家。请根据提供的统计数字，"
        "用中文写一份简洁周报，300 字以内，内容包含：总体表现、亮点、需要注意的问题、下周改进建议。"
        "语气积极客观，直接输出正文，不要 markdown 标题、不要列表符号、不要客套开场白。"
    )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def generate_report_text(stats: dict, api_cfg: dict, log_callback=None) -> str:
    """生成 AI 周报正文；未配置 API Key 或调用失败返回空串。"""
    api_key = (api_cfg or {}).get("api_key", "")
    if not api_key:
        return ""
    analyzer = AIAnalyzer(
        api_key=api_key,
        api_base=api_cfg.get("api_base") or DEFAULT_API_BASE,
        model=api_cfg.get("model") or DEFAULT_MODEL,
        cache_enabled=False,
        log_callback=log_callback,
    )
    messages = _build_report_prompt(stats)
    text = analyzer._call_api_text(messages, "生成 AI 投递周报...")
    return (text or "").strip()
