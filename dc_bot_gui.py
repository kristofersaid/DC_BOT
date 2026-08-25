# ==========================================
# FILE: dc_bot_gui.py
# ==========================================

#!/usr/bin/env python3
"""
Discord Media Downloader - GUI
All modes: Week, Date Range, Since Date, Latest
"""

import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import subprocess
import json
import time
import sys
import os
import threading
import queue
import re
import winsound
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageTk

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "OUTPUT"
CONFIG_FILE = BASE / "main_config.json"
DC_CLIENT = BASE / "dc_media_downloader.py"

OUTPUT.mkdir(exist_ok=True)

THUMB_SIZE = (80, 80)
THUMB_SIZE_SMALL = (70, 70)
TILES_PER_ROW = 4
TIMEZONE_OFFSET = 2
WEEK_OFFSET = 2

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".jfif"}

SPECIAL_WEEKS = {
    354: {
        "start": datetime(2025, 4, 28, 14, 0),
        "end": datetime(2025, 5, 12, 14, 0),
    },
}


def week_to_date(week_number: int) -> datetime:
    week_1_start_utc = datetime(2018, 7, 30, 14, 0, tzinfo=timezone.utc)
    if week_number in SPECIAL_WEEKS:
        dt = SPECIAL_WEEKS[week_number]["start"]
        return dt.replace(tzinfo=timezone.utc)
    if week_number >= 355:
        adjusted_week = week_number - WEEK_OFFSET + 1
    else:
        adjusted_week = week_number - WEEK_OFFSET
    return week_1_start_utc + timedelta(weeks=adjusted_week)


def week_to_end_date(week_number: int) -> datetime:
    week_1_start_utc = datetime(2018, 7, 30, 14, 0, tzinfo=timezone.utc)
    if week_number in SPECIAL_WEEKS:
        dt = SPECIAL_WEEKS[week_number]["end"]
        return dt.replace(tzinfo=timezone.utc)
    if week_number >= 355:
        adjusted_week = week_number - WEEK_OFFSET + 1
    else:
        adjusted_week = week_number - WEEK_OFFSET
    return week_1_start_utc + timedelta(weeks=adjusted_week + 1)


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


# ==================== WIDGETS ====================


class ScrollableFrame(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, bg="#1e1e1e", highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg="#1e1e1e")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)


