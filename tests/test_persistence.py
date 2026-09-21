"""
Download Manager - Görev Kalıcılığı ve Yeniden Yükleme Testi (test_persistence.py)

Bu test:
1. Görevlerin DownloadTask.to_dict ve from_dict ile serileştirildiğini doğrular.
2. TaskManager'a eklenen HTTP ve Medya görevlerinin diske (tasks.json) yazıldığını doğrular.
3. Uygulama kapandığında ve yeni bir TaskManager açıldığında görevlerin eksiksiz geri yüklendiğini doğrular.
4. Tamamlanmamış görevlerin yeniden açılışta güvenli şekilde PAUSED durumuna geçtiğini doğrular.
5. MainWindow açılışında kayıtlı görevlerin tabloya ve kategori sayaçlarına yansıdığını doğrular.
6. Görev silindiğinde tasks.json dosyasının da güncellendiğini doğrular.
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
        """DownloadTask to_dict ve from_dict işlevselliğini test eder."""
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

        # from_dict ile geri yükle: aktif DOWNLOADING durumu PAUSED olmalı
        restored = DownloadTask.from_dict(data)
        self.assertEqual(restored.task_id, "test_ser_1")
        self.assertEqual(restored.task_type, TaskType.MEDIA_VIDEO)
        self.assertEqual(restored.status, DownloadStatus.PAUSED)
        self.assertEqual(restored.downloaded_size, 25000000)
        self.assertEqual(len(restored.chunks), 2)
        self.assertTrue(restored.chunks[0].is_completed)

    def test_02_task_manager_save_and_reload(self):
        """TaskManager'ın tasks.json dosyasına yazıp yeni oturumda geri yüklemesini test eder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_file = os.path.join(tmpdir, "tasks.json")

            # 1. Oturum: İki görev ekle (biri tamamlanmış, biri duraklatılmış)
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

            # 2. Oturum: Uygulama kapatıldı ve yeniden açıldı (tm2)
            tm2 = TaskManager(default_download_dir=tmpdir, tasks_file=tasks_file, auto_load=True)
            self.assertEqual(len(tm2.tasks), 2)
            self.assertIn("t1", tm2.tasks)
            self.assertIn("t2", tm2.tasks)

            # t1 COMPLETED kalmalı
            self.assertEqual(tm2.tasks["t1"].status, DownloadStatus.COMPLETED)
            # t2 güvenli şekilde PAUSED olmalı
            self.assertEqual(tm2.tasks["t2"].status, DownloadStatus.PAUSED)
            self.assertEqual(tm2.tasks["t2"].downloaded_size, 2000)

    def test_03_main_window_loads_persisted_tasks_and_shows_categories(self):
        """MainWindow açıldığında persisted görevlerin tabloya ve kategori sayaçlarına yansıdığını test eder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_file = os.path.join(tmpdir, "tasks.json")

            # Görevleri dosyaya yaz
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

            # MainWindow başlat
            bridge = ServerBridge()
            tm = TaskManager(default_download_dir=tmpdir, tasks_file=tasks_file, auto_load=True)
            win = MainWindow(task_manager=tm, bridge=bridge)

            # Tabloda 2 görev olmalı ve empty_label gizlenmeli
            self.assertEqual(win.downloads_table.rowCount(), 2)
            self.assertEqual(len(win.cards), 2)
            self.assertTrue(win.empty_label.isHidden())

            # Kategori sayaçları doğru olmalı
            all_text = win.sidebar_items["ALL"][0].text(0)
            self.assertIn("(2)", all_text)

            video_text = win.sidebar_items["Video"][0].text(0)
            self.assertIn("(1)", video_text)

            image_text = win.sidebar_items["Image"][0].text(0)
            self.assertIn("(1)", image_text)

            # Silme işlemi tasks.json'ı da güncellemeli
            tm.remove_task("i1", delete_file=False)
            with open(tasks_file, "r", encoding="utf-8") as f:
                after_delete = json.load(f)
            self.assertEqual(len(after_delete), 1)
            self.assertEqual(after_delete[0]["task_id"], "v1")

            win.close()

        print("\n[OK] Tum gorev kaliciligi ve yeniden yukleme testleri basariyla gecti!")


if __name__ == "__main__":
    unittest.main()
