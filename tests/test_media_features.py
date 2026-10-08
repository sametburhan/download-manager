"""
Download Manager - YouTube & Streaming Media Features Test Suite (test_media_features.py)
"""

import unittest
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
    """Tests YouTube and media streaming download capabilities."""

    def test_ffmpeg_detection(self):
        """Verifies that FFmpeg executable is successfully detected."""
        ffmpeg = get_ffmpeg_path()
        if ffmpeg is not None:
            self.assertTrue(os.path.exists(ffmpeg), f"FFmpeg path must be an existing file: {ffmpeg}")

    def test_js_runtime_detection(self):
        """Checks Node.js or Deno runtime detection."""
        runtimes = get_js_runtimes()
        self.assertIsInstance(runtimes, dict)
        if shutil.which("node"):
            self.assertIn("node", runtimes)

    def test_ytdl_base_opts(self):
        """Tests that basic yt-dlp options contain correct parameters."""
        headers = {"Referer": "https://stream-site.com", "User-Agent": "Mozilla/5.0"}
        opts = get_ytdl_base_opts(headers=headers)

        self.assertTrue(opts.get("noplaylist"))
        for k, v in headers.items():
            self.assertEqual(opts.get("http_headers", {}).get(k), v)
        if get_ffmpeg_path():
            self.assertIn("ffmpeg_location", opts)

    def test_is_video_stream_url(self):
        """Tests detection of YouTube and video streams by is_video_stream_url."""
        self.assertTrue(is_video_stream_url("https://www.youtube.com/watch?v=aqz-KE-bpKQ"))
        self.assertTrue(is_video_stream_url("https://youtu.be/aqz-KE-bpKQ"))
        self.assertTrue(is_video_stream_url("https://youtube.com/shorts/abcdefgh123"))
        self.assertTrue(is_video_stream_url("https://cdn.example.com/hls/master.m3u8?token=abc"))
        self.assertTrue(is_video_stream_url("https://cdn.example.com/playlist.m3u8"))
        self.assertTrue(is_video_stream_url("https://vimeo.com/12345678"))

        # Standard file links should not be considered video streams
        self.assertFalse(is_video_stream_url("https://example.com/archive.zip"))
        self.assertFalse(is_video_stream_url("https://example.com/document.pdf"))

    def test_task_manager_headers_forwarding(self):
        """Tests that TaskManager.add_media_download forwards headers parameter to task."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tm = TaskManager(
                default_download_dir=tmpdir,
                tasks_file=os.path.join(tmpdir, "tasks.json"),
                auto_load=False
            )
            test_headers = {"Referer": "https://vidmoly.to/", "User-Agent": "TestBrowser/1.0"}

            task_id = tm.add_media_download(
                url="https://cdn.test/master.m3u8",
                title="Test Movie S01E01",
                destination_folder=tmpdir,
                headers=test_headers,
                auto_start=False
            )

            task = tm.get_task(task_id)
            self.assertIsNotNone(task)
            self.assertEqual(task.headers, test_headers)
            self.assertEqual(task.task_type, TaskType.MEDIA_VIDEO)
            self.assertEqual(task.filename, "Test Movie S01E01")
            # Category must be Video, not Other, even without extension
            self.assertEqual(task.category, "Video")
            self.assertEqual(task.category_icon, "🎬")

    def test_media_task_category_and_size_resolution(self):
        """Verifies that category, icon, and sizes of media tasks are correctly resolved."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            task = DownloadTask(
                task_id="test1234",
                url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
                destination_folder=tmpdir,
                filename="Do NOT mess with this channel",
                task_type=TaskType.MEDIA_VIDEO
            )

            # 1. Initially when size is unknown, should return English 'Unknown'
            self.assertEqual(task.formatted_total_size, "Unknown")
            self.assertEqual(task.category, "Video")
            self.assertEqual(task.category_icon, "🎬")

            # 2. Should automatically pick up file size when file exists on disk
            mp4_file = os.path.join(tmpdir, "Do NOT mess with this channel.mp4")
            with open(mp4_file, "wb") as f:
                f.write(b"X" * (5 * 1024 * 1024))  # 5 MB

            self.assertEqual(task.formatted_total_size, "5.00 MB")
            self.assertEqual(task.filename, "Do NOT mess with this channel.mp4")
            self.assertEqual(task.category, "Video")

            # 3. Audio/Music task test
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
        """Verifies MediaQualityDialog transition to IDM-style live progress view and its fields."""
        import sys
        from PyQt6.QtWidgets import QApplication
        from app.ui.media_dialog import MediaQualityDialog

        app = QApplication.instance() or QApplication(sys.argv)
        tmp_dir = tempfile.TemporaryDirectory()
        tm = TaskManager(
            default_download_dir=tmp_dir.name,
            tasks_file=os.path.join(tmp_dir.name, "tasks.json"),
            auto_load=False
        )

        dialog = MediaQualityDialog(
            url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            initial_title="Test Video Title",
            default_save_dir=tmp_dir.name,
            task_manager=tm,
            auto_start_analysis=False
        )
        dialog.show()

        # Mock add_media_download to avoid real network thread
        tm.add_media_download = lambda **kwargs: "mock_task_123"

        # 1. Initially should be on quality selection page at index 0
        self.assertEqual(dialog.stack.currentIndex(), 0)

        # 2. When download starts, should switch to page 1 (IDM Live Progress View)
        dialog.extracted_info = {"title": "Test Video Title"}
        dialog.format_combo.addItem("1080p FHD", "height_1080")
        dialog.format_combo.setCurrentIndex(0)
        dialog._on_start_download_clicked()

        self.assertEqual(dialog.stack.currentIndex(), 1)
        self.assertEqual(dialog.current_task_id, "mock_task_123")

        # 3. Verify presence of IDM fields
        self.assertIn("Connecting", dialog.status_val.text())
        self.assertEqual(dialog.prog_title_label.text(), "Test Video Title")
        self.assertTrue(dialog.progress_bar.isVisible())
        self.assertTrue(dialog.open_folder_btn.isVisible())
        self.assertTrue(dialog.play_video_btn.isVisible())
        self.assertTrue(dialog.pause_btn.isVisible())

        # 4. Simulate progress signal
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

        # 5. Simulate completion
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
        tmp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
