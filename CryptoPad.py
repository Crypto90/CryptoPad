"""
CryptoPad - OBS Streaming Gamepad / Controller Overlay Widget
Broadcast-ready real-time controller visualizer with Cross-Controller Mapping Engine.

Author: Crypto90
Repository: https://github.com/Crypto90/CryptoPad
License: MIT License
"""

import sys
import os
import time
import datetime
import json
import shutil
import socket
import queue
import logging
import threading
import webbrowser
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox
from jinja2 import FileSystemLoader, ChoiceLoader
from flask import Flask, render_template
from flask_socketio import SocketIO
import engineio.async_drivers.threading

# High-DPI and Windows-specific imports
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes


CURRENT_VERSION = "v0.2.3"
SETTINGS_FILENAME = "cryptopad_settings.json"
LEGACY_TEMPLATE_FILE = ".last_template"
DEFAULT_TEMPLATE = "Xbox"

shutdown_event = threading.Event()
flask_shutdown_event = threading.Event()
controller_thread_handle = None


def enable_high_dpi():
    """Enable Per-Monitor V2 DPI awareness on Windows."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def get_exe_dir():
    """Get root directory of the application."""
    if getattr(sys, '_MEIPASS', False):
        return sys._MEIPASS
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_data_dir():
    r"""
    Returns a reliable, writable directory for settings storage.
    Uses executable directory if writable (portable mode),
    otherwise falls back to %LOCALAPPDATA%\Crypto90s_CryptoPad.
    """
    base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    test_path = os.path.join(base_dir, ".cryptopad_write_test")
    try:
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
        return base_dir
    except (PermissionError, OSError):
        appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        target_dir = os.path.join(appdata, "Crypto90s_CryptoPad")
        os.makedirs(target_dir, exist_ok=True)
        return target_dir


def get_settings_path():
    return os.path.join(get_data_dir(), SETTINGS_FILENAME)


def load_settings():
    path = get_settings_path()
    legacy_path = os.path.join(get_exe_dir(), LEGACY_TEMPLATE_FILE)

    defaults = {
        "version": CURRENT_VERSION,
        "template": DEFAULT_TEMPLATE,
        "port": 5001,
        "input_profile": "auto"  # auto, xbox, playstation, nintendo
    }

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
                return defaults
        except Exception:
            pass

    # Legacy fallback
    if os.path.exists(legacy_path):
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                t = f.read().strip()
                if t:
                    defaults["template"] = t
        except Exception:
            pass

    return defaults


def save_settings_data(settings_data):
    path = get_settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False


def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def find_available_port(preferred_port=5001, max_attempts=20):
    for p in range(preferred_port, preferred_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('0.0.0.0', p))
                return p
            except OSError:
                continue
    return preferred_port


# Resource directory resolution for PyInstaller
def resolve_resource_dir(dir_name):
    if getattr(sys, '_MEIPASS', False):
        p = os.path.join(sys._MEIPASS, dir_name)
        if os.path.exists(p):
            return p
    local_p = os.path.join(get_exe_dir(), dir_name)
    if os.path.exists(local_p):
        return local_p
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), dir_name)


template_root = resolve_resource_dir('templates')
static_root = resolve_resource_dir('static')

settings = load_settings()
current_template = settings.get("template", DEFAULT_TEMPLATE)
current_input_profile = settings.get("input_profile", "auto")
server_port = find_available_port(settings.get("port", 5001))
lan_ip = get_lan_ip()

# Flask & SocketIO Server setup
app = Flask(__name__, static_folder=static_root, template_folder=template_root)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('socketio').setLevel(logging.ERROR)
logging.getLogger('engineio').setLevel(logging.ERROR)

template_queue_flask = queue.Queue()
template_queue_controller = queue.Queue()
controller_status_queue = queue.Queue()
input_profile_queue = queue.Queue()


def list_available_templates():
    if not os.path.exists(template_root):
        return [DEFAULT_TEMPLATE]
    return sorted([
        name for name in os.listdir(template_root)
        if os.path.isdir(os.path.join(template_root, name))
    ])


@app.before_request
def sync_template_from_queue():
    global current_template
    while not template_queue_flask.empty():
        try:
            new_t = template_queue_flask.get_nowait()
            if new_t != current_template:
                current_template = new_t
        except Exception:
            break


@app.route('/')
def index():
    global current_template
    tpl_path = os.path.join(template_root, current_template)
    orig_loader = app.jinja_loader
    app.jinja_loader = ChoiceLoader([FileSystemLoader(tpl_path), orig_loader])
    app.jinja_env.cache.clear()
    try:
        return render_template('index.html')
    finally:
        app.jinja_loader = orig_loader


@app.route('/api/status')
def api_status():
    return {
        "status": "online",
        "version": CURRENT_VERSION,
        "template": current_template,
        "input_profile": current_input_profile,
        "port": server_port
    }


# =====================================================================
# Cross-Controller Normalization Engine
# =====================================================================
def normalize_controller_input(joystick, profile_setting="auto"):
    """
    Translates physical controller hardware (Xbox, PlayStation, Nintendo, Generic)
    into a standardized logical gamepad model so ANY controller can visualize
    correctly on ANY layout (Xbox on PS5, PS4 on Xbox, etc.).
    """
    num_b = joystick.get_numbuttons()
    num_a = joystick.get_numaxes()
    num_h = joystick.get_numhats()

    raw_b = [joystick.get_button(i) for i in range(num_b)]
    raw_a = [joystick.get_axis(i) for i in range(num_a)]
    raw_h = [joystick.get_hat(i) for i in range(num_h)]

    ctrl_name = joystick.get_name().lower()

    # Determine hardware profile
    detected = "xbox"
    if profile_setting == "playstation":
        detected = "playstation"
    elif profile_setting == "nintendo":
        detected = "nintendo"
    elif profile_setting == "xbox":
        detected = "xbox"
    else:
        # Auto-detect mode
        if any(w in ctrl_name for w in ["ps4", "ps5", "playstation", "dualshock", "dualsense", "sony"]) or num_b >= 14:
            detected = "playstation"
        elif any(w in ctrl_name for w in ["switch", "nintendo", "joy-con", "pro controller"]):
            detected = "nintendo"
        else:
            detected = "xbox"

    standard = {
        "a": False,         # Bottom: Xbox A / PS Cross
        "b": False,         # Right:  Xbox B / PS Circle
        "x": False,         # Left:   Xbox X / PS Square
        "y": False,         # Top:    Xbox Y / PS Triangle
        "lb": False,        # Left Bumper / L1
        "rb": False,        # Right Bumper / R1
        "select": False,    # Back / Share / Select / -
        "start": False,     # Start / Options / Menu / +
        "ls": False,        # Left Stick Click (L3)
        "rs": False,        # Right Stick Click (R3)
        "meta": False,      # Guide / PS Button
        "touchpad": False,  # Touchpad Click
        "dpad_up": False,
        "dpad_down": False,
        "dpad_left": False,
        "dpad_right": False,
        "left_stick_x": 0.0,
        "left_stick_y": 0.0,
        "right_stick_x": 0.0,
        "right_stick_y": 0.0,
        "lt": 0.0,
        "rt": 0.0
    }

    if detected == "xbox":
        # Standard XInput / Xbox Mapping
        if num_b > 0: standard["a"] = bool(raw_b[0])
        if num_b > 1: standard["b"] = bool(raw_b[1])
        if num_b > 2: standard["x"] = bool(raw_b[2])
        if num_b > 3: standard["y"] = bool(raw_b[3])
        if num_b > 4: standard["lb"] = bool(raw_b[4])
        if num_b > 5: standard["rb"] = bool(raw_b[5])
        if num_b > 6: standard["select"] = bool(raw_b[6])
        if num_b > 7: standard["start"] = bool(raw_b[7])
        if num_b > 8: standard["ls"] = bool(raw_b[8])
        if num_b > 9: standard["rs"] = bool(raw_b[9])
        if num_b > 10: standard["meta"] = bool(raw_b[10])

        if num_h > 0:
            hx, hy = raw_h[0]
            standard["dpad_up"] = (hy == 1)
            standard["dpad_down"] = (hy == -1)
            standard["dpad_left"] = (hx == -1)
            standard["dpad_right"] = (hx == 1)

        if num_a > 0: standard["left_stick_x"] = float(raw_a[0])
        if num_a > 1: standard["left_stick_y"] = float(raw_a[1])
        if num_a > 2: standard["right_stick_x"] = float(raw_a[2])
        if num_a > 3: standard["right_stick_y"] = float(raw_a[3])
        if num_a > 4: standard["lt"] = max(0.0, min(1.0, (float(raw_a[4]) + 1.0) / 2.0))
        if num_a > 5: standard["rt"] = max(0.0, min(1.0, (float(raw_a[5]) + 1.0) / 2.0))

    elif detected == "playstation":
        # Standard PlayStation DirectInput / HID Mapping
        if num_b >= 14:
            # 0: Square, 1: Cross, 2: Circle, 3: Triangle
            standard["x"] = bool(raw_b[0])
            standard["a"] = bool(raw_b[1])
            standard["b"] = bool(raw_b[2])
            standard["y"] = bool(raw_b[3])

            if num_b > 9: standard["lb"] = bool(raw_b[9])
            elif num_b > 4: standard["lb"] = bool(raw_b[4])

            if num_b > 10: standard["rb"] = bool(raw_b[10])
            elif num_b > 5: standard["rb"] = bool(raw_b[5])

            if num_b > 4: standard["select"] = bool(raw_b[4] if num_b > 9 else raw_b[8])
            if num_b > 6: standard["start"] = bool(raw_b[6] if num_b > 10 else raw_b[9])

            if num_b > 8:
                standard["ls"] = bool(raw_b[7] if num_b > 10 else raw_b[10])
                standard["rs"] = bool(raw_b[8] if num_b > 10 else raw_b[11])

            if num_b > 5: standard["meta"] = bool(raw_b[5] if num_b > 12 else raw_b[12])
            if num_b > 15: standard["touchpad"] = bool(raw_b[15] if num_b > 15 else raw_b[13])

            if num_b > 14 and any(raw_b[11:15]):
                standard["dpad_up"] = bool(raw_b[11])
                standard["dpad_down"] = bool(raw_b[12])
                standard["dpad_left"] = bool(raw_b[13])
                standard["dpad_right"] = bool(raw_b[14])
            elif num_h > 0:
                hx, hy = raw_h[0]
                standard["dpad_up"] = (hy == 1)
                standard["dpad_down"] = (hy == -1)
                standard["dpad_left"] = (hx == -1)
                standard["dpad_right"] = (hx == 1)
        else:
            if num_b > 0: standard["a"] = bool(raw_b[0])
            if num_b > 1: standard["b"] = bool(raw_b[1])
            if num_b > 2: standard["x"] = bool(raw_b[2])
            if num_b > 3: standard["y"] = bool(raw_b[3])
            if num_b > 4: standard["lb"] = bool(raw_b[4])
            if num_b > 5: standard["rb"] = bool(raw_b[5])
            if num_b > 6: standard["select"] = bool(raw_b[6])
            if num_b > 7: standard["start"] = bool(raw_b[7])
            if num_b > 8: standard["ls"] = bool(raw_b[8])
            if num_b > 9: standard["rs"] = bool(raw_b[9])

        if num_a > 0: standard["left_stick_x"] = float(raw_a[0])
        if num_a > 1: standard["left_stick_y"] = float(raw_a[1])
        if num_a > 2: standard["right_stick_x"] = float(raw_a[2])
        if num_a > 3: standard["right_stick_y"] = float(raw_a[3])
        if num_a > 4: standard["lt"] = max(0.0, min(1.0, (float(raw_a[4]) + 1.0) / 2.0))
        elif num_b > 6: standard["lt"] = 1.0 if raw_b[6] else 0.0

        if num_a > 5: standard["rt"] = max(0.0, min(1.0, (float(raw_a[5]) + 1.0) / 2.0))
        elif num_b > 7: standard["rt"] = 1.0 if raw_b[7] else 0.0

    elif detected == "nintendo":
        # Nintendo Switch Physical -> Standard
        if num_b > 0: standard["a"] = bool(raw_b[0])  # B -> Bottom
        if num_b > 1: standard["b"] = bool(raw_b[1])  # A -> Right
        if num_b > 2: standard["x"] = bool(raw_b[2])  # Y -> Left
        if num_b > 3: standard["y"] = bool(raw_b[3])  # X -> Top
        if num_b > 4: standard["select"] = bool(raw_b[4])
        if num_b > 5: standard["start"] = bool(raw_b[5])
        if num_b > 6: standard["ls"] = bool(raw_b[6])
        if num_b > 7: standard["rs"] = bool(raw_b[7])
        if num_b > 8: standard["lb"] = bool(raw_b[8])
        if num_b > 9: standard["rb"] = bool(raw_b[9])
        if num_b > 10: standard["lt"] = 1.0 if raw_b[10] else 0.0
        if num_b > 11: standard["rt"] = 1.0 if raw_b[11] else 0.0
        if num_b > 12: standard["meta"] = bool(raw_b[12])

        if num_h > 0:
            hx, hy = raw_h[0]
            standard["dpad_up"] = (hy == 1)
            standard["dpad_down"] = (hy == -1)
            standard["dpad_left"] = (hx == -1)
            standard["dpad_right"] = (hx == 1)

        if num_a > 0: standard["left_stick_x"] = float(raw_a[0])
        if num_a > 1: standard["left_stick_y"] = float(raw_a[1])
        if num_a > 2: standard["right_stick_x"] = float(raw_a[2])
        if num_a > 3: standard["right_stick_y"] = float(raw_a[3])

    return standard, detected


# Pygame Gamepad Polling Worker Thread
def controller_worker(status_q):
    try:
        import pygame
        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
        pygame.init()
        pygame.joystick.init()
    except Exception as e:
        status_q.put_nowait({"status": "error", "name": f"Pygame Init Error: {e}"})
        return

    joystick = None
    last_known_template = current_template
    active_profile = current_input_profile

    while not shutdown_event.is_set():
        while pygame.joystick.get_count() == 0 and not shutdown_event.is_set():
            try:
                status_q.put_nowait({"status": "disconnected", "name": None})
            except Exception:
                pass
            time.sleep(1.0)
            try:
                pygame.joystick.quit()
                pygame.joystick.init()
            except Exception:
                pass

        if shutdown_event.is_set():
            break

        try:
            joystick = pygame.joystick.Joystick(0)
            joystick.init()
            ctrl_name = joystick.get_name()
            status_q.put_nowait({"status": "connected", "name": ctrl_name})
        except Exception:
            time.sleep(1.0)
            continue

        while not shutdown_event.is_set():
            while not template_queue_controller.empty():
                try:
                    new_t = template_queue_controller.get_nowait()
                    if new_t != last_known_template:
                        last_known_template = new_t
                        socketio.emit('reload_page')
                except Exception:
                    pass

            while not input_profile_queue.empty():
                try:
                    active_profile = input_profile_queue.get_nowait()
                except Exception:
                    pass

            pygame.event.pump()

            if pygame.joystick.get_count() == 0:
                try:
                    status_q.put_nowait({"status": "disconnected", "name": None})
                except Exception:
                    pass
                try:
                    pygame.joystick.quit()
                    pygame.joystick.init()
                except Exception:
                    pass
                break

            try:
                standard_data, profile_used = normalize_controller_input(joystick, active_profile)

                payload = {
                    'standard': standard_data,
                    'profile': profile_used,
                    'axes': [joystick.get_axis(i) for i in range(joystick.get_numaxes())],
                    'buttons': [joystick.get_button(i) for i in range(joystick.get_numbuttons())],
                    'hats': [joystick.get_hat(i) for i in range(joystick.get_numhats())]
                }
                socketio.emit('controller_data', payload)
                time.sleep(0.03)
            except Exception:
                break


# Modern Windows 11 Dark Slate Tkinter Desktop UI
class CryptoPadApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Crypto90's CryptoPad")
        self.root.geometry("680x560")
        self.root.minsize(620, 500)

        # Windows 11 Dark Slate Design Tokens
        self.BG_MAIN = "#121418"
        self.BG_CARD = "#1a1d24"
        self.BG_HOVER = "#242832"
        self.BORDER_COLOR = "#2a303c"
        self.ACCENT_CYAN = "#00d2ff"
        self.ACCENT_GREEN = "#10b981"
        self.ACCENT_AMBER = "#f59e0b"
        self.ACCENT_RED = "#ef4444"
        self.TEXT_PRIMARY = "#f1f5f9"
        self.TEXT_MUTED = "#94a3b8"

        self.root.configure(bg=self.BG_MAIN)
        self.templates = list_available_templates()

        self._configure_styles()
        self._build_header_ui()
        self._build_url_bar_ui()
        self._build_profile_bar_ui()
        self._build_main_content_ui()
        self._build_console_ui()
        self._build_status_bar_ui()

        self.update_preview()
        self.poll_controller_status()

        self.log(f"CryptoPad {CURRENT_VERSION} initialized.", "info")
        self.log("Cross-Controller Normalization Engine Active.", "success")
        self.log(f"HTTP & WebSocket server running on port {server_port}", "success")
        self.log(f"Localhost URL: http://127.0.0.1:{server_port}", "info")
        if lan_ip != "127.0.0.1":
            self.log(f"Dual-PC LAN URL: http://{lan_ip}:{server_port}", "info")

    def _configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        font_family = "Segoe UI" if IS_WINDOWS else "Helvetica"
        style.configure("Custom.TCombobox",
                        foreground="#ffffff",
                        fieldbackground="#242832",
                        background="#1a1d24",
                        arrowcolor="#00d2ff")

    def _build_header_ui(self):
        font_family = "Segoe UI" if IS_WINDOWS else "Helvetica"
        header = tk.Frame(self.root, bg=self.BG_CARD, height=44)
        header.pack(fill=tk.X, padx=0, pady=0)

        brand_label = tk.Label(
            header,
            text="🎮  Crypto90's CryptoPad",
            font=(font_family, 11, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD
        )
        brand_label.pack(side=tk.LEFT, padx=14, pady=8)

        version_badge = tk.Label(
            header,
            text=CURRENT_VERSION,
            font=(font_family, 8, "bold"),
            fg=self.ACCENT_CYAN,
            bg="#222834",
            padx=6,
            pady=1
        )
        version_badge.pack(side=tk.LEFT, padx=4, pady=8)

        self.controller_badge = tk.Label(
            header,
            text="⚪ Detecting Gamepad...",
            font=(font_family, 8, "bold"),
            fg=self.TEXT_MUTED,
            bg="#20242d",
            padx=8,
            pady=2
        )
        self.controller_badge.pack(side=tk.RIGHT, padx=14, pady=8)

        port_badge = tk.Label(
            header,
            text=f"🟢 Port: {server_port}",
            font=(font_family, 8, "bold"),
            fg=self.ACCENT_GREEN,
            bg="#132e27",
            padx=8,
            pady=2
        )
        port_badge.pack(side=tk.RIGHT, padx=6, pady=8)

    def _build_url_bar_ui(self):
        font_family = "Segoe UI" if IS_WINDOWS else "Helvetica"
        url_frame = tk.Frame(self.root, bg=self.BG_MAIN)
        url_frame.pack(fill=tk.X, padx=14, pady=(8, 2))

        tk.Label(
            url_frame,
            text="OBS Browser Source URL:",
            font=(font_family, 9, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_MAIN
        ).pack(anchor="w", pady=(0, 2))

        box = tk.Frame(url_frame, bg=self.BG_CARD, bd=1, relief=tk.FLAT)
        box.pack(fill=tk.X)

        local_url = f"http://127.0.0.1:{server_port}"
        self.url_entry = tk.Entry(
            box,
            bg=self.BG_CARD,
            fg=self.ACCENT_CYAN,
            font=(font_family, 9, "bold"),
            relief=tk.FLAT,
            bd=0
        )
        self.url_entry.insert(0, local_url)
        self.url_entry.configure(state="readonly")
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, ipady=4)

        self.copy_btn = tk.Button(
            box,
            text="📋 Copy Local URL",
            command=lambda: self.copy_url(local_url, self.copy_btn),
            bg="#242832",
            fg=self.TEXT_PRIMARY,
            activebackground="#333a48",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            font=(font_family, 8, "bold"),
            cursor="hand2",
            padx=10,
            pady=2
        )
        self.copy_btn.pack(side=tk.LEFT, padx=4, pady=3)

        if lan_ip != "127.0.0.1":
            lan_url = f"http://{lan_ip}:{server_port}"
            self.copy_lan_btn = tk.Button(
                box,
                text="🌐 Copy LAN (Dual-PC)",
                command=lambda: self.copy_url(lan_url, self.copy_lan_btn),
                bg="#242832",
                fg=self.TEXT_PRIMARY,
                activebackground="#333a48",
                activeforeground="#ffffff",
                relief=tk.FLAT,
                font=(font_family, 8),
                cursor="hand2",
                padx=8,
                pady=2
            )
            self.copy_lan_btn.pack(side=tk.LEFT, padx=2, pady=3)

        open_btn = tk.Button(
            box,
            text="🚀 Open Web",
            command=lambda: webbrowser.open(local_url),
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            font=(font_family, 8, "bold"),
            cursor="hand2",
            padx=8,
            pady=2
        )
        open_btn.pack(side=tk.LEFT, padx=(2, 6), pady=3)

    def _build_profile_bar_ui(self):
        font_family = "Segoe UI" if IS_WINDOWS else "Helvetica"
        p_frame = tk.Frame(self.root, bg=self.BG_MAIN)
        p_frame.pack(fill=tk.X, padx=14, pady=(4, 2))

        box = tk.Frame(p_frame, bg=self.BG_CARD, bd=1, relief=tk.FLAT)
        box.pack(fill=tk.X, ipady=3)

        tk.Label(
            box,
            text="⚡ Cross-Controller Input Profile:",
            font=(font_family, 8, "bold"),
            fg=self.TEXT_MUTED,
            bg=self.BG_CARD
        ).pack(side=tk.LEFT, padx=(10, 6))

        self.profile_var = tk.StringVar(value=current_input_profile)
        profile_options = [
            ("auto", "Auto-Detect (Recommended)"),
            ("xbox", "Force Xbox (XInput)"),
            ("playstation", "Force PlayStation (DualShock / DualSense)"),
            ("nintendo", "Force Nintendo Switch")
        ]

        self.profile_combo = ttk.Combobox(
            box,
            values=[opt[1] for opt in profile_options],
            state="readonly",
            style="Custom.TCombobox",
            width=30
        )
        current_label = next((opt[1] for opt in profile_options if opt[0] == current_input_profile), profile_options[0][1])
        self.profile_combo.set(current_label)
        self.profile_combo.pack(side=tk.LEFT, padx=4)

        def on_change_profile(event):
            selected_text = self.profile_combo.get()
            selected_key = next((opt[0] for opt in profile_options if opt[1] == selected_text), "auto")
            global current_input_profile
            current_input_profile = selected_key
            settings["input_profile"] = current_input_profile
            save_settings_data(settings)
            input_profile_queue.put_nowait(current_input_profile)
            self.log(f"Input mapping profile switched to: {selected_text}", "info")

        self.profile_combo.bind("<<ComboboxSelected>>", on_change_profile)

    def _build_main_content_ui(self):
        font_family = "Segoe UI" if IS_WINDOWS else "Helvetica"
        content_frame = tk.Frame(self.root, bg=self.BG_MAIN)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)

        # Left Column: Controller Skin Selection
        left_box = tk.Frame(content_frame, bg=self.BG_CARD, bd=1, relief=tk.FLAT)
        left_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 8), pady=2)

        tk.Label(
            left_box,
            text="SELECT CONTROLLER SKIN",
            font=(font_family, 8, "bold"),
            fg=self.TEXT_MUTED,
            bg=self.BG_CARD
        ).pack(anchor="w", padx=10, pady=(8, 4))

        list_container = tk.Frame(left_box, bg=self.BG_CARD)
        list_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.skin_listbox = tk.Listbox(
            list_container,
            bg="#0f1115",
            fg=self.TEXT_PRIMARY,
            selectbackground="#0d9488",
            selectforeground="#ffffff",
            font=(font_family, 9),
            relief=tk.FLAT,
            bd=0,
            width=24,
            height=8,
            highlightthickness=1,
            highlightbackground=self.BORDER_COLOR,
            activestyle="none"
        )
        sb = tk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.skin_listbox.yview, bg="#0f1115")
        self.skin_listbox.config(yscrollcommand=sb.set)

        self.skin_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        for i, t in enumerate(self.templates):
            self.skin_listbox.insert(tk.END, f"  {t}")
            if t == current_template:
                self.skin_listbox.selection_set(i)
                self.skin_listbox.activate(i)

        self.skin_listbox.bind("<<ListboxSelect>>", self.on_select_skin)

        # Right Column: High-Res Skin Preview
        right_box = tk.Frame(content_frame, bg=self.BG_CARD, bd=1, relief=tk.FLAT)
        right_box.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(0, 0), pady=2)

        top_bar = tk.Frame(right_box, bg=self.BG_CARD)
        top_bar.pack(fill=tk.X, padx=10, pady=(8, 4))

        self.active_skin_title = tk.Label(
            top_bar,
            text=f"Skin Preview: {current_template}",
            font=(font_family, 9, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD
        )
        self.active_skin_title.pack(side=tk.LEFT)

        preview_wrap = tk.Frame(right_box, bg="#0f1115", bd=1, relief=tk.FLAT)
        preview_wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        self.preview_image_label = tk.Label(
            preview_wrap,
            bg="#0f1115",
            text="Loading preview...",
            fg=self.TEXT_MUTED,
            font=(font_family, 9)
        )
        self.preview_image_label.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        bottom_bar = tk.Frame(right_box, bg=self.BG_CARD)
        bottom_bar.pack(fill=tk.X, padx=10, pady=(4, 8))

        kofi_btn = tk.Button(
            bottom_bar,
            text="☕ Buy me a Coffee",
            command=lambda: webbrowser.open("https://ko-fi.com/crypto90"),
            bg="#d97706",
            fg="#ffffff",
            activebackground="#b45309",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            font=(font_family, 8, "bold"),
            cursor="hand2",
            padx=8,
            pady=2
        )
        kofi_btn.pack(side=tk.RIGHT)

    def _build_console_ui(self):
        font_family = "Segoe UI" if IS_WINDOWS else "Helvetica"
        console_container = tk.Frame(self.root, bg=self.BG_MAIN)
        console_container.pack(fill=tk.X, padx=14, pady=(2, 4))

        bar = tk.Frame(console_container, bg=self.BG_CARD, height=20)
        bar.pack(fill=tk.X)

        tk.Label(
            bar,
            text="ACTIVITY & DIAGNOSTICS CONSOLE",
            font=(font_family, 8, "bold"),
            fg=self.TEXT_MUTED,
            bg=self.BG_CARD
        ).pack(side=tk.LEFT, padx=8, pady=2)

        tk.Button(
            bar,
            text="Clear Console",
            bg=self.BG_CARD,
            fg=self.TEXT_MUTED,
            activebackground=self.BG_CARD,
            activeforeground=self.TEXT_PRIMARY,
            font=(font_family, 7),
            relief=tk.FLAT,
            bd=0,
            command=self.clear_console,
            cursor="hand2"
        ).pack(side=tk.RIGHT, padx=6)

        log_frame = tk.Frame(console_container, bg="#0f1115")
        log_frame.pack(fill=tk.X)

        self.log_text = tk.Text(
            log_frame,
            height=4,
            state=tk.DISABLED,
            bg="#0f1115",
            fg="#e2e8f0",
            insertbackground="white",
            highlightbackground=self.BORDER_COLOR,
            font=("Consolas" if IS_WINDOWS else "Courier", 9),
            relief=tk.FLAT,
            padx=6,
            pady=3
        )
        sb = tk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview, bg="#0f1115")
        self.log_text.config(yscrollcommand=sb.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text.tag_config("error", foreground="#f87171")
        self.log_text.tag_config("info", foreground="#38bdf8")
        self.log_text.tag_config("success", foreground="#34d399")
        self.log_text.tag_config("warn", foreground="#fbbf24")
        self.log_text.tag_config("time", foreground="#64748b")

    def _build_status_bar_ui(self):
        font_family = "Segoe UI" if IS_WINDOWS else "Helvetica"
        self.statusbar = tk.Label(
            self.root,
            text=f"Ready • Local: http://127.0.0.1:{server_port} • Skin: {current_template}",
            bg=self.BG_CARD,
            fg=self.TEXT_MUTED,
            font=(font_family, 8),
            anchor=tk.W,
            padx=12,
            pady=2
        )
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM)

    def log(self, message, level="info"):
        def _write():
            now = datetime.datetime.now().strftime("%H:%M:%S")
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"[{now}] ", "time")
            tag = level if level in ("error", "info", "success", "warn") else "info"
            self.log_text.insert(tk.END, message + "\n", tag)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

        if threading.current_thread() is threading.main_thread():
            _write()
        else:
            self.root.after_idle(_write)

    def clear_console(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def copy_url(self, url, btn):
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        orig_text = btn.cget("text")
        btn.config(text="✓ Copied!", bg=self.ACCENT_GREEN)
        self.root.after(1500, lambda: btn.config(text=orig_text, bg="#242832"))
        self.log(f"Copied '{url}' to clipboard.", "info")

    def on_select_skin(self, event):
        sel = self.skin_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        selected_template = self.templates[idx]
        global current_template
        if selected_template != current_template:
            current_template = selected_template
            settings['template'] = current_template
            save_settings_data(settings)

            template_queue_flask.put_nowait(current_template)
            template_queue_controller.put_nowait(current_template)

            self.active_skin_title.config(text=f"Skin Preview: {current_template}")
            self.statusbar.config(text=f"Ready • Local: http://127.0.0.1:{server_port} • Skin: {current_template}")
            self.log(f"Switched controller skin to '{current_template}'", "success")
            self.update_preview()

    def update_preview(self):
        preview_path = os.path.join(static_root, "images", current_template, "preview.png")
        if os.path.exists(preview_path):
            try:
                img = Image.open(preview_path)
                img.thumbnail((260, 190), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.preview_image_label.config(image=photo, text="")
                self.preview_image_label.image = photo
            except Exception as e:
                self.preview_image_label.config(text="Preview unavailable", image="")
        else:
            self.preview_image_label.config(text="Preview unavailable", image="")

    def poll_controller_status(self):
        try:
            while not controller_status_queue.empty():
                data = controller_status_queue.get_nowait()
                if isinstance(data, dict):
                    status = data.get('status', 'disconnected')
                    name = data.get('name') or "Unknown Controller"

                    if status == "connected":
                        self.controller_badge.config(
                            text=f"🎮 {name}",
                            fg=self.ACCENT_GREEN,
                            bg="#132e27"
                        )
                        self.log(f"Gamepad connected: {name}", "success")
                    elif status == "disconnected":
                        self.controller_badge.config(
                            text="⚪ No Controller Detected",
                            fg=self.TEXT_MUTED,
                            bg="#20242d"
                        )
        except Exception:
            pass

        self.root.after(800, self.poll_controller_status)


def run_flask_socketio():
    try:
        socketio.run(app, host='0.0.0.0', port=server_port, debug=False, allow_unsafe_werkzeug=True)
    except Exception as e:
        print(f"Server error: {e}")


def main():
    enable_high_dpi()

    flask_th = threading.Thread(target=run_flask_socketio, daemon=True)
    flask_th.start()

    ctrl_th = threading.Thread(target=controller_worker, args=(controller_status_queue,), daemon=True)
    ctrl_th.start()

    root = tk.Tk()
    app_gui = CryptoPadApp(root)

    def on_closing():
        shutdown_event.set()
        flask_shutdown_event.set()
        os._exit(0)

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == '__main__':
    main()
