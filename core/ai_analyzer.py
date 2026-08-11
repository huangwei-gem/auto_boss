"""
AI 智能解析引擎 — 调用 Agnes API 进行岗位匹配分析

职责：
- 调用 Agnes 2.5 Flash API 分析岗位描述与简历的匹配度
- 缓存分析结果，避免重复请求
- 支持批量分析和流式处理
"""
import json
import os
import time
import hashlib
import threading
from typing import Optional, Callable
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── 常量 ──

CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web_app", "ai_cache.json")
DEFAULT_API_BASE = "https://apihub.agnes-ai.com/v1"
DEFAULT_MODEL = "agnes-2.5-flash"
DEFAULT_THRESHOLD = 70

# ── 缓存管理 ──

_cache_lock = threading.Lock()


def _load_cache() -> dict:
    """加载 AI 分析缓存。"""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 清理过期缓存
            now = time.time()
            expired = [k for k, v in data.items() if v.get("_expires_at", 0) < now]
            for k in expired:
                del data[k]
            return data
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict):
    """保存 AI 分析缓存。"""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _make_cache_key(job_url: str, resume_hash: str) -> str:
    """生成缓存 key（基于岗位 URL + 简历摘要）。"""
    raw = f"{job_url}:{resume_hash}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ── AI 分析器 ──

class AIAnalyzer:
    """AI 岗位匹配分析器。"""

    def __init__(
        self,
        api_key: str = "",
        api_base: str = DEFAULT_API_BASE,
        model: str = DEFAULT_MODEL,
        match_threshold: int = DEFAULT_THRESHOLD,
        cache_enabled: bool = True,
        cache_ttl_hours: int = 24,
        log_callback: Optional[Callable] = None,
    ):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.match_threshold = match_threshold
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl_hours * 3600
        self.log_cb = log_callback

        # 统计
        self.analyzed_count = 0
        self.match_count = 0
        self.cache_hit_count = 0

    def _log(self, level: str, msg: str):
        if self.log_cb:
            self.log_cb(f"[AI] [{level}] {msg}")

    def set_resume(self, resume: dict):
        """设置简历信息。"""
        self._resume = resume
        self._resume_hash = hashlib.md5(
            json.dumps(resume, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def analyze_job(self, job: dict) -> dict:
        """分析单个岗位与简历的匹配度。

        Args:
            job: 岗位信息字典，包含 job_name, salary, description, requirements, company, url

        Returns:
            匹配结果字典，包含 score, is_match, reason, strengths, weaknesses, suggested_greeting
        """
        if not self.api_key:
            self._log("WARN", "API Key 未配置，跳过 AI 分析")
            return {"score": 50, "is_match": True, "reason": "AI 未配置，默认通过", "suggested_greeting": ""}

        # 检查缓存
        if self.cache_enabled and hasattr(self, "_resume_hash"):
            cache_key = _make_cache_key(job.get("url", ""), self._resume_hash)
            cache = _load_cache()
            if cache_key in cache:
                self.cache_hit_count += 1
                self._log("INFO", f"缓存命中: {job.get('job_name', '')}")
                return cache[cache_key]["result"]

        # 构建 prompt
        prompt = self._build_prompt(job)

        # 调用 API
        try:
            result = self._call_api(prompt)
            self.analyzed_count += 1

            if result.get("is_match", False):
                self.match_count += 1

            # 写入缓存
            if self.cache_enabled and hasattr(self, "_resume_hash"):
                cache_key = _make_cache_key(job.get("url", ""), self._resume_hash)
                cache = _load_cache()
                cache[cache_key] = {
                    "result": result,
                    "cached_at": time.time(),
                    "_expires_at": time.time() + self.cache_ttl,
                }
                _save_cache(cache)

            return result

        except Exception as e:
            self._log("ERROR", f"AI 分析失败: {e}")
            return {"score": 50, "is_match": True, "reason": f"AI 分析异常: {e}，默认通过", "suggested_greeting": ""}

    def analyze_batch(self, jobs: list, progress_cb: Optional[Callable] = None) -> list:
        """批量分析岗位。

        Args:
            jobs: 岗位列表
            progress_cb: 进度回调，接收 (current, total, result)

        Returns:
            匹配结果列表
        """
        results = []
        total = len(jobs)
        for i, job in enumerate(jobs):
            result = self.analyze_job(job)
            results.append(result)
            if progress_cb:
                progress_cb(i + 1, total, result)
        return results

    def _build_prompt(self, job: dict) -> list:
        """构建分析 prompt。"""
        resume = getattr(self, "_resume", {})

        system_msg = (
            "你是 Boss直聘智能投递助手的岗位匹配分析专家。你的任务是分析招聘岗位与求职者简历的匹配程度，"
            "给出评分和详细理由。请按 JSON 格式返回结果。"
        )

        user_msg = (
            "【求职者简历】\n"
            f"教育背景：{resume.get('education', {}).get('school', '')} "
            f"{resume.get('education', {}).get('major', '')} "
            f"{resume.get('education', {}).get('degree', '')}\n"
            f"技能：{', '.join(resume.get('skills', []))}\n"
            f"工作经验：{resume.get('experience', '')}\n"
            f"求职意向：{resume.get('target_position', '')}\n\n"
            "【招聘岗位】\n"
            f"岗位名称：{job.get('job_name', '')}\n"
            f"薪资：{job.get('salary', '')}\n"
            f"岗位描述：{job.get('description', '')}\n"
            f"任职要求：{job.get('requirements', '')}\n"
            f"公司：{job.get('company', '')}\n\n"
            "请分析匹配度，按以下 JSON 格式返回（不要包含其他内容）：\n"
            '{\n  "score": 0-100,\n  "is_match": true/false,\n'
            '  "reason": "匹配分析简要说明",\n'
            '  "strengths": ["优势1", "优势2"],\n'
            '  "weaknesses": ["劣势1", "劣势2"],\n'
            '  "suggested_greeting": "基于岗位要求生成的个性化打招呼消息"\n}'
        )

        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

    def _call_api(self, messages: list) -> dict:
        """调用 Agnes API。"""
        url = f"{self.api_base}/chat/completions"
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1024,
            "chat_template_kwargs": {"enable_thinking": True},
        }).encode("utf-8")

        req = Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")

        self._log("INFO", "正在调用 AI 分析...")
        try:
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except URLError as e:
            raise Exception(f"API 请求失败: {e}")

        # 解析响应
        try:
            content = data["choices"][0]["message"]["content"]
            # 提取 JSON 部分
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(content[json_start:json_end])
                return result
            else:
                raise ValueError("响应中未找到 JSON")
        except (KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
            self._log("WARN", f"解析 AI 响应失败: {e}")
            return {"score": 50, "is_match": True, "reason": "解析失败，默认通过"}

    def clear_cache(self):
        """清空分析缓存。"""
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        self._log("INFO", "AI 分析缓存已清空")

    def get_stats(self) -> dict:
        """获取分析统计。"""
        return {
            "analyzed": self.analyzed_count,
            "matched": self.match_count,
            "cache_hits": self.cache_hit_count,
            "match_rate": round(self.match_count / max(self.analyzed_count, 1) * 100, 1),
            "threshold": self.match_threshold,
        }
