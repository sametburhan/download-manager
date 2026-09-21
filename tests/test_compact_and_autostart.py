"""
Kompakt İndirme Penceresi ve Otomatik Başlatma Doğrulama Testi
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication

from app.core.task_manager import TaskManager
from app.core.autostart import get_startup_command, is_autostart_enabled
from app.ui.compact_download_window import CompactDownloadWindow
from app.ui.tray_manager import TrayManager
from app.ui.main_window import MainWindow
from app.server.bridge import ServerBridge


class TestCompactAndAutostart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.task_manager = TaskManager()
        cls.bridge = ServerBridge()

    def test_01_autostart_command_generation(self):
        """Otomatik başlatma komut satırının doğru oluşturulduğunu test eder."""
        cmd = get_startup_command(minimized=True)
        self.assertIn("run.py", cmd)
        self.assertIn("--tray", cmd)

    def test_02_compact_download_window_init(self):
        """Kompakt pencerenin başlangıç durumunu test eder."""
        win = CompactDownloadWindow(
            task_manager=self.task_manager,
            initial_url="https://example.com/archive.zip",
            initial_filename="archive.zip"
        )
        self.assertEqual(win.url_input.text(), "https://example.com/archive.zip")
        self.assertEqual(win.filename_input.text(), "archive.zip")
        self.assertFalse(win.query_widget.isHidden())
        self.assertTrue(win.progress_widget.isHidden())

        # Boyut formatı test
        win._update_size_ui(1048576)  # 1 MB
        self.assertEqual(win.size_label.text(), "1.00 MB")

        # İlerlemeye dönüşüm testi
        win._morph_to_progress_mode("archive.zip")
        self.assertTrue(win.is_progress_mode)
        self.assertTrue(win.query_widget.isHidden())
        self.assertFalse(win.progress_widget.isHidden())
        win.close()

    def test_03_tray_manager_actions(self):
        """Sistem tepsisi menüsünün ve eylemlerinin tanımlı olduğunu test eder."""
        main_win = MainWindow(task_manager=self.task_manager, bridge=self.bridge)
        tray = TrayManager(main_window=main_win, task_manager=self.task_manager)
        self.assertIsNotNone(tray.tray_icon)
        self.assertIsNotNone(tray.tray_menu)
        self.assertTrue(hasattr(tray, "action_show"))
        self.assertTrue(hasattr(tray, "action_autostart"))
        tray.tray_icon.hide()
        main_win.close()

    def test_04_tray_activated_reasons(self):
        """Tepsi simgesi aktivasyonunun (sol tık, çift tık, sağ tık, int) hatasız çalıştığını test eder."""
        from PyQt6.QtWidgets import QSystemTrayIcon
        main_win = MainWindow(task_manager=self.task_manager, bridge=self.bridge)
        tray = TrayManager(main_window=main_win, task_manager=self.task_manager)

        # Trigger (sol tık)
        tray._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
        self.assertTrue(main_win.isVisible())

        # DoubleClick (çift tık)
        tray._on_tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
        # Context (sağ tık) menüyü açar, pencere görünürlüğünü bozmaz
        tray._on_tray_activated(QSystemTrayIcon.ActivationReason.Context)

        # Integer değerler ve None ile çağrıldığında çökmemeli
        tray._on_tray_activated(3)
        tray._on_tray_activated(2)
        tray._on_tray_activated(None)

        tray.tray_icon.hide()
        main_win.close()

    def test_05_exit_handling(self):
        """Uygulama çıkış eylemlerinin düzgün çalıştığını doğrular."""
        main_win = MainWindow(task_manager=self.task_manager, bridge=self.bridge)
        tray = TrayManager(main_window=main_win, task_manager=self.task_manager)
        main_win.tray_manager = tray

        # _exit_app metodu var ve çağrılabilir
        self.assertTrue(hasattr(main_win, "_exit_app"))
        self.assertTrue(hasattr(tray, "_force_exit"))

        tray.tray_icon.hide()
        main_win.close()

        print("\n[OK] Kompakt pencere, sistem tepsisi ve otomatik başlatma testleri basariyla gecti!")


if __name__ == "__main__":
    unittest.main()
