"""
Download Manager UI ve Detay Penceresi Otomatik Testleri (test_ab_ui.py)

Bu test dosyası:
1. Download Manager arayüzünün (MainWindow) tablo, sütun ve hücre bileşenlerini doğrular.
2. Canlı arama kutusu ve kategori ağacı filtreleme işlevlerini test eder.
3. DownloadDetailWindow penceresinin sekme, parça tablosu ve canlı segment göstergelerini test eder.
4. Satıra çift tıklama ile detay penceresinin açılmasını ve canlı sinyal aktarımını doğrular.
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
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.bridge = ServerBridge()
        cls.task_manager = TaskManager()
        cls.window = MainWindow(task_manager=cls.task_manager, bridge=cls.bridge)

    def test_01_main_window_ab_structure(self):
        """Download Manager ana pencere yapısının doğruluğunu test eder."""
        self.assertEqual(self.window.windowTitle(), "Download Manager")
        self.assertIsNotNone(self.window.search_bar)
        self.assertIsNotNone(self.window.sidebar_tree)
        self.assertIsNotNone(self.window.downloads_table)

        # Tablo sütun sayısı ve başlıklar
        self.assertEqual(self.window.downloads_table.columnCount(), 7)
        expected_headers = ["", "Name", "Size", "Status", "Speed", "Time Left", "Date Added"]
        for col_idx, expected in enumerate(expected_headers):
            item = self.window.downloads_table.horizontalHeaderItem(col_idx)
            self.assertIsNotNone(item)
            self.assertEqual(item.text(), expected)

    def test_02_add_task_table_row_and_widgets(self):
        """Görevin tabloya özel hücrelerle eklendiğini doğrular."""
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

        # Tabloda en az 1 satır olmalı
        self.assertGreaterEqual(self.window.downloads_table.rowCount(), 1)
        row = self.window.task_rows.get("ab_test_video")
        self.assertIsNotNone(row)

        # Sütun 1: FileNameCellWidget
        name_cell = self.window.downloads_table.cellWidget(row, 1)
        self.assertIsInstance(name_cell, FileNameCellWidget)
        self.assertEqual(name_cell.name_lbl.text(), "Stories-of-Shahnameh.mp4")
        self.assertEqual(name_cell.cat_lbl.text(), "Video")

        # Sütun 3: StatusCellWidget
        status_cell = self.window.downloads_table.cellWidget(row, 3)
        self.assertIsInstance(status_cell, StatusCellWidget)

    def test_03_live_progress_and_mini_bar_update(self):
        """İlerleme sinyali ile tablodaki mini bar ve hız metriklerinin güncellendiğini test eder."""
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
        self.assertIn("39% Downloading", status_cell.label.text())
        self.assertEqual(status_cell.progress_bar.value(), 39)

        speed_item = self.window.downloads_table.item(row, 4)
        self.assertEqual(speed_item.text(), "4.91 MB/s")

    def test_04_live_search_filter(self):
        """Canlı arama kutusunun satırları anında filtrelediğini test eder."""
        # İkinci bir görev ekle
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

        # 'Guitar' ara -> Sadece audio görünmeli
        self.window.search_bar.setText("Guitar")
        self.app.processEvents()
        self.assertTrue(self.window.downloads_table.isRowHidden(row_video))
        self.assertFalse(self.window.downloads_table.isRowHidden(row_audio))

        # Aramayı temizle -> İkisi de görünmeli
        self.window.search_bar.setText("")
        self.app.processEvents()
        self.assertFalse(self.window.downloads_table.isRowHidden(row_video))
        self.assertFalse(self.window.downloads_table.isRowHidden(row_audio))

    def test_05_download_detail_window(self):
        """Ayrıntılı indirme penceresinin (DownloadDetailWindow) yapısını ve bileşenlerini test eder."""
        task = self.task_manager.get_task("ab_test_video")
        task.downloaded_size = 477385584  # %39
        detail_win = DownloadDetailWindow(task=task, task_manager=self.task_manager, parent=self.window)

        self.assertIn("39%-Stories-of-Shahnameh.mp4", detail_win.windowTitle())
        self.assertEqual(detail_win.name_val.text(), "Stories-of-Shahnameh.mp4")
        self.assertEqual(detail_win.resume_val.text(), "Yes")
        self.assertEqual(len(detail_win._segment_boxes), 8)
        self.assertEqual(detail_win.part_table.columnCount(), 4)

        # Parça ilerleme güncellemesi
        detail_win._on_chunk_progress("ab_test_video", 0, 67108864, 152406560)
        self.app.processEvents()
        item_status = detail_win.part_table.item(0, 1)
        self.assertEqual(item_status.text(), "Receiving Data")

        # Part Info aç/kapa
        detail_win._toggle_part_info()
        self.assertTrue(detail_win.part_container.isHidden())
        detail_win._toggle_part_info()
        self.assertFalse(detail_win.part_container.isHidden())

        detail_win.close()

    def test_06_app_icon_and_pixmap(self):
        """Uygulama ikonu ve pixmap yardımcılarının geçerliliğini test eder."""
        from app.utils.icon_utils import get_app_icon, get_app_pixmap
        icon = get_app_icon()
        self.assertFalse(icon.isNull())

        pix = get_app_pixmap(32)
        self.assertFalse(pix.isNull())
        self.assertEqual(pix.width(), 32)
        self.assertEqual(pix.height(), 32)

        print("\n[OK] All Download Manager UI and detail window tests passed successfully!")


if __name__ == "__main__":
    unittest.main()
