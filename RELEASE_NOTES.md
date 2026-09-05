# 🎮 CryptoPad v0.2.3 — Standalone Stability & PyInstaller Runtime Fixes

CryptoPad v0.2.3 resolves critical startup and runtime errors present in standalone executables. It fixes the missing Flask-SocketIO Engine.IO threading driver and bundles the missing `datetime` logger module, ensuring that `CryptoPad.exe` launches instantly and operates reliably without requiring any local Python installation.

---

### 🛠️ Bug Fixes & Stability Improvements

#### 1. 🔌 Engine.IO Threading Driver Bundling
- **Fixed Startup Crash**: Resolves `ValueError: Invalid async_mode specified` when initializing `SocketIO(app, cors_allowed_origins="*", async_mode='threading')`.
- **Automatic Driver Inclusion**: Because `python-engineio` dynamically loads drivers at runtime via `importlib.import_module('engineio.async_drivers.' + mode)`, PyInstaller previously omitted it from standalone builds.
- **Top-Level Driver Import**: Added `import engineio.async_drivers.threading` to `CryptoPad.py` and updated build configurations with `--hidden-import "engineio.async_drivers.threading"`.

#### 2. 📝 Missing `datetime` Logger Module Fix
- **Fixed Startup Crash**: Resolves `NameError: name 'datetime' is not defined` inside `App.log()`, which previously caused the application window to crash on initialization when writing the startup banner to the console.
- **Explicit Import Added**: Imported `datetime` at the top level of `CryptoPad.py`.

#### 3. ⚡ WebSocket Backend & Packaging Modernization
- **Explicit WebSocket Dependency**: Added `simple-websocket>=1.0.0` to `requirements.txt` and `CryptoPad.spec` for low-latency WebSocket streaming.
- **Spec & Asset Bundling**: Added `templates` and `static` directories to PyInstaller `datas` and bundled the application icon (`icon.ico`).
- **Python 3.12+ Syntax Compatibility**: Converted docstrings to raw string format (`r"""..."""`) to eliminate `SyntaxWarning: invalid escape sequence '\C'`.

---

### 📦 Standalone Executable Download

| Asset | Size | Operating System | Description |
| :--- | :--- | :--- | :--- |
| [**`CryptoPad.exe`**](https://github.com/Crypto90/CryptoPad/releases/download/0.2.3/CryptoPad.exe) | ~29 MB | Windows 10 / 11 (64-bit) | Standalone portable executable. No Python installation required. |

### 🚀 Quick Start
1. Download and run `CryptoPad.exe`.
2. Connect your Xbox, PlayStation, or Switch controller.
3. Select your desired skin from the **Template** dropdown.
4. Copy the OBS URL (`http://localhost:5001`) and paste it into an **OBS Studio Browser Source** (Width: `800`, Height: `600`).
