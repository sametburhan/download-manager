"""
Aşama 2 Otomatik Doğrulama Testi (İndirme Motoru, HTTP Range, Pause/Resume, Birleştirme)

Bu test dosyası:
1. Yerel bir Range-destekli HTTP test sunucusu ayağa kaldırır.
2. 4 parçalı (chunked) indirme motorunu çalıştırır ve parça birleştirmeyi doğrular.
3. Pause ve Resume (duraklatma ve devam ettirme) akışını test eder.
4. Dosya sanitization ve hash doğrulamasını test eder.
"""

import sys
import os
import time
import hashlib
import unittest
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication

from app.core.models import DownloadTask, DownloadStatus, ChunkInfo, TaskType
from app.utils.file_utils import sanitize_filename, merge_chunks, cleanup_temp_files, calculate_file_hash
from app.core.http_downloader import HttpChunkDownloader
from app.core.task_manager import TaskManager


# Test için 2 MB büyüklüğünde rastgele ikili veri üret
TEST_DATA = os.urandom(2 * 1024 * 1024)
TEST_HASH = hashlib.sha256(TEST_DATA).hexdigest()


class RangeTestHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP Range (206 Partial Content) başlıklarını destekleyen test sunucu işleyicisi."""

    def log_message(self, format, *args):
        pass  # Test loglarını kirletmemek için sessize al

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(TEST_DATA)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        range_header = self.headers.get("Range")
        data_len = len(TEST_DATA)

        if range_header and range_header.startswith("bytes="):
            # Range formatı: bytes=start-end
            range_val = range_header.replace("bytes=", "").strip()
            parts = range_val.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if parts[1] else data_len - 1

            if start >= data_len:
                self.send_response(416)  # Range Not Satisfiable
                self.end_headers()
                return

            end = min(end, data_len - 1)
            chunk = TEST_DATA[start:end + 1]

            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Range", f"bytes {start}-{end}/{data_len}")
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(data_len))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(TEST_DATA)


class TestDownloadEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.port = 8765
        cls.server = HTTPServer(("127.0.0.1", cls.port), RangeTestHTTPRequestHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

        cls.test_dir = os.path.join(os.path.dirname(__file__), "test_scratch")
        os.makedirs(cls.test_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        # Test klasörünü temizle
        import shutil
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_sanitize_filename(self):
        """Windows geçersiz karakterlerinin temizlendiğini test eder."""
        raw_name = 'video:part1/test*file?.mp4'
        clean = sanitize_filename(raw_name)
        self.assertEqual(clean, "video_part1_test_file_.mp4")

    def test_02_merge_chunks(self):
        """Parça dosyalarının sıralı ve kayıpsız birleştirildiğini test eder."""
        chunk1 = os.path.join(self.test_dir, "test.part0")
        chunk2 = os.path.join(self.test_dir, "test.part1")
        merged = os.path.join(self.test_dir, "test.merged")

        with open(chunk1, "wb") as f1:
            f1.write(b"HELLO_")
        with open(chunk2, "wb") as f2:
            f2.write(b"WORLD!")

        merge_chunks([chunk1, chunk2], merged)

        with open(merged, "rb") as mf:
            content = mf.read()
        self.assertEqual(content, b"HELLO_WORLD!")

        cleanup_temp_files([chunk1, chunk2], None)
        self.assertFalse(os.path.exists(chunk1))
        self.assertFalse(os.path.exists(chunk2))

    def test_03_http_range_chunked_download(self):
        """HTTP Range ile 4 parçalı indirmeyi ve SHA256 bütünlüğünü test eder."""
        target_filename = "downloaded_2mb.bin"
        task = DownloadTask(
            task_id="task_test_01",
            url=f"http://127.0.0.1:{self.port}/file.bin",
            destination_folder=self.test_dir,
            filename=target_filename
        )

        downloader = HttpChunkDownloader(task=task, num_chunks=4)
        finished_results = []
        progress_events = []

        downloader.finished.connect(lambda tid, path: finished_results.append((tid, path)))
        downloader.progress_updated.connect(lambda d: progress_events.append(d))

        downloader.start()

        # İndirmenin bitmesini bekle (en fazla 10 sn)
        start_time = time.time()
        while not finished_results and time.time() - start_time < 10:
            self.app.processEvents()
            time.sleep(0.05)

        downloader.wait(2000)

        # Doğrulamalar
        self.assertEqual(len(finished_results), 1)
        final_file = finished_results[0][1]
        self.assertTrue(os.path.exists(final_file))
        self.assertEqual(os.path.getsize(final_file), len(TEST_DATA))

        # Hash kontrolü (Veri eksiksiz mi indi?)
        downloaded_hash = calculate_file_hash(final_file)
        self.assertEqual(downloaded_hash, TEST_HASH)
        self.assertTrue(len(progress_events) > 0)

    def test_04_pause_and_resume_download(self):
        """İndirmeyi duraklatıp (pause) ardından devam ettirmeyi (resume) test eder."""
        target_filename = "resumable_2mb.bin"
        task = DownloadTask(
            task_id="task_test_02",
            url=f"http://127.0.0.1:{self.port}/file.bin",
            destination_folder=self.test_dir,
            filename=target_filename
        )

        # 1. İndirmeyi başlat ve veri akışı başlayınca duraklat
        downloader = HttpChunkDownloader(task=task, num_chunks=4)
        downloader.start()

        for _ in range(50):
            self.app.processEvents()
            if task.status == DownloadStatus.DOWNLOADING:
                break
            time.sleep(0.02)

        time.sleep(0.02)
        downloader.pause()
        downloader.wait(2000)

        self.assertEqual(task.status, DownloadStatus.PAUSED)
        self.assertTrue(os.path.exists(task.meta_file_path))

        # 2. Kaldığı yerden devam ettir (Resume)
        resume_finished = []
        resume_downloader = HttpChunkDownloader(task=task, num_chunks=4)
        resume_downloader.finished.connect(lambda tid, path: resume_finished.append((tid, path)))
        resume_downloader.start()

        start_time = time.time()
        while not resume_finished and time.time() - start_time < 10:
            self.app.processEvents()
            time.sleep(0.05)

        resume_downloader.wait(2000)

        self.assertEqual(len(resume_finished), 1)
        final_file = resume_finished[0][1]
        self.assertTrue(os.path.exists(final_file))
        self.assertEqual(calculate_file_hash(final_file), TEST_HASH)

        print("\n[OK] All Stage 2 download engine tests passed successfully!")


if __name__ == "__main__":
    unittest.main()
