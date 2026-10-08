"""
Download Manager UI and Detail Window Automated Tests (test_ab_ui.py)

This test suite:
1. Verifies table, column, and cell components of the Download Manager UI (MainWindow).
2. Tests live search box and category tree filtering functions.
3. Tests DownloadDetailWindow tabs, parts table, and live segment indicators.
4. Verifies opening detail window via double click on rows and live signal transmission.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from app.core.models import DownloadTask, DownloadStatus, TaskType, ChunkInfo
from app.core.task_manager import TaskManager
from app.server.bridge import ServerBridge
from app.ui.main_window import MainWindow, FileNameCellWidget, StatusCellWidget
from app.ui.download_detail_window import DownloadDetailWindow


class TestAbDownloadManagerUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls.bridge = ServerBridge()
        cls.task_manager = TaskManager(
            tasks_file=os.path.join(cls._tmp_dir.name, "tasks.json"),
            auto_load=False
        )
        cls.window = MainWindow(task_manager=cls.task_manager, bridge=cls.bridge)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.window.close()
            cls._tmp_dir.cleanup()
        except Exception:
            pass

    def test_01_main_window_ab_structure(self):
        """Tests validity of the Download Manager main window structure."""
        self.assertEqual(self.window.windowTitle(), "Download Manager")
        self.assertIsNotNone(self.window.search_bar)
        self.assertIsNotNone(self.window.sidebar_tree)
        self.assertIsNotNone(self.window.downloads_table)

        # Table column count and headers
        self.assertEqual(self.window.downloads_table.columnCount(), 7)
        expected_headers = ["", "FILE NAME", "SIZE", "PROGRESS & STATUS", "SPEED", "TIME LEFT", "DATE"]
        for col_idx, expected in enumerate(expected_headers):
            item = self.window.downloads_table.horizontalHeaderItem(col_idx)
            self.assertIsNotNone(item)
            self.assertEqual(item.text(), expected)

    def test_02_add_task_table_row_and_widgets(self):
        """Verifies task is added to table with custom cell widgets."""
        task = DownloadTask(
            task_id="ab_test_video",
            url="https://example.com/video.mp4",
            destination_folder="C:/Downloads",
            filename="Stories-of-Shahnameh.mp4",
            total_size=1224065600,  # ~1.14 GB
            status=DownloadStatus.DOWNLOADING,
            is_resumable=True
        )

        self.task_manager.tasks[task.task_id] = task
        self.task_manager.task_added.emit(task)
        self.app.processEvents()

        # Table must have at least 1 row
        self.assertGreaterEqual(self.window.downloads_table.rowCount(), 1)
        row = self.window.task_rows.get("ab_test_video")
        self.assertIsNotNone(row)

        # Column 1: FileNameCellWidget
        name_cell = self.window.downloads_table.cellWidget(row, 1)
        self.assertIsInstance(name_cell, FileNameCellWidget)
        self.assertEqual(name_cell.name_lbl.text(), "Stories-of-Shahnameh.mp4")
        self.assertTrue("Video" in name_cell.cat_lbl.text() or "example.com" in name_cell.cat_lbl.text())

        # Column 3: StatusCellWidget
        status_cell = self.window.downloads_table.cellWidget(row, 3)
        self.assertIsInstance(status_cell, StatusCellWidget)

    def test_03_live_progress_and_mini_bar_update(self):
        """Tests that mini bar and speed metrics in table are updated via progress signal."""
        progress_data = {
            "task_id": "ab_test_video",
            "downloaded_bytes": 477385584,
            "total_bytes": 1224065600,
            "percent": 39.0,
            "speed_str": "4.91 MB/s",
            "eta_str": "2 m 22 s",
            "speed_bps": 5148500
        }

        self.task_manager.task_progress.emit(progress_data)
        self.app.processEvents()

        row = self.window.task_rows.get("ab_test_video")
        status_cell = self.window.downloads_table.cellWidget(row, 3)
        self.assertIn("Downloading", status_cell.label.text())
        self.assertEqual(status_cell.pct_label.text(), "39%")
        self.assertEqual(status_cell.progress_bar.value(), 39)

        speed_item = self.window.downloads_table.item(row, 4)
        self.assertIn("4.91 MB/s", speed_item.text())

    def test_04_live_search_filter(self):
        """Tests that live search box immediately filters rows."""
        # Add a second task
        task2 = DownloadTask(
            task_id="ab_test_audio",
            url="https://example.com/audio.mp3",
            destination_folder="C:/Downloads",
            filename="Guitar.mp3",
            total_size=2222981,
            status=DownloadStatus.COMPLETED
        )
        self.task_manager.tasks[task2.task_id] = task2
        self.task_manager.task_added.emit(task2)
        self.app.processEvents()

        row_video = self.window.task_rows["ab_test_video"]
        row_audio = self.window.task_rows["ab_test_audio"]

        # Search 'Guitar' -> Only audio should be visible
        self.window.search_bar.setText("Guitar")
        self.app.processEvents()
        self.assertTrue(self.window.downloads_table.isRowHidden(row_video))
        self.assertFalse(self.window.downloads_table.isRowHidden(row_audio))

        # Clear search -> Both should be visible
        self.window.search_bar.setText("")
        self.app.processEvents()
        self.assertFalse(self.window.downloads_table.isRowHidden(row_video))
        self.assertFalse(self.window.downloads_table.isRowHidden(row_audio))

    def test_05_download_detail_window(self):
        """Tests structure and components of detailed download window (DownloadDetailWindow)."""
        task = self.task_manager.get_task("ab_test_video")
        task.downloaded_size = 477385584  # %39
        detail_win = DownloadDetailWindow(task=task, task_manager=self.task_manager, parent=self.window)

        self.assertIn("39%-Stories-of-Shahnameh.mp4", detail_win.windowTitle())
        self.assertEqual(detail_win.name_val.text(), "Stories-of-Shahnameh.mp4")
        self.assertEqual(detail_win.resume_val.text(), "Yes")
        from app.core.config import load_network_settings
        self.assertEqual(len(detail_win._segment_boxes), load_network_settings().segments_per_download)
        self.assertEqual(detail_win.part_table.columnCount(), 4)

        # Chunk progress update
        detail_win._on_chunk_progress("ab_test_video", 0, 67108864, 152406560)
        self.app.processEvents()
        item_status = detail_win.part_table.item(0, 1)
        self.assertEqual(item_status.text(), "Receiving Data")

        # Toggle Part Info
        detail_win._toggle_part_info()
        self.assertTrue(detail_win.part_container.isHidden())
        detail_win._toggle_part_info()
        self.assertFalse(detail_win.part_container.isHidden())

        detail_win.close()

    def test_06_app_icon_and_pixmap(self):
        """Tests validity of application icon and pixmap utilities."""
        from app.utils.icon_utils import get_app_icon, get_app_pixmap
        icon = get_app_icon()
        self.assertFalse(icon.isNull())

        pix = get_app_pixmap(32)
        self.assertFalse(pix.isNull())
        self.assertEqual(pix.width(), 32)
        self.assertEqual(pix.height(), 32)
    def test_07_table_column_sorting(self):
        """Tests sorting by name, size, and date when table column headers are clicked."""
        # DATE sorting (Column 6)
        # Click 1: Newest to oldest (Descending)
        self.window._on_header_section_clicked(6)
        self.app.processEvents()
        self.assertEqual(self.window._sort_column, 6)
        self.assertEqual(self.window._sort_order, Qt.SortOrder.DescendingOrder)

        first_tid = self.window.row_tasks.get(0)
        last_tid = self.window.row_tasks.get(self.window.downloads_table.rowCount() - 1)
        task_first = self.task_manager.get_task(first_tid)
        task_last = self.task_manager.get_task(last_tid)
        self.assertGreaterEqual(task_first.created_at, task_last.created_at)

        # Click 2: Oldest to newest (Ascending)
        self.window._on_header_section_clicked(6)
        self.app.processEvents()
        self.assertEqual(self.window._sort_order, Qt.SortOrder.AscendingOrder)
        first_tid_asc = self.window.row_tasks.get(0)
        last_tid_asc = self.window.row_tasks.get(self.window.downloads_table.rowCount() - 1)
        task_first_asc = self.task_manager.get_task(first_tid_asc)
        task_last_asc = self.task_manager.get_task(last_tid_asc)
        self.assertLessEqual(task_first_asc.created_at, task_last_asc.created_at)

        # FILE NAME sorting (Column 1)
        # Click 1: A-Z (Ascending)
        self.window._on_header_section_clicked(1)
        self.app.processEvents()
        self.assertEqual(self.window._sort_column, 1)
        self.assertEqual(self.window._sort_order, Qt.SortOrder.AscendingOrder)

        # Click 2: Z-A (Descending)
        self.window._on_header_section_clicked(1)
        self.app.processEvents()
        self.assertEqual(self.window._sort_order, Qt.SortOrder.DescendingOrder)

        # SIZE sorting (Column 2)
        # Click 1: Largest to smallest (Descending)
        self.window._on_header_section_clicked(2)
        self.app.processEvents()
        self.assertEqual(self.window._sort_column, 2)
        self.assertEqual(self.window._sort_order, Qt.SortOrder.DescendingOrder)

        # Click 2: Smallest to largest (Ascending)
        self.window._on_header_section_clicked(2)
        self.app.processEvents()
        self.assertEqual(self.window._sort_order, Qt.SortOrder.AscendingOrder)

        print("\n[OK] All Download Manager UI and detail window tests passed successfully!")


if __name__ == "__main__":
    unittest.main()
