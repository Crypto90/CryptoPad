import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import threading
import time
import shutil
import sys
import os
import tkinter as tk
from tkinter import ttk
import socket
from contextlib import redirect_stdout
import signal



# Console info
print("\n==========================================")
print("CryptoPad - OBS Controller Widget")
print("© Crypto90")
print("https://github.com/Crypto90/CryptoPad")
print("==========================================")


TEMPLATE_SAVE_FILE = ".last_template"
DEFAULT_TEMPLATE = "xbox"
shutdown_event = threading.Event()


def get_exe_dir():
    if getattr(sys, '_MEIPASS', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

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

# GUI to select template
def select_template_gui(template_dir):
    templates = list_templates(template_dir)
    remembered = load_last_template(template_dir)

    def start_countdown():
        seconds = 5
        def countdown():
            nonlocal seconds
            if seconds > 0:
                label_var.set(f"Starting in {seconds} seconds...")
                seconds -= 1
                root.after(1000, countdown)
            else:
                submit()

        countdown()

    def submit():
        nonlocal selected_template
        selected_template = template_var.get()
        save_last_template(selected_template, template_dir)
        root.destroy()

    root = tk.Tk()
    root.title("CryptoPad - OBS Controller Widget")
    root.minsize(width=300, height=1)

    selected_template = remembered
    template_var = tk.StringVar(value=remembered)

    ttk.Label(root, text="Choose Controller Layout:").pack(pady=10)

    for t in templates:
        ttk.Radiobutton(root, text=t.capitalize(), variable=template_var, value=t).pack(padx=20)

    #ttk.Button(root, text="Start Now", command=submit).pack(pady=(10, 5))
    label_var = tk.StringVar()
    ttk.Label(root, textvariable=label_var).pack(pady=5)

    start_countdown()
    root.mainloop()
    return selected_template

# Setup
base_dir = get_exe_dir()
template_root = os.path.join(base_dir, 'templates')
selected_template = select_template_gui(template_root)
template_folder = copy_templates()
template_static = copy_static()
template_path = os.path.join(template_folder, selected_template)

#print(f"Using template path: {template_path}")

# Flask app
app = Flask(__name__, template_folder=template_path)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
controller_state = {}

@app.route('/')
def index():
    return render_template('index.html')

def controller_thread():
    
    with open(os.devnull, 'w') as f, redirect_stdout(f):
        import pygame
        pygame.init()
        pygame.joystick.init()

    # Print the message once
    if not shutdown_event.is_set() and pygame.joystick.get_count() == 0:
        print("No controller detected.", end='', flush=True)

    dot_count = 1
    while not shutdown_event.is_set() and pygame.joystick.get_count() == 0:
        # Cycle the dot count between 1, 2, and 3
        print(f"\rNo controller detected{'.' * dot_count}", end='', flush=True)
        dot_count = (dot_count % 3) + 1  # Cycle dot_count between 1, 2, 3
        time.sleep(1)
        pygame.joystick.quit()
        pygame.joystick.init()

    if pygame.joystick.get_count() == 0 or shutdown_event.is_set():
        return  # Exit early if no controller or shutdown triggered

    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(f"\rController initialized: {joystick.get_name()}")

    while not shutdown_event.is_set():
        pygame.event.pump()
        state = {
            'axes': [joystick.get_axis(i) for i in range(joystick.get_numaxes())],
            'buttons': [joystick.get_button(i) for i in range(joystick.get_numbuttons())],
            'hats': joystick.get_hat(0)
        }
        socketio.emit('controller_data', state)
        time.sleep(0.03)


def get_lan_ip():
    try:
        # Connect to a public IP, doesn't have to be reachable
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def start_controller_thread():
    thread = threading.Thread(target=controller_thread)
    thread.daemon = True
    thread.start()

if __name__ == '__main__':
    try:
        lan_ip = get_lan_ip()
        wport = 5001
        print(f"Widget running at:")
        print(f"Localhost: http://127.0.0.1:{wport}")
        print(f"LAN:       http://{lan_ip}:{wport}")
        print("==========================================\n")
        print("[INFO] Press Ctrl + C to exit gracefully.")

        start_controller_thread()
        socketio.run(app, host='0.0.0.0', port=wport)

    except KeyboardInterrupt:
        print("\n\nExiting... Thank you for using CryptoPad! ✨")
        sys.exit(0)

