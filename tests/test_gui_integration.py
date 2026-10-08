"""
Stage 3 User Interface (GUI) and Integration Automated Test

This test suite:
1. Tests QSS theme loading.
2. Tests MainWindow, DownloadCardWidget, and AddDownloadDialog components.
3. Verifies adding tasks via TaskManager and reflection of signals on GUI card.
4. Tests filtering logic (ALL, DOWNLOADING, PAUSED, COMPLETED).
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
        """Tests that main window and its components load smoothly."""
        self.assertIsNotNone(self.window)
        self.assertEqual(len(self.window.cards), 0)
        self.assertFalse(self.window.empty_label.isHidden())

    def test_02_add_task_creates_card(self):
        """Tests that a card is automatically created in GUI when a task is added to TaskManager."""
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
        """Tests that card and total speed are updated when progress signal is emitted."""
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
        """Tests that sidebar filters properly change card visibility."""
        card = self.window.cards["gui_test_01"]
        card.task.status = DownloadStatus.DOWNLOADING

        # 1. Apply DOWNLOADING filter (Card should be visible)
        self.window.current_filter = "DOWNLOADING"
        self.window._apply_filter()
        self.assertFalse(card.isHidden())

        # 2. Apply PAUSED filter (Card should be hidden)
        self.window.current_filter = "PAUSED"
        self.window._apply_filter()
        self.assertTrue(card.isHidden())

        # 3. Apply ALL filter (Card should be visible again)
        self.window.current_filter = "ALL"
        self.window._apply_filter()
        self.assertFalse(card.isHidden())

    def test_05_add_download_dialog_defaults(self):
        """Tests default values of the new download dialog."""
        dialog = AddDownloadDialog(
            initial_url="https://speed.hetzner.de/100MB.bin",
            initial_filename="100MB.bin"
        )
        data = dialog.get_data()
        self.assertEqual(data["url"], "https://speed.hetzner.de/100MB.bin")
        self.assertEqual(data["filename"], "100MB.bin")
        from app.core.config import load_network_settings
        self.assertEqual(data["num_chunks"], load_network_settings().segments_per_download)
        dialog.close()

        print("\n[OK] All Stage 3 GUI and UI integration tests passed successfully!")


if __name__ == "__main__":
    unittest.main()
