from flask import Flask, render_template
from flask_socketio import SocketIO
import threading
import time
import shutil
import sys
import os
import socket
from contextlib import redirect_stdout
import queue
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk
from jinja2 import FileSystemLoader, ChoiceLoader
import webbrowser
import logging



VERSION = "v0.1.0"

print("\n==========================================")
print(f"CryptoPad - OBS Controller Widget {VERSION}")
print("© Crypto90")
print("https://github.com/Crypto90/CryptoPad")
print("==========================================")

TEMPLATE_SAVE_FILE = ".last_template"
DEFAULT_TEMPLATE = "Xbox"
shutdown_event = threading.Event()
flask_shutdown_event = threading.Event()
current_template = None

controller_thread_handle = None

def get_exe_dir():
    if getattr(sys, '_MEIPASS', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


log_path = os.path.join(get_exe_dir(), 'CryptoPad.log')

class LazyErrorFileHandler(logging.Handler):
    def __init__(self, path):
        super().__init__(level=logging.ERROR)
        self.path = path
        self.file_handler = None

    def emit(self, record):
        if self.file_handler is None:
            # First error — create file handler and add it to root logger
            self.file_handler = logging.FileHandler(self.path, mode='a', encoding='utf-8')
            self.file_handler.setLevel(logging.ERROR)
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
            self.file_handler.setFormatter(formatter)
            logging.getLogger().addHandler(self.file_handler)
        # Delegate actual writing to file handler
        self.file_handler.emit(record)

# Set up root logger with console output or no file handler
logging.basicConfig(
    level=logging.INFO,  # or DEBUG if you want console info logs
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]  # or omit to silence output
)

# Add lazy file handler that creates log file only on first error
logging.getLogger().addHandler(LazyErrorFileHandler(log_path))

# Silence noisy libraries, still only errors to file
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('flask').setLevel(logging.ERROR)
logging.getLogger('socketio').setLevel(logging.ERROR)
logging.getLogger('engineio').setLevel(logging.ERROR)



def copy_templates():
    exe_dir = get_exe_dir()
    temp_dir = getattr(sys, '_MEIPASS', exe_dir)
    src_templates = os.path.join(exe_dir, 'templates')
    dest_templates = os.path.join(temp_dir, 'templates')
    if os.path.exists(src_templates) and not os.path.exists(dest_templates):
        shutil.copytree(src_templates, dest_templates)
        print(f"Copied templates to: {dest_templates}")
    return dest_templates

def copy_static():
    exe_dir = get_exe_dir()
    temp_dir = getattr(sys, '_MEIPASS', exe_dir)
    src_static = os.path.join(exe_dir, 'static')
    dest_static = os.path.join(temp_dir, 'static')
    if os.path.exists(src_static) and not os.path.exists(dest_static):
        shutil.copytree(src_static, dest_static)
        print(f"Copied static to: {dest_static}")
    return dest_static

def list_templates(template_dir):
    return [name for name in os.listdir(template_dir)
            if os.path.isdir(os.path.join(template_dir, name))]

def load_last_template(template_dir):
    path = os.path.join(template_dir, '..', TEMPLATE_SAVE_FILE)
    if os.path.exists(path):
        with open(path, 'r') as f:
            template = f.read().strip()
        if template in list_templates(template_dir):
            return template
    return DEFAULT_TEMPLATE

def save_last_template(template, template_dir):
    path = os.path.join(template_dir, '..', TEMPLATE_SAVE_FILE)
    with open(path, 'w') as f:
        f.write(template)

