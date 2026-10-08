"""
Download Manager - Application Entry Point (main.py)

This file launches the application by bringing together the modern user interface
with Windows 11 Fluent design (MainWindow), the WebSocket communication server,
and the multi-chunk download engine.
"""

import sys
import os

# Add project root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from app.core.task_manager import TaskManager
from app.server.bridge import ServerBridge
from app.server.ws_server import WebSocketServerThread
from app.ui.main_window import MainWindow
from app.ui.tray_manager import TrayManager
from app.utils.icon_utils import get_app_icon


def load_stylesheet(app: QApplication) -> None:
    """Loads Download Manager modern QSS stylesheet."""
    ab_qss_path = os.path.join(os.path.dirname(__file__), "ui", "styles", "ab_dark_theme.qss")
    fallback_qss_path = os.path.join(os.path.dirname(__file__), "ui", "styles", "windows11_dark.qss")
    
    qss_file = ab_qss_path if os.path.exists(ab_qss_path) else fallback_qss_path
    if os.path.exists(qss_file):
        try:
            with open(qss_file, "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
        except Exception as exc:
            print(f"Style loading error: {exc}")


def main():
    # 0. Set Explicit AppUserModelID to display custom icon in Windows Taskbar
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("downloadmanager.desktop.app.1.0")
    except Exception:
        pass

    # 1. Initialize PyQt6 Application
    from app import __version__
    app = QApplication(sys.argv)
    app.setApplicationName("Download Manager")
    app.setApplicationVersion(__version__)

    # Set official logo for application and all windows
    app.setWindowIcon(get_app_icon())

    # Ensure application stays active in system tray when windows are closed
    app.setQuitOnLastWindowClosed(False)

    # 2. Apply Modern Dark Theme
    load_stylesheet(app)

    # 3. Initialize Core Managers and Signal Bridge
    bridge = ServerBridge()
    task_manager = TaskManager()

    # 4. Create Main Window and Connect Signals
    window = MainWindow(task_manager=task_manager, bridge=bridge)

    # 5. Initialize System Tray Manager
    tray_manager = TrayManager(main_window=window, task_manager=task_manager)
    window.tray_manager = tray_manager

    # 6. Start WebSocket Server
    ws_thread = WebSocketServerThread(host="127.0.0.1", port=6800, bridge=bridge)
    ws_thread.start()

    # Clean shutdown hook: stop WebSocket server, save tasks, and hide tray icon
    def on_exit():
        try:
            task_manager.save_tasks(force=True)
        except Exception as e:
            print(f"[WARN] Error saving tasks on exit: {e}")
        try:
            if hasattr(tray_manager, "tray_icon") and tray_manager.tray_icon:
                tray_manager.tray_icon.hide()
        except Exception:
            pass
        ws_thread.stop()

    app.aboutToQuit.connect(on_exit)

    # 7. Startup Mode: If opened with --tray or --minimized, stay silently in tray
    start_minimized = ("--tray" in sys.argv) or ("--minimized" in sys.argv)
    if not start_minimized:
        window.show()
    else:
        tray_manager.show_notification(
            "Download Manager",
            "Application started silently in system tray at Windows startup."
        )

    # 8. Run Event Loop
    sys.exit(app.exec())



if __name__ == "__main__":
    main()
