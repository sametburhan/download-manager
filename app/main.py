"""
Download Manager - Ana Başlangıç Noktası (Application Entry Point)

Bu dosya, Windows 11 Fluent tasarımına sahip modern kullanıcı arayüzünü (MainWindow),
WebSocket haberleşme sunucusunu ve çok parçalı indirme motorunu bir araya getirerek
uygulamayı başlatır.
"""

import sys
import os

# Proje ana dizinini Python yoluna ekle (python app/main.py çalıştırıldığında 'app' paketinin bulunması için)
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
    """Download Manager modern QSS stil dosyasını yükler."""
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
    # 0. Windows Görev Çubuğunda Kendi Logo ve İkonumuzu Göster
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("downloadmanager.desktop.app.1.0")
    except Exception:
        pass

    # 1. PyQt6 Uygulamasını Başlat
    app = QApplication(sys.argv)
    app.setApplicationName("Download Manager")
    app.setApplicationVersion("1.0.0")

    # Uygulama ve tüm pencereler için resmi logoyu ata
    app.setWindowIcon(get_app_icon())

    # Pencereler kapandığında uygulamanın sistem tepsisinde açık kalmasını sağla
    app.setQuitOnLastWindowClosed(False)

    # 2. Modern Koyu Temayı Uygula
    load_stylesheet(app)

    # 3. Çekirdek Yöneticileri ve Sinyal Köprüsünü Oluştur
    bridge = ServerBridge()
    task_manager = TaskManager()

    # 4. Ana Pencereyi Oluştur ve Sinyalleri Bağla
    window = MainWindow(task_manager=task_manager, bridge=bridge)

    # 5. Sistem Tepsisi Yöneticisini (System Tray) Başlat
    tray_manager = TrayManager(main_window=window, task_manager=task_manager)
    window.tray_manager = tray_manager

    # 6. WebSocket Sunucusunu Başlat
    ws_thread = WebSocketServerThread(host="127.0.0.1", port=6800, bridge=bridge)
    ws_thread.start()

    # Uygulama tamamen kapatıldığında WebSocket sunucusunu temiz durdur, görevleri kaydet ve tepsi simgesini kaldır
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

    # 7. Başlatma Modu: Eğer --tray veya --minimized ile açıldıysa pencereyi gösterme, tepside kal
    start_minimized = ("--tray" in sys.argv) or ("--minimized" in sys.argv)
    if not start_minimized:
        window.show()
    else:
        tray_manager.show_notification(
            "Download Manager",
            "Application started silently in system tray at Windows startup."
        )

    # 8. Olay Döngüsünü Çalıştır
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
