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
        """Tests DeleteDownloadsDialog UI components, default state, and properties."""
        dialog = DeleteDownloadsDialog(count=2)

        self.assertEqual(dialog.windowTitle(), "Delete downloads")
        self.assertIn("Are you sure you want to delete selected downloads?", dialog.msg_label.text())
        self.assertFalse(dialog.chk_delete_files.isChecked())
        self.assertFalse(dialog.delete_from_disk)

        # Check checkbox
        dialog.chk_delete_files.setChecked(True)
        self.assertTrue(dialog.delete_from_disk)

        # Buttons
        self.assertEqual(dialog.btn_delete.text(), "Delete")
        self.assertEqual(dialog.btn_cancel.text(), "Cancel")

        dialog.close()

    def test_02_task_manager_remove_task_memory_only(self):
        """Tests removing task from list (memory) without deleting file from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "sample.txt")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("test content")

            tm = TaskManager(
                default_download_dir=tmpdir,
                tasks_file=os.path.join(tmpdir, "tasks.json"),
                auto_load=False
            )
            task = DownloadTask(
                task_id="task_mem_1",
                url="https://example.com/sample.txt",
                destination_folder=tmpdir,
                filename="sample.txt",
                status=DownloadStatus.COMPLETED
            )
            tm.tasks[task.task_id] = task

            # Delete with delete_file=False
            result = tm.remove_task("task_mem_1", delete_file=False)
            self.assertTrue(result)
            self.assertNotIn("task_mem_1", tm.tasks)
            # File must remain on disk!
            self.assertTrue(os.path.exists(test_file))

    def test_03_task_manager_remove_task_permanent_disk_delete(self):
        """Tests permanent deletion from disk via TaskManager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "permanent.mp4")
            with open(test_file, "wb") as f:
                f.write(b"permanent video stream content")

            tm = TaskManager(
                default_download_dir=tmpdir,
                tasks_file=os.path.join(tmpdir, "tasks.json"),
                auto_load=False
            )
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

            # Delete with delete_file=True
            result = tm.remove_task("task_disk_1", delete_file=True)
            self.assertTrue(result)
            self.assertNotIn("task_disk_1", tm.tasks)
            # File must be completely removed from disk as well!
            self.assertFalse(os.path.exists(test_file))

    def test_04_main_window_toolbar_delete_button_and_batch_selection(self):
        """Tests Delete button in main window toolbar, checkbox selection, and batch deletion flow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = ServerBridge()
            temp_tasks_file = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(tasks_file=temp_tasks_file)
            win = MainWindow(task_manager=tm, bridge=bridge)

            # 1. Verify Delete button exists on toolbar
            self.assertIsNotNone(win.btn_delete)
            self.assertIn("Delete", win.btn_delete.text())

            # 2. Add tasks
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

            # 3. Checkbox selection simulation: check tasks 1 and 3
            item_0 = win.downloads_table.item(0, 0)
            item_2 = win.downloads_table.item(2, 0)
            item_0.setCheckState(Qt.CheckState.Checked)
            item_2.setCheckState(Qt.CheckState.Checked)

            selected_ids = win._get_selected_task_ids()
            self.assertIn("t1", selected_ids)
            self.assertIn("t3", selected_ids)
            self.assertNotIn("t2", selected_ids)

            # 4. Execute batch delete
            win._delete_tasks_batch(selected_ids, delete_files=False)

            # Only 1 row (t2) should remain in table
            self.assertEqual(win.downloads_table.rowCount(), 1)
            self.assertIn("t2", win.task_rows)
            self.assertNotIn("t1", win.task_rows)
            self.assertNotIn("t3", win.task_rows)
            self.assertEqual(win.row_tasks.get(0), "t2")

            win.close()

    def test_05_select_all_toolbar_button_and_toggle(self):
        """Tests Select All button in toolbar, toggle state changes, and header section click."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = ServerBridge()
            temp_tasks_file = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(tasks_file=temp_tasks_file)
            win = MainWindow(task_manager=tm, bridge=bridge)

            # 1. Verify Select All button exists on toolbar
            self.assertIsNotNone(win.btn_select_all)
            self.assertIn("Select All", win.btn_select_all.text())

            # 2. Add tasks
            t1 = DownloadTask(task_id="sa1", url="http://a.com/1.zip", destination_folder=".", filename="1.zip")
            t2 = DownloadTask(task_id="sa2", url="http://a.com/2.zip", destination_folder=".", filename="2.zip")
            t3 = DownloadTask(task_id="sa3", url="http://a.com/3.zip", destination_folder=".", filename="3.zip")
            tm.tasks["sa1"] = t1
            tm.tasks["sa2"] = t2
            tm.tasks["sa3"] = t3

            win._on_task_added(t1)
            win._on_task_added(t2)
            win._on_task_added(t3)

            self.assertEqual(win.downloads_table.rowCount(), 3)
            self.assertEqual(win.btn_select_all.text(), "☑ Select All")

            # 3. Click Select All button -> all should be checked
            win.btn_select_all.click()
            self.assertEqual(win.btn_select_all.text(), "☐ Deselect All")
            self.assertEqual(win.downloads_table.item(0, 0).checkState(), Qt.CheckState.Checked)
            self.assertEqual(win.downloads_table.item(1, 0).checkState(), Qt.CheckState.Checked)
            self.assertEqual(win.downloads_table.item(2, 0).checkState(), Qt.CheckState.Checked)

            selected_ids = win._get_selected_task_ids()
            self.assertEqual(set(selected_ids), {"sa1", "sa2", "sa3"})

            # 4. Click again -> all should be unchecked
            win.btn_select_all.click()
            self.assertEqual(win.btn_select_all.text(), "☑ Select All")
            self.assertEqual(win.downloads_table.item(0, 0).checkState(), Qt.CheckState.Unchecked)
            self.assertEqual(win.downloads_table.item(1, 0).checkState(), Qt.CheckState.Unchecked)
            self.assertEqual(win.downloads_table.item(2, 0).checkState(), Qt.CheckState.Unchecked)

            # 5. Column 0 header click toggles selection
            win._on_header_section_clicked(0)
            self.assertEqual(win.btn_select_all.text(), "☐ Deselect All")
            self.assertEqual(win.downloads_table.item(0, 0).checkState(), Qt.CheckState.Checked)

            # 6. Bulk delete all selected tasks
            win._delete_tasks_batch(win._get_selected_task_ids(), delete_files=False)
            self.assertEqual(win.downloads_table.rowCount(), 0)
            self.assertEqual(win.btn_select_all.text(), "☑ Select All")

            win.close()


if __name__ == "__main__":
    unittest.main()
