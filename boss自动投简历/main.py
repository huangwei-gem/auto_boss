"""
Boss 直聘 · 自动投递工具
============================
多账号 · 多岗位 · Cookie 连通性测试 · 实时浏览器预览

UI 设计（Modern Dark-Light Hybrid）:
  ┌────────────────────────────────────────────────────────┐
  │  ⬤ Boss 直聘 · 自动投递     [●●● 就绪]   状态指示    │  顶栏
  ├──────┬─────────────────────────────────────────────────┤
  │      │  ┌─────────────────────────────────────────┐   │
  │ 账号  │  │         浏览器实时预览                   │   │
  │ 列表  │  │                                         │   │
  │ ┌──┐  │  └─────────────────────────────────────────┘   │
  │ │A1│  │  ┌─────────────────────────────────────────┐   │
  │ │A2│  │  │ 运行日志 (monospace)                     │   │
  │ │+ │  │  │                                         │   │
  │ └──┘  │  └─────────────────────────────────────────┘   │
  ├──────┴─────────────────────────────────────────────────┤
  │  [▶开始] [⏹停止] [🔗测试] [✓确认登录] [💾保存] [↺重置]│  底栏
  └────────────────────────────────────────────────────────┘
"""

import base64
import json
import os
import re
import threading
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from datetime import datetime
from io import BytesIO
from typing import Optional

import customtkinter as ctk
from PIL import Image

from config import load_config, save_config, reset_config
from bot_core import BotCore, DEFAULT_GREETING

# ═══════════════════════════════════════════════════════
#  DESIGN SYSTEM
# ═══════════════════════════════════════════════════════

BG          = "#f0f0ec"
CARD        = "#ffffff"
CARD_HOVER  = "#f8f8f4"
SURFACE     = "#e8e8e3"
SURFACE2    = "#e0e0d8"
BORDER      = "#d4d4cc"
BORDER_LIGHT= "#e6e6e0"

TEXT        = "#1a1a17"
TEXT_MUTED  = "#6b6b63"
TEXT_DIM    = "#9a9a91"
TEXT_INVERSE= "#ffffff"

ACCENT        = "#4a4d7a"
ACCENT_HOVER  = "#3b3e68"
ACCENT_LIGHT  = "#e8e8ee"
ACCENT_DIM    = "#9a9bb8"
ACCENT_MUTED  = "#b8b9d0"

GREEN       = "#2b7a4e"
RED         = "#b33a3a"
AMBER       = "#a67c0e"
SLATE       = "#7a7a72"

FONT_TITLE  = ("", 15, "bold")
FONT_H2     = ("", 12, "bold")
FONT_H3     = ("", 11, "bold")
FONT_BODY   = ("", 12)
FONT_SMALL  = ("", 11)
FONT_TINY   = ("", 10)
FONT_BTN    = ("", 12, "bold")
FONT_MONO   = ("Consolas", 11)

S4 = 4
S8 = 8
S12 = 12
S16 = 16
S20 = 20
S24 = 24

R6 = 6
R8 = 8
R10 = 10
R12 = 12

TOPBAR_H = 44
BOTBAR_H = 50
ACCT_W = 130


# ═══════════════════════════════════════════════════════
#  App
# ═══════════════════════════════════════════════════════

