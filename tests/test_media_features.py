"""
Download Manager - YouTube & Streaming Media Features Test Suite (test_media_features.py)
"""

import unittest
import os
import shutil

from app.core.media_downloader import (
    get_ffmpeg_path,
    get_js_runtimes,
    get_ytdl_base_opts,
    MediaInfoExtractor,
    MediaDownloader
)
from app.core.models import DownloadTask, DownloadStatus, TaskType
from app.core.task_manager import TaskManager
from app.ui.compact_download_window import is_video_stream_url


class TestMediaFeatures(unittest.TestCase):
    """YouTube ve Medya akışı indirme yeteneklerini test eder."""

    def test_ffmpeg_detection(self):
        """FFmpeg çalıştırılabilir dosyasının başarıyla tespit edildiğini doğrular."""
        ffmpeg = get_ffmpeg_path()
        self.assertIsNotNone(ffmpeg, "FFmpeg çalıştırılabilir dosyası bulunmalıdır.")
        self.assertTrue(os.path.exists(ffmpeg), f"FFmpeg yolu mevcut bir dosya olmalıdır: {ffmpeg}")

    def test_js_runtime_detection(self):
        """Node.js veya Deno runtime tespitini kontrol eder."""
        runtimes = get_js_runtimes()
        self.assertIsInstance(runtimes, dict)
        if shutil.which("node"):
            self.assertIn("node", runtimes)

    def test_ytdl_base_opts(self):
        """Temel yt-dlp seçeneklerinin doğru parametreleri içerdiğini test eder."""
        headers = {"Referer": "https://stream-site.com", "User-Agent": "Mozilla/5.0"}
        opts = get_ytdl_base_opts(headers=headers)

        self.assertTrue(opts.get("noplaylist"))
        for k, v in headers.items():
            self.assertEqual(opts.get("http_headers", {}).get(k), v)
        self.assertIn("ffmpeg_location", opts)

    def test_is_video_stream_url(self):
        """is_video_stream_url fonksiyonunun YouTube ve video akışlarını tespitini test eder."""
        self.assertTrue(is_video_stream_url("https://www.youtube.com/watch?v=aqz-KE-bpKQ"))
        self.assertTrue(is_video_stream_url("https://youtu.be/aqz-KE-bpKQ"))
        self.assertTrue(is_video_stream_url("https://youtube.com/shorts/abcdefgh123"))
        self.assertTrue(is_video_stream_url("https://cdn.example.com/hls/master.m3u8?token=abc"))
        self.assertTrue(is_video_stream_url("https://cdn.example.com/playlist.m3u8"))
        self.assertTrue(is_video_stream_url("https://vimeo.com/12345678"))

        # Standart dosya linkleri video akışı sayılmamalı
        self.assertFalse(is_video_stream_url("https://example.com/archive.zip"))
        self.assertFalse(is_video_stream_url("https://example.com/document.pdf"))

    def test_task_manager_headers_forwarding(self):
        """TaskManager.add_media_download metodunun headers parametresini göreve aktardığını test eder."""
        tm = TaskManager(default_download_dir="test_downloads")
        test_headers = {"Referer": "https://vidmoly.to/", "User-Agent": "TestBrowser/1.0"}

        task_id = tm.add_media_download(
            url="https://cdn.test/master.m3u8",
            title="Test Movie S01E01",
            destination_folder="test_downloads",
            headers=test_headers,
            auto_start=False
        )

        task = tm.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task.headers, test_headers)
        self.assertEqual(task.task_type, TaskType.MEDIA_VIDEO)
        self.assertEqual(task.filename, "Test Movie S01E01")
        # Kategori uzantı olmasa dahi Video olmalı, Other olmamalı
        self.assertEqual(task.category, "Video")
        self.assertEqual(task.category_icon, "🎬")

    def test_media_task_category_and_size_resolution(self):
        """Medya görevlerinin kategori, ikon ve boyutlarının doğru çözümlendiğini doğrular."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            task = DownloadTask(
                task_id="test1234",
                url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
                destination_folder=tmpdir,
                filename="Do NOT mess with this channel",
                task_type=TaskType.MEDIA_VIDEO
            )

            # 1. Başlangıçta boyut bilinmediğinde Türkçe 'Bilinmiyor' değil İngilizce 'Unknown' dönmeli
            self.assertEqual(task.formatted_total_size, "Unknown")
            self.assertEqual(task.category, "Video")
            self.assertEqual(task.category_icon, "🎬")

            # 2. Disk üzerinde dosya oluştuğunda otomatik disk boyutunu almalı
            mp4_file = os.path.join(tmpdir, "Do NOT mess with this channel.mp4")
            with open(mp4_file, "wb") as f:
                f.write(b"X" * (5 * 1024 * 1024))  # 5 MB

            self.assertEqual(task.formatted_total_size, "5.00 MB")
            self.assertEqual(task.filename, "Do NOT mess with this channel.mp4")
            self.assertEqual(task.category, "Video")

            # 3. Ses/Müzik görevi testi
            audio_task = DownloadTask(
                task_id="test5678",
                url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
                destination_folder=tmpdir,
                filename="My Favorite Song",
                task_type=TaskType.MEDIA_AUDIO
            )
            self.assertEqual(audio_task.category, "Music")
            self.assertEqual(audio_task.category_icon, "🎵")
            self.assertEqual(audio_task.formatted_total_size, "Unknown")

    def test_media_dialog_idm_progress_view(self):
        """MediaQualityDialog'un IDM tarzı canlı ilerleme görünümüne geçişini ve alanlarını doğrular."""
        import sys
        from PyQt6.QtWidgets import QApplication
        from app.ui.media_dialog import MediaQualityDialog

        app = QApplication.instance() or QApplication(sys.argv)
        tm = TaskManager(default_download_dir="test_downloads")

        dialog = MediaQualityDialog(
            url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            initial_title="Test Video Title",
            default_save_dir="test_downloads",
            task_manager=tm,
            auto_start_analysis=False
        )
        dialog.show()

        # Mock add_media_download to avoid real network thread
        tm.add_media_download = lambda **kwargs: "mock_task_123"

        # 1. Başlangıçta 0. indeksteki kalite seçim sayfasında olmalı
        self.assertEqual(dialog.stack.currentIndex(), 0)

        # 2. İndirme başlatıldığında 1. sayfaya (IDM Canlı İlerleme Görünümü) geçmeli
        dialog.extracted_info = {"title": "Test Video Title"}
        dialog.format_combo.addItem("1080p FHD", "height_1080")
        dialog.format_combo.setCurrentIndex(0)
        dialog._on_start_download_clicked()

        self.assertEqual(dialog.stack.currentIndex(), 1)
        self.assertEqual(dialog.current_task_id, "mock_task_123")

        # 3. IDM alanlarının varlığını doğrula
        self.assertIn("Connecting", dialog.status_val.text())
        self.assertEqual(dialog.prog_title_label.text(), "Test Video Title")
        self.assertTrue(dialog.progress_bar.isVisible())
        self.assertTrue(dialog.open_folder_btn.isVisible())
        self.assertTrue(dialog.play_video_btn.isVisible())
        self.assertTrue(dialog.pause_btn.isVisible())

        # 4. İlerleme sinyali simülasyonu
        dialog._on_progress_updated({
            "task_id": dialog.current_task_id,
            "percent": 45.0,
            "downloaded_bytes": 45 * 1024 * 1024,
            "total_bytes": 100 * 1024 * 1024,
            "speed_str": "5.50 MB/s",
            "eta_str": "10s"
        })
        self.assertEqual(dialog.progress_bar.value(), 45)
        self.assertIn("45.0%", dialog.downloaded_val.text())
        self.assertEqual(dialog.speed_val.text(), "5.50 MB/s")

        # 5. Tamamlanma simülasyonu
        dialog._on_finished(dialog.current_task_id, "")
        self.assertEqual(dialog.progress_bar.value(), 100)
        self.assertIn("Completed", dialog.status_val.text())
        self.assertTrue(dialog.play_video_btn.isEnabled())

        if hasattr(dialog, "extractor") and dialog.extractor and dialog.extractor.isRunning():
            dialog.extractor.terminate()
            dialog.extractor.wait(300)

        dialog.close()
        dialog.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
