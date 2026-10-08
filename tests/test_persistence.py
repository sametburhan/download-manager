"""
Download Manager - Task Persistence and Reload Test (test_persistence.py)

This test suite:
1. Verifies tasks are serialized with DownloadTask.to_dict and from_dict.
2. Verifies HTTP and Media tasks added to TaskManager are written to disk (tasks.json).
3. Verifies tasks are fully restored when app closes and a new TaskManager opens.
4. Verifies unfinished tasks safely transition to PAUSED upon reload.
5. Verifies recorded tasks reflect on table and category counters when MainWindow opens.
6. Verifies tasks.json is updated when a task is deleted.
"""

import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication

from app.core.models import DownloadTask, DownloadStatus, TaskType, ChunkInfo
from app.core.task_manager import TaskManager
from app.server.bridge import ServerBridge
from app.ui.main_window import MainWindow


class TestTaskPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_01_model_serialization(self):
        """Tests DownloadTask to_dict and from_dict functionality."""
        task = DownloadTask(
            task_id="test_ser_1",
            url="https://example.com/video.mp4",
            destination_folder="C:/Downloads",
            filename="video.mp4",
            task_type=TaskType.MEDIA_VIDEO,
            status=DownloadStatus.DOWNLOADING,
            total_size=50000000,
            downloaded_size=25000000,
            is_resumable=True,
            chunks=[
                ChunkInfo(chunk_id=0, start_byte=0, end_byte=24999999, downloaded_bytes=25000000, is_completed=True),
                ChunkInfo(chunk_id=1, start_byte=25000000, end_byte=49999999, downloaded_bytes=0, is_completed=False)
            ]
        )

        data = task.to_dict()
        self.assertEqual(data["task_id"], "test_ser_1")
        self.assertEqual(data["task_type"], "MEDIA_VIDEO")
        self.assertEqual(len(data["chunks"]), 2)

        # Restore via from_dict: active DOWNLOADING status must become PAUSED
        restored = DownloadTask.from_dict(data)
        self.assertEqual(restored.task_id, "test_ser_1")
        self.assertEqual(restored.task_type, TaskType.MEDIA_VIDEO)
        self.assertEqual(restored.status, DownloadStatus.PAUSED)
        self.assertEqual(restored.downloaded_size, 25000000)
        self.assertEqual(len(restored.chunks), 2)
        self.assertTrue(restored.chunks[0].is_completed)

    def test_02_task_manager_save_and_reload(self):
        """Tests TaskManager writing to tasks.json and restoring in a new session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_file = os.path.join(tmpdir, "tasks.json")

            # Session 1: Add two tasks (one completed, one paused)
            tm1 = TaskManager(default_download_dir=tmpdir, tasks_file=tasks_file, auto_load=False)

            task1 = DownloadTask(
                task_id="t1",
                url="https://example.com/file1.zip",
                destination_folder=tmpdir,
                filename="file1.zip",
                task_type=TaskType.HTTP_FILE,
                status=DownloadStatus.COMPLETED,
                total_size=1000,
                downloaded_size=1000
            )
            task2 = DownloadTask(
                task_id="t2",
                url="https://example.com/video2.mp4",
                destination_folder=tmpdir,
                filename="video2.mp4",
                task_type=TaskType.MEDIA_VIDEO,
                status=DownloadStatus.DOWNLOADING,
                total_size=5000,
                downloaded_size=2000
            )

            tm1.tasks["t1"] = task1
            tm1.tasks["t2"] = task2
            tm1.save_tasks(force=True)

            self.assertTrue(os.path.exists(tasks_file))

            with open(tasks_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(len(saved), 2)

            # Session 2: Application closed and reopened (tm2)
            tm2 = TaskManager(default_download_dir=tmpdir, tasks_file=tasks_file, auto_load=True)
            self.assertEqual(len(tm2.tasks), 2)
            self.assertIn("t1", tm2.tasks)
            self.assertIn("t2", tm2.tasks)

            # t1 must remain COMPLETED
            self.assertEqual(tm2.tasks["t1"].status, DownloadStatus.COMPLETED)
            # t2 must safely become PAUSED
            self.assertEqual(tm2.tasks["t2"].status, DownloadStatus.PAUSED)
            self.assertEqual(tm2.tasks["t2"].downloaded_size, 2000)

    def test_03_main_window_loads_persisted_tasks_and_shows_categories(self):
        """Tests that persisted tasks reflect on table and category counters when MainWindow opens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_file = os.path.join(tmpdir, "tasks.json")

            # Write tasks to file
            tm_init = TaskManager(default_download_dir=tmpdir, tasks_file=tasks_file, auto_load=False)
            task_video = DownloadTask(
                task_id="v1",
                url="https://example.com/movie.mp4",
                destination_folder=tmpdir,
                filename="movie.mp4",
                task_type=TaskType.MEDIA_VIDEO,
                status=DownloadStatus.COMPLETED,
                total_size=1024 * 1024
            )
            task_img = DownloadTask(
                task_id="i1",
                url="https://example.com/photo.png",
                destination_folder=tmpdir,
                filename="photo.png",
                task_type=TaskType.HTTP_FILE,
                status=DownloadStatus.PAUSED,
                total_size=512 * 1024
            )
            tm_init.tasks["v1"] = task_video
            tm_init.tasks["i1"] = task_img
            tm_init.save_tasks(force=True)

            # Launch MainWindow
            bridge = ServerBridge()
            tm = TaskManager(default_download_dir=tmpdir, tasks_file=tasks_file, auto_load=True)
            win = MainWindow(task_manager=tm, bridge=bridge)

            # Table must have 2 tasks and empty_label must be hidden
            self.assertEqual(win.downloads_table.rowCount(), 2)
            self.assertEqual(len(win.cards), 2)
            self.assertTrue(win.empty_label.isHidden())

            # Category counters must be correct
            all_text = win.sidebar_items["ALL"][0].text(0)
            self.assertIn("(2)", all_text)

            video_text = win.sidebar_items["Video"][0].text(0)
            self.assertIn("(1)", video_text)

            image_text = win.sidebar_items["Image"][0].text(0)
            self.assertIn("(1)", image_text)

            # Deletion must also update tasks.json
            tm.remove_task("i1", delete_file=False)
            with open(tasks_file, "r", encoding="utf-8") as f:
                after_delete = json.load(f)
            self.assertEqual(len(after_delete), 1)
            self.assertEqual(after_delete[0]["task_id"], "v1")

            win.close()

    def test_04_deleted_file_from_disk_preserves_task_in_app_and_tasks_json(self):
        """Verifies that even if file is deleted from disk, the application preserves the task, keeps it in tasks.json,
        and only updates the list when deleted from the UI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_file = os.path.join(tmpdir, "tasks.json")
            download_dir = os.path.join(tmpdir, "Downloads")
            os.makedirs(download_dir, exist_ok=True)

            # 1. Simulate completed download and create file on disk
            real_file_path = os.path.join(download_dir, "my_video.mp4")
            with open(real_file_path, "wb") as f:
                f.write(b"0" * (2 * 1024 * 1024))  # 2 MB file

            tm1 = TaskManager(default_download_dir=download_dir, tasks_file=tasks_file, auto_load=False)
            completed_task = DownloadTask(
                task_id="persist_test_1",
                url="https://example.com/my_video.mp4",
                destination_folder=download_dir,
                filename="my_video.mp4",
                task_type=TaskType.MEDIA_VIDEO,
                status=DownloadStatus.COMPLETED,
                total_size=2 * 1024 * 1024,
                downloaded_size=2 * 1024 * 1024,
                completed_at=1789757000.0
            )
            tm1.tasks["persist_test_1"] = completed_task
            tm1.save_tasks(force=True)

            # 2. User deletes file from Downloads folder
            self.assertTrue(os.path.exists(real_file_path))
            os.remove(real_file_path)
            self.assertFalse(os.path.exists(real_file_path))

            # 3. Application opens (new session / TaskManager and MainWindow)
            tm2 = TaskManager(default_download_dir=download_dir, tasks_file=tasks_file, auto_load=True)
            self.assertIn("persist_test_1", tm2.tasks)
            loaded_task = tm2.tasks["persist_test_1"]

            # Task must remain COMPLETED; size and name must be preserved
            self.assertEqual(loaded_task.status, DownloadStatus.COMPLETED)
            self.assertEqual(loaded_task.filename, "my_video.mp4")
            self.assertEqual(loaded_task.formatted_total_size, "2.00 MB")

            # 4. Task must appear completely in UI table
            bridge = ServerBridge()
            win = MainWindow(task_manager=tm2, bridge=bridge)
            self.assertEqual(win.downloads_table.rowCount(), 1)
            self.assertEqual(len(win.cards), 1)

            # Category counters must accurately count Completed and Video
            all_text = win.sidebar_items["ALL"][0].text(0)
            self.assertIn("(1)", all_text)
            completed_text = win.sidebar_items["COMPLETED"][0].text(0)
            self.assertIn("(1)", completed_text)

            # 5. Record must still be preserved in tasks.json
            with open(tasks_file, "r", encoding="utf-8") as f:
                json_data = json.load(f)
            self.assertEqual(len(json_data), 1)
            self.assertEqual(json_data[0]["task_id"], "persist_test_1")
            self.assertEqual(json_data[0]["status"], "COMPLETED")
            self.assertEqual(json_data[0]["total_size"], 2 * 1024 * 1024)

            # 6. List must update ONLY when user deletes from UI
            win._delete_tasks_batch(["persist_test_1"], delete_files=False)
            self.assertEqual(win.downloads_table.rowCount(), 0)
            self.assertEqual(len(tm2.tasks), 0)

            # tasks.json must be updated and empty
            with open(tasks_file, "r", encoding="utf-8") as f:
                updated_json = json.load(f)
            self.assertEqual(len(updated_json), 0)

            win.close()

        print("\n[OK] All task persistence and reload tests passed successfully!")


if __name__ == "__main__":
    unittest.main()
