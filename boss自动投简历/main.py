"""
Boss直聘 · 自动投递工具 — 主入口 + GUI 界面

依赖 config.py (配置) + bot_core.py (自动化引擎)
"""
import json
import os
import threading
import tkinter.filedialog
import tkinter.messagebox
from io import BytesIO

import customtkinter as ctk
from PIL import Image, ImageTk

from config import load_config, save_config, reset_config, validate_config
from bot_core import BotCore
from DrissionPage import ChromiumPage


# ── Design System ────────────────────────────────────────
BG_PRIMARY   = "#fafafa"
BG_SECONDARY = "#f4f4f5"
BG_TERTIARY  = "#e4e4e7"
CARD         = "#ffffff"
BORDER       = "#d4d4d8"
BORDER_SUBTLE= "#e4e4e7"

TEXT_PRIMARY = "#18181b"
TEXT_SECONDARY = "#52525b"
TEXT_TERTIARY = "#a1a1aa"

ACCENT       = "#4f46e5"
ACCENT_HOVER = "#4338ca"
ACCENT_LIGHT = "#eef2ff"

STATUS_SUCCESS = "#16a34a"
STATUS_ERROR   = "#dc2626"
STATUS_WARN    = "#ca8a04"
STATUS_IDLE    = "#71717a"
BG_SUCCESS = "#f0fdf4"
BG_ERROR   = "#fef2f2"

RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 12
SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 12
SPACING_LG = 16

FONT_SIZE_SM = 11
FONT_SIZE_BASE = 13
FONT_SIZE_LG = 15


