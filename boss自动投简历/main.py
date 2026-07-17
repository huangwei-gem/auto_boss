import json
import os
import threading
import tkinter.filedialog
import tkinter.messagebox
from io import BytesIO

import customtkinter as ctk
from PIL import Image, ImageTk

from config import load_config, save_config, reset_config, validate_image_files
from bot_core import BotCore


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

    # ── LEFT PANEL ────────────────────────────────────────

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
                        ["上海", "北京", "深圳", "广州", "杭州", "成都", "武汉", "南京", "西安", "苏州"])

        # ── Multi-job keywords ──
        self._section_header(scroll, "岗位关键词", SPACING_LG)
        self.jobs_text = ctk.CTkTextbox(scroll, height=60, wrap="word", fg_color=BG_SECONDARY,
                                        corner_radius=RADIUS_MD)
        self.jobs_text.pack(fill="x", padx=SPACING_LG, pady=(0, SPACING_MD))

        # Manage jobs buttons
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
                    text_color=TEXT_SECONDARY).grid(row=0, column=0, padx=(SPACING_MD, 0), pady=SPACING_SM, sticky="w")
        self.scroll_var = ctk.StringVar(value="5")
        ctk.CTkEntry(row_frame, textvariable=self.scroll_var, width=60,
                    font=ctk.CTkFont(size=FONT_SIZE_SM), corner_radius=RADIUS_SM).grid(
                    row=0, column=0, padx=(SPACING_MD, SPACING_MD), pady=SPACING_SM, sticky="w")

        ctk.CTkLabel(row_frame, text="发送间隔(秒)", font=ctk.CTkFont(size=FONT_SIZE_SM),
                    text_color=TEXT_SECONDARY).grid(row=0, column=1, padx=(0, SPACING_MD), pady=SPACING_SM, sticky="e")
        int_frame = ctk.CTkFrame(row_frame, fg_color=CARD, corner_radius=RADIUS_SM)
        int_frame.grid(row=0, column=1, padx=(0, SPACING_MD), pady=SPACING_SM, sticky="e")
        int_frame.grid_columnconfigure(0, weight=1)
        int_frame.grid_columnconfigure(1, weight=0)
        int_frame.grid_columnconfigure(2, weight=1)

        self.interval_min_var = ctk.IntVar(value=3)
        self.interval_max_var = ctk.IntVar(value=8)
        ctk.CTkEntry(int_frame, textvariable=self.interval_min_var, width=40,
                    font=ctk.CTkFont(size=FONT_SIZE_SM), corner_radius=RADIUS_SM).grid(
                    row=0, column=0, padx=SPACING_XS, pady=SPACING_XS, sticky="ew")
        ctk.CTkLabel(int_frame, text="—", font=ctk.CTkFont(size=FONT_SIZE_SM),
                    text_color=TEXT_TERTIARY).grid(row=0, column=1, padx=SPACING_XS)
        ctk.CTkEntry(int_frame, textvariable=self.interval_max_var, width=40,
                    font=ctk.CTkFont(size=FONT_SIZE_SM), corner_radius=RADIUS_SM).grid(
                    row=0, column=2, padx=SPACING_XS, pady=SPACING_XS, sticky="ew")

        self._divider(scroll)

        # ── Greeting message ──
        self._section_header(scroll, "打招呼语", SPACING_LG)
        self.msg_text = ctk.CTkTextbox(scroll, height=100, wrap="word", fg_color=BG_SECONDARY,
                                      corner_radius=RADIUS_MD)
        self.msg_text.pack(fill="x", padx=SPACING_LG, pady=(0, SPACING_MD))

        self._divider(scroll)

        # ── Images section ──
        self._section_header(scroll, "图片附件", SPACING_LG)
        self.img_frame = ctk.CTkFrame(scroll, fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        self.img_frame.pack(fill="both", expand=True, padx=SPACING_LG, pady=(0, SPACING_MD))
        self.img_labels: list[dict] = []  # [{"text": lbl, "path": str, "frame": frame}]

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
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(size=FONT_SIZE_LG, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack(anchor="w", padx=SPACING_LG, pady=(pady, SPACING_SM))

    def _divider(self, parent) -> None:
        line = ctk.CTkFrame(parent, height=1, fg_color=BORDER_SUBTLE)
        line.pack(fill="x", padx=SPACING_LG, pady=SPACING_MD)

    def _select_row(self, parent, label: str, var_name: str, widget_type: str, values: list | None = None) -> None:
        frame = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        frame.pack(fill="x", padx=SPACING_LG, pady=(0, SPACING_MD))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=label, width=80, anchor="w",
                    font=ctk.CTkFont(size=FONT_SIZE_BASE), text_color=TEXT_SECONDARY).grid(
                    row=0, column=0, padx=(SPACING_MD, SPACING_SM), pady=SPACING_SM, sticky="w")

        if widget_type == "dropdown" and values:
            var = ctk.StringVar()
            setattr(self, var_name, var)
            ctk.CTkComboBox(frame, values=values, variable=var, width=0,
                          font=ctk.CTkFont(size=FONT_SIZE_BASE), corner_radius=RADIUS_SM).grid(
                          row=0, column=1, padx=(0, SPACING_MD), pady=SPACING_SM, sticky="ew")
        elif widget_type == "text":
            var = ctk.StringVar()
            setattr(self, var_name, var)
            ctk.CTkEntry(frame, textvariable=var, width=0,
                        font=ctk.CTkFont(size=FONT_SIZE_BASE), corner_radius=RADIUS_SM).grid(
                        row=0, column=1, padx=(0, SPACING_MD), pady=SPACING_SM, sticky="ew")

    def _input_row(self, parent, label: str, var_name: str, widget_type: str) -> None:
        self._select_row(parent, label, var_name, widget_type)

    def _action_buttons(self, parent: ctk.CTkFrame) -> None:
        btn_frame = ctk.CTkFrame(parent, fg_color=CARD)
        btn_frame.pack(fill="x", side="bottom")
        btn_frame.pack_propagate(False)
        btn_frame.configure(height=90)

        # Login check button
        login_frame = ctk.CTkFrame(btn_frame, fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        login_frame.pack(fill="x", padx=SPACING_LG, pady=(SPACING_MD, SPACING_XS))
        login_frame.grid_columnconfigure(0, weight=1)

        self.btn_check_login = ctk.CTkButton(
            login_frame, text="检查登录状态",
            height=28, font=ctk.CTkFont(size=FONT_SIZE_SM, weight="medium"),
            corner_radius=RADIUS_SM, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="#ffffff", command=self._check_login_status
        )
        self.btn_check_login.grid(row=0, column=0, padx=SPACING_XS, sticky="ew")

        self.login_status_label = ctk.CTkLabel(
            login_frame, text="未检查", font=ctk.CTkFont(size=FONT_SIZE_SM),
            text_color=TEXT_TERTIARY
        )
        self.login_status_label.grid(row=0, column=0, padx=(SPACING_LG, 0), pady=SPACING_SM, sticky="w")

        # Primary actions row
        primary_frame = ctk.CTkFrame(btn_frame, fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        primary_frame.pack(fill="x", padx=SPACING_LG, pady=SPACING_SM)
        primary_frame.grid_columnconfigure((0, 1, 2), weight=1)

        btn_opts = dict(
            height=32,
            font=ctk.CTkFont(size=FONT_SIZE_BASE, weight="medium"),
            corner_radius=RADIUS_SM
        )

        self.btn_start = ctk.CTkButton(
            primary_frame, text="开始投递", fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="#ffffff", **btn_opts, command=self._on_start
        )
        self.btn_start.grid(row=0, column=0, padx=SPACING_XS, sticky="ew")

        self.btn_stop = ctk.CTkButton(
            primary_frame, text="停止", fg_color=STATUS_ERROR, hover_color="#b91c1c",
            text_color="#ffffff", state="disabled", **btn_opts,
            command=self._on_stop
        )
        self.btn_stop.grid(row=0, column=1, padx=SPACING_XS, sticky="ew")

        # Secondary actions row
        secondary_frame = ctk.CTkFrame(btn_frame, fg_color=BG_SECONDARY, corner_radius=RADIUS_MD)
        secondary_frame.pack(fill="x", padx=SPACING_LG, pady=(SPACING_SM, SPACING_MD))
        secondary_frame.grid_columnconfigure((0, 1), weight=1)

        sec_btn_opts = dict(
            height=26,
            font=ctk.CTkFont(size=FONT_SIZE_SM),
            corner_radius=RADIUS_SM,
            fg_color=CARD,
            hover_color=BG_TERTIARY,
            text_color=TEXT_SECONDARY
        )

        ctk.CTkButton(secondary_frame, text="保存配置", **sec_btn_opts,
                     command=self._save_current).grid(row=0, column=0, padx=SPACING_XS, sticky="ew")
        ctk.CTkButton(secondary_frame, text="重置配置", **sec_btn_opts,
                     command=self._reset_all).grid(row=0, column=1, padx=SPACING_XS, sticky="ew")