class ZoomableImageViewer(tk.Frame):
    def __init__(self, parent, log_func=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.log_func = log_func
        self.pil_image = None
        self.tk_image = None
        self.zoom_level = 1.0

        header_frame = tk.Frame(self, bg="#1a1a1a")
        header_frame.pack(fill="x")
        self.header_label = tk.Label(header_frame, text="Click an image to preview",
                                     bg="#1a1a1a", fg="#888", font=("Segoe UI", 11), anchor="w", padx=10, pady=4)
        self.header_label.pack(side="left", fill="x", expand=True)

        zoom_frame = tk.Frame(header_frame, bg="#1a1a1a")
        zoom_frame.pack(side="right", padx=6)
        for txt, cmd in [("🔍−", "zoom_out"), ("", None), ("🔍+", "zoom_in"), ("FIT", "zoom_fit"), ("1:1", "zoom_reset")]:
            if cmd:
                tk.Button(zoom_frame, text=txt, command=getattr(self, cmd),
                          bg="#3a3a3a", fg="white" if "🔍" in txt else "#4a90d9",
                          font=("Segoe UI", 9 if "🔍" in txt else 8, "bold"),
                          relief="flat", padx=6, pady=1, cursor="hand2").pack(side="left", padx=2)
            elif txt == "":
                self.zoom_label = tk.Label(zoom_frame, text="100%", bg="#1a1a1a", fg="#aaa",
                                            font=("Consolas", 9), width=6, anchor="center")
                self.zoom_label.pack(side="left", padx=2)

        self.canvas = tk.Canvas(self, bg="#0d0d0d", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.image_id = None
        self.canvas.bind("<MouseWheel>", lambda e: self.zoom_in() if e.delta > 0 else self.zoom_out())
        self.canvas.bind("<ButtonPress-3>", self._pan_start)
        self.canvas.bind("<B3-Motion>", self._pan_move)
        self.canvas.bind("<Configure>", lambda e: self._render() if self.pil_image else None)
        self._pan_data = {"x": 0, "y": 0}

    def _pan_start(self, e): self._pan_data["x"], self._pan_data["y"] = e.x, e.y
    def _pan_move(self, e):
        if self.image_id:
            self.canvas.move(self.image_id, e.x - self._pan_data["x"], e.y - self._pan_data["y"])
            self._pan_data["x"], self._pan_data["y"] = e.x, e.y

    def load_image(self, path):
        try:
            self.pil_image = Image.open(path)
            self.header_label.config(text=f"{path.name}  ({self.pil_image.width}x{self.pil_image.height})", fg="#ddd")
            self.zoom_fit()
            if self.log_func: self.log_func(f"Preview: {path.name}")
        except Exception as e:
            if self.log_func: self.log_func(f"Image error: {e}")

    def _render(self):
        if not self.pil_image: return
        w = max(1, int(self.pil_image.width * self.zoom_level))
        h = max(1, int(self.pil_image.height * self.zoom_level))
        self.tk_image = ImageTk.PhotoImage(self.pil_image.resize((w, h), Image.LANCZOS))
        if self.image_id: self.canvas.delete(self.image_id)
        self.image_id = self.canvas.create_image(self.canvas.winfo_width()//2, self.canvas.winfo_height()//2,
                                                  image=self.tk_image, anchor="center")
        self.zoom_label.config(text=f"{int(self.zoom_level*100)}%")

    def zoom_in(self):
        if self.pil_image: self.zoom_level = min(10, self.zoom_level*1.2); self._render()
    def zoom_out(self):
        if self.pil_image: self.zoom_level = max(0.1, self.zoom_level/1.2); self._render()
    def zoom_fit(self):
        if not self.pil_image: return
        cw, ch = max(self.canvas.winfo_width(), 100), max(self.canvas.winfo_height(), 100)
        self.zoom_level = min(cw/self.pil_image.width, ch/self.pil_image.height, 1.0)*0.95; self._render()
    def zoom_reset(self):
        if self.pil_image: self.zoom_level = 1.0; self._render()


class NotificationPopup(tk.Toplevel):
    def __init__(self, parent, title, message, duration=8000, success=True):
        super().__init__(parent)
        self.overrideredirect(True); self.attributes("-topmost", True)
        bg = "#1a3a1a" if success else "#3a1a1a"
        self.configure(bg="#27ae60" if success else "#c0392b")
        inner = tk.Frame(self, bg=bg, padx=20, pady=15); inner.pack(padx=2, pady=2)
        tk.Label(inner, text=f"{'OK' if success else 'FAIL'} {title}", bg=bg, fg="white",
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(inner, text=message, bg=bg, fg="#ccc", font=("Segoe UI", 10),
                 wraplength=350, justify="left").pack(anchor="w", pady=(5,0))
        self.update_idletasks()
        self.geometry(f"+{self.winfo_screenwidth()-self.winfo_width()-30}+{self.winfo_screenheight()-self.winfo_height()-80}")
        self.attributes("-alpha", 0.0); self._fade_in(0.0)
        self.after(duration, self._fade_out, 1.0)
        for w in [self, inner]+inner.winfo_children(): w.bind("<Button-1>", lambda e: self.destroy())

    def _fade_in(self, a):
        if a < 0.95: self.attributes("-alpha", a+0.1); self.after(30, self._fade_in, a+0.1)
        else: self.attributes("-alpha", 0.95)
    def _fade_out(self, a):
        if a > 0.05:
            try: self.attributes("-alpha", a-0.1); self.after(30, self._fade_out, a-0.1)
            except: pass
        else:
            try: self.destroy()
            except: pass


# ==================== MAIN APP ====================


class DCBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Discord Media Downloader")
        self.root.geometry("1500x900")
        self.root.configure(bg="#121212")

        self.current_folder = None
        self.current_subfolder = None
        self.thumb_cache = {}
        self.selected_folder_widget = None
        self.selected_subfolder_widget = None
        self.selected_file_widget = None
        self.download_process = None
        self.download_start_time = None
        self.output_queue = queue.Queue()

        config = load_config()

        # ==================== TOP BAR ====================
        top_bar = tk.Frame(root, bg="#2a2a2a", pady=5, padx=10)
        top_bar.pack(side="top", fill="x")

        self.dl_button = tk.Button(top_bar, text=">> Download", command=self.start_download,
                                    bg="#7289da", fg="white", font=("Segoe UI", 10, "bold"),
                                    relief="flat", padx=12, pady=3)
        self.dl_button.pack(side="left", padx=4)

        self.stop_button = tk.Button(top_bar, text="Stop", command=self.stop_download,
                                      bg="#c0392b", fg="white", font=("Segoe UI", 10, "bold"),
                                      relief="flat", padx=12, pady=3, state="disabled")
        self.stop_button.pack(side="left", padx=4)

        tk.Button(top_bar, text="Refresh", command=self.refresh_all,
                  bg="#5a5a5a", fg="white", font=("Segoe UI", 10),
                  relief="flat", padx=12, pady=3).pack(side="left", padx=4)

        tk.Button(top_bar, text="Convert to PNG", command=self.convert_to_png_confirm,
                  bg="#e67e22", fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=12, pady=3).pack(side="left", padx=4)

        tk.Button(top_bar, text="Update Token", command=self.update_token,
                  bg="#9b59b6", fg="white", font=("Segoe UI", 10),
                  relief="flat", padx=12, pady=3).pack(side="left", padx=4)

        self.token_status_label = tk.Label(top_bar, text="checking...", bg="#2a2a2a", fg="#ffaa00",
                                            font=("Segoe UI", 9), padx=6)
        self.token_status_label.pack(side="left", padx=4)

        self.status_label = tk.Label(top_bar, text="Idle", bg="#2a2a2a", fg="#888",
                                      font=("Segoe UI", 10), padx=10)
        self.status_label.pack(side="right")

        self.timer_label = tk.Label(top_bar, text="", bg="#2a2a2a", fg="#666",
                                     font=("Consolas", 9), padx=6)
        self.timer_label.pack(side="right")

        # ==================== LOG ====================
        log_frame = tk.Frame(root, bg="#0a0a0a")
        log_frame.pack(fill="x", side="bottom")

        log_header = tk.Frame(log_frame, bg="#0a0a0a"); log_header.pack(fill="x")
        tk.Label(log_header, text="LOG", bg="#0a0a0a", fg="#555", font=("Segoe UI", 8), padx=6).pack(side="left")
        tk.Button(log_header, text="Clear", command=self.clear_log, bg="#1a1a1a", fg="#555",
                  font=("Segoe UI", 7), relief="flat", padx=6, cursor="hand2").pack(side="right", padx=4)

        log_container = tk.Frame(log_frame, bg="#0a0a0a"); log_container.pack(fill="x")
        self.log_box = tk.Text(log_container, height=8, bg="#0a0a0a", fg="#00ff88",
                               font=("Consolas", 9), relief="flat", padx=6, pady=3, wrap="word")
        log_sb = tk.Scrollbar(log_container, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=log_sb.set)
        log_sb.pack(side="right", fill="y"); self.log_box.pack(side="left", fill="both", expand=True)

        for tag, color in [("error","#ff4444"),("success","#44ff44"),("info","#00ff88"),("process","#ffaa00"),("header","#7289da")]:
            self.log_box.tag_configure(tag, foreground=color)

        # ==================== MAIN PANE ====================
        main_pane = tk.PanedWindow(root, orient="horizontal", bg="#121212", sashwidth=5, sashrelief="flat")
        main_pane.pack(fill="both", expand=True)

        # ==================== LEFT PANEL ====================
        left_panel = tk.Frame(main_pane, bg="#1e1e1e")
        main_pane.add(left_panel, minsize=380, width=420)

        # --- CONFIG ---
        config_frame = tk.Frame(left_panel, bg="#1e1e1e")
        config_frame.pack(fill="x", padx=6, pady=4)

        tk.Label(config_frame, text="CONFIGURATION", bg="#2a2a2a", fg="#7289da",
                 font=("Segoe UI", 10, "bold"), anchor="w", padx=6, pady=3).pack(fill="x", pady=(0,4))

        # Channel link
        row = tk.Frame(config_frame, bg="#1e1e1e"); row.pack(fill="x", pady=2)
        tk.Label(row, text="Channel link:", bg="#1e1e1e", fg="#aaa", font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.channel_var = tk.StringVar(value=config.get("channel_link", ""))
        tk.Entry(row, textvariable=self.channel_var, bg="#2a2a2a", fg="#ddd", font=("Consolas", 9),
                 insertbackground="#ddd", relief="flat").pack(side="left", fill="x", expand=True)

        # Folder name
        row = tk.Frame(config_frame, bg="#1e1e1e"); row.pack(fill="x", pady=2)
        tk.Label(row, text="Folder name:", bg="#1e1e1e", fg="#aaa", font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.folder_var = tk.StringVar()
        tk.Entry(row, textvariable=self.folder_var, bg="#2a2a2a", fg="#ddd", font=("Consolas", 9),
                 insertbackground="#ddd", relief="flat").pack(side="left", fill="x", expand=True)

        # ==================== DOWNLOAD MODE ====================
        tk.Label(config_frame, text="DOWNLOAD MODE", bg="#2a2a2a", fg="#e67e22",
                 font=("Segoe UI", 10, "bold"), anchor="w", padx=6, pady=3).pack(fill="x", pady=(8,4))

        mode_frame = tk.Frame(config_frame, bg="#1e1e1e")
        mode_frame.pack(fill="x", pady=2)

        self.dl_mode = tk.StringVar(value="week")
        modes = [("Week", "week"), ("Date range", "range"), ("Since date", "since"), ("Latest N", "latest")]
        for text, val in modes:
            tk.Radiobutton(mode_frame, text=text, variable=self.dl_mode, value=val,
                           bg="#1e1e1e", fg="#aaa", selectcolor="#2a2a2a", activebackground="#1e1e1e",
                           activeforeground="#ddd", font=("Segoe UI", 9),
                           command=self._on_mode_change).pack(side="left", padx=4)

        # --- WEEK FRAME ---
        self.week_frame = tk.Frame(config_frame, bg="#1e1e1e")
        row = tk.Frame(self.week_frame, bg="#1e1e1e"); row.pack(fill="x", pady=2)
        tk.Label(row, text="Week nr:", bg="#1e1e1e", fg="#aaa", font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.week_var = tk.StringVar()
        tk.Entry(row, textvariable=self.week_var, bg="#2a2a2a", fg="#ddd", font=("Consolas", 9),
                 insertbackground="#ddd", relief="flat", width=10).pack(side="left")
        self.week_info_label = tk.Label(row, text="", bg="#1e1e1e", fg="#666", font=("Segoe UI", 8))
        self.week_info_label.pack(side="left", padx=8)
        self.week_var.trace_add("write", self._on_week_change)

        # --- RANGE FRAME ---
        self.range_frame = tk.Frame(config_frame, bg="#1e1e1e")
        row = tk.Frame(self.range_frame, bg="#1e1e1e"); row.pack(fill="x", pady=2)
        tk.Label(row, text="Start date:", bg="#1e1e1e", fg="#aaa", font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.range_start_var = tk.StringVar(value=datetime.now().strftime("%d-%m-%Y %H-%M"))
        tk.Entry(row, textvariable=self.range_start_var, bg="#2a2a2a", fg="#ddd", font=("Consolas", 9),
                 insertbackground="#ddd", relief="flat", width=20).pack(side="left")

        row = tk.Frame(self.range_frame, bg="#1e1e1e"); row.pack(fill="x", pady=2)
        tk.Label(row, text="End date:", bg="#1e1e1e", fg="#aaa", font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.range_end_var = tk.StringVar(value=datetime.now().strftime("%d-%m-%Y %H-%M"))
        tk.Entry(row, textvariable=self.range_end_var, bg="#2a2a2a", fg="#ddd", font=("Consolas", 9),
                 insertbackground="#ddd", relief="flat", width=20).pack(side="left")

        tk.Label(self.range_frame, text="Format: DD-MM-YYYY HH-MM (local time, auto-converted to UTC)",
                 bg="#1e1e1e", fg="#555", font=("Segoe UI", 7), anchor="w", padx=14).pack(fill="x")

        # --- SINCE FRAME ---
        self.since_frame = tk.Frame(config_frame, bg="#1e1e1e")
        row = tk.Frame(self.since_frame, bg="#1e1e1e"); row.pack(fill="x", pady=2)
        tk.Label(row, text="Since date:", bg="#1e1e1e", fg="#aaa", font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.since_date_var = tk.StringVar(value=datetime.now().strftime("%d-%m-%Y %H-%M"))
        tk.Entry(row, textvariable=self.since_date_var, bg="#2a2a2a", fg="#ddd", font=("Consolas", 9),
                 insertbackground="#ddd", relief="flat", width=20).pack(side="left")

        row = tk.Frame(self.since_frame, bg="#1e1e1e"); row.pack(fill="x", pady=2)
        tk.Label(row, text="Limit:", bg="#1e1e1e", fg="#aaa", font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.since_limit_var = tk.StringVar(value=str(config.get("limit", 50)))
        tk.Entry(row, textvariable=self.since_limit_var, bg="#2a2a2a", fg="#ddd", font=("Consolas", 9),
                 insertbackground="#ddd", relief="flat", width=10).pack(side="left")

        tk.Label(self.since_frame, text="Format: DD-MM-YYYY HH-MM (local time)",
                 bg="#1e1e1e", fg="#555", font=("Segoe UI", 7), anchor="w", padx=14).pack(fill="x")

        # --- LATEST FRAME ---
        self.latest_frame = tk.Frame(config_frame, bg="#1e1e1e")
        row = tk.Frame(self.latest_frame, bg="#1e1e1e"); row.pack(fill="x", pady=2)
        tk.Label(row, text="Count:", bg="#1e1e1e", fg="#aaa", font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.latest_count_var = tk.StringVar(value="50")
        tk.Entry(row, textvariable=self.latest_count_var, bg="#2a2a2a", fg="#ddd", font=("Consolas", 9),
                 insertbackground="#ddd", relief="flat", width=10).pack(side="left")
        tk.Label(row, text="newest images from channel", bg="#1e1e1e", fg="#555",
                 font=("Segoe UI", 8)).pack(side="left", padx=6)

        # Separator
        tk.Frame(left_panel, bg="#7289da", height=2).pack(fill="x", padx=8, pady=6)

        # --- OUTPUT FOLDERS ---
        tk.Label(left_panel, text="OUTPUT FOLDERS", bg="#2a2a2a", fg="#27ae60",
                 font=("Segoe UI", 10, "bold"), anchor="w", padx=6, pady=3).pack(fill="x", padx=3)
        self.folder_scroll = ScrollableFrame(left_panel, bg="#1e1e1e")
        self.folder_scroll.pack(fill="x", padx=3, pady=2)
        self.folder_scroll.configure(height=130); self.folder_scroll.pack_propagate(False)

        tk.Frame(left_panel, bg="#27ae60", height=2).pack(fill="x", padx=8, pady=4)

        # --- SUBFOLDERS ---
        self.subfolder_label = tk.Label(left_panel, text="SUBFOLDERS", bg="#2a2a2a", fg="#e67e22",
                                         font=("Segoe UI", 10, "bold"), anchor="w", padx=6, pady=3)
        self.subfolder_label.pack(fill="x", padx=3)
        self.subfolder_scroll = ScrollableFrame(left_panel, bg="#1e1e1e")
        self.subfolder_scroll.pack(fill="x", padx=3, pady=2)
        self.subfolder_scroll.configure(height=110); self.subfolder_scroll.pack_propagate(False)

        tk.Frame(left_panel, bg="#e67e22", height=2).pack(fill="x", padx=8, pady=4)

        # --- FILES ---
        self.files_label = tk.Label(left_panel, text="FILES", bg="#2a2a2a", fg="#e74c3c",
                                     font=("Segoe UI", 10, "bold"), anchor="w", padx=6, pady=3)
        self.files_label.pack(fill="x", padx=3)
        self.files_scroll = ScrollableFrame(left_panel, bg="#1e1e1e")
        self.files_scroll.pack(fill="both", expand=True, padx=3, pady=2)

        # ==================== RIGHT PANEL ====================
        self.viewer = ZoomableImageViewer(main_pane, log_func=self.log, bg="#0d0d0d")
        main_pane.add(self.viewer, minsize=500)

        # Init
        self._on_mode_change()
        self.log("SYSTEM START", "header")
        self.load_folder_tiles()
        self._poll_output()

        if config.get("token", ""):
            self.log("Verifying token...", "info")
            self.root.after(300, self._verify_token_background)
        else:
            self.token_status_label.config(text="No token", fg="#ff4444")
            self.log("No token set! Click 'Update Token'.", "error")

    # ==================== LOG ====================

    def log(self, msg, tag="info"):
        t = time.strftime("%H:%M:%S")
        formatted = f"[{t}] {msg}"
        self.log_box.insert("end", formatted + "\n", tag)
        self.log_box.see("end")
        print(formatted, flush=True)

    def clear_log(self):
        self.log_box.delete("1.0", "end")

    # ==================== TOKEN ====================

    def _verify_token_background(self):
        config = load_config()
        token = config.get("token", "")
        if not token:
            self.token_status_label.config(text="No token", fg="#ff4444"); return

        def _check():
            script = (
                "import requests, json, sys; "
                "r = requests.get('https://discord.com/api/v9/users/@me', "
                "headers={'Authorization': sys.argv[1]}, timeout=10); "
                "d = r.json() if r.status_code == 200 else {}; "
                "print(json.dumps({'ok': r.status_code == 200, 'code': r.status_code, "
                "'user': d.get('username', '?')}))"
            )
            try:
                kwargs = {"capture_output": True, "text": True, "timeout": 15}
                if sys.platform == "win32":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                result = subprocess.run([sys.executable, "-c", script, token], **kwargs)
                if result.stdout.strip():
                    self.output_queue.put(("token_verify", json.loads(result.stdout.strip())))
                else:
                    self.output_queue.put(("token_verify", {"ok": False, "code": 0, "user": "error"}))
            except Exception as e:
                self.output_queue.put(("token_verify", {"ok": False, "code": 0, "user": str(e)}))

        threading.Thread(target=_check, daemon=True).start()

    def update_token(self):
        self.log("=== UPDATE TOKEN ===", "header")
        self.log("Switch to TERMINAL and paste your Discord token.", "process")

        def _ask():
            print("\n" + "=" * 50, flush=True)
            print("  UPDATE DISCORD TOKEN", flush=True)
            print("=" * 50, flush=True)
            print("  Paste your Discord token below.", flush=True)
            print("  (F12 > Network > any request > Authorization header)\n", flush=True)
            try:
                new_token = input("  Token > ").strip()
            except (EOFError, KeyboardInterrupt):
                self.output_queue.put(("token_updated", False)); return
            if not new_token:
                self.output_queue.put(("token_updated", False)); return
            config = load_config(); config["token"] = new_token; save_config(config)
            print("  Token saved!", flush=True); print("=" * 50, flush=True)
            self.output_queue.put(("token_updated", True))

        threading.Thread(target=_ask, daemon=True).start()

    # ==================== MODE SWITCHING ====================

    def _on_mode_change(self):
        for f in [self.week_frame, self.range_frame, self.since_frame, self.latest_frame]:
            f.pack_forget()
        mode = self.dl_mode.get()
        if mode == "week": self.week_frame.pack(fill="x", pady=2)
        elif mode == "range": self.range_frame.pack(fill="x", pady=2)
        elif mode == "since": self.since_frame.pack(fill="x", pady=2)
        elif mode == "latest": self.latest_frame.pack(fill="x", pady=2)

    def _on_week_change(self, *args):
        try:
            wn = int(self.week_var.get())
            s = week_to_date(wn); e = week_to_end_date(wn)
            self.week_info_label.config(
                text=f"{s.strftime('%d-%m-%Y %H:%M')} -> {e.strftime('%d-%m-%Y %H:%M')} UTC", fg="#7289da")
        except:
            self.week_info_label.config(text="", fg="#666")

    # ==================== CONVERT ====================

    def convert_to_png_confirm(self):
        non_png = [f for f in OUTPUT.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTS and f.suffix.lower() != ".png"]
        if not non_png:
            self.log("Everything is already PNG!", "success"); return
        confirm = messagebox.askyesno("Convert to PNG", f"Convert {len(non_png)} files to PNG?", icon="warning")
        if not confirm: return
        self.log("Converting...", "header")
        from dc_cleanup_images import cleanup as run_cleanup
        count = run_cleanup()
        self.log(f"Done! {count} converted.", "success")
        self.thumb_cache.clear(); self.load_folder_tiles()
        if self.current_folder: self.load_subfolder_tiles()

    # ==================== DOWNLOAD ====================

    def _parse_local_to_utc(self, date_str):
        local = datetime.strptime(date_str.strip(), "%d-%m-%Y %H-%M")
        utc = local - timedelta(hours=TIMEZONE_OFFSET)
        return utc.replace(tzinfo=timezone.utc)

    def _validate_and_build(self):
        config = load_config()
        token = config.get("token", "")
        if not token: self.log("ERROR: No token!", "error"); return None
        channel = self.channel_var.get().strip()
        if not channel: self.log("ERROR: Channel link empty!", "error"); return None
        folder = self.folder_var.get().strip()
        if not folder: self.log("ERROR: Folder name empty!", "error"); return None
        match = re.search(r"discord\.com/channels/\d+/(\d+)", channel)
        if not match: self.log("ERROR: Invalid channel link!", "error"); return None
        channel_id = match.group(1)

        config["channel_link"] = channel; save_config(config)
        mode = self.dl_mode.get()
        env = {"DC_TOKEN": token, "DC_CHANNEL_ID": channel_id, "DC_GUI_MODE": "1", "DC_MODE": mode}

        try:
            if mode == "week":
                wn = int(self.week_var.get().strip())
                start = week_to_date(wn); end = week_to_end_date(wn)
                env["DC_START_DATE"] = start.isoformat()
                env["DC_END_DATE"] = end.isoformat()
                env["DC_FOLDER_NAME"] = str(OUTPUT / folder)
                env["DC_FOLDER_SUFFIX"] = str(wn)

            elif mode == "range":
                start = self._parse_local_to_utc(self.range_start_var.get())
                end = self._parse_local_to_utc(self.range_end_var.get())
                env["DC_START_DATE"] = start.isoformat()
                env["DC_END_DATE"] = end.isoformat()
                env["DC_FOLDER_NAME"] = str(OUTPUT / folder)
                env["DC_FOLDER_SUFFIX"] = start.strftime("%d-%m-%Y")

            elif mode == "since":
                start = self._parse_local_to_utc(self.since_date_var.get())
                limit = int(self.since_limit_var.get().strip())
                env["DC_START_DATE"] = start.isoformat()
                env["DC_LIMIT"] = str(limit)
                env["DC_FOLDER_NAME"] = str(OUTPUT / folder)
                env["DC_FOLDER_SUFFIX"] = start.strftime("%d-%m-%Y")

            elif mode == "latest":
                limit = int(self.latest_count_var.get().strip())
                env["DC_LIMIT"] = str(limit)
                env["DC_FOLDER_NAME"] = str(OUTPUT / folder)
                env["DC_FOLDER_SUFFIX"] = ""

        except ValueError as e:
            self.log(f"ERROR: Invalid input - {e}", "error"); return None

        return env

    def start_download(self):
        if self.download_process:
            self.log("Already running!", "error"); return
        env_vars = self._validate_and_build()
        if not env_vars: return

        mode = self.dl_mode.get()
        self.log(f"Starting download (mode: {mode})...", "header")

        self.dl_button.config(state="disabled", bg="#555")
        self.stop_button.config(state="normal")
        self.status_label.config(text="Downloading...", fg="#7289da")
        self.download_start_time = time.time()
        self._update_timer()

        env = os.environ.copy(); env.update(env_vars)
        kwargs = {"cwd": str(BASE), "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
                  "text": True, "bufsize": 1, "encoding": "utf-8", "errors": "replace", "env": env}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        self.download_process = subprocess.Popen([sys.executable, "-u", str(DC_CLIENT)], **kwargs)
        threading.Thread(target=self._read_stream, args=(self.download_process.stdout, "out"), daemon=True).start()
        threading.Thread(target=self._read_stream, args=(self.download_process.stderr, "err"), daemon=True).start()
        threading.Thread(target=self._wait_process, daemon=True).start()

    def stop_download(self):
        if not self.download_process: return
        self.log("Stopping...", "error")
        try: self.download_process.terminate(); self.download_process.wait(timeout=5)
        except:
            try: self.download_process.kill()
            except: pass
        self.download_process = None; self.download_start_time = None
        self.dl_button.config(state="normal", bg="#7289da"); self.stop_button.config(state="disabled")
        self.status_label.config(text="Stopped", fg="#c0392b"); self.timer_label.config(text="")

    # ==================== PROCESS ====================

    def _read_stream(self, stream, stype):
        try:
            for line in iter(stream.readline, ""):
                s = line.rstrip("\n\r")
                if s: self.output_queue.put((stype, s))
            stream.close()
        except: pass

    def _wait_process(self):
        if self.download_process:
            self.output_queue.put(("done", self.download_process.wait()))

    def _poll_output(self):
        try:
            while True:
                msg_type, data = self.output_queue.get_nowait()

                if msg_type == "out":
                    tag = "process"; lower = data.lower()
                    if any(w in lower for w in ["blad","error","fail","invalid"]): tag = "error"
                    elif any(w in lower for w in ["[ok]","zapisano","done","zakonczono"]): tag = "success"
                    elif "===" in data: tag = "header"
                    self.log(data, tag)

                elif msg_type == "err":
                    self.log(data, "error")

                elif msg_type == "token_verify":
                    if data.get("ok"):
                        self.token_status_label.config(text=f"OK: {data['user']}", fg="#44ff44")
                        self.log(f"Token valid! User: {data['user']}", "success")
                    else:
                        self.token_status_label.config(text=f"Invalid ({data.get('code',0)})", fg="#ff4444")
                        self.log(f"Token invalid! Click 'Update Token'", "error")

                elif msg_type == "token_updated":
                    if data:
                        self.log("Token saved! Verifying...", "success")
                        self.token_status_label.config(text="verifying...", fg="#ffaa00")
                        self.root.after(300, self._verify_token_background)
                    else:
                        self.log("Token update cancelled.", "info")

                elif msg_type == "done":
                    rc = data
                    elapsed = time.time() - self.download_start_time if self.download_start_time else 0
                    es = self._fmt_time(elapsed); ok = (rc == 0)
                    self.log(f"{'Done' if ok else 'Failed'}! Time: {es}", "success" if ok else "error")
                    if rc == 1: self.log("Token may be invalid.", "error")
                    self.download_process = None; self.download_start_time = None
                    self.dl_button.config(state="normal", bg="#7289da"); self.stop_button.config(state="disabled")
                    self.status_label.config(text="Done" if ok else "Error", fg="#27ae60" if ok else "#c0392b")
                    self.timer_label.config(text=es)
                    self.thumb_cache.clear(); self.load_folder_tiles()
                    if self.current_folder: self.load_subfolder_tiles()
                    self._notify(ok, es, rc)
        except queue.Empty: pass
        self.root.after(100, self._poll_output)

    # ==================== NOTIFICATIONS ====================

    def _notify(self, ok, es, rc):
        title = "Download Complete!" if ok else "Download Failed"
        msg = f"Time: {es}" + ("" if ok else f"\nExit code: {rc}")
        try: winsound.MessageBeep(winsound.MB_OK if ok else winsound.MB_ICONHAND)
        except: pass
        NotificationPopup(self.root, title, msg, duration=10000, success=ok)
        try: self.root.bell(); self.root.attributes("-topmost", True); self.root.after(100, lambda: self.root.attributes("-topmost", False))
        except: pass

    def _fmt_time(self, s):
        m, s = divmod(int(s), 60); h, m = divmod(m, 60)
        return f"{h}h {m}m {s}s" if h else f"{m}m {s}s" if m else f"{s}s"

    def _update_timer(self):
        if self.download_start_time and self.download_process:
            self.timer_label.config(text=self._fmt_time(time.time()-self.download_start_time))
            self.root.after(1000, self._update_timer)
        else: self.timer_label.config(text="")

    # ==================== TILES ====================

    def make_thumbnail(self, path, size=THUMB_SIZE):
        key = (str(path), size)
        if key in self.thumb_cache: return self.thumb_cache[key]
        try:
            img = Image.open(path); img.thumbnail(size, Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(img); self.thumb_cache[key] = tk_img; return tk_img
        except: return None

    def _find_preview(self, folder):
        for f in sorted(folder.iterdir()):
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS: return f
        for f in sorted(folder.iterdir()):
            if f.is_dir():
                r = self._find_preview(f)
                if r: return r
        return None

    def _set_bg(self, w, c):
        try:
            w.configure(bg=c)
            for ch in w.winfo_children():
                try: ch.configure(bg=c)
                except: pass
        except: pass

    def load_folder_tiles(self):
        for w in self.folder_scroll.inner.winfo_children(): w.destroy()
        self.selected_folder_widget = None
        folders = sorted([f for f in OUTPUT.iterdir() if f.is_dir()])
        if not folders:
            tk.Label(self.folder_scroll.inner, text="Empty", bg="#1e1e1e", fg="#555", font=("Segoe UI",9)).pack(pady=10); return
        rf = None
        for i, folder in enumerate(folders):
            if i % TILES_PER_ROW == 0: rf = tk.Frame(self.folder_scroll.inner, bg="#1e1e1e"); rf.pack(fill="x", padx=2, pady=1)
            tile = tk.Frame(rf, bg="#2a2a2a", padx=1, pady=1, cursor="hand2"); tile.pack(side="left", padx=3, pady=2)
            p = self._find_preview(folder)
            if p:
                th = self.make_thumbnail(p, THUMB_SIZE)
                li = tk.Label(tile, image=th, bg="#2a2a2a", cursor="hand2") if th else tk.Label(tile, text="F", bg="#2a2a2a", fg="#555", font=("Segoe UI",18), width=7, height=3, cursor="hand2")
            else: li = tk.Label(tile, text="F", bg="#2a2a2a", fg="#555", font=("Segoe UI",18), width=7, height=3, cursor="hand2")
            li.pack()
            n = folder.name; n = n[:10]+"..." if len(n)>12 else n
            ln = tk.Label(tile, text=n, bg="#2a2a2a", fg="#999", font=("Segoe UI",7), cursor="hand2"); ln.pack()
            for w in [tile,li,ln]: w.bind("<Button-1>", lambda e,f=folder,t=tile: self._click_folder(f,t))

    def _click_folder(self, folder, tile):
        if self.selected_folder_widget: self._set_bg(self.selected_folder_widget, "#2a2a2a")
        self._set_bg(tile, "#2a4a2a"); self.selected_folder_widget = tile
        self.current_folder = folder; self.current_subfolder = None
        self.subfolder_label.config(text=f"SUBFOLDERS: {folder.name}"); self.load_subfolder_tiles()

    def load_subfolder_tiles(self):
        for w in self.subfolder_scroll.inner.winfo_children(): w.destroy()
        for w in self.files_scroll.inner.winfo_children(): w.destroy()
        self.selected_subfolder_widget = None; self.selected_file_widget = None
        if not self.current_folder: return
        subs = sorted([f for f in self.current_folder.iterdir() if f.is_dir()])
        imgs = sorted([f for f in self.current_folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS])
        if imgs and not subs: self.current_subfolder = self.current_folder; self._load_files(self.current_folder); return
        if not subs:
            tk.Label(self.subfolder_scroll.inner, text="Empty", bg="#1e1e1e", fg="#555", font=("Segoe UI",9)).pack(pady=10); return
        rf = None
        for i, folder in enumerate(subs):
            if i % TILES_PER_ROW == 0: rf = tk.Frame(self.subfolder_scroll.inner, bg="#1e1e1e"); rf.pack(fill="x", padx=2, pady=1)
            tile = tk.Frame(rf, bg="#2a2a2a", padx=1, pady=1, cursor="hand2"); tile.pack(side="left", padx=3, pady=2)
            p = self._find_preview(folder)
            if p:
                th = self.make_thumbnail(p, THUMB_SIZE_SMALL)
                li = tk.Label(tile, image=th, bg="#2a2a2a", cursor="hand2") if th else tk.Label(tile, text="D", bg="#2a2a2a", fg="#555", font=("Segoe UI",16), width=6, height=3, cursor="hand2")
            else: li = tk.Label(tile, text="D", bg="#2a2a2a", fg="#555", font=("Segoe UI",16), width=6, height=3, cursor="hand2")
            li.pack()
            n = folder.name; n = n[:10]+"..." if len(n)>12 else n
            ln = tk.Label(tile, text=n, bg="#2a2a2a", fg="#999", font=("Segoe UI",7), cursor="hand2"); ln.pack()
            for w in [tile,li,ln]: w.bind("<Button-1>", lambda e,f=folder,t=tile: self._click_subfolder(f,t))

    def _click_subfolder(self, folder, tile):
        if self.selected_subfolder_widget: self._set_bg(self.selected_subfolder_widget, "#2a2a2a")
        self._set_bg(tile, "#2a2a4a"); self.selected_subfolder_widget = tile
        self.current_subfolder = folder; self.files_label.config(text=f"FILES: {folder.name}")
        self._load_files(folder)

    def _load_files(self, folder):
        for w in self.files_scroll.inner.winfo_children(): w.destroy()
        self.selected_file_widget = None
        imgs = sorted([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS])
        if not imgs:
            tk.Label(self.files_scroll.inner, text="No images", bg="#1e1e1e", fg="#555", font=("Segoe UI",9)).pack(pady=10); return
        rf = None
        for i, ip in enumerate(imgs):
            if i % TILES_PER_ROW == 0: rf = tk.Frame(self.files_scroll.inner, bg="#1e1e1e"); rf.pack(fill="x", padx=2, pady=1)
            th = self.make_thumbnail(ip, THUMB_SIZE_SMALL)
            if not th: continue
            tile = tk.Frame(rf, bg="#2a2a2a", padx=1, pady=1, cursor="hand2"); tile.pack(side="left", padx=3, pady=2)
            li = tk.Label(tile, image=th, bg="#2a2a2a", cursor="hand2"); li.pack()
            n = ip.stem; n = n[:10]+"..." if len(n)>12 else n
            ln = tk.Label(tile, text=n, bg="#2a2a2a", fg="#999", font=("Segoe UI",7), cursor="hand2"); ln.pack()
            for w in [tile,li,ln]: w.bind("<Button-1>", lambda e,p=ip,t=tile: self._click_file(p,t))

    def _click_file(self, path, tile):
        if self.selected_file_widget: self._set_bg(self.selected_file_widget, "#2a2a2a")
        self._set_bg(tile, "#2a2a4a"); self.selected_file_widget = tile; self.viewer.load_image(path)

    def refresh_all(self):
        self.thumb_cache.clear(); self.load_folder_tiles()
        if self.current_folder: self.load_subfolder_tiles()
        self.log("Refreshed", "success")


if __name__ == "__main__":
    print("=" * 42)
    print("  Discord Media Downloader GUI - start")
    print("=" * 42)
    root = tk.Tk()
    app = DCBotGUI(root)
    root.mainloop()