def select_template_gui(template_dir, queue_flask, queue_ctrl, status_queue, lan_ip, wport):
    def copy_to_clipboard(text):
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()

    def open_in_browser(url):
        webbrowser.open_new(url)

    templates = list_templates(template_dir)
    remembered = load_last_template(template_dir)

    def update_preview(*args):
        selected_template = template_var.get()
        save_last_template(selected_template, template_dir)
        try:
            queue_flask.put_nowait(selected_template)
            queue_flask.put_nowait(selected_template)
            queue_ctrl.put_nowait(selected_template)
            queue_ctrl.put_nowait(selected_template)
        except:
            pass
        skin = selected_template
        preview_path = os.path.join(base_dir, "static", "images", skin, "preview.png")
        
        if os.path.exists(preview_path):
            try:
                img = Image.open(preview_path)
                img = img.resize((300, 300), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                preview_label.config(image=photo, text="")
                preview_label.image = photo
            except Exception as e:
                print(f"[ERROR] Failed to load image: {e}")
                preview_label.config(text="Error loading image", image="")
        else:
            preview_label.config(text="No preview available", image="")
            preview_label.image = None

    root = tk.Tk()
    root.title(f"CryptoPad - OBS Controller Widget {VERSION} © Crypto90")
    root.configure(bg="#1e1e1e")
    root.minsize(width=600, height=350)
    root.resizable(False, False)

    style = ttk.Style()
    style.theme_use('default')
    style.configure("TLabel", background="#1e1e1e", foreground="#ffffff")
    style.configure("TRadiobutton", background="#1e1e1e", foreground="#ffffff", cursor="hand2")
    style.configure("TFrame", background="#1e1e1e")
    
    # Set the hover (active) background to black
    style.map("TRadiobutton",
              background=[("active", "#000000")])

    template_var = tk.StringVar(value=remembered)
    template_var.trace_add("write", update_preview)

    frame = ttk.Frame(root, padding=10)
    frame.pack(fill='both', expand=True)

    left_frame = ttk.Frame(frame)
    left_frame.pack(side='left', fill='y', padx=(0, 10))

    right_frame = ttk.Frame(frame)
    right_frame.pack(side='right', fill='both', expand=True)

    ttk.Label(left_frame, text="Choose Controller Layout:", font=("Arial", 10, "bold")).pack(anchor='w', pady=(0, 10))
    
    max_length = 30
    max_length_names = max(len(t) for t in templates)
    if max_length < max_length_names:
        max_length = max_length_names
    for t in templates:
        rb = ttk.Radiobutton(
            left_frame,
            text=t,
            variable=template_var,
            value=t,
            cursor="hand2",
            width=max_length,
            takefocus=0,  # disables focus highlight
            padding=(5, 4, 5, 4),
        )
        rb.pack(anchor='w', pady=0, padx=0)

    localhost_url = f"http://127.0.0.1:{wport}"
    lan_url = f"http://{lan_ip}:{wport}"
    max_name_length = max(len(name) for name in (localhost_url, lan_url)) - 5

    ttk.Label(left_frame, text="Widget URLs:", font=("Arial", 10, "bold")).pack(anchor='w', pady=(10, 5))

    for label, url in [("localhost", localhost_url), ("LAN", lan_url)]:
        frame_row = ttk.Frame(left_frame)
        frame_row.pack(anchor='w', pady=2, fill='x')
        link = tk.Label(frame_row, text=url, fg="green", cursor="hand2", bg="#1e1e1e",
                        width=max_name_length, anchor='w', justify='left')
        link.pack(side='left')
        link.bind("<Button-1>", lambda e, url=url: open_in_browser(url))
        copy_btn = tk.Button(frame_row, text="Copy", cursor="hand2", bg="#006400",
                             activebackground="#004d00", activeforeground="white", fg="white", relief="flat",
                             command=lambda url=url: copy_to_clipboard(url))
        copy_btn.pack(side='left', padx=(5, 0))

    ttk.Label(left_frame, text="Donate:", font=("Arial", 10, "bold")).pack(anchor='w', pady=(10, 5))
    button_row = ttk.Frame(left_frame)
    button_row.pack(anchor='w', pady=2, fill='x')
    donate_button = tk.Button(button_row, text="Buy me a Coffee ☕", command=lambda: webbrowser.open("https://ko-fi.com/crypto90"),
                              bg="#f39c12", fg="black", activebackground="#d68910", activeforeground="black", cursor="hand2")
    donate_button.pack(side="left", padx=(0, 0))

    controller_status_label = ttk.Label(left_frame, text="Controller: unknown", font=("Arial", 9))
    controller_status_label.pack(anchor='w', pady=(10, 0))
    
    controller_name_label = ttk.Label(left_frame, text="Controller Name: N/A", font=("Arial", 8, "italic"))
    controller_name_label.pack(anchor='w', pady=(0, 10))

    preview_label = ttk.Label(right_frame, text="Loading preview...", anchor='center', justify='center')
    preview_label.pack(expand=True)

    def poll_controller_status():
        try:
            while not status_queue.empty():
                status_data = status_queue.get_nowait()
                # Now we expect status_data as a dict, e.g.:
                # {'status': 'connected', 'name': 'Xbox One Elite 2 Controller'}
                # or {'status': 'disconnected', 'name': None}

                if isinstance(status_data, dict):
                    status = status_data.get('status', 'disconnected')
                    name = status_data.get('name', None)
                else:
                    # backward compatibility, treat as status string only
                    status = status_data
                    name = None

                if status == "connected":
                    controller_status_label.config(text="Controller: ✅ Connected", foreground="green")
                elif status == "disconnected":
                    controller_status_label.config(text="Controller: ❌ Disconnected", foreground="red")

                if name:
                    controller_name_label.config(text=f"{name}")
                else:
                    controller_name_label.config(text="")

        except Exception:
            pass
        root.after(500, poll_controller_status)

    update_preview()
    poll_controller_status()
    root.mainloop()

base_dir = get_exe_dir()
template_root = os.path.join(base_dir, 'templates')
template_folder = copy_templates()
template_static = copy_static()
remembered = load_last_template(template_folder)

#template_queue_flask = multiprocessing.Queue()
#template_queue_controller = multiprocessing.Queue()
#controller_status_queue = multiprocessing.Queue()
template_queue_flask = queue.Queue()
template_queue_controller = queue.Queue()
controller_status_queue = queue.Queue()

current_template = remembered
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
controller_state = {}

@app.before_request
def update_template_from_queue():
    global current_template
    while not template_queue_flask.empty():
        try:
            new_template = template_queue_flask.get_nowait()
            if new_template != current_template:
                print(f"[INFO] [Flask] Template changed to {new_template}")
                current_template = new_template
        except Exception:
            break

@app.route('/')
def index():
    global current_template
    template_path = os.path.join(template_root, current_template)
    original_loader = app.jinja_loader
    new_loader = ChoiceLoader([
        FileSystemLoader(template_path),
        original_loader
    ])
    app.jinja_loader = new_loader
    app.jinja_env.cache.clear()
    try:
        return render_template('index.html')
    finally:
        app.jinja_loader = original_loader

@app.route('/dummy')
def dummy():
    return "Dummy route"

def controller_thread(status_queue):
    import pygame
    pygame.init()
    pygame.joystick.init()

    joystick = None
    last_template = remembered

    while not shutdown_event.is_set():
        while pygame.joystick.get_count() == 0 and not shutdown_event.is_set():
            print("\rNo controller detected...", end='', flush=True)
            try:
                status_queue.put_nowait({"status": "disconnected", "name": None})
            except:
                pass
            time.sleep(1)
            pygame.joystick.quit()
            pygame.joystick.init()

        if shutdown_event.is_set():
            break

        joystick = pygame.joystick.Joystick(0)
        joystick.init()
        controller_name = joystick.get_name()
        print(f"\rController initialized: {controller_name}", end='', flush=True)
        try:
            status_queue.put_nowait({"status": "connected", "name": controller_name})
        except:
            pass

        while not shutdown_event.is_set():
            while not template_queue_controller.empty():
                try:
                    new_template = template_queue_controller.get_nowait()
                    if new_template != last_template:
                        print(f"[INFO] [Controller] Template changed to {new_template}")
                        last_template = new_template
                        global current_template
                        current_template = new_template
                        socketio.emit('reload_page')
                except Exception as e:
                    print(f"[ERROR] Controller queue check failed: {e}")

            pygame.event.pump()

            if pygame.joystick.get_count() == 0:
                print("\rNo controller detected...", end='', flush=True)
                try:
                    status_queue.put_nowait({"status": "disconnected", "name": None})
                except:
                    pass
                pygame.joystick.quit()
                pygame.joystick.init()
                break

            try:
                state = {
                    'axes': [joystick.get_axis(i) for i in range(joystick.get_numaxes())],
                    'buttons': [joystick.get_button(i) for i in range(joystick.get_numbuttons())],
                    'hats': [joystick.get_hat(i) for i in range(joystick.get_numhats())]
                }
                socketio.emit('controller_data', state)
                time.sleep(0.03)
            except pygame.error as e:
                print(f"\n[ERROR] Controller error: {e}")
                pygame.joystick.quit()
                pygame.joystick.init()
                break

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def start_controller_thread(status_queue):
    global controller_thread_handle
    thread = threading.Thread(target=controller_thread, args=(status_queue,))
    thread.daemon = True
    thread.start()
    controller_thread_handle = thread

def stop_controller_thread():
    global controller_thread_handle
    shutdown_event.set()
    if controller_thread_handle is not None:
        controller_thread_handle.join(timeout=5)

def run_tkinter_gui_process(q_flask, q_ctrl, status_q, lan_ip, wport):
    select_template_gui(template_root, q_flask, q_ctrl, status_q, lan_ip, wport)

def run_flask(wport):
    try:
        logging.info(f"Starting Flask server with template: {current_template}")
        socketio.run(app, host='0.0.0.0', port=wport, debug=False, allow_unsafe_werkzeug=True)
    except Exception:
        logging.exception("Flask server failed to start:")



if __name__ == '__main__':
    try:
        lan_ip = get_lan_ip()
        wport = 5001
        print("Widget running at:")
        print(f"Localhost: http://127.0.0.1:{wport}")
        print(f"LAN:       http://{lan_ip}:{wport}")
        print("==========================================\n")
        print("[INFO] Press Ctrl + C to exit gracefully.")
        
        
        flask_thread = threading.Thread(target=run_flask, args=(wport,))
        flask_thread.daemon = True
        flask_thread.start()
        

        gui_thread = threading.Thread(
            target=run_tkinter_gui_process,
            args=(template_queue_flask, template_queue_controller, controller_status_queue, lan_ip, wport)
        )
        gui_thread.daemon = True
        gui_thread.start()

        start_controller_thread(controller_status_queue)
        
        

        while gui_thread.is_alive():
            time.sleep(0.5)

        print("\n\nExiting... Thank you for using CryptoPad! ✨")
        shutdown_event.set()
        flask_shutdown_event.set()
        stop_controller_thread()
        os._exit(0)

    except KeyboardInterrupt:
        print("\n\nExiting... Thank you for using CryptoPad! ✨")
