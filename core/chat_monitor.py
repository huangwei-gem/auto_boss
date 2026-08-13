"""
AI 值守监听模块 — 监听 HR 新消息并生成回复（人工确认后发送）

职责：
- 常驻监听 Boss 会话页，检测 HR 新消息
- 结合岗位要求与简历，用 AI 生成合适回复
- 推送到 Web UI 待用户确认后发送（或开启自动回复直接发送）
- 记录回复日志 reply_log.json

检测策略（两层，选择器/接口匹配字串收拢为常量，可按实机调整）：
- 层 A：dp.listen 嗅探会话/消息接口响应（仿 bot_core 的城市数据捕获）
- 层 B：解析会话页 DOM 气泡文本（用「已处理内容 set」去重）

注意：Boss 会话页的 DOM/接口选择器无法离线确定，初始值为最佳猜测。
monitor.debug_capture=true 时会把会话页 HTML 存盘，便于实机校准后调整常量。
"""
import json
import os
import queue
import time
import uuid
from typing import Optional

from DrissionPage.errors import PageDisconnectedError

from bot_core import BotCore

# ── 常量（需实机校准） ──

CHAT_LIST_URL = "https://www.zhipin.com/web/geek/chat"

# 层 A：网络包 URL 关键字（命中才解析消息内容）
CHAT_API_KEYWORDS = ("wapi/zpgeek/friend", "friend", "message", "contact", "msg", "chat")

# 层 B：消息气泡 / 会话行 / 会话头信息的候选选择器（2026-08-13 依据真实 DOM 校准）
MSG_SELECTORS = [
    "li.message-item.item-friend .text-content",   # 仅 HR(对方) 发的消息文本
]
CONV_ROW_SELECTORS = [
    ".friend-content-warp",                        # 会话列表行（li.friend-content-warp）
]
CONV_META_SELECTORS = {
    "job_name": [".position-name"],                                    # 会话顶部岗位名
    "company": [".friend-content .name-box span:nth-child(2)"],        # 会话列表行公司名
    "chat_name": [".friend-content .name-text"],                       # 会话列表行 HR 名
}

REPLY_LOG_FILE = "reply_log.json"


def _norm(text: str) -> str:
    """消息去重用：去空白/换行，折叠空格。"""
    return "".join(str(text).split())


