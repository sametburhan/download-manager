# ⚡ Download Manager

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt&logoColor=white)](https://riverbankcomputing.com/software/pyqt/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?logo=windows&logoColor=white)](https://microsoft.com)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-51%20Passing-brightgreen.svg)](#running-tests)

A high-performance, modern multi-threaded download accelerator and streaming video downloader for Windows, built with **Python**, **PyQt6**, and **yt-dlp**.

Featuring an **IDM-style segmented chunk downloader**, automated browser interception via a **Manifest V3 extension**, an acrylic **Windows 11 Fluent Dark UI**, and an interactive **Inno Setup installer pipeline**.

---

## 🌟 Key Features

### 🚀 Segmented Multi-Threaded HTTP Downloader
* **Dynamic Connection Slicing**: Splits files into up to 16–32 parallel segments using HTTP `Range` headers, saturating available bandwidth.
* **Pre-Download Size & Quota Probing**: Asynchronously queries file sizes, resumability, and server capabilities prior to download with real-time status feedback.
* **Resumable & Fault-Tolerant**: Seamlessly resumes interrupted downloads; automatically reconnects when connections drop.
* **Smart Categorization**: Automatically groups downloads into Compressed, Documents, Music, Videos, Programs, and Media.

### 🎬 Comprehensive Video & Media Downloader
* **Powered by yt-dlp & FFmpeg**: Full streaming media support for YouTube, Vimeo, Twitter/X, and thousands of video sites.
* **Resolution & Format Selection**: Choose from 8K UHD, 4K, 2K, 1080p, 720p, or convert to MP4, MKV, WEBM, FLV, AVI.
* **Audio Extraction**: Directly extract audio tracks to MP3 (320 kbps / 192 kbps / 128 kbps), M4A, FLAC, WAV, and AAC.
* **Subtitles & Playlists**: Download multi-language subtitles (including auto-generated tracks) and entire video playlists with one click.
* **Dual Action Modes**: **Download Now** (instant download with live progress) or **Download Later** (queues task in paused state for scheduled batches).

### 📊 Real-Time IDM Progress Diagnostics
* **Live Segment Visualization**: Real-time table and neon gradient segment bars tracking individual chunk progress.
* **Detailed Transfer Metrics**: Live transfer rate (MB/s), elapsed time, estimated time of arrival (ETA), and byte counts.
* **Post-Download Actions**: Instantly open the destination folder or launch downloaded files in default players.

### 🔌 Universal Browser Extension (Chrome, Opera, Firefox)
* **Manifest V3 Architecture**: Lightweight browser extension connecting to the desktop app via a local WebSocket bridge (`ws://127.0.0.1:6800`).
* **Automatic Interception**: Intercepts file download links and triggers the desktop download window automatically.
* **Streaming Media Detector**: Sniffs active video streams on web pages and displays an IDM-style **"Download This Video"** overlay and popup menu.
* **Context Menu**: Right-click any link or media element to **"Download with Download Manager"**.

### 🎨 Windows 11 Fluent Dark Acrylic UI
* **Modern Aesthetic**: Dark acrylic glassmorphism (`#0b0f19`), subtle neon accents (`#38bdf8`, `#6366f1`), and crisp Segoe UI typography.
* **System Tray Integration**: Minimize to tray with continuous background downloads and native Windows balloon notifications.
* **Windows Autostart**: Optional Windows startup launch via registry integration.
* **Proxy Configuration**: Comprehensive network settings supporting Direct, Windows System Proxy, or Manual HTTP/SOCKS5 proxies with authentication.

### 📦 Interactive Packaging & Installer Pipeline
* **Custom Inno Setup Wizard**: Compiles standalone executables using PyInstaller and packages them into a Windows setup installer.
* **Interactive Versioning**: `build.bat` prompts for release versions (e.g. `1.1.0`), automatically updates executable file version metadata, and produces clean installer artifacts.

---

## 📁 Repository Structure

```
download-manager/
├── app/
│   ├── core/                  # Core engines: HTTP chunk downloader, yt-dlp media downloader, task manager
│   │   ├── http_downloader.py   # Multi-part parallel chunk download worker
│   │   ├── media_downloader.py  # yt-dlp metadata extractor and media downloader
│   │   ├── task_manager.py      # Download task queue, persistence, and signal coordinator
│   │   ├── config.py            # Application settings and proxy configurations
│   │   └── models.py            # Data structures, enums, and download task models
│   ├── server/                # WebSocket bridge for browser extension
│   │   ├── ws_server.py         # Async WebSocket server listening on port 6800
│   │   ├── bridge.py            # Thread-safe Qt signal bridge between WebSocket and GUI
│   │   └── protocol.py          # JSON-RPC command parser and message schemas
│   ├── ui/                    # PyQt6 graphical interface
│   │   ├── main_window.py       # Main window with download table, categories, and toolbar
│   │   ├── compact_download_window.py # Pre-download size query and live progress dialog
│   │   ├── media_dialog.py      # Video download quality selector and live progress view
│   │   ├── download_detail_window.py  # Segment inspection and chunk diagnostics
│   │   ├── settings_dialog.py   # Network and proxy configuration dialog
│   │   ├── delete_dialog.py     # Deletion confirmation and disk clean-up modal
│   │   ├── tray_manager.py      # System tray icon and background lifecycle manager
│   │   └── styles/              # Windows 11 Fluent dark acrylic stylesheets
│   └── utils/                 # File and icon utility functions
├── extension/                 # Browser Extension (Manifest V3)
│   ├── manifest.json          # Chrome, Opera, and Firefox compatible manifest
│   ├── background.js          # Service worker managing downloads and WebSocket bridge
│   ├── content.js             # Media stream sniffer and floating download buttons
│   ├── popup/                 # Toolbar popup menu (HTML/CSS/JS)
│   └── icons/                 # Extension toolbar and badge icons
├── installer/                 # Inno Setup installation scripts and compiler configs
├── tests/                     # Automated unit and integration test suite (51 tests)
├── website/                   # Modern landing page and extension setup documentation
├── build.bat                  # Interactive build and packaging script
├── build.spec                 # PyInstaller specification file
├── requirements.txt           # Python package dependencies
├── run.py                     # Application entry point
└── LICENSE                    # MIT License
```

---

## 🚀 Getting Started

### Prerequisites
* **Windows 10 or Windows 11** (64-bit recommended)
* **Python 3.10** or higher
* **FFmpeg** (Recommended for video format conversion and audio extraction; automatically resolved if available in PATH)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/download-manager.git
   cd download-manager
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the application:**
   ```bash
   python run.py
   ```

---

## 🧩 Browser Extension Setup (Sideloading)

The browser extension integrates seamlessly with Google Chrome, Opera, and Mozilla Firefox.

### Google Chrome & Chromium Browsers (Brave, Edge)
1. Open your browser and navigate to `chrome://extensions/`.
2. Toggle on **Developer mode** in the top-right corner.
3. Click **"Load unpacked"** in the top-left corner.
4. Select the `extension/` folder in this repository.
5. When Download Manager is running, the extension badge will show green **ON**.

### Opera
1. Navigate to `opera://extensions`.
2. Enable **Developer mode** in the top-right corner.
3. Click **"Load unpacked"** and select the `extension/` folder.

### Mozilla Firefox
1. Navigate to `about:debugging#/runtime/this-firefox`.
2. Click **"Load Temporary Add-on..."**.
3. Select the `extension/manifest.json` file.

---

## 🛠️ Building the Installer (.exe)

### Option A: Local Build (Windows)
An interactive script is provided to compile the standalone binary with PyInstaller and create an Inno Setup installer on your local machine.

1. **Ensure Inno Setup 6 is installed** on your system:
   * Download from: [Inno Setup Downloads](https://jrsoftware.org/isinfo.php)
2. **Run the build script:**
   ```cmd
   build.bat
   ```
3. Enter the desired version tag when prompted (e.g. `1.1.0`).
4. The compiled installer executable will be saved in `dist/DownloadManagerSetup.exe`.

### Option B: Automated Cloud Build & Release (GitHub Actions)
The repository includes a ready-to-use **GitHub Actions CI/CD pipeline** (`.github/workflows/build-release.yml`):
* **Trigger via Git Tag:** Push a tag like `git tag v1.1.0 && git push origin v1.1.0`.
* **Trigger Manually:** Navigate to the **Actions** tab in GitHub, select **"Build & Release Download Manager"**, click **"Run workflow"**, and enter your version number.
* GitHub Actions will automatically:
  1. Run all 51 automated tests on a Windows runner.
  2. Compile the standalone `.exe` using PyInstaller.
  3. Package the setup installer using Inno Setup.
  4. Create a **GitHub Release** with auto-generated release notes and attach the installer (`.exe`), portable archive (`.zip`), and browser extension (`.zip`).

---

## 🧪 Running Tests

The test suite covers HTTP segmented downloads, yt-dlp media extraction, WebSocket server synchronization, task persistence, and PyQt6 GUI components.

To execute all 51 automated tests:

```powershell
python -m unittest discover tests
```

---

## 🌐 Marketing & Documentation Website

A responsive website is included in `website/` featuring:
* Product overview and download buttons.
* Animated feature highlights and screenshots.
* Step-by-step browser extension installation guide with interactive tabs.
* Contact and support form.

Open `website/index.html` in any web browser to view the site.

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.
