"""多 AI 容灾链 — 支持多个 AI 接口自动切换

如果当前 AI 请求失败（超时、网络错误等），自动切换到下一个 AI 接口，
直到有一个成功或全部失败。
"""
import json
import os
import time
import hashlib
import threading
from typing import Optional, Callable

from urllib.request import Request, urlopen
from urllib.error import URLError

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ai_cache.json")

_cache_lock = threading.Lock()


def _load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            now = time.time()
            expired = [k for k, v in data.items() if v.get("_expires_at", 0) < now]
            for k in expired:
                del data[k]
            return data
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _make_cache_key(job_url: str, resume_hash: str) -> str:
    raw = f"{job_url}:{resume_hash}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class AIProviderConfig:
    """单个 AI 接口配置。"""

    def __init__(self, name: str, api_key: str, api_base: str, model: str, timeout: int = 30):
        self.name = name
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.timeout = timeout

    def is_valid(self) -> bool:
        return bool(self.api_key and self.api_base and self.model)


class AIAnalyzerChain:
    """多 AI 容灾链：按顺序尝试多个 AI 接口。"""

    def __init__(
        self,
        providers: list,
        match_threshold: int = 70,
        cache_enabled: bool = True,
        cache_ttl_hours: int = 24,
        log_callback: Optional[Callable] = None,
        prompts: Optional[dict] = None,
    ):
        # providers: list of AIProviderConfig or dict
        self.providers = []
        for p in providers:
            if isinstance(p, dict):
                self.providers.append(AIProviderConfig(
                    name=p.get("name", "AI"),
                    api_key=p.get("api_key", ""),
                    api_base=p.get("api_base", ""),
                    model=p.get("model", ""),
                    timeout=p.get("timeout", 30),
                ))
            elif isinstance(p, AIProviderConfig):
                self.providers.append(p)

        self.match_threshold = match_threshold
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl_hours * 3600
        self.log_cb = log_callback
        self._custom_prompts = prompts or {}

        self.analyzed_count = 0
        self.match_count = 0
        self.cache_hit_count = 0
        self._current_provider_idx = 0
        self._resume = None
        self._resume_hash = ""

    def _log(self, level: str, msg: str):
        if self.log_cb:
            self.log_cb(f"[AI] [{level}] {msg}")

    def set_resume(self, resume: dict):
        self._resume = resume
        self._resume_hash = hashlib.md5(
            json.dumps(resume, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def analyze_job(self, job: dict) -> dict:
        """分析单个岗位。依次尝试所有 provider，直到成功。"""
        if not self.providers:
            return {"score": 50, "is_match": True, "reason": "未配置 AI 接口", "suggested_greeting": ""}

        # 检查缓存
        if self.cache_enabled and self._resume_hash:
            cache_key = _make_cache_key(job.get("url", ""), self._resume_hash)
            cache = _load_cache()
            if cache_key in cache:
                self.cache_hit_count += 1
                self._log("INFO", f"缓存命中: {job.get('job_name', '')}")
                return cache[cache_key]["result"]

        # 依次尝试每个 provider
        prompt = self._build_prompt(job)
        last_error = None
        for idx, provider in enumerate(self.providers):
            if not provider.is_valid():
                self._log("WARN", f"AI 接口 '{provider.name}' 配置无效，跳过")
                continue
            try:
                self._log("INFO", f"通过 [{provider.name}] ({provider.model}) 分析...")
                result = self._call_provider_api(provider, prompt)
                self.analyzed_count += 1
                if result.get("is_match", False):
                    self.match_count += 1

                # 写入缓存
                if self.cache_enabled and self._resume_hash:
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
                last_error = e
                self._log("WARN", f"[{provider.name}] 失败: {e}，尝试下一个...")
                continue

        # 全部失败
        self._log("ERROR", f"所有 AI 接口均失败，最后错误: {last_error}")
        return {"score": 50, "is_match": True, "reason": f"AI 分析异常: {last_error}，默认通过", "suggested_greeting": ""}

    def _call_provider_api(self, provider: AIProviderConfig, messages: list) -> dict:
        """调用指定 AI 接口。"""
        url = f"{provider.api_base}/chat/completions"
        payload = json.dumps({
            "model": provider.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1024,
            "chat_template_kwargs": {"enable_thinking": True},
        }).encode("utf-8")

        req = Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {provider.api_key}")

        try:
            with urlopen(req, timeout=provider.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except URLError as e:
            raise Exception(f"API 请求失败: {e}")
        except TimeoutError:
            raise Exception(f"请求超时（{provider.timeout}s）")

        try:
            content = data["choices"][0]["message"]["content"]
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

    def _build_prompt(self, job: dict) -> list:
        resume = self._resume or {}
        custom_system = self._custom_prompts.get("system", "")
        custom_user = self._custom_prompts.get("user", "")

        system_msg = custom_system or (
            "你是 Boss直聘智能投递助手的岗位匹配分析专家。你的任务是分析招聘岗位与求职者简历的匹配程度，"
            "给出评分和详细理由。请按 JSON 格式返回结果。"
        )

        user_msg = custom_user or (
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

        # 如果自定义 user prompt 包含占位符，填充它们
        if custom_user:
            try:
                user_msg = custom_user.format(
                    job_name=job.get("job_name", ""),
                    salary=job.get("salary", ""),
                    description=job.get("description", ""),
                    requirements=job.get("requirements", ""),
                    company=job.get("company", ""),
                    school=resume.get("education", {}).get("school", ""),
                    major=resume.get("education", {}).get("major", ""),
                    degree=resume.get("education", {}).get("degree", ""),
                    skills=", ".join(resume.get("skills", [])),
                    experience=resume.get("experience", ""),
                    target_position=resume.get("target_position", ""),
                )
            except (KeyError, ValueError):
                pass

        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

    def set_prompts(self, prompts: dict):
        """设置自定义提示词。"""
        self._custom_prompts = prompts or {}

    def clear_cache(self):
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)

    def get_stats(self) -> dict:
        return {
            "analyzed": self.analyzed_count,
            "matched": self.match_count,
            "cache_hits": self.cache_hit_count,
            "match_rate": round(self.match_count / max(self.analyzed_count, 1) * 100, 1),
            "threshold": self.match_threshold,
            "providers_total": len(self.providers),
            "providers_valid": sum(1 for p in self.providers if p.is_valid()),
        }