class ChatMonitor(BotCore):
    """Boss 值守监听器。继承 BotCore 复用浏览器初始化/登录/发送逻辑。

    socket 线程只通过 self._user_actions 入队（send/skip），浏览器操作全部
    由本类的监听线程串行执行，避免并发操作 dp。
    """

    def __init__(self, config: dict, log_callback=None, emit_callback=None, sid: str = None):
        super().__init__(config=config, log_callback=log_callback)
        self.emit_cb = emit_callback
        self.sid = sid
        self._seen_messages = set()      # 已处理过的消息内容（去重）
        self._sent_texts = set()         # 本会话已发送的文本（避免把自己发的当新消息）
        self._pending = {}               # event_id -> {conv, hr_message, reply}
        self._user_actions = queue.Queue()  # {"type":"send"|"skip", "event_id":..., "reply_text":...}
        self._auto_reply = False
        self._poll_interval = 15.0
        self._max_per_cycle = 5
        self._debug_capture = False
        self._debug_capture_counter = 0

    # ── 对外接口（socket 线程调用） ──

    def enqueue_send(self, event_id: str, reply_text: str):
        self._user_actions.put({"type": "send", "event_id": event_id, "reply_text": reply_text})

    def enqueue_skip(self, event_id: str):
        self._user_actions.put({"type": "skip", "event_id": event_id})

    def _emit(self, event: str, data: dict):
        if self.emit_cb:
            try:
                self.emit_cb(event, data)
            except Exception:
                pass

    # ── 主循环 ──

    def run_monitor(self):
        self.running = True
        try:
            if not self._init_browser():
                return
            if not self._check_and_handle_login():
                return

            m_cfg = self.config.get("monitor", {}) or {}
            self._auto_reply = bool(m_cfg.get("auto_reply", False))
            self._poll_interval = max(3.0, float(m_cfg.get("poll_interval_sec", 15)))
            self._max_per_cycle = max(1, int(m_cfg.get("max_messages_per_cycle", 5)))
            self._debug_capture = bool(m_cfg.get("debug_capture", (self.config.get("debug") or {}).get("capture", False)))

            self._log("INFO", f"正在打开会话列表: {CHAT_LIST_URL}")
            self.dp.get(CHAT_LIST_URL)
            self._random_delay(3, 5)
            try:
                self.dp.listen.start()
            except Exception as e:
                self._log("WARN", f"网络监听启动失败（将用 DOM 兜底）: {e}")

            # 建立消息基线：忽略当前已有的历史消息，只推之后的真正新消息
            self._log("INFO", "正在建立消息基线（忽略当前已有消息）...")
            try:
                baseline = self._scan_conversations()
                self._log("INFO", f"基线完成，共忽略 {len(baseline)} 条现有消息")
            except Exception as e:
                self._log("WARN", f"建立基线异常（继续）: {e}")

            self._log("SUCCESS", "🤖 AI 值守已启动，正在监听 HR 新消息...")
            self._emit("monitor_status", {"running": True})

            while self.running:
                try:
                    self._drain_user_actions()
                    new_msgs = self._scan_conversations()
                    processed = 0
                    for item in new_msgs:
                        if not self.running:
                            break
                        if processed >= self._max_per_cycle:
                            self._log("INFO", "本轮已达处理上限，剩余下轮处理")
                            break
                        self._handle_new_message(item)
                        processed += 1
                    if self._debug_capture and self._debug_capture_counter < 2:
                        self._dump_chat_page()
                        self._debug_capture_counter += 1
                except PageDisconnectedError:
                    self._log("WARN", "值守轮询中页面断开，尝试恢复...")
                    if not self._handle_disconnect():
                        self._log("ERROR", "无法恢复连接，值守退出")
                        break
                except Exception as e:
                    self._log("WARN", f"值守轮询异常: {e}")
                    import traceback
                    self._log("WARN", traceback.format_exc())
                self._sleep_slices(self._poll_interval)
        except Exception as e:
            self._log("ERROR", f"值守异常退出: {e}")
            import traceback
            self._log("ERROR", traceback.format_exc())
        finally:
            self.running = False
            self._emit("monitor_status", {"running": False})
            if self.dp:
                try:
                    self.dp.quit()
                except Exception:
                    pass

    def _sleep_slices(self, seconds: float):
        """分片休眠，能及时响应 stop。"""
        end = time.time() + seconds
        while self.running and time.time() < end:
            time.sleep(1)

    # ── 新消息检测 ──

    def _scan_conversations(self) -> list:
        """扫描新 HR 消息，返回 [{"message","conv","source"}, ...]（已去重）。"""
        out = []
        # 层 A：网络接口嗅探
        try:
            for packet in self.dp.listen.steps(timeout=0.3):
                self._handle_packet(packet, out)
        except Exception as e:
            self._log("WARN", f"网络监听读取异常: {e}")
        # 层 B：DOM 兜底
        try:
            out.extend(self._scan_dom_messages())
        except Exception as e:
            self._log("WARN", f"DOM 扫描异常: {e}")
        return out

    def _handle_packet(self, packet, out: list):
        url = getattr(packet, "url", "") or ""
        if not any(k in url for k in CHAT_API_KEYWORDS):
            return
        body = None
        try:
            res = getattr(packet, "response", None)
            body = getattr(res, "body", None)
        except Exception:
            return
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                return
        if isinstance(body, dict):
            self._extract_json_messages(body, out)

    def _extract_json_messages(self, obj, out: list):
        """从接口 JSON 里递归找出像消息文本的字段（宽松匹配，需实机校准）。"""
        hits = []
        conv_meta = {}

        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    kl = k.lower()
                    if isinstance(v, str) and len(v.strip()) >= 2 and any(
                        kw in kl for kw in ("content", "message", "msg", "text")
                    ):
                        hits.append(v.strip())
                    elif isinstance(v, (dict, list)):
                        walk(v)
            elif isinstance(o, list):
                for it in o:
                    walk(it)

        walk(obj)
        for content in hits:
            key = _norm(content)
            if key in self._seen_messages:
                continue
            self._seen_messages.add(key)
            out.append({"message": content, "conv": conv_meta, "source": "api"})

    def _scan_dom_messages(self) -> list:
        """层 B：读取会话页可见的消息文本。"""
        out = []
        texts = set()
        for sel in MSG_SELECTORS:
            try:
                for el in self.dp.eles(sel, timeout=1):
                    t = el.text
                    if t and len(t.strip()) >= 2:
                        texts.add(t.strip())
            except Exception:
                pass
        conv_meta = self._scan_conversations_meta()
        for t in texts:
            key = _norm(t)
            if key in self._seen_messages:
                continue
            if key in self._sent_texts:
                continue
            self._seen_messages.add(key)
            out.append({"message": t, "conv": dict(conv_meta), "source": "dom"})
        return out

    def _scan_conversations_meta(self) -> dict:
        """尽力读取当前会话的岗位名/公司（找不到则为空）。"""
        meta = {"job_name": "", "company": "", "chat_name": ""}
        for field, sels in CONV_META_SELECTORS.items():
            for sel in sels:
                try:
                    el = self.dp.ele(sel, timeout=1)
                    if el:
                        t = (el.text or "").strip()
                        if t:
                            meta[field] = t
                            break
                except Exception:
                    pass
        # 兜底：取第一个会话行文本作定位线索
        if not meta["job_name"] and not meta["company"]:
            for sel in CONV_ROW_SELECTORS:
                try:
                    el = self.dp.ele(sel, timeout=1)
                    if el:
                        meta["chat_name"] = (el.text or "").strip()
                        break
                except Exception:
                    pass
        return meta

    # ── 回复生成与用户确认 ──

    def _handle_new_message(self, item: dict):
        message = item["message"]
        conv = item.get("conv", {})
        event_id = uuid.uuid4().hex
        analyzer = self._init_ai()
        ctx = {"job_name": conv.get("job_name", ""), "company": conv.get("company", "")}
        reply = analyzer.chat_reply(message, ctx) if analyzer else ""

        self._pending[event_id] = {"conv": conv, "hr_message": message, "reply": reply}
        self._log("INFO", f"💬 收到 HR 新消息: {message[:60]}")
        self._emit("ai_reply_ready", {
            "event_id": event_id,
            "job_name": ctx["job_name"],
            "company": ctx["company"],
            "hr_message": message,
            "suggested_reply": reply,
            "auto": self._auto_reply,
        })
        if self._auto_reply and reply:
            self._log("INFO", "自动回复模式，直接发送")
            self._send_reply_internal(event_id, reply)

    def _drain_user_actions(self):
        while not self._user_actions.empty():
            action = self._user_actions.get_nowait()
            if action["type"] == "send":
                self._send_reply_internal(action["event_id"], action.get("reply_text", ""))
            elif action["type"] == "skip":
                self._skip_reply(action["event_id"])

    def _skip_reply(self, event_id: str):
        if event_id in self._pending:
            del self._pending[event_id]
            self._log("INFO", "已跳过该回复")
        self._emit("ai_reply_sent", {"event_id": event_id, "ok": True, "err": "", "skipped": True})

    def _send_reply_internal(self, event_id: str, reply_text: str):
        pending = self._pending.pop(event_id, None)
        if pending is None:
            self._log("WARN", f"事件 {event_id} 不存在或已处理")
            self._emit("ai_reply_sent", {"event_id": event_id, "ok": False, "err": "事件不存在"})
            return
        conv = pending["conv"]
        hr_message = pending["hr_message"]
        ok = False
        err = ""
        try:
            ok = self._send_text_to_conversation(conv, reply_text)
            if ok:
                self._sent_texts.add(_norm(reply_text))
        except Exception as e:
            err = str(e)
            self._log("WARN", f"发送回复异常: {e}")
        if ok:
            self._log("SUCCESS", "✅ 回复已发送")
        else:
            self._log("ERROR", f"❌ 回复发送失败: {err}")
        self._emit("ai_reply_sent", {"event_id": event_id, "ok": ok, "err": err})
        self._save_reply_log(conv, hr_message, reply_text, ok)

    def _send_text_to_conversation(self, conv: dict, text: str) -> bool:
        """打开目标会话并发送文本回复。复用 bot_core 的 .input-area/.send-message。"""
        if not text:
            self._log("WARN", "回复内容为空，未发送")
            return False
        self.dp.get(CHAT_LIST_URL)
        self._random_delay(2, 4)

        find_key = (conv.get("chat_name") or conv.get("job_name") or conv.get("company") or "").strip()
        if find_key:
            try:
                row = self.dp.ele(f"text:{find_key}", timeout=5)
                if row:
                    row.click()
                    self._random_delay(1, 2)
            except Exception as e:
                self._log("WARN", f"点击会话失败（尝试直接输入）: {e}")
        else:
            self._log("INFO", "无会话定位信息，尝试点击第一条会话")
            for sel in CONV_ROW_SELECTORS:
                try:
                    el = self.dp.ele(sel, timeout=2)
                    if el:
                        el.click()
                        self._random_delay(1, 2)
                        break
                except Exception:
                    pass

        input_area = None
        for _ in range(3):
            try:
                input_area = self.dp.ele("#chat-input", timeout=3)
                if input_area:
                    break
            except Exception:
                pass
            self._random_delay(1, 1)
        if not input_area:
            self._log("WARN", "未找到输入框，无法发送回复")
            return False

        input_area.input(text)
        self._random_delay(1, 1)
        try:
            send_btn = self.dp.ele(".btn-send", timeout=5)
            if send_btn:
                send_btn.click()
            else:
                self.dp.run_js("document.querySelector('.btn-send')?.click()")
        except Exception as e:
            self._log("WARN", f"点击发送失败: {e}")
            return False
        self._random_delay(1, 2)
        if not self._wait_human_verify():
            self._log("WARN", "发送回复后检测到验证弹层，请手动处理")
            return False
        return True

    # ── 调试与日志 ──

    def _dump_chat_page(self):
        try:
            html = self.dp.html
            web_app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            dump_dir = os.path.join(web_app_dir, "debug")
            os.makedirs(dump_dir, exist_ok=True)
            with open(os.path.join(dump_dir, "chat_page.html"), "w", encoding="utf-8") as f:
                f.write(html or "")
            self._log("INFO", "已保存会话页 HTML 到 web_app/debug/chat_page.html 供校准")
        except Exception as e:
            self._log("WARN", f"保存调试页面失败: {e}")

    def _reply_log_path(self) -> str:
        web_app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(web_app_dir, REPLY_LOG_FILE)

    def _save_reply_log(self, conv: dict, hr_message: str, reply: str, ok: bool):
        try:
            logs = []
            path = self._reply_log_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            logs.append({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "job_name": conv.get("job_name", ""),
                "company": conv.get("company", ""),
                "hr_message": hr_message,
                "my_reply": reply,
                "sent": ok,
            })
            with open(path, "w", encoding="utf-8") as f:
                json.dump(logs[-1000:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass
