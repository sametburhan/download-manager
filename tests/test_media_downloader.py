"""
Aşama 2 Medya İndirme Motoru (yt-dlp) Doğrulama Testi
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
import yt_dlp

from app.core.models import DownloadTask, TaskType
from app.core.media_downloader import MediaInfoExtractor, MediaDownloader


class TestMediaDownloader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_01_yt_dlp_import_and_version(self):
        """yt-dlp kütüphanesinin başarıyla yüklendiğini ve sürüm verebildiğini test eder."""
        import yt_dlp.version
        self.assertIsNotNone(yt_dlp.version.__version__)

    def test_02_media_info_extractor_signals(self):
        """MediaInfoExtractor sınıfının QThread sinyallerinin doğru bağlandığını test eder."""
        extractor = MediaInfoExtractor("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertTrue(hasattr(extractor, "metadata_ready"))
        self.assertTrue(hasattr(extractor, "error_occurred"))

    def test_03_media_downloader_signals(self):
        """MediaDownloader sınıfının QThread sinyallerinin ve iptal mantığının hazır olduğunu test eder."""
        task = DownloadTask(
            task_id="media_test_01",
            url="https://example.com/video.mp4",
            destination_folder="C:/temp",
            filename="video.mp4",
            task_type=TaskType.MEDIA_VIDEO
        )
        downloader = MediaDownloader(task=task)
        self.assertTrue(hasattr(downloader, "progress_updated"))
        self.assertTrue(hasattr(downloader, "status_changed"))
        self.assertTrue(hasattr(downloader, "finished"))
        self.assertTrue(hasattr(downloader, "error_occurred"))
        downloader.cancel()
        self.assertTrue(downloader._is_cancelled)


if __name__ == "__main__":
    unittest.main()
