"""
Boss 直聘 · 自动投递工具
==========================
多账号 · 多岗位 · Cookie 连通性测试 · 实时浏览器预览

Taste-Skill 设计系统 v2：
  - 暖米白基底，靛灰强调色，克制的视觉层次
  - 五区布局：顶栏 | 左(账号) + 中(配置) | 右(预览+日志) | 底栏(操作)
  - 配置面板紧凑化，预览区最大化
  - 实时进度条 + 截图显示
"""

import base64
import json
import os
import threading
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from datetime import datetime
from io import BytesIO
from typing import Optional

import customtkinter as ctk
from PIL import Image

from config import load_config, save_config, reset_config
from bot_core import BotCore

# ═══════════════════════════════════════════════════════
#  TASTE-SKILL DESIGN SYSTEM v2
# ═══════════════════════════════════════════════════════

# ── Surface ──
BG          = "#f4f4ef"
CARD        = "#ffffff"
CARD_HOVER  = "#fafaf6"
SURFACE     = "#eeeee8"
SURFACE2    = "#e6e6df"
BORDER      = "#d8d8d0"
BORDER_LIGHT= "#eaeae4"

# ── Text ──
TEXT        = "#1a1a17"
TEXT_MUTED  = "#6b6b63"
TEXT_DIM    = "#9a9a91"
TEXT_INVERSE= "#ffffff"

# ── Accent ──
ACCENT        = "#4a4d7a"
ACCENT_HOVER  = "#3b3e68"
ACCENT_LIGHT  = "#e8e8ee"
ACCENT_DIM    = "#9a9bb8"
ACCENT_MUTED  = "#b8b9d0"

# ── Status ──
GREEN       = "#2b7a4e"
RED         = "#b33a3a"
AMBER       = "#a67c0e"
SLATE       = "#7a7a72"

# ── Typography ──
FONT_TITLE  = ("", 15, "bold")
FONT_H2     = ("", 12, "bold")
FONT_H3     = ("", 11, "bold")
FONT_BODY   = ("", 12)
FONT_SMALL  = ("", 11)
FONT_TINY   = ("", 10)
FONT_BTN    = ("", 12, "bold")
FONT_MONO   = ("Consolas", 11)

# ── Spacing ──
S4  = 4;  S6  = 6;  S8  = 8;  S12 = 12
S16 = 16; S20 = 20; S24 = 24

# ── Radius ──
R6  = 6;  R8  = 8;  R10 = 10; R12 = 12

# ── Sizing ──
TOPBAR_H = 42
BOTBAR_H = 56
ACCT_W   = 140
CFG_W    = 340


# ═══════════════════════════════════════════════════════
#  App
# ═══════════════════════════════════════════════════════

