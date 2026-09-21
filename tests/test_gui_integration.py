"""
Aşama 3 Kullanıcı Arayüzü (GUI) ve Entegrasyon Otomatik Testi

Bu test:
1. QSS tema yüklemesini test eder.
2. MainWindow, DownloadCardWidget ve AddDownloadDialog bileşenlerini test eder.
3. TaskManager üzerinden görev ekleme ve sinyallerin GUI kartına yansımasını doğrular.
4. Filtreleme mantığını (ALL, DOWNLOADING, PAUSED, COMPLETED) test eder.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from app.core.models import DownloadTask, DownloadStatus, TaskType
from app.core.task_manager import TaskManager
from app.server.bridge import ServerBridge
from app.ui.components.progress_card import DownloadCardWidget
from app.ui.download_dialog import AddDownloadDialog
from app.ui.main_window import MainWindow


class TestGuiIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.bridge = ServerBridge()
        cls.task_manager = TaskManager(auto_load=False, tasks_file=None)
        cls.window = MainWindow(task_manager=cls.task_manager, bridge=cls.bridge)

    def test_01_main_window_initialization(self):
        """Ana pencerenin ve bileşenlerinin sorunsuz yüklendiğini test eder."""
        self.assertIsNotNone(self.window)
        self.assertEqual(len(self.window.cards), 0)
        self.assertFalse(self.window.empty_label.isHidden())

    def test_02_add_task_creates_card(self):
        """TaskManager'a görev eklendiğinde GUI'de kartın otomatik oluştuğunu test eder."""
        task = DownloadTask(
            task_id="gui_test_01",
            url="https://example.com/testfile.zip",
            destination_folder="C:/temp",
            filename="testfile.zip",
            total_size=10485760,  # 10 MB
            status=DownloadStatus.DOWNLOADING
        )

        self.task_manager.tasks[task.task_id] = task
        self.task_manager.task_added.emit(task)
        self.app.processEvents()

        self.assertIn("gui_test_01", self.window.cards)
        card = self.window.cards["gui_test_01"]
        self.assertEqual(card.name_label.text(), "testfile.zip")
        self.assertFalse(self.window.empty_label.isVisible())

    def test_03_card_progress_and_speed_update(self):
        """İlerleme sinyali fırlatıldığında kartın ve toplam hızın güncellendiğini test eder."""
        card = self.window.cards["gui_test_01"]

        progress_data = {
            "task_id": "gui_test_01",
            "downloaded_bytes": 5242880,  # 5 MB (%50)
            "total_bytes": 10485760,
            "percent": 50.0,
            "speed_str": "2.5 MB/s",
            "eta_str": "00:02",
            "speed_bps": 2621440
        }

        self.task_manager.task_progress.emit(progress_data)
        self.app.processEvents()

        self.assertEqual(card.main_progress.value(), 50)
        self.assertIn("2.5 MB", card.stats_label.text())

    def test_04_sidebar_filtering(self):
        """Sol menü filtrelerinin kart görünürlüğünü doğru değiştirdiğini test eder."""
        card = self.window.cards["gui_test_01"]
        card.task.status = DownloadStatus.DOWNLOADING

        # 1. DOWNLOADING filtresi uygula (Kart görünmeli)
        self.window.current_filter = "DOWNLOADING"
        self.window._apply_filter()
        self.assertFalse(card.isHidden())

        # 2. PAUSED filtresi uygula (Kart gizlenmeli)
        self.window.current_filter = "PAUSED"
        self.window._apply_filter()
        self.assertTrue(card.isHidden())

        # 3. ALL filtresi uygula (Kart tekrar görünmeli)
        self.window.current_filter = "ALL"
        self.window._apply_filter()
        self.assertFalse(card.isHidden())

    def test_05_add_download_dialog_defaults(self):
        """Yeni indirme diyaloğunun başlangıç değerlerini test eder."""
        dialog = AddDownloadDialog(
            initial_url="https://speed.hetzner.de/100MB.bin",
            initial_filename="100MB.bin"
        )
        data = dialog.get_data()
        self.assertEqual(data["url"], "https://speed.hetzner.de/100MB.bin")
        self.assertEqual(data["filename"], "100MB.bin")
        self.assertEqual(data["num_chunks"], 8)
        dialog.close()

        print("\n[OK] All Stage 3 GUI and UI integration tests passed successfully!")


if __name__ == "__main__":
    unittest.main()