class App(ctk.CTk):
    """主窗口 — 五区布局。"""

    def __init__(self):
        super().__init__()
        self.title("Boss 直聘 · 自动投递")
        self.geometry("1360x800")
        self.minsize(1024, 680)
        self.configure(fg_color=BG)

        # ── 状态 ──
        self._config = load_config()
        self._bot: Optional[BotCore] = None
        self._bot_thread: Optional[threading.Thread] = None
        self._current_account_id: Optional[str] = None
        self._status_text = "就绪"
        self._status_color = SLATE

        # 配置面板引用
        self._config_scroll: Optional[ctk.CTkScrollableFrame] = None
        self._name_var: Optional[ctk.StringVar] = None
        self._city_var: Optional[ctk.StringVar] = None
        self._min_var: Optional[ctk.StringVar] = None
        self._max_var: Optional[ctk.StringVar] = None
        self._greeting_text: Optional[ctk.CTkTextbox] = None
        self._job_widgets: list = []
        self._img_widgets: list = []

        # UI
        self._build_ui()

        # 加载初始账号
        if self._config.get("accounts"):
            self._switch_account(self._config["accounts"][0]["id"])

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 工具 ──────────────────────────────────────────

    def _get_current_account(self) -> Optional[dict]:
        for acc in self._config.get("accounts", []):
            if acc.get("id") == self._current_account_id:
                return acc
        return None

    def _set_status(self, text: str, color: str = None):
        self._status_text = text
        if color:
            self._status_color = color
        self._status_label.configure(text=f"● {text}", text_color=self._status_color)

    # ═══════════════════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════════════════

    def _build_ui(self):
        """五区布局：顶栏 | 左(账号)+右(上预览下日志) | 底栏"""
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── 顶栏 ──
        self._topbar = ctk.CTkFrame(self, height=TOPBAR_H, fg_color=CARD, corner_radius=0)
        self._topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._topbar.grid_propagate(False)
        self._build_topbar()

        # ── 左：账号侧栏 ──
        self._acct_frame = ctk.CTkFrame(self, width=ACCT_W, fg_color=CARD, corner_radius=0)
        self._acct_frame.grid(row=1, column=0, sticky="ns")
        self._acct_frame.grid_propagate(False)
        self._build_account_sidebar()

        # ── 右：预览 + 日志（垂直分栏，中间放配置按钮） ──
        right_frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=3)
        right_frame.grid_rowconfigure(1, weight=0)
        right_frame.grid_rowconfigure(2, weight=2)
        right_frame.grid_columnconfigure(0, weight=1)

        # 预览区
        self._preview_frame = ctk.CTkFrame(right_frame, fg_color=SURFACE, corner_radius=R10)
        self._preview_frame.grid(row=0, column=0, sticky="nsew", padx=S12, pady=(S12, S4))
        self._preview_frame.grid_propagate(False)
        self._build_preview()

        # 中间切换按钮（折叠配置面板）
        self._toggle_cfg_btn = ctk.CTkButton(
            right_frame, text="▼ 配置面板", font=FONT_SMALL,
            height=28, corner_radius=R6,
            fg_color=CARD, hover_color=CARD_HOVER,
            text_color=ACCENT, border_width=1, border_color=BORDER_LIGHT,
            command=self._toggle_config_panel
        )
        self._toggle_cfg_btn.grid(row=1, column=0, sticky="ew", padx=S12, pady=(S4, S4))

        # 日志区
        self._log_frame = ctk.CTkFrame(right_frame, fg_color=CARD, corner_radius=R10)
        self._log_frame.grid(row=2, column=0, sticky="nsew", padx=S12, pady=(S4, S12))
        self._log_frame.grid_propagate(False)
        self._build_log()

        # ── 底栏 ──
        self._botbar = ctk.CTkFrame(self, height=BOTBAR_H, fg_color=CARD, corner_radius=0)
        self._botbar.grid(row=2, column=0, columnspan=2, sticky="ew")
        self._botbar.grid_propagate(False)
        self._build_botbar()

        # ── 配置浮动面板（半透明覆盖） ──
        self._show_config = True
        self._config_overlay = None
        self._rebuild_config_overlay()

    # ── 顶栏 ──

    def _build_topbar(self):
        self._topbar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self._topbar, text="⬤  Boss 直聘 · 自动投递",
                     font=FONT_TITLE, text_color=TEXT,
                     anchor="w").grid(row=0, column=0, padx=S16, pady=0)

        self._status_label = ctk.CTkLabel(
            self._topbar, text=f"● {self._status_text}",
            font=FONT_BTN, text_color=self._status_color, anchor="e"
        )
        self._status_label.grid(row=0, column=1, padx=S16, pady=0, sticky="e")

    # ── 账号侧栏 ──

    def _build_account_sidebar(self):
        for w in self._acct_frame.winfo_children():
            w.destroy()

        self._acct_frame.grid_rowconfigure(0, weight=0)
        self._acct_frame.grid_rowconfigure(1, weight=1)
        self._acct_frame.grid_rowconfigure(2, weight=0)
        self._acct_frame.grid_columnconfigure(0, weight=1)

        # 标题
        header = ctk.CTkFrame(self._acct_frame, fg_color=CARD, corner_radius=0, height=36)
        header.grid(row=0, column=0, sticky="ew", pady=(S8, S4))
        header.grid_propagate(False)
        ctk.CTkLabel(header, text="账号", font=FONT_H2,
                     text_color=TEXT_MUTED).pack(padx=S12)

        # 账号按钮列表
        acct_container = ctk.CTkScrollableFrame(
            self._acct_frame, fg_color=CARD, corner_radius=0,
            scrollbar_button_color=ACCENT_DIM
        )
        acct_container.grid(row=1, column=0, sticky="nsew")
        acct_container.grid_columnconfigure(0, weight=1)

        self._acct_buttons = {}
        for acc in self._config.get("accounts", []):
            btn = ctk.CTkButton(
                acct_container, text=acc.get("name", "?"),
                font=FONT_BODY, anchor="w",
                height=36, corner_radius=R6,
                fg_color=CARD, hover_color=CARD_HOVER,
                text_color=TEXT, border_width=0,
                command=lambda a=acc: self._switch_account(a["id"])
            )
            btn.pack(fill="x", padx=S8, pady=(0, S4))
            self._acct_buttons[acc["id"]] = btn

        # 底部按钮
        btn_frame = ctk.CTkFrame(self._acct_frame, fg_color=CARD, corner_radius=0)
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(S4, S12))
        btn_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(btn_frame, text="+ 添加账号", height=32,
                      font=FONT_SMALL, corner_radius=R6,
                      fg_color=ACCENT_LIGHT, hover_color="#ddddee",
                      text_color=ACCENT, border_width=1, border_color=ACCENT_DIM,
                      command=self._add_account
                      ).grid(row=0, column=0, padx=S8, pady=(0, S4), sticky="ew")

        ctk.CTkButton(btn_frame, text="✕ 删除当前", height=28,
                      font=FONT_TINY, corner_radius=R6,
                      fg_color=CARD, hover_color="#f0e0e0",
                      text_color=RED, border_width=1, border_color=BORDER_LIGHT,
                      command=self._delete_account
                      ).grid(row=1, column=0, padx=S8, sticky="ew")

    def _switch_account(self, acc_id: str):
        """切换当前编辑的账号。"""
        # 先保存当前
        self._save_current_config()

        self._current_account_id = acc_id

        # 更新按钮高亮
        for aid, btn in self._acct_buttons.items():
            if aid == acc_id:
                btn.configure(fg_color=ACCENT_LIGHT, text_color=ACCENT,
                              border_width=1, border_color=ACCENT_DIM)
            else:
                btn.configure(fg_color=CARD, text_color=TEXT,
                              border_width=0, border_color=BORDER_LIGHT)

        # 重建配置面板
        self._rebuild_config_overlay()
        self._set_status(f"编辑: {self._get_current_account().get('name', '?')}", ACCENT)

    def _add_account(self):
        cfg = self._config
        n = len(cfg.get("accounts", [])) + 1
        new_acc = {
            "id": f"account_{n}",
            "name": f"账号{n}",
            "city": "上海",
            "jobs": [{"query": "数据分析", "scroll_pages": 5}],
            "greeting_message": DEFAULT_GREETING,
            "image_files": [],
            "cookies_file": "",
        }
        cfg.setdefault("accounts", []).append(new_acc)
        save_config(cfg)
        self._build_account_sidebar()
        self._switch_account(new_acc["id"])
        self._log("OK", f"已添加账号: {new_acc['name']}")

    def _delete_account(self):
        if not self._current_account_id:
            return
        if not messagebox.askyesno("确认", "确定删除当前账号？"):
            return
        cfg = self._config
        cfg["accounts"] = [a for a in cfg.get("accounts", [])
                         if a["id"] != self._current_account_id]
        if not cfg["accounts"]:
            cfg["accounts"] = [{
                "id": "account_1", "name": "默认账号", "city": "上海",
                "jobs": [{"query": "数据分析", "scroll_pages": 5}],
                "greeting_message": DEFAULT_GREETING,
                "image_files": [], "cookies_file": "",
            }]
        save_config(cfg)
        self._build_account_sidebar()
        self._switch_account(cfg["accounts"][0]["id"])
        self._log("WARN", "账号已删除")

    # ── 配置浮动面板 ──

    def _toggle_config_panel(self):
        self._show_config = not self._show_config
        if self._config_overlay:
            if self._show_config:
                self._config_overlay.grid()
                self._toggle_cfg_btn.configure(text="▼ 隐藏配置面板")
            else:
                self._config_overlay.grid_remove()
                self._toggle_cfg_btn.configure(text="▶ 显示配置面板")

    def _rebuild_config_overlay(self):
        """配置面板 — 在右侧浮动显示。"""
        if self._config_overlay:
            self._config_overlay.destroy()

        self._config_overlay = ctk.CTkFrame(
            self, fg_color=CARD, corner_radius=R12,
            border_width=1, border_color=BORDER
        )
        # 放在右侧预览区上面（右上角浮动）
        self._config_overlay.place(
            relx=1.0, x=-16, y=TOPBAR_H + 4,
            anchor="ne", width=380, relheight=0.94
        )
        self._config_overlay.grid_propagate(False)
        self._build_config_panel_inner()

        if not self._show_config:
            self._config_overlay.grid_remove()

    def _build_config_panel_inner(self):
        """配置面板内容。"""
        for w in self._config_overlay.winfo_children():
            w.destroy()

        # 标题
        title_row = ctk.CTkFrame(self._config_overlay, fg_color=CARD, height=36)
        title_row.pack(fill="x", padx=S12, pady=(S12, S4))
        title_row.grid_propagate(False)
        ctk.CTkLabel(title_row, text="⚙ 账号配置", font=FONT_H2,
                     text_color=TEXT).pack(side="left")

        # 滚动区域
        scroll = ctk.CTkScrollableFrame(
            self._config_overlay, fg_color=CARD, corner_radius=0,
            scrollbar_button_color=ACCENT_DIM
        )
        scroll.pack(fill="both", expand=True, padx=S12, pady=(S4, S12))
        self._config_scroll = scroll

        if not self._current_account_id:
            ctk.CTkLabel(scroll, text="请添加或选择一个账号",
                         font=FONT_BODY, text_color=TEXT_MUTED).pack(pady=S20)
            return

        acc = self._get_current_account()
        if not acc:
            return

        def _section(title: str):
            ctk.CTkLabel(scroll, text=title, font=FONT_H2,
                         text_color=TEXT_MUTED, anchor="w"
                         ).pack(fill="x", padx=S4, pady=(S12, S4))

        def _input_row(label: str, var, **kw):
            row = ctk.CTkFrame(scroll, fg_color=CARD)
            row.pack(fill="x", padx=S4, pady=(0, S6))
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=label, font=FONT_BODY,
                         text_color=TEXT, width=44, anchor="w"
                         ).grid(row=0, column=0, padx=(0, S8))
            entry = ctk.CTkEntry(row, font=FONT_BODY, height=30,
                                 corner_radius=R6, fg_color=SURFACE,
                                 border_width=1, border_color=BORDER_LIGHT,
                                 textvariable=var, **kw)
            entry.grid(row=0, column=1, sticky="ew")
            return entry

        # 账号名称
        name_var = ctk.StringVar(value=acc.get("name", ""))
        _input_row("名称", name_var)
        self._name_var = name_var

        # 城市
        city_var = ctk.StringVar(value=acc.get("city", "上海"))
        _input_row("城市", city_var)
        self._city_var = city_var

        # 岗位列表
        _section("🏷 岗位关键词")
        jobs_container = ctk.CTkFrame(scroll, fg_color=CARD)
        jobs_container.pack(fill="x", padx=S4, pady=(0, S4))

        self._job_widgets = []
        for j_idx, jd in enumerate(acc.get("jobs", [{"query": ""}])):
            self._add_job_ui(jobs_container, self._job_widgets, jd)

        # 添加岗位按钮
        add_job_btn = ctk.CTkButton(
            scroll, text="+ 添加岗位", height=28,
            font=FONT_SMALL, corner_radius=R6,
            fg_color=ACCENT_LIGHT, hover_color="#ddddee",
            text_color=ACCENT, border_width=1, border_color=ACCENT_DIM,
            command=lambda: self._add_job_ui(jobs_container, self._job_widgets)
        )
        add_job_btn.pack(fill="x", padx=S4, pady=(0, S8))

        # 招呼语
        _section("💬 招呼语")
        greeting_text = ctk.CTkTextbox(
            scroll, height=72, font=FONT_BODY,
            corner_radius=R8, fg_color=SURFACE,
            border_width=1, border_color=BORDER_LIGHT, wrap="word"
        )
        greeting_text.pack(fill="x", padx=S4, pady=(0, S8))
        greeting_text.insert("1.0", acc.get("greeting_message", ""))
        self._greeting_text = greeting_text

        # 图片附件
        _section("📷 作品集图片")
        img_container = ctk.CTkFrame(scroll, fg_color=CARD)
        img_container.pack(fill="x", padx=S4, pady=(0, S4))

        self._img_widgets = []
        for img_path in acc.get("image_files", []):
            lbl = ctk.CTkLabel(
                img_container, text=f"  {os.path.basename(img_path)}",
                font=FONT_SMALL, text_color=TEXT_MUTED, anchor="w"
            )
            lbl.pack(fill="x", pady=(0, S2))
            self._img_widgets.append({"label": lbl, "path": img_path})

        img_btn_row = ctk.CTkFrame(scroll, fg_color=CARD)
        img_btn_row.pack(fill="x", padx=S4, pady=(0, S8))
        ctk.CTkButton(img_btn_row, text="选择图片", height=26,
                      font=FONT_SMALL, corner_radius=R6,
                      fg_color=SURFACE, hover_color=CARD_HOVER,
                      text_color=ACCENT, border_width=1,
                      border_color=ACCENT_DIM,
                      command=lambda: self._add_image_dialog(img_container, self._img_widgets)
                      ).pack(side="left", padx=(0, S8))
        ctk.CTkButton(img_btn_row, text="清空", height=26,
                      font=FONT_SMALL, corner_radius=R6,
                      fg_color=SURFACE, hover_color=CARD_HOVER,
                      text_color=TEXT_MUTED, border_width=1,
                      border_color=BORDER_LIGHT,
                      command=lambda: self._clear_images(img_container, self._img_widgets)
                      ).pack(side="left")

        # 投递间隔
        _section("⏱ 投递间隔(秒)")
        set_frame = ctk.CTkFrame(scroll, fg_color=CARD)
        set_frame.pack(fill="x", padx=S4, pady=(0, S16))

        min_var = ctk.StringVar(value=str(self._config.get("message_interval_min", 3)))
        max_var = ctk.StringVar(value=str(self._config.get("message_interval_max", 8)))

        ctk.CTkLabel(set_frame, text="最小", font=FONT_BODY,
                     text_color=TEXT).pack(side="left", padx=(0, S4))
        ctk.CTkEntry(set_frame, font=FONT_BODY, width=52, height=28,
                     corner_radius=R6, border_width=1, border_color=BORDER_LIGHT,
                     textvariable=min_var).pack(side="left", padx=(0, S12))
        ctk.CTkLabel(set_frame, text="最大", font=FONT_BODY,
                     text_color=TEXT).pack(side="left", padx=(0, S4))
        ctk.CTkEntry(set_frame, font=FONT_BODY, width=52, height=28,
                     corner_radius=R6, border_width=1, border_color=BORDER_LIGHT,
                     textvariable=max_var).pack(side="left")

        self._min_var = min_var
        self._max_var = max_var

    # ── 岗位行UI ──

    def _add_job_ui(self, container, widgets_list, jd: dict = None):
        row = ctk.CTkFrame(container, fg_color=SURFACE, corner_radius=R6)
        row.pack(fill="x", pady=(0, S4))
        row.grid_columnconfigure(0, weight=1)

        q_var = ctk.StringVar(value=(jd or {}).get("query", ""))
        entry = ctk.CTkEntry(row, font=FONT_BODY, height=28,
                             corner_radius=R6, border_width=1,
                             border_color=BORDER_LIGHT, textvariable=q_var)
        entry.grid(row=0, column=0, sticky="ew", padx=(S8, S4), pady=S4)

        scroll_var = ctk.StringVar(value=str((jd or {}).get("scroll_pages", 5)))
        scroll_entry = ctk.CTkEntry(row, font=FONT_SMALL, width=36,
                                    height=28, corner_radius=R6,
                                    border_width=1, border_color=BORDER_LIGHT,
                                    textvariable=scroll_var)
        scroll_entry.grid(row=0, column=1, padx=S4, pady=S4)
        ctk.CTkLabel(scroll_entry.master, text="页", font=FONT_TINY,
                     text_color=TEXT_DIM).place(relx=1.0, rely=0.5,
                                                anchor="w", x=2)

        def _del():
            row.destroy()
            nonlocal wd
            if wd in widgets_list:
                widgets_list.remove(wd)

        del_btn = ctk.CTkButton(row, text="✕", width=26, height=26,
                                corner_radius=R6, font=FONT_SMALL,
                                fg_color=CARD, hover_color="#f0e0e0",
                                text_color=TEXT_MUTED, border_width=1,
                                border_color=BORDER_LIGHT, command=_del)
        del_btn.grid(row=0, column=2, padx=(S4, S8), pady=S4)

        wd = {"row": row, "query_var": q_var, "scroll_var": scroll_var}
        widgets_list.append(wd)
        return wd

    # ── 图片UI ──

    def _add_image_dialog(self, container, widgets_list):
        paths = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if not paths:
            return
        for p in paths:
            lbl = ctk.CTkLabel(
                container, text=f"  {os.path.basename(p)}",
                font=FONT_SMALL, text_color=TEXT_MUTED, anchor="w"
            )
            lbl.pack(fill="x", pady=(0, S2))
            widgets_list.append({"label": lbl, "path": p})

    def _clear_images(self, container, widgets_list):
        for w in widgets_list:
            w["label"].destroy()
        widgets_list.clear()

    # ── 预览区 ──

    def _build_preview(self):
        for w in self._preview_frame.winfo_children():
            w.destroy()
        self._preview_frame.grid_rowconfigure(0, weight=1)
        self._preview_frame.grid_columnconfigure(0, weight=1)
        self._preview_label = ctk.CTkLabel(
            self._preview_frame, text="浏览器预览\n（启动后自动显示）",
            font=FONT_BODY, text_color=TEXT_DIM, anchor="center"
        )
        self._preview_label.grid(row=0, column=0, sticky="nsew")

    # ── 日志区 ──

    def _build_log(self):
        for w in self._log_frame.winfo_children():
            w.destroy()
        self._log_frame.grid_rowconfigure(0, weight=1)
        self._log_frame.grid_columnconfigure(0, weight=1)
        self._log_text = ctk.CTkTextbox(
            self._log_frame, font=FONT_MONO, corner_radius=R6,
            fg_color=CARD, border_width=1, border_color=BORDER_LIGHT,
            wrap="word", state="disabled"
        )
        self._log_text.grid(row=0, column=0, sticky="nsew", padx=S8, pady=S8)

        # 清空日志按钮
        clear_btn = ctk.CTkButton(
            self._log_frame, text="清空日志", font=FONT_TINY,
            height=22, width=70, corner_radius=R6,
            fg_color=SURFACE, hover_color=CARD_HOVER,
            text_color=TEXT_MUTED, border_width=1, border_color=BORDER_LIGHT,
            command=self._clear_log
        )
        clear_btn.place(relx=1.0, rely=0.0, x=-12, y=12, anchor="ne")

    # ── 底栏 ──

    def _build_botbar(self):
        self._botbar.grid_columnconfigure(6, weight=1)

        def _btn(text, cmd, color=ACCENT, **kw):
            return ctk.CTkButton(
                self._botbar, text=text, font=FONT_BTN,
                height=34, corner_radius=R8, border_width=0,
                fg_color=color, hover_color=ACCENT_HOVER,
                text_color=TEXT_INVERSE, command=cmd, **kw
            )

        btns = [
            ("▶ 开始投递", self._on_start, GREEN),
            ("⏹ 停止", self._on_stop, RED),
            ("🔗 测试连通性", self._on_test_connectivity, ACCENT),
            ("✓ 确认已登录", self._on_confirm_login, ACCENT),
            ("💾 保存配置", self._on_save, ACCENT),
            ("↺ 重置", self._on_reset, SLATE),
        ]

        for i, (text, cmd, color) in enumerate(btns):
            btn = _btn(text, cmd, color,
                       fg_color=color if color != ACCENT else ACCENT)
            btn.configure(hover_color=ACCENT_HOVER)
            if color == GREEN:
                btn.configure(hover_color="#236a42")
            elif color == RED:
                btn.configure(hover_color="#992e2e")
            btn.grid(row=0, column=i, padx=(S12 if i == 0 else S4, S4), pady=S8)

        # 保存按钮单独颜色（底栏右侧用浅色）
        self._save_btn = _btn("保存", self._on_save, ACCENT)
        self._save_btn.grid(row=0, column=6, padx=(S4, S12), pady=S8, sticky="e")

    # ═══════════════════════════════════════════════════
    #  事件处理器
    # ═══════════════════════════════════════════════════

    # ── 保存当前配置 ──

    def _save_current_config(self):
        """把UI上当前账号的配置写回 self._config。"""
        if not self._current_account_id:
            return
        acc = self._get_current_account()
        if not acc:
            return

        # 名称
        if self._name_var:
            acc["name"] = self._name_var.get()
        # 城市
        if self._city_var:
            acc["city"] = self._city_var.get()
        # 岗位
        jobs = []
        for w in self._job_widgets:
            query = w["query_var"].get().strip()
            if query:
                try:
                    pages = int(w["scroll_var"].get())
                except ValueError:
                    pages = 5
                jobs.append({"query": query, "scroll_pages": pages})
        if jobs:
            acc["jobs"] = jobs
        # 招呼语
        if self._greeting_text:
            acc["greeting_message"] = self._greeting_text.get("1.0", "end-1c").strip()
        # 图片
        acc["image_files"] = [w["path"] for w in self._img_widgets]
        # 间隔
        if self._min_var:
            try:
                self._config["message_interval_min"] = int(self._min_var.get())
            except ValueError:
                pass
        if self._max_var:
            try:
                self._config["message_interval_max"] = int(self._max_var.get())
            except ValueError:
                pass

    # ── 保存配置到文件 ──

    def _on_save(self):
        self._save_current_config()
        self._rebuild_account_sidebar_buttons()
        save_config(self._config)
        self._set_status("已保存", GREEN)
        self._log("OK", "配置已保存")

    def _rebuild_account_sidebar_buttons(self):
        """保存后刷新账号按钮文本（名称可能已改）。"""
        for acc in self._config.get("accounts", []):
            btn = self._acct_buttons.get(acc["id"])
            if btn:
                btn.configure(text=acc.get("name", "?"))

    # ── 重置 ──

    def _on_reset(self):
        if messagebox.askyesno("确认重置", "将重置所有配置为默认值，确定？"):
            self._config = reset_config()
            self._build_account_sidebar()
            self._rebuild_config_overlay()
            if self._config.get("accounts"):
                self._switch_account(self._config["accounts"][0]["id"])
            self._set_status("已重置", AMBER)
            self._log("WARN", "配置已重置为默认值")

    # ── 开始投递 ──

    def _on_start(self):
        if self._bot and self._bot.running:
            self._log("WARN", "已在运行中")
            return

        self._save_current_config()
        save_config(self._config)

        self._bot = BotCore(config=self._config,
                            log_callback=self._log,
                            screenshot_callback=self._on_screenshot)
        self._bot_thread = threading.Thread(target=self._bot.run, daemon=True)
        self._bot_thread.start()
        self._set_status("运行中...", GREEN)
        self._log("START", "▶ 自动投递已启动")
        self._poll_progress()

    # ── 停止 ──

    def _on_stop(self):
        if self._bot:
            self._bot.stop()
            self._set_status("停止中...", AMBER)
            self._log("WARN", "⏹ 正在停止...")
        else:
            self._log("WARN", "没有正在运行的实例")

    # ── 测试连通性 ──

    def _on_test_connectivity(self):
        if self._bot and self._bot.running:
            self._log("WARN", "请先停止运行再测试")
            return

        self._save_current_config()
        save_config(self._config)

        if not self._current_account_id:
            self._log("WARN", "请先选择账号")
            return

        acc = self._get_current_account()
        if not acc:
            return

        self._bot = BotCore(config=self._config,
                            log_callback=self._log,
                            screenshot_callback=self._on_screenshot)
        self._bot._start_screenshot_loop()

        def _test():
            self._bot.test_connectivity(acc)
            self._bot._stop_screenshot_loop()
            self._set_status("测试完成", SLATE if not self._bot.running else GREEN)

        threading.Thread(target=_test, daemon=True).start()
        self._set_status("测试中...", AMBER)

    # ── 确认已登录 ──

    def _on_confirm_login(self):
        if self._bot and self._bot.dp:
            if self._bot.confirm_login():
                self._set_status("已登录", GREEN)
            else:
                self._set_status("登录失败", RED)
        else:
            self._log("WARN", "请先点击「开始投递」打开浏览器")
            # 如果没有 bot，创建一个只打开浏览器的 bot
            self._bot = BotCore(config=self._config,
                                log_callback=self._log,
                                screenshot_callback=self._on_screenshot)
            success = self._bot.ensure_login(self._get_current_account() or {})
            if not success:
                self._set_status("需要手动登录", AMBER)
            else:
                self._confirm_login_inner()

    def _confirm_login_inner(self):
        if self._bot and self._bot.confirm_login():
            self._set_status("已登录", GREEN)
        else:
            self._set_status("登录失败", RED)

    # ── 清除日志 ──

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    # ── 关闭 ──

    def _on_close(self):
        if self._bot and self._bot.running:
            if not messagebox.askyesno("确认退出", "投递正在运行，确认退出？"):
                return
            self._bot.stop()
        self.destroy()

    # ═══════════════════════════════════════════════════
    #  回调
    # ═══════════════════════════════════════════════════

    def _log(self, level: str, msg: str):
        """彩色日志输出。"""
        colors = {
            "OK": GREEN, "INFO": TEXT, "WARN": AMBER,
            "ERROR": RED, "HEADER": ACCENT, "START": GREEN,
            "WAIT": AMBER,
        }
        tag = level
        self._log_text.configure(state="normal")
        self._log_text.insert("end", msg + "\n", tag)
        # 配置 tag 颜色
        c = colors.get(level, TEXT)
        self._log_text.tag_config(tag, foreground=c)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _on_screenshot(self, b64_data: str):
        """更新预览标签的图片。"""
        try:
            img_data = base64.b64decode(b64_data.split(",")[-1])
            img = Image.open(BytesIO(img_data))
            # 缩放到预览帧大小
            pw = self._preview_frame.winfo_width() - 20
            ph = self._preview_frame.winfo_height() - 20
            if pw > 20 and ph > 20:
                img.thumbnail((pw, ph), Image.LANCZOS)
                tk_img = ctk.CTkImage(light_image=img, dark_image=img,
                                      size=img.size)
                self._preview_label.configure(image=tk_img, text="")
        except Exception:
            pass

    def _poll_progress(self):
        """轮询投递进度。"""
        if not self._bot or not self._bot.running:
            self._set_status("已停止", SLATE)
            return
        prog = self._bot.get_progress()
        if prog.get("text"):
            self._set_status(prog["text"], GREEN)
        self.after(1000, self._poll_progress)


# ═══════════════════════════════════════════════════════
#  Entry
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    ctk.set_appearance_mode("Light")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
