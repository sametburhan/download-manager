"""
Stage 2 Automated Verification Test (Download Engine, HTTP Range, Pause/Resume, Merging)

This test suite:
1. Spins up a local Range-supported HTTP test server.
2. Runs 4-chunk download engine and verifies chunk merging.
3. Tests Pause and Resume download flows.
4. Verifies filename sanitization and hash integrity.
"""

import sys
import os
import time
import hashlib
import unittest
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication

from app.core.models import DownloadTask, DownloadStatus, ChunkInfo, TaskType
from app.utils.file_utils import sanitize_filename, merge_chunks, cleanup_temp_files, calculate_file_hash
from app.core.http_downloader import HttpChunkDownloader
from app.core.task_manager import TaskManager


# Generate 2 MB random binary test data
TEST_DATA = os.urandom(2 * 1024 * 1024)
TEST_HASH = hashlib.sha256(TEST_DATA).hexdigest()


class RangeTestHTTPRequestHandler(BaseHTTPRequestHandler):
    """Test server handler supporting HTTP Range (206 Partial Content) headers."""

    def log_message(self, format, *args):
        pass  # Silence logging to keep test output clean

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(TEST_DATA)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self):
        range_header = self.headers.get("Range")
        data_len = len(TEST_DATA)
        is_slow = "/slow" in self.path

        if range_header and range_header.startswith("bytes="):
            # Range format: bytes=start-end
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
            self.send_header("Connection", "close")
            self.end_headers()

            if is_slow:
                block_size = 16 * 1024
                for i in range(0, len(chunk), block_size):
                    try:
                        self.wfile.write(chunk[i:i + block_size])
                        self.wfile.flush()
                        time.sleep(0.01)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        break
            else:
                self.wfile.write(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(data_len))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Connection", "close")
            self.end_headers()
            if is_slow:
                block_size = 16 * 1024
                for i in range(0, data_len, block_size):
                    try:
                        self.wfile.write(TEST_DATA[i:i + block_size])
                        self.wfile.flush()
                        time.sleep(0.01)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        break
            else:
                self.wfile.write(TEST_DATA)


class TestDownloadEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.port = 8765
        cls.server = ThreadingHTTPServer(("127.0.0.1", cls.port), RangeTestHTTPRequestHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

        cls.test_dir = os.path.join(os.path.dirname(__file__), "test_scratch")
        os.makedirs(cls.test_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        # Clean up test directory
        import shutil
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_sanitize_filename(self):
        """Tests sanitization of Windows invalid characters."""
        raw_name = 'video:part1/test*file?.mp4'
        clean = sanitize_filename(raw_name)
        self.assertEqual(clean, "video_part1_test_file_.mp4")

    def test_02_merge_chunks(self):
        """Tests sequential, lossless merging of chunk files."""
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
        """Tests 4-chunk HTTP Range download and SHA256 integrity."""
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

        # Wait for download completion (max 10s)
        start_time = time.time()
        while not finished_results and time.time() - start_time < 10:
            self.app.processEvents()
            time.sleep(0.05)

        downloader.wait(2000)

        # Verifications
        self.assertEqual(len(finished_results), 1)
        final_file = finished_results[0][1]
        self.assertTrue(os.path.exists(final_file))
        self.assertEqual(os.path.getsize(final_file), len(TEST_DATA))

        # Hash verification (Did data download completely?)
        downloaded_hash = calculate_file_hash(final_file)
        self.assertEqual(downloaded_hash, TEST_HASH)
        self.assertTrue(len(progress_events) > 0)

    def test_04_pause_and_resume_download(self):
        """Tests pausing download and subsequently resuming it."""
        target_filename = "resumable_2mb.bin"
        task = DownloadTask(
            task_id="task_test_02",
            url=f"http://127.0.0.1:{self.port}/slow_file_04.bin",
            destination_folder=self.test_dir,
            filename=target_filename
        )

        # 1. Start download and pause once data stream begins
        downloader = HttpChunkDownloader(task=task, num_chunks=4)
        downloader.start()

        start_wait = time.time()
        while time.time() - start_wait < 10:
            self.app.processEvents()
            if task.downloaded_size > 0:
                break
            time.sleep(0.01)

        downloader.pause()
        downloader.wait(2000)

        self.assertEqual(task.status, DownloadStatus.PAUSED)
        self.assertTrue(os.path.exists(task.meta_file_path))

        # 2. Resume download
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

    def test_05_temp_dir_isolation_and_no_destination_pollution(self):
        """Tests that chunks are stored in isolated temp directory, not polluting destination folder."""
        target_filename = "clean_dest_2mb.bin"
        task = DownloadTask(
            task_id="task_test_isolation",
            url=f"http://127.0.0.1:{self.port}/slow_file_05.bin",
            destination_folder=self.test_dir,
            filename=target_filename
        )

        downloader = HttpChunkDownloader(task=task, num_chunks=4)
        downloader.start()

        # Allow partial download and pause
        start_wait = time.time()
        while time.time() - start_wait < 10:
            self.app.processEvents()
            if task.downloaded_size > 0:
                break
            time.sleep(0.01)

        downloader.pause()
        downloader.wait(2000)

        # 1. Destination folder MUST NOT contain .part or .meta files!
        dest_files = os.listdir(self.test_dir)
        for f in dest_files:
            self.assertFalse(f.endswith(".part0") or f.endswith(".part1") or f.endswith(".part2") or f.endswith(".part3"))
            self.assertFalse(f.endswith(".meta.json"))

        # 2. Temporary chunks and meta file must exist in task isolated temp dir!
        self.assertTrue(os.path.exists(task.temp_dir))
        temp_files = os.listdir(task.temp_dir)
        self.assertTrue(any(f.endswith(".meta.json") for f in temp_files))
        self.assertTrue(any(".part" in f for f in temp_files))

        # 3. Complete download
        resume_finished = []
        resume_downloader = HttpChunkDownloader(task=task, num_chunks=4)
        resume_downloader.finished.connect(lambda tid, path: resume_finished.append((tid, path)))
        resume_downloader.start()

        start_time = time.time()
        while not resume_finished and time.time() - start_time < 10:
            self.app.processEvents()
            time.sleep(0.05)

        resume_downloader.wait(2000)

        # 4. Target file must be in destination, and temp dir must be completely cleaned up!
        final_file = os.path.join(self.test_dir, target_filename)
        self.assertTrue(os.path.exists(final_file))
        self.assertEqual(calculate_file_hash(final_file), TEST_HASH)
        self.assertFalse(os.path.exists(task.temp_dir))

        print("\n[OK] All Stage 2 download engine tests passed successfully!")


if __name__ == "__main__":
    unittest.main()