class App(ctk.CTk):
    """Boss直聘自动投递 GUI 应用。"""

    def __init__(self):
        super().__init__()
        self.title("Boss 直聘 · 自动投递工具")
        self.geometry("1366x768")
        self.minsize(1024, 640)
        ctk.set_appearance_mode("light")
        self.configure(fg_color=BG_PRIMARY)

        self.config = load_config()
        self.bot: BotCore | None = None
        self._screenshot_data: bytes | None = None
        self._preview_lock = threading.Lock()
        self._login_check_thread: threading.Thread | None = None

        # 投递统计
        self._stats = {"applied": 0, "skipped": 0, "total": 0}

        self._build_ui()
        self._populate_fields()

    # ═══════════════════════════════════════════════════════
    #  UI CONSTRUCTION
    # ═══════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=7)
        self.grid_rowconfigure(0, weight=1)

        self._top_bar()
        self._main_content()

    def _top_bar(self) -> None:
        top = ctk.CTkFrame(self, height=44, fg_color=CARD)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.pack_propagate(False)

        ctk.CTkLabel(
            top, text="Boss 直聘 · 自动投递",
            font=ctk.CTkFont(size=FONT_SIZE_LG, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack(side="left", padx=SPACING_LG, pady=SPACING_MD)

        ctk.CTkFrame(top, width=0).pack(side="left", expand=True)

        self.status_var = ctk.StringVar(value="就绪")
        status_frame = ctk.CTkFrame(top, fg_color=BG_SECONDARY, corner_radius=RADIUS_LG)
        status_frame.pack(side="right", padx=SPACING_LG, pady=SPACING_SM)
        status_frame.pack_propagate(False)
        status_frame.configure(height=28)

        self._status_dot = ctk.CTkLabel(
            status_frame, text="●", font=ctk.CTkFont(size=10),
            text_color=STATUS_IDLE
        )
        self._status_dot.pack(side="left", padx=(SPACING_MD, SPACING_SM))

        ctk.CTkLabel(
            status_frame, textvariable=self.status_var,
            font=ctk.CTkFont(size=FONT_SIZE_SM),
            text_color=TEXT_SECONDARY
        ).pack(side="left", padx=(0, SPACING_MD))

    def _main_content(self) -> None:
        main_frame = ctk.CTkFrame(self, fg_color=BG_PRIMARY)
        main_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=0)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        self._left_panel(main_frame)
        self._right_panel(main_frame)

    # ═══════════════════════════════════════════════════════
    #  LEFT PANEL — 配置
    # ═══════════════════════════════════════════════════════

    def _left_panel(self, parent) -> None:
        panel = ctk.CTkFrame(parent, width=380, fg_color=CARD)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.pack_propagate(False)
        panel.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(panel, fg_color=CARD)
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1)

        # ── Job search settings ──
        self._section_header(scroll, "搜索设置", SPACING_LG)

        self._select_row(scroll, "目标城市:", "_city_var", "dropdown",
                         ["上海", "北京", "深圳", "广州", "杭州", "成都",
                          "武汉", "南京", "西安", "苏州"])

        # ── Job keywords ──
        self._section_header(scroll, "岗位关键词", SPACING_LG)
        self.jobs_text = ctk.CTkTextbox(scroll, height=60, wrap="word",
                                        fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        self.jobs_text.pack(fill="x", padx=SPACING_LG, pady=(0, SPACING_MD))

        job_btns = ctk.CTkFrame(scroll, fg_color=BG_SECONDARY, corner_radius=RADIUS_SM)
        job_btns.pack(fill="x", padx=SPACING_LG, pady=(0, SPACING_MD))
        job_btns.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(job_btns, text="+ 添加岗位", height=26, width=0,
                      font=ctk.CTkFont(size=FONT_SIZE_SM), corner_radius=RADIUS_SM,
                      fg_color=CARD, hover_color=BG_TERTIARY, text_color=TEXT_SECONDARY,
                      command=self._add_job_dialog).grid(row=0, column=0, padx=SPACING_XS, sticky="ew")
        ctk.CTkButton(job_btns, text="- 删除选中", height=26, width=0,
                      font=ctk.CTkFont(size=FONT_SIZE_SM), corner_radius=RADIUS_SM,
                      fg_color=CARD, hover_color=BG_TERTIARY, text_color=TEXT_SECONDARY,
                      command=self._remove_job_dialog).grid(row=0, column=1, padx=SPACING_XS, sticky="ew")

        # ── Pagination & interval ──
        row_frame = ctk.CTkFrame(scroll, fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        row_frame.pack(fill="x", padx=SPACING_LG, pady=(SPACING_SM, SPACING_MD))
        row_frame.grid_columnconfigure(0, weight=1)
        row_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row_frame, text="滚动页数", font=ctk.CTkFont(size=FONT_SIZE_SM),
                     text_color=TEXT_SECONDARY).grid(row=0, column=0, padx=(SPACING_MD, 0),
                                                     pady=SPACING_SM, sticky="w")
        self.scroll_var = ctk.StringVar(value="5")
        ctk.CTkEntry(row_frame, textvariable=self.scroll_var, width=60,
                     font=ctk.CTkFont(size=FONT_SIZE_SM), corner_radius=RADIUS_SM).grid(
                     row=0, column=0, padx=(SPACING_MD, SPACING_MD), pady=SPACING_SM, sticky="w")

        ctk.CTkLabel(row_frame, text="发送间隔(秒)", font=ctk.CTkFont(size=FONT_SIZE_SM),
                     text_color=TEXT_SECONDARY).grid(row=0, column=1, padx=(0, SPACING_MD),
                                                     pady=SPACING_SM, sticky="e")
        int_frame = ctk.CTkFrame(row_frame, fg_color=CARD, corner_radius=RADIUS_SM)
        int_frame.grid(row=0, column=1, padx=(0, SPACING_MD), pady=SPACING_SM, sticky="e")
        int_frame.grid_columnconfigure(0, weight=1)
        int_frame.grid_columnconfigure(1, weight=0)
        int_frame.grid_columnconfigure(2, weight=1)

        self.interval_min_var = ctk.IntVar(value=3)
        self.interval_max_var = ctk.IntVar(value=8)
        ctk.CTkEntry(int_frame, textvariable=self.interval_min_var, width=40,
                     font=ctk.CTkFont(size=FONT_SIZE_SM), corner_radius=RADIUS_SM).grid(
                     row=0, column=0, padx=SPACING_XS, pady=SPACING_XS)
        ctk.CTkLabel(int_frame, text="—", font=ctk.CTkFont(size=FONT_SIZE_SM),
                     text_color=TEXT_TERTIARY).grid(row=0, column=1, padx=SPACING_XS)
        ctk.CTkEntry(int_frame, textvariable=self.interval_max_var, width=40,
                     font=ctk.CTkFont(size=FONT_SIZE_SM), corner_radius=RADIUS_SM).grid(
                     row=0, column=2, padx=SPACING_XS, pady=SPACING_XS)

        self._divider(scroll)

        # ── Greeting message ──
        self._section_header(scroll, "打招呼语", SPACING_LG)
        self.msg_text = ctk.CTkTextbox(scroll, height=100, wrap="word",
                                       fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        self.msg_text.pack(fill="x", padx=SPACING_LG, pady=(0, SPACING_MD))

        self._divider(scroll)

        # ── Images section ──
        self._section_header(scroll, "图片附件", SPACING_LG)
        self.img_frame = ctk.CTkFrame(scroll, fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        self.img_frame.pack(fill="both", expand=True, padx=SPACING_LG, pady=(0, SPACING_MD))
        self.img_labels: list[dict] = []

        img_btns = ctk.CTkFrame(self.img_frame, fg_color=BG_SECONDARY)
        img_btns.pack(fill="x", padx=SPACING_SM, pady=SPACING_SM)

        ctk.CTkButton(img_btns, text="+ 添加图片", height=26, width=0,
                      font=ctk.CTkFont(size=FONT_SIZE_SM), corner_radius=RADIUS_SM,
                      fg_color=CARD, hover_color=BG_TERTIARY, text_color=TEXT_SECONDARY,
                      command=self._add_image_dialog).pack(side="left", padx=SPACING_XS, expand=True)
        ctk.CTkButton(img_btns, text="恢复默认", height=26, width=0,
                      font=ctk.CTkFont(size=FONT_SIZE_SM), corner_radius=RADIUS_SM,
                      fg_color=CARD, hover_color=BG_TERTIARY, text_color=TEXT_SECONDARY,
                      command=self._reset_images).pack(side="left", padx=SPACING_XS, expand=True)

        # ── Action buttons (fixed at bottom) ──
        self._action_buttons(panel)

    def _section_header(self, parent, title: str, pady: int = SPACING_LG) -> None:
        ctk.CTkLabel(parent, text=title,
                     font=ctk.CTkFont(size=FONT_SIZE_LG, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(anchor="w", padx=SPACING_LG,
                                                   pady=(pady, SPACING_SM))

    def _divider(self, parent) -> None:
        line = ctk.CTkFrame(parent, height=1, fg_color=BORDER_SUBTLE)
        line.pack(fill="x", padx=SPACING_LG, pady=SPACING_MD)

    def _select_row(self, parent, label: str, var_name: str,
                    widget_type: str, values: list | None = None) -> None:
        frame = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        frame.pack(fill="x", padx=SPACING_LG, pady=(0, SPACING_MD))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=label, width=80, anchor="w",
                     font=ctk.CTkFont(size=FONT_SIZE_BASE),
                     text_color=TEXT_SECONDARY).grid(
                     row=0, column=0, padx=(SPACING_MD, SPACING_SM),
                     pady=SPACING_SM, sticky="w")

        if widget_type == "dropdown" and values:
            var = ctk.StringVar()
            setattr(self, var_name, var)
            ctk.CTkComboBox(frame, values=values, variable=var, width=0,
                           font=ctk.CTkFont(size=FONT_SIZE_BASE),
                           corner_radius=RADIUS_SM).grid(
                           row=0, column=1, padx=(0, SPACING_MD),
                           pady=SPACING_SM, sticky="ew")
        elif widget_type == "text":
            var = ctk.StringVar()
            setattr(self, var_name, var)
            ctk.CTkEntry(frame, textvariable=var, width=0,
                        font=ctk.CTkFont(size=FONT_SIZE_BASE),
                        corner_radius=RADIUS_SM).grid(
                        row=0, column=1, padx=(0, SPACING_MD),
                        pady=SPACING_SM, sticky="ew")

    # ═══════════════════════════════════════════════════════
    #  RIGHT PANEL — 预览 + 日志
    # ═══════════════════════════════════════════════════════

    def _right_panel(self, parent) -> None:
        panel = ctk.CTkFrame(parent, fg_color=BG_PRIMARY)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=3)
        panel.grid_rowconfigure(1, weight=0)
        panel.grid_rowconfigure(2, weight=2)

        # ── Screenshot preview ──
        preview_title = ctk.CTkLabel(
            panel, text="浏览器预览", anchor="w",
            font=ctk.CTkFont(size=FONT_SIZE_BASE, weight="bold"),
            text_color=TEXT_PRIMARY
        )
        preview_title.grid(row=0, column=0, sticky="nw", padx=SPACING_LG, pady=(SPACING_LG, 0))

        self.preview_label = ctk.CTkLabel(
            panel, text="启动投递后将在此处显示浏览器画面\n\n点击「开始投递」按钮",
            fg_color=CARD, corner_radius=RADIUS_MD,
            font=ctk.CTkFont(size=FONT_SIZE_SM),
            text_color=TEXT_TERTIARY
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew", padx=SPACING_LG, pady=(SPACING_SM, SPACING_MD))

        # ── 统计面板 ──
        self._stats_frame = ctk.CTkFrame(panel, fg_color=CARD, corner_radius=RADIUS_MD)
        self._stats_frame.grid(row=1, column=0, sticky="ew", padx=SPACING_LG, pady=(0, SPACING_MD))
        for i in range(4):
            self._stats_frame.grid_columnconfigure(i, weight=1)

        self._stat_widgets = {}
        for idx, (key, label, color) in enumerate([
            ("total", "总计", TEXT_PRIMARY),
            ("applied", "已投递", STATUS_SUCCESS),
            ("skipped", "跳过", STATUS_WARN),
            ("remaining", "剩余", TEXT_SECONDARY),
        ]):
            f = ctk.CTkFrame(self._stats_frame, fg_color=CARD)
            f.grid(row=0, column=idx, padx=SPACING_SM, pady=SPACING_SM, sticky="nsew")
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=FONT_SIZE_SM),
                         text_color=TEXT_TERTIARY).pack()
            val = ctk.CTkLabel(f, text="0", font=ctk.CTkFont(size=22, weight="bold"),
                              text_color=color)
            val.pack()
            self._stat_widgets[key] = val

        # ── Log output ──
        log_title = ctk.CTkLabel(
            panel, text="运行日志", anchor="w",
            font=ctk.CTkFont(size=FONT_SIZE_BASE, weight="bold"),
            text_color=TEXT_PRIMARY
        )
        log_title.grid(row=2, column=0, sticky="nw", padx=SPACING_LG, pady=(0, SPACING_SM))

        self.log_text = ctk.CTkTextbox(
            panel, wrap="word", state="disabled",
            fg_color=CARD, corner_radius=RADIUS_MD,
            font=ctk.CTkFont(size=FONT_SIZE_SM, family="Consolas")
        )
        self.log_text.grid(row=2, column=0, sticky="nsew",
                           padx=SPACING_LG, pady=(0, SPACING_LG))
        self.log_text.configure(text_color=TEXT_SECONDARY)

    # ═══════════════════════════════════════════════════════
    #  ACTION BUTTONS
    # ═══════════════════════════════════════════════════════

    def _action_buttons(self, parent: ctk.CTkFrame) -> None:
        btn_frame = ctk.CTkFrame(parent, fg_color=CARD)
        btn_frame.pack(fill="x", side="bottom")
        btn_frame.pack_propagate(False)
        btn_frame.configure(height=90)

        # Login check
        login_frame = ctk.CTkFrame(btn_frame, fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        login_frame.pack(fill="x", padx=SPACING_LG, pady=(SPACING_MD, SPACING_XS))
        login_frame.grid_columnconfigure(0, weight=1)

        self.btn_check_login = ctk.CTkButton(
            login_frame, text="检查登录状态", height=28,
            font=ctk.CTkFont(size=FONT_SIZE_SM, weight="bold"),
            corner_radius=RADIUS_SM, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="#ffffff", command=self._check_login_status
        )
        self.btn_check_login.grid(row=0, column=0, padx=SPACING_XS, sticky="ew")

        self.login_status_label = ctk.CTkLabel(
            login_frame, text="未检查", font=ctk.CTkFont(size=FONT_SIZE_SM),
            text_color=TEXT_TERTIARY
        )
        self.login_status_label.grid(row=0, column=0, padx=(SPACING_LG, 0),
                                     pady=SPACING_SM, sticky="w")

        # Primary actions
        primary_frame = ctk.CTkFrame(btn_frame, fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        primary_frame.pack(fill="x", padx=SPACING_LG, pady=SPACING_SM)
        primary_frame.grid_columnconfigure((0, 1, 2), weight=1)

        btn_opts = dict(height=32,
                        font=ctk.CTkFont(size=FONT_SIZE_BASE, weight="bold"),
                        corner_radius=RADIUS_SM)

        self.btn_start = ctk.CTkButton(
            primary_frame, text="开始投递", fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="#ffffff", **btn_opts, command=self._on_start
        )
        self.btn_start.grid(row=0, column=0, padx=SPACING_XS, sticky="ew")

        self.btn_stop = ctk.CTkButton(
            primary_frame, text="停止", fg_color=STATUS_ERROR, hover_color="#b91c1c",
            text_color="#ffffff", state="disabled", **btn_opts, command=self._on_stop
        )
        self.btn_stop.grid(row=0, column=1, padx=SPACING_XS, sticky="ew")

        # Secondary actions
        secondary_frame = ctk.CTkFrame(btn_frame, fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        secondary_frame.pack(fill="x", padx=SPACING_LG, pady=(SPACING_SM, SPACING_MD))
        secondary_frame.grid_columnconfigure((0, 1), weight=1)

        sec_btn_opts = dict(height=26, font=ctk.CTkFont(size=FONT_SIZE_SM),
                           corner_radius=RADIUS_SM, fg_color=CARD,
                           hover_color=BG_TERTIARY, text_color=TEXT_SECONDARY)

        ctk.CTkButton(secondary_frame, text="保存配置", **sec_btn_opts,
                      command=self._save_current).grid(row=0, column=0, padx=SPACING_XS, sticky="ew")
        ctk.CTkButton(secondary_frame, text="重置配置", **sec_btn_opts,
                      command=self._reset_all).grid(row=0, column=1, padx=SPACING_XS, sticky="ew")

    # ═══════════════════════════════════════════════════════
    #  CALLBACKS
    # ═══════════════════════════════════════════════════════

    def _populate_fields(self) -> None:
        """从配置填充 UI 字段值。"""
        # 城市下拉用 set() 方法
        if hasattr(self, "_city_var"):
            self._city_var.set(self.config.get("city", "上海"))

        # 岗位关键词
        if hasattr(self, "jobs_text"):
            self.jobs_text.delete("1.0", "end")
            self.jobs_text.insert("1.0", self.config.get("job_query", ""))

        # 滚动页数
        if hasattr(self, "scroll_var"):
            self.scroll_var.set(str(self.config.get("scroll_pages", 5)))

        # 间隔
        if hasattr(self, "interval_min_var"):
            self.interval_min_var.set(self.config.get("message_interval_min", 3))
        if hasattr(self, "interval_max_var"):
            self.interval_max_var.set(self.config.get("message_interval_max", 8))

        # 打招呼语
        if hasattr(self, "msg_text"):
            self.msg_text.delete("1.0", "end")
            self.msg_text.insert("1.0", self.config.get("greeting_message", ""))

        # 图片列表
        self._render_images(self.config.get("image_files", []))

    def _render_images(self, paths: list[str]) -> None:
        """在 UI 中渲染图片附件列表。"""
        if not hasattr(self, "img_labels"):
            return
        for item in self.img_labels:
            item["frame"].destroy()
        self.img_labels.clear()

        for p in paths:
            exists = os.path.isfile(p)
            bg = BG_SUCCESS if exists else BG_ERROR
            row_frame = ctk.CTkFrame(self.img_frame, fg_color=CARD, corner_radius=RADIUS_SM)
            row_frame.pack(fill="x", padx=SPACING_SM, pady=SPACING_XS)
            icon = "🖼️" if exists else "⚠️"
            lbl = ctk.CTkLabel(row_frame, text=f"{icon} {os.path.basename(p)}",
                               font=ctk.CTkFont(size=FONT_SIZE_SM), anchor="w")
            lbl.pack(side="left", padx=SPACING_SM, pady=SPACING_XS)
            self.img_labels.append({"frame": row_frame, "path": p,
                                    "label": lbl, "exists": exists})

    def _gather_config(self) -> dict:
        """从 UI 控件收集当前配置。"""
        cfg = {}
        cfg["city"] = self._city_var.get() if hasattr(self, "_city_var") else "上海"

        if hasattr(self, "jobs_text"):
            raw = self.jobs_text.get("1.0", "end").strip()
        else:
            raw = ""
        cfg["job_query"] = raw.split("\n")[0] if raw else ""

        try:
            cfg["scroll_pages"] = int(self.scroll_var.get())
        except (ValueError, AttributeError):
            cfg["scroll_pages"] = 5

        try:
            cfg["message_interval_min"] = int(self.interval_min_var.get())
            cfg["message_interval_max"] = int(self.interval_max_var.get())
        except (ValueError, AttributeError):
            cfg["message_interval_min"] = 3
            cfg["message_interval_max"] = 8

        if hasattr(self, "msg_text"):
            cfg["greeting_message"] = self.msg_text.get("1.0", "end").strip()
        else:
            cfg["greeting_message"] = ""

        cfg["image_files"] = [item["path"] for item in getattr(self, "img_labels", [])]
        return cfg

    def _update_stats(self) -> None:
        """刷新统计面板。"""
        self._stat_widgets["total"].configure(text=str(self._stats["total"]))
        self._stat_widgets["applied"].configure(text=str(self._stats["applied"]))
        self._stat_widgets["skipped"].configure(text=str(self._stats["skipped"]))
        remaining = max(0, self._stats["total"] - self._stats["applied"] - self._stats["skipped"])
        self._stat_widgets["remaining"].configure(text=str(remaining))

    # ── 配置回调 ──

    def _save_current(self) -> None:
        """保存当前 UI 配置到文件。"""
        cfg = self._gather_config()
        errors = validate_config(cfg)
        if errors:
            tkinter.messagebox.showerror("配置错误", "\n".join(errors))
            return
        save_config(cfg)
        self.config = cfg
        tkinter.messagebox.showinfo("提示", "配置已保存")

    def _reset_all(self) -> None:
        """重置为默认配置。"""
        if tkinter.messagebox.askyesno("确认", "确定要重置所有配置吗？"):
            self.config = reset_config()
            self._populate_fields()
            tkinter.messagebox.showinfo("提示", "配置已重置")

    def _add_job_dialog(self) -> None:
        """弹出对话框添加岗位关键词。"""
        dialog = ctk.CTkInputDialog(title="添加岗位", text="输入岗位关键词：")
        keyword = dialog.get_input().strip()
        if keyword:
            current = self.jobs_text.get("1.0", "end").strip()
            lines = [l.strip() for l in current.split("\n") if l.strip()]
            if keyword not in lines:
                lines.append(keyword)
                self.jobs_text.delete("1.0", "end")
                self.jobs_text.insert("1.0", "\n".join(lines))

    def _remove_job_dialog(self) -> None:
        """弹出对话框删除岗位关键词。"""
        current = self.jobs_text.get("1.0", "end").strip()
        lines = [l.strip() for l in current.split("\n") if l.strip()]
        if not lines:
            tkinter.messagebox.showinfo("提示", "没有可删除的岗位")
            return
        dialog = ctk.CTkInputDialog(title="删除岗位", text="输入要删除的岗位关键词：")
        keyword = dialog.get_input().strip()
        if keyword and keyword in lines:
            lines.remove(keyword)
            self.jobs_text.delete("1.0", "end")
            self.jobs_text.insert("1.0", "\n".join(lines))

    def _add_image_dialog(self) -> None:
        """文件选择对话框添加作品图片。"""
        files = tkinter.filedialog.askopenfilenames(
            title="选择图片文件",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if files:
            current_paths = [item["path"] for item in self.img_labels]
            new_paths = list(current_paths)
            for f in files:
                if f not in new_paths:
                    new_paths.append(f)
            self._render_images(new_paths)

    def _reset_images(self) -> None:
        """恢复默认图片路径。"""
        from config import load_config
        cfg = load_config()
        self._render_images(cfg.get("image_files", []))

    # ── Bot 回调 ──

    def _log_callback(self, msg: str) -> None:
        """来自 BotCore 的日志回调（在后台线程调用）。"""
        self.after(0, self._append_log, msg)

    def _append_log(self, msg: str) -> None:
        """在主线程追加日志。"""
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

        # 同步更新状态指示器
        if "[ERROR]" in msg:
            self._set_status("错误", STATUS_ERROR)
        elif "[SUCCESS]" in msg:
            self._set_status("成功", STATUS_SUCCESS)
            # 尝试从日志中解析统计
            if "投递完成" in msg:
                import re
                m = re.search(r"成功 (\d+)，跳过/失败 (\d+)，总计 (\d+)", msg)
                if m:
                    self._stats["applied"] = int(m.group(1))
                    self._stats["skipped"] = int(m.group(2))
                    self._stats["total"] = int(m.group(3))
                    self._update_stats()
        elif "[WARN]" in msg:
            self._set_status("警告", STATUS_WARN)

    def _screenshot_callback(self, data: bytes) -> None:
        """来自 BotCore 的截图回调（在后台线程调用）。"""
        self._screenshot_data = data
        self.after(0, self._update_preview)

    def _progress_callback(self, stats: dict) -> None:
        """来自 BotCore 的实时进度回调（在后台线程调用）。"""
        self._stats.update(stats)
        self.after(0, self._update_stats)

    def _update_preview(self) -> None:
        """在主线程更新截图预览。"""
        if not self._screenshot_data or not hasattr(self, "preview_label"):
            return
        with self._preview_lock:
            try:
                img = Image.open(BytesIO(self._screenshot_data))
                # 缩放适配
                pw = self.preview_label.winfo_width() or 600
                ph = self.preview_label.winfo_height() or 400
                if pw > 50 and ph > 50:
                    img.thumbnail((pw - 20, ph - 20), Image.LANCZOS)
                    tk_img = ImageTk.PhotoImage(img)
                    self.preview_label.configure(image=tk_img, text="")
                    self.preview_label.image = tk_img  # type: ignore[attr-defined]
            except Exception:
                pass

    def _set_status(self, text: str, color: str = STATUS_IDLE) -> None:
        """更新顶部状态栏。"""
        if hasattr(self, "status_var"):
            self.status_var.set(text)
        if hasattr(self, "_status_dot"):
            self._status_dot.configure(text_color=color)

    # ── 按钮回调 ──

    def _check_login_status(self) -> None:
        """检查登录状态按钮。"""
        if self._login_check_thread and self._login_check_thread.is_alive():
            return

        def check():
            cfg = self._gather_config()
            # 临时创建一个 BotCore 仅用于检查登录
            temp_bot = BotCore(cfg, self._log_callback)
            temp_bot.dp = ChromiumPage()
            logged_in = temp_bot.check_login_status()
            if logged_in:
                self.after(0, lambda: self.login_status_label.configure(
                    text="✅ 已登录", text_color=STATUS_SUCCESS))
                self.after(0, lambda: self._set_status("已登录", STATUS_SUCCESS))
            else:
                self.after(0, lambda: self.login_status_label.configure(
                    text="❌ 未登录", text_color=STATUS_ERROR))
                self.after(0, lambda: self._set_status("未登录", STATUS_ERROR))
            try:
                temp_bot.dp.quit()
            except Exception:
                pass

        self._login_check_thread = threading.Thread(target=check, daemon=True)
        self._login_check_thread.start()
        self._set_status("检查登录中...", STATUS_WARN)

    def _on_start(self) -> None:
        """开始投递按钮。"""
        if self.bot and self.bot.running:
            tkinter.messagebox.showinfo("提示", "投递正在进行中")
            return

        cfg = self._gather_config()
        errors = validate_config(cfg)
        if errors:
            tkinter.messagebox.showerror("配置错误", "\n".join(errors))
            return

        # 保存配置
        self.config = cfg
        save_config(cfg)

        self._stats = {"applied": 0, "skipped": 0, "total": 0}
        self._update_stats()

        self.btn_start.configure(state="disabled", text="运行中...")
        self.btn_stop.configure(state="normal")
        self._set_status("投递中...", STATUS_WARN)

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        self.bot = BotCore(cfg, self._log_callback, self._screenshot_callback, self._progress_callback)

        thread = threading.Thread(target=self.bot.start, daemon=True)
        thread.start()

        # 启动监控线程，检测 bot 结束
        def _monitor():
            thread.join()
            self.after(0, self._on_bot_finished)

        threading.Thread(target=_monitor, daemon=True).start()

    def _on_bot_finished(self) -> None:
        """Bot 线程结束后恢复 UI。"""
        self.btn_start.configure(state="normal", text="开始投递")
        self.btn_stop.configure(state="disabled")
        if self._stats["applied"] > 0:
            self._set_status("完成", STATUS_SUCCESS)
        else:
            self._set_status("已停止", STATUS_IDLE)

    def _on_stop(self) -> None:
        """停止投递按钮。"""
        if self.bot:
            self.bot.stop()


# ═══════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    app = App()
    app.mainloop()
           