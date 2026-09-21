"""
Download Manager - Delete Downloads & Confirmation Test Suite (test_delete_features.py)
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from app.core.models import DownloadTask, DownloadStatus, TaskType
from app.core.task_manager import TaskManager
from app.server.bridge import ServerBridge
from app.ui.main_window import MainWindow
from app.ui.delete_dialog import DeleteDownloadsDialog


class TestDeleteFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_01_delete_dialog_components_and_default_state(self):
        """DeleteDownloadsDialog arayüz bileşenlerini, varsayılan durumunu ve özelliklerini test eder."""
        dialog = DeleteDownloadsDialog(count=2)

        self.assertEqual(dialog.windowTitle(), "Delete downloads")
        self.assertIn("Are you sure you want to delete selected downloads?", dialog.msg_label.text())
        self.assertFalse(dialog.chk_delete_files.isChecked())
        self.assertFalse(dialog.delete_from_disk)

        # Kutucuğu işaretle
        dialog.chk_delete_files.setChecked(True)
        self.assertTrue(dialog.delete_from_disk)

        # Butonlar
        self.assertEqual(dialog.btn_delete.text(), "Delete")
        self.assertEqual(dialog.btn_cancel.text(), "Cancel")

        dialog.close()

    def test_02_task_manager_remove_task_memory_only(self):
        """TaskManager'dan dosya silinmeden yalnızca listeden (bellekten) silmeyi test eder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "sample.txt")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("test content")

            tm = TaskManager(default_download_dir=tmpdir)
            task = DownloadTask(
                task_id="task_mem_1",
                url="https://example.com/sample.txt",
                destination_folder=tmpdir,
                filename="sample.txt",
                status=DownloadStatus.COMPLETED
            )
            tm.tasks[task.task_id] = task

            # delete_file=False ile sil
            result = tm.remove_task("task_mem_1", delete_file=False)
            self.assertTrue(result)
            self.assertNotIn("task_mem_1", tm.tasks)
            # Dosya diskte kalmalı!
            self.assertTrue(os.path.exists(test_file))

    def test_03_task_manager_remove_task_permanent_disk_delete(self):
        """TaskManager'dan kalıcı (diskten) silmeyi test eder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "permanent.mp4")
            with open(test_file, "wb") as f:
                f.write(b"permanent video stream content")

            tm = TaskManager(default_download_dir=tmpdir)
            task = DownloadTask(
                task_id="task_disk_1",
                url="https://example.com/permanent.mp4",
                destination_folder=tmpdir,
                filename="permanent.mp4",
                task_type=TaskType.MEDIA_VIDEO,
                status=DownloadStatus.COMPLETED
            )
            tm.tasks[task.task_id] = task

            self.assertTrue(os.path.exists(test_file))

            # delete_file=True ile sil
            result = tm.remove_task("task_disk_1", delete_file=True)
            self.assertTrue(result)
            self.assertNotIn("task_disk_1", tm.tasks)
            # Dosya diskten de tamamen silinmiş olmalı!
            self.assertFalse(os.path.exists(test_file))

    def test_04_main_window_toolbar_delete_button_and_batch_selection(self):
        """Ana penceredeki Delete butonu, onay kutusu seçimi ve toplu silme akışını test eder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = ServerBridge()
            temp_tasks_file = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(tasks_file=temp_tasks_file)
            win = MainWindow(task_manager=tm, bridge=bridge)

            # 1. Araç çubuğunda Delete butonu var mı?
            self.assertIsNotNone(win.btn_delete)
            self.assertIn("Delete", win.btn_delete.text())

            # 2. Görevleri ekle
            task1 = DownloadTask(task_id="t1", url="http://a.com/1.zip", destination_folder=".", filename="1.zip")
            task2 = DownloadTask(task_id="t2", url="http://a.com/2.zip", destination_folder=".", filename="2.zip")
            task3 = DownloadTask(task_id="t3", url="http://a.com/3.zip", destination_folder=".", filename="3.zip")

            tm.tasks["t1"] = task1
            tm.tasks["t2"] = task2
            tm.tasks["t3"] = task3

            win._on_task_added(task1)
            win._on_task_added(task2)
            win._on_task_added(task3)

            self.assertEqual(win.downloads_table.rowCount(), 3)

            # 3. Checkbox işaretleme simülasyonu: 1. ve 3. görevleri işaretle
            item_0 = win.downloads_table.item(0, 0)
            item_2 = win.downloads_table.item(2, 0)
            item_0.setCheckState(Qt.CheckState.Checked)
            item_2.setCheckState(Qt.CheckState.Checked)

            selected_ids = win._get_selected_task_ids()
            self.assertIn("t1", selected_ids)
            self.assertIn("t3", selected_ids)
        self.assertNotIn("t2", selected_ids)

        # 4. Toplu silme (batch delete) çalıştır
        win._delete_tasks_batch(selected_ids, delete_files=False)

        # Tabloda yalnızca 1 satır (t2) kalmalı
        self.assertEqual(win.downloads_table.rowCount(), 1)
        self.assertIn("t2", win.task_rows)
        self.assertNotIn("t1", win.task_rows)
        self.assertNotIn("t3", win.task_rows)
        self.assertEqual(win.row_tasks.get(0), "t2")

        win.close()


if __name__ == "__main__":
    unittest.main()
