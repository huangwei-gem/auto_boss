import os
import threading
import tkinter.filedialog
import tkinter.messagebox
from io import BytesIO

import customtkinter as ctk
from PIL import Image, ImageTk

from config import load_config, save_config, reset_config, validate_image_files
from bot_core import BotCore


# ── Color palette (macOS/iOS style) ──────────────────────
BG          = "#f5f5f7"
CARD        = "#ffffff"
BORDER      = "#e0e0e0"
DIVIDER     = "#efefef"
TEXT        = "#1d1d1f"
TEXT_DIM    = "#86868b"
ACCENT      = "#007193"
ACCENT_DARK = "#005a7a"
GREEN       = "#30d158"
RED         = "#ff453a"
YELLOW      = "#ffd60a"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Boss 直聘 · 自动投递")
        self.geometry("1420x800")
        self.minsize(900, 560)
        ctk.set_appearance_mode("light")
        self.configure(fg_color=BG)

        self.config = load_config()
        self.bot: BotCore | None = None
        self._screenshot_data: bytes | None = None
        self._preview_lock = threading.Lock()

        self._build_ui()
        self._populate_fields()

    # ═══════════════════════════════════════════════════════
    #  UI CONSTRUCTION
    # ═══════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Top bar ──
        top = ctk.CTkFrame(self, height=48, fg_color=CARD)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)
        self._draw_traffic_lights(top)

        # Status badge
        self.status_var = ctk.StringVar(value="就绪")
        status_frame = ctk.CTkFrame(top, fg_color=BG, corner_radius=12)
        status_frame.place(x=100, y=10)
        status_frame.pack_propagate(False)
        self._status_dot = ctk.CTkLabel(status_frame, text="●", font=ctk.CTkFont(size=14),
                                        text_color=TEXT_DIM)
        self._status_dot.pack(side="left", padx=(8, 4))
        ctk.CTkLabel(status_frame, textvariable=self.status_var,
                     font=ctk.CTkFont(size=13), text_color=TEXT).pack(side="left", padx=(0, 8))

        # ── Main content ──
        main = ctk.CTkFrame(self, fg_color=BG)
        main.pack(fill="both", expand=True)
        main.grid_columnconfigure(0, weight=0)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        self._sidebar(main)
        self._right_panel(main)

    def _draw_traffic_lights(self, parent: ctk.CTkFrame) -> None:
        colors = ("#ff5f57", "#febc2e", "#28c840")
        for i, color in enumerate(colors):
            cmd = self.destroy if i == 0 else lambda: None
            btn = ctk.CTkButton(parent, width=12, height=12, fg_color=color,
                                hover_color=color, text="", corner_radius=6,
                                command=cmd)
            btn.place(x=14 + i * 18, y=18)

    # ── LEFT SIDEBAR ───────────────────────────────────────

    def _sidebar(self, parent) -> None:
        frame = ctk.CTkFrame(parent, width=420, fg_color=CARD)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.pack_propagate(False)

        scroll = ctk.CTkScrollableFrame(frame, fg_color=CARD)
        scroll.pack(fill="both", expand=True)

        # Search settings
        self._section_header(scroll, "搜索设置")
        self._combo_row(scroll, "城市:", ["上海","北京","深圳","广州","杭州","成都","武汉","南京","西安","苏州"],
                        var_name="_city_var")
        self._entry_row(scroll, "岗位关键词:", var_name="_job_var")

        # Scroll pages & interval on same row
        row_a = ctk.CTkFrame(scroll, fg_color=BG, corner_radius=10)
        row_a.pack(fill="x", padx=16, pady=(4, 6))
        ctk.CTkLabel(row_a, text="滚动页数", anchor="w",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(12, 6), pady=9)
        self.scroll_var = ctk.StringVar(value="5")
        ctk.CTkEntry(row_a, textvariable=self.scroll_var, width=56,
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 16), pady=6)

        row_b = ctk.CTkFrame(scroll, fg_color=BG, corner_radius=10)
        row_b.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(row_b, text="发送间隔(秒)", anchor="w",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(12, 6), pady=9)
        int_f = ctk.CTkFrame(row_b, fg_color=CARD, corner_radius=8)
        int_f.pack(side="left", padx=(0, 12))
        self.interval_min_var = ctk.IntVar(value=3)
        self.interval_max_var = ctk.IntVar(value=8)
        ctk.CTkEntry(int_f, textvariable=self.interval_min_var, width=44,
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=4, pady=4)
        ctk.CTkLabel(int_f, text="—", text_color=TEXT_DIM,
                     font=ctk.CTkFont(size=13)).pack(side="left")
        ctk.CTkEntry(int_f, textvariable=self.interval_max_var, width=44,
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=4, pady=4)

        # Divider
        self._divider(scroll)

        # Greeting
        self._section_header(scroll, "打招呼语")
        self.msg_text = ctk.CTkTextbox(scroll, height=90, wrap="word", fg_color=BG, corner_radius=10)
        self.msg_text.pack(padx=16, pady=(0, 6))

        self._divider(scroll)

        # Images
        self._section_header(scroll, "图片附件")
        self.img_frame = ctk.CTkFrame(scroll, fg_color=BG, corner_radius=10)
        self.img_frame.pack(fill="x", padx=16, pady=(0, 6))
        self.img_labels: list[ctk.CTkLabel] = []

        img_btns = ctk.CTkFrame(self.img_frame, fg_color=BG)
        img_btns.pack(fill="x", padx=4, pady=4)
        ctk.CTkButton(img_btns, text="+ 添加图片", height=28, width=100,
                      font=ctk.CTkFont(size=12), corner_radius=6,
                      fg_color=BORDER, hover_color="#d0d0d0", text_color=TEXT,
                      command=self._add_image_dialog).pack(side="right", padx=3)
        ctk.CTkButton(img_btns, text="恢复默认", height=28, width=90,
                      font=ctk.CTkFont(size=12), corner_radius=6,
                      fg_color=BORDER, hover_color="#d0d0d0", text_color=TEXT,
                      command=self._reset_images).pack(side="right", padx=3)

        # Action buttons — outside scrollable so they stay visible
        self._action_buttons(frame)

    def _section_header(self, parent, title: str) -> None:
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 4))

    def _divider(self, parent) -> None:
        line = ctk.CTkFrame(parent, height=1, fg_color=DIVIDER)
        line.pack(fill="x", padx=16, pady=4)

    def _combo_row(self, parent, label: str, values: list, *, var_name: str) -> None:
        frame = ctk.CTkFrame(parent, fg_color=BG, corner_radius=10)
        frame.pack(fill="x", padx=16, pady=(0, 6))
        setattr(self, var_name, ctk.StringVar())
        ctk.CTkLabel(frame, text=label, width=80, anchor="w",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(12, 6), pady=10)
        ctk.CTkComboBox(frame, values=values, variable=getattr(self, var_name), width=180,
                        font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 12), pady=6)

    def _entry_row(self, parent, label: str = "", *, var_name: str = "_job_var") -> None:
        frame = ctk.CTkFrame(parent, fg_color=BG, corner_radius=10)
        frame.pack(fill="x", padx=16, pady=(0, 6))
        setattr(self, var_name, ctk.StringVar())
        ctk.CTkLabel(frame, text=label, width=80, anchor="w",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(12, 6), pady=10)
        ctk.CTkEntry(frame, textvariable=getattr(self, var_name), width=180,
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 12), pady=6)

    def _action_buttons(self, parent: ctk.CTkFrame) -> None:
        f = ctk.CTkFrame(parent, fg_color=CARD)
        f.pack(fill="x", side="bottom")

        # Primary action buttons
        btn_opts = dict(height=38, font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8)

        self.btn_start = ctk.CTkButton(f, text="开始投递", fg_color=ACCENT, hover_color=ACCENT_DARK,
                                       width=130, **btn_opts, command=self._on_start)
        self.btn_start.pack(side="left", padx=16, pady=12)

        self.btn_confirm_login = ctk.CTkButton(f, text="确认已登录", fg_color=ACCENT, hover_color=ACCENT_DARK,
                                               width=130, state="disabled", **btn_opts,
                                               command=self._on_confirm_login)
        self.btn_confirm_login.pack(side="left", padx=6, pady=12)

        self.btn_stop = ctk.CTkButton(f, text="停止", fg_color=RED, hover_color="#e0332b",
                                      width=130, state="disabled", **btn_opts,
                                      command=self._on_stop)
        self.btn_stop.pack(side="left", padx=6, pady=12)

        # Secondary actions
        sec = ctk.CTkFrame(f, fg_color=BG)
        sec.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(sec, text="保存配置", height=30, width=80,
                      font=ctk.CTkFont(size=11), corner_radius=6,
                      fg_color=CARD, hover_color=BORDER, text_color=TEXT,
                      command=self._save_current).pack(side="left", padx=3)
        ctk.CTkButton(sec, text="重置", height=30, width=80,
                      font=ctk.CTkFont(size=11), corner_radius=6,
                      fg_color=CARD, hover_color=BORDER, text_color=TEXT,
                      command=self._reset_all).pack(side="left", padx=3)

    # ── RIGHT PANEL ────────────────────────────────────────

    def _right_panel(self, parent) -> None:
        parent.grid_rowconfigure(0, weight=6)
        parent.grid_rowconfigure(1, weight=4)

        # Browser preview
        pv_outer = ctk.CTkFrame(parent, fg_color=CARD)
        pv_outer.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        pv_outer.grid_rowconfigure(1, weight=1)
        pv_outer.pack_propagate(False)

        # Toolbar
        pv_toolbar = ctk.CTkFrame(pv_outer, height=42, fg_color="#ececec")
        pv_toolbar.grid(row=0, column=0, sticky="ew")
        pv_toolbar.pack_propagate(False)

        for i, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
            dot = ctk.CTkFrame(pv_toolbar, width=12, height=12, fg_color=color)
            dot.place(x=14 + i * 18, y=15)
            dot.pack_propagate(False)

        # URL bar
        url_bar = ctk.CTkFrame(pv_toolbar, height=26, fg_color=BG, corner_radius=13)
        url_bar.place(x=76, y=8)
        url_bar.pack_propagate(False)
        ctk.CTkLabel(url_bar, text="  zhipin.com", font=ctk.CTkFont(size=12),
                     text_color=TEXT_DIM).pack(side="left")

        # Canvas
        self.preview_canvas = ctk.CTkCanvas(pv_outer, bg=BG, highlightthickness=0)
        self.preview_canvas.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.preview_label_id = self.preview_canvas.create_image(0, 0, anchor="nw")

        # Empty state in canvas
        self._empty_state = self.preview_canvas.create_text(
            300, 200, text="启动投递后将\n实时显示浏览器画面",
            font=ctk.CTkFont(size=14), fill=TEXT_DIM)

        # Log area
        lg_outer = ctk.CTkFrame(parent, fg_color=CARD)
        lg_outer.grid(row=1, column=1, sticky="nsew", padx=0, pady=(0, 0))
        lg_outer.grid_rowconfigure(1, weight=1)
        lg_outer.pack_propagate(False)

        lg_hdr = ctk.CTkFrame(lg_outer, height=36, fg_color=CARD)
        lg_hdr.grid(row=0, column=0, sticky="ew")
        lg_hdr.pack_propagate(False)
        ctk.CTkLabel(lg_hdr, text="运行日志", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT).pack(side="left", padx=12, pady=6)
        ctk.CTkButton(lg_hdr, text="清空", height=22, width=44, font=ctk.CTkFont(size=11),
                      corner_radius=4, fg_color=CARD, hover_color=BORDER, text_color=TEXT,
                      command=self._clear_log).pack(side="right", padx=12, pady=7)

        self.log_text = ctk.CTkTextbox(lg_outer, wrap="word", state="disabled",
                                       fg_color=BG, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

    # ═══════════════════════════════════════════════════════
    #  FIELD POPULATION
    # ═══════════════════════════════════════════════════════

    def _populate_fields(self) -> None:
        self._city_var.set(self.config.get("city", "上海"))
        self._job_var.set(self.config.get("job_query", "数据分析"))
        self.scroll_var.set(str(self.config.get("scroll_pages", 5)))
        self.interval_min_var.set(self.config.get("message_interval_min", 3))
        self.interval_max_var.set(self.config.get("message_interval_max", 8))
        self.msg_text.delete("1.0", "end")
        self.msg_text.insert("1.0", self.config.get("greeting_message", ""))
        self._render_image_list()

    def _render_image_list(self) -> None:
        for lbl in self.img_labels:
            lbl.destroy()
        self.img_labels.clear()
        images = self.config.get("image_files", [])
        if not images:
            ctk.CTkLabel(self.img_frame, text="暂无图片附件", text_color=TEXT_DIM,
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=6, pady=6)
            return
        for img in images:
            mark = "[ok]" if os.path.isfile(img) else "[!]"
            lbl = ctk.CTkLabel(self.img_frame, text=f"{mark}  {img}", width=350, anchor="w",
                               font=ctk.CTkFont(size=12))
            lbl.pack(side="left", padx=6, pady=3)
            self.img_labels.append(lbl)

    def _add_image_dialog(self) -> None:
        paths = tkinter.filedialog.askopenfilenames(
            title="选择图片文件",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All", "*.*")],
        )
        if not paths:
            return
        images = self.config.get("image_files", [])
        for p in paths:
            rel = os.path.relpath(p, start=os.getcwd())
            if rel not in images:
                images.append(rel)
        self.config["image_files"] = images
        self._render_image_list()

    def _reset_images(self) -> None:
        self.config["image_files"] = [
            "数据分析看板/看板1.png",
            "数据分析看板/看板2.png",
            "数据分析看板/看板3.png",
        ]
        self._render_image_list()

    # ═══════════════════════════════════════════════════════
    #  ACTIONS
    # ═══════════════════════════════════════════════════════

    def _on_start(self) -> None:
        self._save_current()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_var.set("运行中...")
        self._set_status_color(GREEN)
        self._clear_log()

        self.bot = BotCore(self.config, self._append_log, self._update_preview)
        self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
        self.bot_thread.start()

    def _run_bot(self) -> None:
        try:
            self.bot.start()
        finally:
            self.after(0, self._on_bot_finished)

    def _on_bot_finished(self) -> None:
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_confirm_login.configure(state="disabled")
        self.status_var.set("已完成")
        self._set_status_color(TEXT_DIM)

    def _on_stop(self) -> None:
        if self.bot:
            self.bot.stop()
        self.status_var.set("已停止")
        self._set_status_color(YELLOW)

    def _on_confirm_login(self) -> None:
        if self.bot:
            self.bot.confirm_login()
            self.btn_confirm_login.configure(state="disabled")
            self.status_var.set("登录已确认，等待bot继续...")
            self._set_status_color(GREEN)

    def _set_status_color(self, color: str) -> None:
        """Update the status dot color in the top bar."""
        self._status_dot.configure(text_color=color)

    # ═══════════════════════════════════════════════════════
    #  CONFIG
    # ═══════════════════════════════════════════════════════

    def _save_current(self) -> None:
        self.config["city"] = self._city_var.get()
        self.config["job_query"] = self._job_var.get()
        self.config["scroll_pages"] = int(self.scroll_var.get()) if self.scroll_var.get().isdigit() else 5
        self.config["message_interval_min"] = self.interval_min_var.get()
        self.config["message_interval_max"] = self.interval_max_var.get()
        self.config["greeting_message"] = self.msg_text.get("1.0", "end-1c")
        self.config["image_files"] = validate_image_files(self.config.get("image_files", []))
        save_config(self.config)
        tkinter.messagebox.showinfo("提示", "配置已保存")

    def _reset_all(self) -> None:
        if tkinter.messagebox.askyesno("确认", "确定要重置所有配置吗？"):
            self.config = reset_config()
            self._populate_fields()
            tkinter.messagebox.showinfo("提示", "配置已重置为默认值")

    # ═══════════════════════════════════════════════════════
    #  LOGGING
    # ═══════════════════════════════════════════════════════

    def _append_log(self, msg: str) -> None:
        self.after(0, lambda: self._do_append(msg))

    def _do_append(self, msg: str) -> None:
        self.log_text.configure(state="normal")

        if msg.startswith("[SUCCESS]"):
            color = GREEN; text = "  " + msg[9:]
        elif msg.startswith("[ERROR]"):
            color = RED; text = "  " + msg[7:]
        elif msg.startswith("[WARN]"):
            color = YELLOW; text = "  " + msg[6:]
        else:
            color = TEXT; text = "  " + msg

        self.log_text.insert("end", text)
        self.log_text.tag_add("c", "end-{}c".format(len(text)+1), "end-1c")
        self.log_text.tag_configure("c", foreground=color)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ═══════════════════════════════════════════════════════
    #  BROWSER PREVIEW
    # ═══════════════════════════════════════════════════════

    def _update_preview(self, screenshot_bytes: bytes) -> None:
        with self._preview_lock:
            self._screenshot_data = screenshot_bytes
        self.after(0, self._draw_preview)

    def _draw_preview(self) -> None:
        with self._preview_lock:
            data = self._screenshot_data
        if not data:
            return

        # Hide empty state
        self.preview_canvas.itemconfig(self._empty_state, state="hidden")

        try:
            img = Image.open(BytesIO(data))
            cw = self.preview_canvas.winfo_width() or 800
            ch = self.preview_canvas.winfo_height() or 480
            ratio = min(cw / img.width, ch / img.height)
            img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.preview_canvas.delete(self.preview_label_id)
            self.preview_label_id = self.preview_canvas.create_image(
                0, 0, anchor="nw", image=photo)
            self.preview_label_id._photo_ref = photo  # prevent GC
        except Exception:
            pass


if __name__ == "__main__":
    app = App()
    app.mainloop()