class App(ctk.CTk):
    """主窗口 — 五区布局。"""

    def __init__(self):
        super().__init__()
        self.title("Boss 直聘 · 自动投递")
        self.geometry("1320x800")
        self.minsize(1050, 680)
        self.configure(fg_color=BG)

        # ── 状态 ──
        self._config = load_config()
        self._bot: Optional[BotCore] = None
        self._bot_thread: Optional[threading.Thread] = None
        self._current_account_id: Optional[str] = None
        self._status_text = "就绪"
        self._status_color = SLATE

        # ── 变量容器 ──
        self._account_widgets: dict = {}
        self._name_var = ctk.StringVar()
        self._city_var = ctk.StringVar()
        self._min_var = ctk.StringVar(value="3")
        self._max_var = ctk.StringVar(value="8")
        self._greeting_text: Optional[ctk.CTkTextbox] = None
        self._job_widgets: list = []
        self._img_widgets: list = []
        self._preview_label: Optional[ctk.CTkLabel] = None
        self._log_text: Optional[ctk.CTkTextbox] = None
        self._progress_bar: Optional[ctk.CTkProgressBar] = None
        self._progress_label: Optional[ctk.CTkLabel] = None

        # ── 构建 UI ──
        self._build_ui()

        # ── 加载初始账号 ──
        if self._config.get("accounts"):
            self._switch_account(self._config["accounts"][0]["id"])

        # ── 关闭回调 ──
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ═══════════════════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════════════════

    def _build_ui(self):
        """
        五区布局：
        ┌──────────────────────────────────────────────────┐
        │                   顶栏 (状态)                     │
        ├─────┬──────────┬─────────────────────────────────┤
        │账号  │  配置     │  预览                           │
        │列表  │  面板     │  (大)                          │
        │     │          ├─────────────────────────────────┤
        │     │          │  日志                           │
        ├─────┴──────────┴─────────────────────────────────┤
        │                   底栏 (操作)                     │
        └──────────────────────────────────────────────────┘
        """
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=0)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        # 顶栏
        self._topbar = ctk.CTkFrame(self, height=TOPBAR_H, fg_color=CARD, corner_radius=0)
        self._topbar.grid(row=0, column=0, columnspan=3, sticky="ew")
        self._topbar.grid_propagate(False)
        self._build_topbar()

        # 左1: 账号列表
        self._acct_frame = ctk.CTkFrame(self, width=ACCT_W, fg_color=CARD, corner_radius=0)
        self._acct_frame.grid(row=1, column=0, sticky="ns")
        self._acct_frame.grid_propagate(False)
        self._build_account_bar()

        # 左2: 配置面板
        self._cfg_frame = ctk.CTkFrame(self, width=CFG_W, fg_color=BG, corner_radius=0)
        self._cfg_frame.grid(row=1, column=1, sticky="ns")
        self._cfg_frame.grid_propagate(False)
        self._cfg_frame.grid_rowconfigure(0, weight=1)
        self._cfg_frame.grid_columnconfigure(0, weight=1)

        self._config_canvas = ctk.CTkScrollableFrame(
            self._cfg_frame, fg_color=BG, corner_radius=0,
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=BORDER
        )
        self._config_canvas.grid(row=0, column=0, sticky="nsew")
        self._config_scroll = self._config_canvas

        # 右: 预览 + 日志
        right_frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        right_frame.grid(row=1, column=2, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=3)
        right_frame.grid_rowconfigure(1, weight=2)
        right_frame.grid_columnconfigure(0, weight=1)

        self._preview_frame = ctk.CTkFrame(right_frame, fg_color=SURFACE, corner_radius=R8)
        self._preview_frame.grid(row=0, column=0, sticky="nsew", padx=(S8, S12), pady=(S12, S6))
        self._preview_frame.grid_propagate(False)
        self._preview_frame.grid_rowconfigure(0, weight=1)
        self._preview_frame.grid_columnconfigure(0, weight=1)
        self._preview_label = ctk.CTkLabel(
            self._preview_frame, text="浏览器预览\n（启动后自动显示）",
            font=FONT_BODY, text_color=TEXT_DIM, anchor="center"
        )
        self._preview_label.grid(row=0, column=0, sticky="nsew")

        self._log_frame = ctk.CTkFrame(right_frame, fg_color=CARD, corner_radius=R8)
        self._log_frame.grid(row=1, column=0, sticky="nsew", padx=(S8, S12), pady=(S6, S12))
        self._log_frame.grid_propagate(False)
        self._log_frame.grid_rowconfigure(0, weight=1)
        self._log_frame.grid_columnconfigure(0, weight=1)
        self._log_text = ctk.CTkTextbox(
            self._log_frame, font=FONT_MONO, corner_radius=R6,
            fg_color=CARD, border_width=1, border_color=BORDER_LIGHT,
            wrap="word", state="disabled"
        )
        self._log_text.grid(row=0, column=0, sticky="nsew", padx=S8, pady=S8)

        # 底栏
        self._botbar = ctk.CTkFrame(self, height=BOTBAR_H, fg_color=CARD, corner_radius=0)
        self._botbar.grid(row=2, column=0, columnspan=3, sticky="ew")
        self._botbar.grid_propagate(False)
        self._build_botbar()

    # ═══════════════════════════════════════════════════
    #  顶栏
    # ═══════════════════════════════════════════════════

    def _build_topbar(self):
        self._topbar.grid_columnconfigure(2, weight=1)
        logo = ctk.CTkLabel(
            self._topbar, text="\u2b24 Boss 直聘 \u00b7 自动投递",
            font=FONT_TITLE, text_color=TEXT, anchor="w"
        )
        logo.grid(row=0, column=0, padx=(S16, S12), pady=0, sticky="w")

        self._status_dot = ctk.CTkLabel(
            self._topbar, text="\u25cf", font=FONT_BODY, text_color=self._status_color
        )
        self._status_dot.grid(row=0, column=1, padx=(0, S4))

        self._status_label = ctk.CTkLabel(
            self._topbar, text=self._status_text, font=FONT_BODY,
            text_color=self._status_color
        )
        self._status_label.grid(row=0, column=2, padx=(0, S16), sticky="w")

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        ctk.CTkLabel(
            self._topbar, text=now, font=FONT_SMALL,
            text_color=TEXT_DIM, anchor="e"
        ).grid(row=0, column=3, padx=S16, sticky="e")

    def _set_status(self, text: str, color: str = None):
        self._status_text = text
        self._status_color = color or SLATE
        self._status_label.configure(text=text, text_color=self._status_color)
        self._status_dot.configure(text_color=self._status_color)

    # ═══════════════════════════════════════════════════
    #  账号侧栏
    # ═══════════════════════════════════════════════════

    def _build_account_bar(self):
        for w in self._acct_frame.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._acct_frame, text="账号", font=FONT_H2,
            text_color=TEXT_MUTED, anchor="w"
        ).pack(fill="x", padx=S8, pady=(S12, S8))

        self._acct_container = ctk.CTkFrame(self._acct_frame, fg_color=CARD)
        self._acct_container.pack(fill="both", expand=True, padx=S4, pady=(0, S4))

        self._rebuild_account_buttons()

        ctk.CTkButton(
            self._acct_frame, text="+ 添加账号", height=30,
            font=FONT_SMALL, corner_radius=R6,
            fg_color=CARD, hover_color=CARD_HOVER,
            text_color=ACCENT, border_width=1, border_color=ACCENT_DIM,
            command=self._add_account
        ).pack(fill="x", padx=S8, pady=(S4, S12))

    def _rebuild_account_buttons(self):
        for w in self._acct_container.winfo_children():
            w.destroy()

        for acc in self._config.get("accounts", []):
            acc_id = acc["id"]
            acc_name = acc.get("name", acc_id)
            is_active = (acc_id == self._current_account_id)

            btn = ctk.CTkButton(
                self._acct_container,
                text=acc_name,
                anchor="w",
                height=36,
                font=FONT_BODY,
                corner_radius=R6,
                fg_color=ACCENT if is_active else CARD,
                hover_color=ACCENT_LIGHT if not is_active else ACCENT_HOVER,
                text_color=TEXT_INVERSE if is_active else TEXT,
                border_width=1 if not is_active else 0,
                border_color=BORDER_LIGHT,
                command=lambda aid=acc_id: self._switch_account(aid)
            )
            btn.pack(fill="x", padx=S4, pady=(0, S4))
            self._account_widgets[acc_id] = btn

    def _add_account(self):
        n = len(self._config.get("accounts", []))
        new_id = f"account_{n + 1}"
        new_acc = {
            "id": new_id,
            "name": f"账号{n + 1}",
            "city": "上海",
            "jobs": [{"query": "", "scroll_pages": 5}],
            "greeting_message": "您好，应聘该岗位。希望能获得面试机会。",
            "image_files": [],
            "cookies_file": "",
        }
        self._config.setdefault("accounts", []).append(new_acc)
        save_config(self._config)
        self._rebuild_account_buttons()
        self._switch_account(new_id)
        self._log("OK", f"已添加账号: {new_acc['name']}")

    def _switch_account(self, acc_id: str):
        self._save_current()
        self._current_account_id = acc_id
        self._rebuild_account_buttons()
        self._build_config_panel()

    def _get_current_account(self) -> Optional[dict]:
        for acc in self._config.get("accounts", []):
            if acc["id"] == self._current_account_id:
                return acc
        return None

    # ═══════════════════════════════════════════════════
    #  配置面板
    # ═══════════════════════════════════════════════════

    def _build_config_panel(self):
        for w in self._config_scroll.winfo_children():
            w.destroy()

        if not self._current_account_id:
            ctk.CTkLabel(
                self._config_scroll, text="请添加账号",
                font=FONT_BODY, text_color=TEXT_MUTED
            ).pack(pady=S20)
            return

        acc = self._get_current_account()
        if not acc:
            return

        scroll = self._config_scroll

        def _section(title: str):
            ctk.CTkLabel(
                scroll, text=title, font=FONT_H2,
                text_color=TEXT_MUTED, anchor="w"
            ).pack(fill="x", padx=S8, pady=(S12, S4))

        def _input_row(label: str, var, **kw):
            row = ctk.CTkFrame(scroll, fg_color=BG)
            row.pack(fill="x", padx=S8, pady=(0, S6))
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                row, text=label, font=FONT_BODY,
                text_color=TEXT, width=52, anchor="w"
            ).grid(row=0, column=0, padx=(0, S8))
            entry = ctk.CTkEntry(
                row, font=FONT_BODY, height=30,
                corner_radius=R6, fg_color=CARD,
                border_width=1, border_color=BORDER_LIGHT,
                textvariable=var, **kw
            )
            entry.grid(row=0, column=1, sticky="ew")
            return entry

        self._name_var = ctk.StringVar(value=acc.get("name", ""))
        _input_row("名称", self._name_var)

        self._city_var = ctk.StringVar(value=acc.get("city", "上海"))
        _input_row("城市", self._city_var)

        _section("岗位关键词")
        jobs_container = ctk.CTkFrame(scroll, fg_color=BG)
        jobs_container.pack(fill="x", padx=S8, pady=(0, S8))

        self._job_widgets.clear()
        for jd in acc.get("jobs", [{"query": ""}]):
            self._add_job_ui(jobs_container, self._job_widgets,
                             query=jd.get("query", ""),
                             scroll_pages=str(jd.get("scroll_pages", 5)))

        add_job_btn = ctk.CTkButton(
            scroll, text="+ 添加岗位", height=28,
            font=FONT_SMALL, corner_radius=R6,
            fg_color=CARD, hover_color=CARD_HOVER,
            text_color=ACCENT, border_width=1, border_color=ACCENT_DIM,
            command=lambda: self._add_job_ui(jobs_container, self._job_widgets)
        )
        add_job_btn.pack(fill="x", padx=S8, pady=(0, S12))

        _section("招呼语")
        greeting_text = ctk.CTkTextbox(
            scroll, height=80, font=FONT_BODY,
            corner_radius=R8, fg_color=CARD,
            border_width=1, border_color=BORDER_LIGHT, wrap="word"
        )
        greeting_text.pack(fill="x", padx=S8, pady=(0, S8))
        greeting_text.insert("1.0", acc.get("greeting_message", ""))
        self._greeting_text = greeting_text

        _section("作品集图片")
        img_container = ctk.CTkFrame(scroll, fg_color=BG)
        img_container.pack(fill="x", padx=S8, pady=(0, S4))

        self._img_widgets.clear()
        for img_path in acc.get("image_files", []):
            lbl = ctk.CTkLabel(
                img_container, text=f"\U0001f4f7 {os.path.basename(img_path)}",
                font=FONT_SMALL, text_color=TEXT_MUTED, anchor="w"
            )
            lbl.pack(fill="x", pady=(0, S2))
            self._img_widgets.append({"label": lbl, "path": img_path})

        img_btn_row = ctk.CTkFrame(scroll, fg_color=BG)
        img_btn_row.pack(fill="x", padx=S8, pady=(0, S12))
        ctk.CTkButton(
            img_btn_row, text="选择图片", height=26,
            font=FONT_SMALL, corner_radius=R6,
            fg_color=CARD, hover_color=CARD_HOVER,
            text_color=ACCENT, border_width=1, border_color=ACCENT_DIM,
            command=lambda: self._add_image_dialog(img_container, self._img_widgets)
        ).pack(side="left", padx=(0, S8))
        ctk.CTkButton(
            img_btn_row, text="清空", height=26,
            font=FONT_SMALL, corner_radius=R6,
            fg_color=CARD, hover_color=CARD_HOVER,
            text_color=TEXT_MUTED, border_width=1, border_color=BORDER_LIGHT,
            command=lambda: self._clear_images(img_container, self._img_widgets)
        ).pack(side="left")

        _section("投递间隔 (秒)")
        set_frame = ctk.CTkFrame(scroll, fg_color=BG)
        set_frame.pack(fill="x", padx=S8, pady=(0, S16))

        self._min_var = ctk.StringVar(value=str(self._config.get("message_interval_min", 3)))
        self._max_var = ctk.StringVar(value=str(self._config.get("message_interval_max", 8)))

        ctk.CTkLabel(set_frame, text="最小", font=FONT_BODY,
                     text_color=TEXT).pack(side="left", padx=(0, S4))
        ctk.CTkEntry(set_frame, font=FONT_BODY, width=48, height=28,
                     corner_radius=R6, border_width=1, border_color=BORDER_LIGHT,
                     textvariable=self._min_var).pack(side="left", padx=(0, S12))
        ctk.CTkLabel(set_frame, text="最大", font=FONT_BODY,
                     text_color=TEXT).pack(side="left", padx=(0, S4))
        ctk.CTkEntry(set_frame, font=FONT_BODY, width=48, height=28,
                     corner_radius=R6, border_width=1, border_color=BORDER_LIGHT,
                     textvariable=self._max_var).pack(side="left")

    def _add_job_ui(self, container, widgets_list, query="", scroll_pages="5"):
        row = ctk.CTkFrame(container, fg_color=CARD, corner_radius=R6)
        row.pack(fill="x", pady=(0, S4))
        row.grid_columnconfigure(0, weight=1)

        q_var = ctk.StringVar(value=query)
        entry = ctk.CTkEntry(row, font=FONT_BODY, height=28,
                             corner_radius=R6, border_width=1,
                             border_color=BORDER_LIGHT, textvariable=q_var)
        entry.grid(row=0, column=0, sticky="ew", padx=(S8, S4), pady=S4)

        s_var = ctk.StringVar(value=scroll_pages)
        s_entry = ctk.CTkEntry(row, font=FONT_SMALL, width=40,
                               height=28, corner_radius=R6,
                               border_width=1, border_color=BORDER_LIGHT,
                               textvariable=s_var)
        s_entry.grid(row=0, column=1, padx=S4, pady=S4)

        def _del():
            row.destroy()
            nonlocal wd
            if wd in widgets_list:
                widgets_list.remove(wd)

        del_btn = ctk.CTkButton(row, text="\u2715", width=28, height=28,
                                corner_radius=R6, font=FONT_SMALL,
                                fg_color=CARD, hover_color="#f0e0e0",
                                text_color=TEXT_MUTED, border_width=1,
                                border_color=BORDER_LIGHT, command=_del)
        del_btn.grid(row=0, column=2, padx=(S4, S8), pady=S4)

        wd = {"row": row, "query_var": q_var, "scroll_var": s_var}
        widgets_list.append(wd)
        return wd

    def _add_image_dialog(self, container, widgets_list):
        paths = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if not paths:
            return
        for p in paths:
            lbl = ctk.CTkLabel(
                container, text=f"\U0001f4f7 {os.path.basename(p)}",
                font=FONT_SMALL, text_color=TEXT_MUTED, anchor="w"
            )
            lbl.pack(fill="x", pady=(0, S2))
            widgets_list.append({"label": lbl, "path": p})

    def _clear_images(self, container, widgets_list):
        for w in widgets_list:
            w["label"].destroy()
        widgets_list.clear()

    # ═══════════════════════════════════════════════════
    #  底栏
    # ═══════════════════════════════════════════════════

    def _build_botbar(self):
        self._botbar.grid_columnconfigure(4, weight=1)
        padding = dict(padx=(0, S8), pady=S8)

        self._btn_start = ctk.CTkButton(
            self._botbar, text="\u25b6 开始投递", height=34,
            font=FONT_BTN, corner_radius=R8,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=TEXT_INVERSE, command=self._on_start
        )
        self._btn_start.grid(row=0, column=0, **padding)

        self._btn_stop = ctk.CTkButton(
            self._botbar, text="\u25a0 停止", height=34,
            font=FONT_BTN, corner_radius=R8,
            fg_color=CARD, hover_color="#f0e0e0",
            text_color=RED, border_width=1, border_color=RED,
            state="disabled", command=self._on_stop
        )
        self._btn_stop.grid(row=0, column=1, **padding)

        self._btn_confirm = ctk.CTkButton(
            self._botbar, text="\u2713 确认已登录", height=34,
            font=FONT_BTN, corner_radius=R8,
            fg_color=CARD, hover_color="#e0f0e8",
            text_color=GREEN, border_width=1, border_color=GREEN,
            command=self._on_confirm_login
        )
        self._btn_confirm.grid(row=0, column=2, **padding)

        self._btn_test = ctk.CTkButton(
            self._botbar, text="\u25ce 测试连通性", height=34,
            font=FONT_BTN, corner_radius=R8,
            fg_color=CARD, hover_color=CARD_HOVER,
            text_color=AMBER, border_width=1, border_color=AMBER,
            command=self._on_test_connectivity
        )
        self._btn_test.grid(row=0, column=3, **padding)

        progress_frame = ctk.CTkFrame(self._botbar, fg_color=BG)
        progress_frame.grid(row=0, column=4, sticky="ew", padx=(S12, S8), pady=S8)
        progress_frame.grid_columnconfigure(0, weight=1)
        progress_frame.grid_columnconfigure(1, weight=0)

        self._progress_bar = ctk.CTkProgressBar(
            progress_frame, height=8, corner_radius=4,
            fg_color=BORDER_LIGHT, progress_color=ACCENT
        )
        self._progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, S8))
        self._progress_bar.set(0)

        self._progress_label = ctk.CTkLabel(
            progress_frame, text="就绪", font=FONT_SMALL,
            text_color=TEXT_MUTED, anchor="e", width=120
        )
        self._progress_label.grid(row=0, column=1, sticky="e")

        self._btn_save = ctk.CTkButton(
            self._botbar, text="\U0001f4be 保存配置", height=34,
            font=FONT_BTN, corner_radius=R8,
            fg_color=CARD, hover_color=CARD_HOVER,
            text_color=TEXT, border_width=1, border_color=BORDER,
            command=self._on_save
        )
        self._btn_save.grid(row=0, column=5, **padding)

        self._btn_reset = ctk.CTkButton(
            self._botbar, text="\u21ba 重置", height=34,
            font=FONT_BTN, corner_radius=R8,
            fg_color=CARD, hover_color=CARD_HOVER,
            text_color=TEXT_MUTED, border_width=1, border_color=BORDER,
            command=self._on_reset
        )
        self._btn_reset.grid(row=0, column=6, **padding)

    # ═══════════════════════════════════════════════════
    #  日志
    # ═══════════════════════════════════════════════════

    def _log(self, msg: str):
        if self._log_text:
            self._log_text.configure(state="normal")
            self._log_text.insert("end", msg + "\n")
            self._log_text.see("end")
            self._log_text.configure(state="disabled")

    # ═══════════════════════════════════════════════════
    #  截图回调
    # ═══════════════════════════════════════════════════

    def _on_screenshot(self, b64_data: str):
        try:
            raw = base64.b64decode(b64_data.split(",")[1] if "," in b64_data else b64_data)
            img = Image.open(BytesIO(raw))
            pw = self._preview_frame.winfo_width() or 480
            ph = self._preview_frame.winfo_height() or 320
            img.thumbnail((pw - 16, ph - 16), Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self._preview_label.configure(image=ctk_img, text="")
            self._preview_label.image = ctk_img
        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    #  进度回调
    # ═══════════════════════════════════════════════════

    def _on_progress(self, cur: int, total: int, text: str):
        if total > 0:
            self._progress_bar.set(cur / total)
        self._progress_label.configure(
            text=f"{text} ({cur}/{total})" if text else f"{cur}/{total}"
        )

    # ═══════════════════════════════════════════════════
    #  保存当前配置到 dict (不写盘)
    # ═══════════════════════════════════════════════════

    def _save_current(self):
        if not self._current_account_id:
            return
        acc = self._get_current_account()
        if not acc:
            return

        if hasattr(self, "_name_var") and self._name_var.get():
            acc["name"] = self._name_var.get()
        if hasattr(self, "_city_var") and self._city_var.get():
            acc["city"] = self._city_var.get()

        jobs = []
        for wd in self._job_widgets:
            q = wd["query_var"].get().strip()
            if q:
                jobs.append({
                    "query": q,
                    "scroll_pages": int(wd["scroll_var"].get() or 5)
                })
        if jobs:
            acc["jobs"] = jobs

        if hasattr(self, "_greeting_text") and self._greeting_text:
            txt = self._greeting_text.get("1.0", "end-1c").strip()
            if txt:
                acc["greeting_message"] = txt

        acc["image_files"] = [w["path"] for w in self._img_widgets]

        if hasattr(self, "_min_var") and self._min_var.get():
            self._config["message_interval_min"] = int(self._min_var.get())
        if hasattr(self, "_max_var") and self._max_var.get():
            self._config["message_interval_max"] = int(self._max_var.get())

    # ═══════════════════════════════════════════════════
    #  事件处理器
    # ═══════════════════════════════════════════════════

    def _on_start(self):
        if self._bot and self._bot.running:
            self._log("[WARN] 正在运行中，请先停止")
            return

        self._save_current()
        save_config(self._config)

        self._set_status("启动中…", ACCENT)
        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal")

        if self._bot:
            self._bot.close()
        self._bot = BotCore(
            config=self._config,
            log_callback=self._log,
            screenshot_callback=self._on_screenshot,
            progress_callback=self._on_progress,
        )

        self._bot_thread = threading.Thread(target=self._bot.run, daemon=True)
        self._bot_thread.start()

        self._set_status("运行中…", GREEN)
        self._log("[OK] 已启动投递")
        self._poll_bot()

    def _poll_bot(self):
        if self._bot and self._bot.running:
            self.after(1000, self._poll_bot)
        else:
            self._on_bot_finished()

    def _on_bot_finished(self):
        self._set_status("就绪", SLATE)
        self._btn_start.configure(state="normal")
        self._btn_stop.configure(state="disabled")
        self._progress_bar.set(0)
        self._progress_label.configure(text="已完成")
        self._log("[INFO] 投递已结束")

    def _on_stop(self):
        if self._bot:
            self._bot.stop()
        self._set_status("已停止", RED)
        self._on_bot_finished()
        self._log("[WARN] 已手动停止")

    def _on_confirm_login(self):
        if not self._bot:
            self._save_current()
            save_config(self._config)
            self._bot = BotCore(
                config=self._config,
                log_callback=self._log,
                screenshot_callback=self._on_screenshot,
                progress_callback=self._on_progress,
            )

        self._set_status("登录确认，继续执行…", AMBER)
        self._log("[OK] 用户已确认登录，继续执行")

        accounts = self._config.get("accounts", [])
        interval_min = self._config.get("message_interval_min", 3)
        interval_max = self._config.get("message_interval_max", 8)
        global_scroll = self._config.get("global_scroll_pages", 5)

        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal")

        self._bot_thread = threading.Thread(
            target=self._bot.run_all,
            args=(accounts, interval_min, interval_max, global_scroll),
            daemon=True
        )
        self._bot_thread.start()
        self._set_status("运行中…", GREEN)
        self._poll_bot()

    def _on_test_connectivity(self):
        self._save_current()
        acc = self._get_current_account()
        if not acc:
            self._log("[WARN] 请先选择账号")
            return

        self._log(f"[INFO] 测试账号 [{acc.get('name')}] Cookie 连通性…")
        self._set_status("测试中…", AMBER)

        test_bot = BotCore(config=self._config, log_callback=self._log)
        result = test_bot.test_connectivity(acc["id"])

        if result.get("success"):
            if result.get("cookies_valid"):
                self._set_status("连通正常 \u2705", GREEN)
                self._log(f"[OK] {result.get('message', '连通正常')}")
            else:
                self._set_status("Cookie 失效 \u274c", RED)
                self._log(f"[WARN] {result.get('message', 'Cookie 失效')}")
        else:
            self._set_status("测试失败 \u274c", RED)
            self._log(f"[ERROR] {result.get('message', '测试异常')}")

        test_bot.close()

    def _on_save(self):
        self._save_current()
        save_config(self._config)
        self._log(f"[OK] 配置已保存 ({datetime.now().strftime('%H:%M:%S')})")
        self._set_status("已保存", GREEN)
        self.after(2000, lambda: self._set_status("就绪", SLATE))

    def _on_reset(self):
        if messagebox.askyesno("确认重置", "将恢复默认配置，确定？"):
            self._config = reset_config()
            self._current_account_id = None
            self._rebuild_account_buttons()
            self._build_config_panel()
            self._log("[OK] 配置已重置")
            self._set_status("已重置", AMBER)
            self.after(2000, lambda: self._set_status("就绪", SLATE))

    def _on_close(self):
        if self._bot:
            self._bot.close()
        if self._bot_thread and self._bot_thread.is_alive():
            self._bot_thread.join(timeout=3)
        self.destroy()


# ═══════════════════════════════════════════════════════
#  Entry
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
