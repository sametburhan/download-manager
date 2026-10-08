"""
Download Manager - HTTP Range Multi-part Download Engine (http_downloader.py)

This module splits downloads into concurrent threads using HTTP 'Range' headers,
downloads each chunk independently, manages Pause/Resume operations,
and merges the parts into the final target file upon completion.
"""

import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any

import urllib.request
from PyQt6.QtCore import QThread, pyqtSignal
import httpx

from app.core.models import DownloadTask, DownloadStatus, ChunkInfo, TaskType
from app.utils.file_utils import sanitize_filename, merge_chunks, cleanup_temp_files


class HttpChunkDownloader(QThread):
    """
    QThread-based HTTP multi-chunk download engine.
    Runs in the background without blocking the PyQt6 GUI and emits status updates via pyqtSignal.
    """

    # Signals (PyQt signal mechanism)
    progress_updated = pyqtSignal(dict)           # Progress, speed, ETA dictionary
    chunk_progress = pyqtSignal(int, int, int)    # chunk_id, downloaded_bytes, total_bytes
    status_changed = pyqtSignal(str, str)         # task_id, new_status (enum string)
    finished = pyqtSignal(str, str)               # task_id, completed_file_path
    error_occurred = pyqtSignal(str, str)         # task_id, error_message

    def __init__(
        self,
        task: DownloadTask,
        num_chunks: Optional[int] = None,
        chunk_buffer_size: int = 64 * 1024,  # 64 KB read buffer
        parent=None
    ):
        super().__init__(parent)
        self.task = task
        if num_chunks is None or num_chunks <= 0:
            try:
                from app.core.config import load_network_settings
                num_chunks = load_network_settings().segments_per_download
            except Exception:
                num_chunks = 8
        self.num_chunks = max(1, num_chunks)
        self.chunk_buffer_size = chunk_buffer_size

        # Thread control flags and locks
        self._is_paused = False
        self._is_cancelled = False
        self._lock = threading.Lock()

        # Speed and ETA calculation variables
        self._last_calc_time = time.time()
        self._last_downloaded_bytes = 0

    # ==================== External Control Methods ====================

    def pause(self) -> None:
        """Safely pauses the download and saves current state."""
        with self._lock:
            if self.task.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED):
                return
            self._is_paused = True
            self.task.status = DownloadStatus.PAUSED
            self._save_meta_file()
            self.status_changed.emit(self.task.task_id, DownloadStatus.PAUSED.value)

    def cancel(self) -> None:
        """Cancels the download and cleans up temporary files."""
        with self._lock:
            if self.task.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED):
                return
            self._is_cancelled = True
            self.task.status = DownloadStatus.CANCELLED
            self.status_changed.emit(self.task.task_id, DownloadStatus.CANCELLED.value)

    # ==================== QThread Main Execution Loop ====================

    def run(self) -> None:
        """Main execution function triggered when QThread.start() is called."""
        self._is_paused = False
        self._is_cancelled = False

        try:
            self.task.status = DownloadStatus.CONNECTING
            self.status_changed.emit(self.task.task_id, DownloadStatus.CONNECTING.value)

            if self.task.url.startswith("file://"):
                local_path = urllib.request.url2pathname(self.task.url.replace("file://", ""))
                if local_path.startswith("/") and len(local_path) > 2 and local_path[2] == ":":
                    local_path = local_path[1:]
                if not os.path.exists(local_path):
                    raise FileNotFoundError(f"Local file not found: {local_path}")

                total = os.path.getsize(local_path)
                self.task.total_size = total
                self.task.status = DownloadStatus.DOWNLOADING
                self.status_changed.emit(self.task.task_id, DownloadStatus.DOWNLOADING.value)

                chunk_size = 64 * 1024
                copied = 0
                start_time = time.time()
                with open(local_path, "rb") as src, open(self.task.final_file_path, "wb") as dst:
                    while True:
                        if self._is_paused or self._is_cancelled:
                            return
                        data = src.read(chunk_size)
                        if not data:
                            break
                        dst.write(data)
                        copied += len(data)
                        self.task.downloaded_size = copied
                        elapsed = time.time() - start_time
                        speed = copied / max(elapsed, 0.001)
                        self.progress_updated.emit({
                            "task_id": self.task.task_id,
                            "downloaded_bytes": copied,
                            "total_bytes": total,
                            "percent": (copied / total * 100.0) if total > 0 else 100.0,
                            "speed_str": f"{speed / (1024 * 1024):.2f} MB/s",
                            "eta_str": "00:00:00"
                        })

                if os.path.exists(self.task.final_file_path):
                    real_size = os.path.getsize(self.task.final_file_path)
                    if real_size > 0:
                        self.task.total_size = real_size
                        self.task.downloaded_size = real_size
                elif copied > 0:
                    self.task.total_size = copied
                    self.task.downloaded_size = copied

                self.task.status = DownloadStatus.COMPLETED
                self.task.completed_at = time.time()
                self.status_changed.emit(self.task.task_id, DownloadStatus.COMPLETED.value)
                self.finished.emit(self.task.task_id, self.task.final_file_path)
                return

            # 1. Query server headers and Range support
            self._inspect_server()

            # 2. Setup chunk boundaries or load from existing state
            self._setup_chunks()

            if self._is_paused or self._is_cancelled:
                self._save_meta_file()
                return

            # 3. Start download
            self.task.status = DownloadStatus.DOWNLOADING
            self.status_changed.emit(self.task.task_id, DownloadStatus.DOWNLOADING.value)

            self._download_all_chunks()

            # Exit if paused or cancelled
            if self._is_paused or self._is_cancelled:
                self._save_meta_file()
                if self._is_cancelled:
                    self._cleanup_all()
                return

            # 4. If all chunks are finished, move to merging stage
            self.task.status = DownloadStatus.MERGING
            self.status_changed.emit(self.task.task_id, DownloadStatus.MERGING.value)

            chunk_paths = [chunk.temp_file for chunk in self.task.chunks]
            merge_chunks(chunk_paths, self.task.final_file_path)

            # Clean up temporary files and task temp directory
            cleanup_temp_files(chunk_paths, self.task.meta_file_path, self.task.temp_dir)

            # 5. Successfully completed
            if os.path.exists(self.task.final_file_path):
                real_size = os.path.getsize(self.task.final_file_path)
                if real_size > 0:
                    self.task.total_size = real_size
                    self.task.downloaded_size = real_size
            elif self.task.downloaded_size > 0 and self.task.total_size <= 0:
                self.task.total_size = self.task.downloaded_size

            self.task.status = DownloadStatus.COMPLETED
            self.task.completed_at = time.time()
            self.status_changed.emit(self.task.task_id, DownloadStatus.COMPLETED.value)
            self.finished.emit(self.task.task_id, self.task.final_file_path)

        except Exception as exc:
            self.task.status = DownloadStatus.FAILED
            self.task.error_message = str(exc)
            self.status_changed.emit(self.task.task_id, DownloadStatus.FAILED.value)
            self.error_occurred.emit(self.task.task_id, str(exc))

    # ==================== Internal Logic & Network Operations ====================

    @staticmethod
    def _get_proxy_url() -> Optional[str]:
        """Reads proxy configuration from settings and returns an httpx / httpx-socks compatible URL."""
        try:
            from app.core.config import load_network_settings
            net_settings = load_network_settings()
            if net_settings.proxy_mode == "manual" and net_settings.proxy_host:
                pwd = getattr(net_settings, "proxy_pass", getattr(net_settings, "proxy_password", ""))
                auth = f"{net_settings.proxy_user}:{pwd}@" if net_settings.proxy_user else ""
                proto = (getattr(net_settings, "proxy_type", "HTTP") or "HTTP").lower()
                return f"{proto}://{auth}{net_settings.proxy_host}:{net_settings.proxy_port}"
            elif net_settings.proxy_mode == "none":
                return None
            elif net_settings.proxy_mode == "system":
                sys_proxies = urllib.request.getproxies()
                return sys_proxies.get("https") or sys_proxies.get("http")
        except Exception:
            pass
        return None

    @classmethod
    def _create_http_client(cls, timeout: float = 30.0) -> httpx.Client:
        """
        Creates an httpx.Client instance matching proxy configuration.
        Uses SyncProxyTransport for SOCKS4 and SOCKS5 proxies.
        """
        proxy_url = cls._get_proxy_url()
        if proxy_url:
            lower_proxy = proxy_url.lower()
            if lower_proxy.startswith(("socks4://", "socks4a://", "socks5://", "socks5h://")):
                try:
                    from httpx_socks import SyncProxyTransport
                    transport = SyncProxyTransport.from_url(proxy_url)
                    return httpx.Client(transport=transport, follow_redirects=True, timeout=timeout)
                except Exception:
                    pass
        return httpx.Client(proxy=proxy_url, follow_redirects=True, timeout=timeout)

    def _inspect_server(self) -> None:
        """Determines size and Range support by sending a HEAD or test GET request."""
        req_headers = dict(self.task.headers)
        # Some servers block HEAD requests, so test GET with Range: bytes=0-0
        req_headers["Range"] = "bytes=0-0"

        with self._create_http_client(timeout=15.0) as client:
            try:
                response = client.get(self.task.url, headers=req_headers)
            except httpx.RequestError as err:
                raise ConnectionError(f"Could not connect to server: {str(err)}")

            if response.status_code == 206:
                # Server returned 206 Partial Content, Range is supported!
                self.task.is_resumable = True
                content_range = response.headers.get("Content-Range", "")
                # Format: "bytes 0-0/1234567"
                if "/" in content_range:
                    total_str = content_range.split("/")[-1]
                    if total_str.isdigit():
                        self.task.total_size = int(total_str)
            elif response.status_code in (200, 302):
                # Server returned 200 OK. Check Accept-Ranges header
                accept_ranges = response.headers.get("Accept-Ranges", "").lower()
                self.task.is_resumable = (accept_ranges == "bytes")
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    self.task.total_size = int(content_length)
                else:
                    self.task.total_size = 0
            else:
                raise RuntimeError(f"Server returned unexpected HTTP response: {response.status_code}")

            # Extract filename from Content-Disposition header if available
            content_disp = response.headers.get("Content-Disposition", "")
            if "filename=" in content_disp:
                extracted_name = content_disp.split("filename=")[-1].strip('"\'; ')
                if extracted_name:
                    self.task.filename = sanitize_filename(extracted_name)

    def _setup_chunks(self) -> None:
        """Loads existing meta file if available, otherwise calculates chunks dynamically."""
        # 1. Does a saved meta file exist for Pause/Resume?
        if os.path.exists(self.task.meta_file_path):
            try:
                with open(self.task.meta_file_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    chunks_data = meta.get("chunks", [])

                if chunks_data:
                    self.task.total_size = meta.get("total_size", self.task.total_size)
                    self.task.is_resumable = meta.get("is_resumable", self.task.is_resumable)
                    self.task.chunks = [ChunkInfo.from_dict(c) for c in chunks_data]

                    # Synchronize actual chunk sizes on disk
                    total_downloaded = 0
                    for chunk in self.task.chunks:
                        if os.path.exists(chunk.temp_file):
                            actual_size = os.path.getsize(chunk.temp_file)
                            chunk.downloaded_bytes = actual_size
                            if chunk.total_bytes > 0 and chunk.downloaded_bytes >= chunk.total_bytes:
                                chunk.is_completed = True
                        total_downloaded += chunk.downloaded_bytes

                    self.task.downloaded_size = total_downloaded
                    return
            except Exception:
                # If meta file is corrupted, restart clean
                pass

        # 2. New chunk setup
        self.task.chunks.clear()
        os.makedirs(self.task.temp_dir, exist_ok=True)

        # If Range is not supported or file size is unknown, run SINGLE chunk
        if not self.task.is_resumable or self.task.total_size <= 0:
            part_file = os.path.join(self.task.temp_dir, f"{self.task.filename}.part0")
            chunk = ChunkInfo(
                chunk_id=0,
                start_byte=0,
                end_byte=self.task.total_size - 1 if self.task.total_size > 0 else 0,
                temp_file=part_file
            )
            self.task.chunks.append(chunk)
            if not os.path.exists(part_file):
                try:
                    open(part_file, "a").close()
                except OSError:
                    pass
            self._save_meta_file()
            return

        # Range is supported: Split file into num_chunks parts
        chunk_size = self.task.total_size // self.num_chunks
        for i in range(self.num_chunks):
            start = i * chunk_size
            # Last chunk covers up to the last byte of the file
            end = self.task.total_size - 1 if i == self.num_chunks - 1 else (i + 1) * chunk_size - 1
            part_file = os.path.join(self.task.temp_dir, f"{self.task.filename}.part{i}")

            chunk = ChunkInfo(
                chunk_id=i,
                start_byte=start,
                end_byte=end,
                temp_file=part_file
            )
            self.task.chunks.append(chunk)

            # Prepare temp chunk file in temp dir
            if not os.path.exists(part_file):
                try:
                    open(part_file, "a").close()
                except OSError:
                    pass

        self._save_meta_file()

    def _download_all_chunks(self) -> None:
        """Downloads all chunks concurrently in worker threads using ThreadPoolExecutor."""
        # Filter incomplete chunks
        incomplete_chunks = [c for c in self.task.chunks if not c.is_completed]
        if not incomplete_chunks:
            return

        # Start concurrent chunk downloaders
        with ThreadPoolExecutor(max_workers=len(incomplete_chunks)) as executor:
            futures = [executor.submit(self._download_chunk_worker, chunk) for chunk in incomplete_chunks]
            for future in as_completed(futures):
                future.result()  # Call result() to re-raise any worker exceptions

    def _download_chunk_worker(self, chunk: ChunkInfo) -> None:
        """Worker function that downloads a single chunk using HTTP Range."""
        if chunk.is_completed or self._is_paused or self._is_cancelled:
            return

        # Determine remaining byte range (Resume logic)
        current_start = chunk.start_byte + chunk.downloaded_bytes
        if current_start > chunk.end_byte and chunk.total_bytes > 0:
            chunk.is_completed = True
            return

        req_headers = dict(self.task.headers)
        if self.task.is_resumable and chunk.total_bytes > 0:
            req_headers["Range"] = f"bytes={current_start}-{chunk.end_byte}"

        # Open file in append mode ("ab") if continuing, or "wb" if fresh
        mode = "ab" if chunk.downloaded_bytes > 0 and os.path.exists(chunk.temp_file) else "wb"

        with self._create_http_client(timeout=30.0) as client:
            with client.stream("GET", self.task.url, headers=req_headers) as response:
                if response.status_code not in (200, 206):
                    raise RuntimeError(f"Failed to download chunk #{chunk.chunk_id}. HTTP Code: {response.status_code}")

                os.makedirs(os.path.dirname(chunk.temp_file), exist_ok=True)
                with open(chunk.temp_file, mode) as f:
                    for data_block in response.iter_bytes(chunk_size=self.chunk_buffer_size):
                        # Exit immediately if paused or cancelled
                        if self._is_paused or self._is_cancelled:
                            break

                        f.write(data_block)
                        block_len = len(data_block)

                        with self._lock:
                            chunk.downloaded_bytes += block_len
                            self.task.downloaded_size += block_len

                        self._emit_progress(chunk)

        if not self._is_paused and not self._is_cancelled:
            if chunk.total_bytes > 0 and chunk.downloaded_bytes >= chunk.total_bytes:
                chunk.is_completed = True

    def _emit_progress(self, chunk: ChunkInfo) -> None:
        """Calculates speed, ETA, and progress signals and emits them to GUI."""
        now = time.time()
        elapsed = now - self._last_calc_time

        # Calculate speed and ETA every 200 ms
        if elapsed >= 0.2:
            with self._lock:
                bytes_diff = self.task.downloaded_size - self._last_downloaded_bytes
                speed = bytes_diff / elapsed if elapsed > 0 else 0
                self.task.speed_bytes_per_sec = speed

                # Remaining time (ETA) calculation
                if speed > 0 and self.task.total_size > self.task.downloaded_size:
                    remaining_bytes = self.task.total_size - self.task.downloaded_size
                    self.task.eta_seconds = int(remaining_bytes / speed)
                else:
                    self.task.eta_seconds = None

                self._last_calc_time = now
                self._last_downloaded_bytes = self.task.downloaded_size

            # Emit signals
            self.progress_updated.emit({
                "task_id": self.task.task_id,
                "downloaded_bytes": self.task.downloaded_size,
                "total_bytes": self.task.total_size,
                "percent": self.task.progress_percent,
                "speed_str": self.task.formatted_speed,
                "eta_str": self.task.formatted_eta,
                "speed_bps": self.task.speed_bytes_per_sec
            })

            self.chunk_progress.emit(
                chunk.chunk_id,
                chunk.downloaded_bytes,
                chunk.total_bytes
            )

    def _save_meta_file(self) -> None:
        """Writes Pause/Resume state to meta JSON file."""
        try:
            # Synchronize actual chunk sizes on disk
            for chunk in self.task.chunks:
                if os.path.exists(chunk.temp_file):
                    chunk.downloaded_bytes = os.path.getsize(chunk.temp_file)
                    if chunk.total_bytes > 0 and chunk.downloaded_bytes >= chunk.total_bytes:
                        chunk.is_completed = True

            meta_data = {
                "task_id": self.task.task_id,
                "url": self.task.url,
                "filename": self.task.filename,
                "total_size": self.task.total_size,
                "is_resumable": self.task.is_resumable,
                "chunks": [c.to_dict() for c in self.task.chunks]
            }
            os.makedirs(os.path.dirname(self.task.meta_file_path), exist_ok=True)
            with open(self.task.meta_file_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2)
        except Exception:
            pass

    def _cleanup_all(self) -> None:
        """Deletes all temporary and artifact files of cancelled task."""
        chunk_paths = [c.temp_file for c in self.task.chunks]
        cleanup_temp_files(chunk_paths, self.task.meta_file_path, self.task.temp_dir)
        if os.path.exists(self.task.final_file_path):
            try:
                os.remove(self.task.final_file_path)
            except OSError:
                pass
