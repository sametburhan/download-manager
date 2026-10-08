"""
Download Manager - Task Manager (task_manager.py)

This class is the central coordination point for all active, paused,
and completed downloads. It queues download requests coming from the GUI
or WebSocket server, starts the appropriate engine (HTTP or yt-dlp) as a QThread,
and dispatches signals to the GUI from a unified source.
"""

import os
import re
import uuid
import json
import time
from typing import Dict, Optional, List
from PyQt6.QtCore import QObject, pyqtSignal

from app.core.models import DownloadTask, DownloadStatus, TaskType
from app.core.http_downloader import HttpChunkDownloader
from app.core.media_downloader import MediaDownloader
from app.core.config import get_tasks_file_path


class TaskManager(QObject):
    """Central manager class orchestrating download engines."""

    task_added = pyqtSignal(object)           # DownloadTask instance
    task_progress = pyqtSignal(dict)          # Progress dictionary
    task_chunk_progress = pyqtSignal(str, int, int, int) # task_id, chunk_id, downloaded, total
    task_status_changed = pyqtSignal(str, str)# task_id, status
    task_finished = pyqtSignal(str, str)      # task_id, file_path
    task_error = pyqtSignal(str, str)         # task_id, error

    def __init__(
        self,
        default_download_dir: Optional[str] = None,
        tasks_file: Optional[str] = None,
        auto_load: bool = True,
        parent=None
    ):
        super().__init__(parent)
        self.default_download_dir = default_download_dir or os.path.join(
            os.path.expanduser("~"), "Downloads"
        )
        self.tasks_file = tasks_file if tasks_file is not None else get_tasks_file_path()
        self.tasks: Dict[str, DownloadTask] = {}
        self.workers: Dict[str, object] = {}
        self._last_save_time = 0.0

        if auto_load:
            self.load_tasks()

    # ==================== Task Persistence ====================

    def load_tasks(self) -> None:
        """Reads saved tasks from tasks.json and loads them into memory."""
        if not self.tasks_file or not os.path.exists(self.tasks_file):
            return

        try:
            with open(self.tasks_file, "r", encoding="utf-8-sig") as f:
                raw_data = json.load(f)

            if isinstance(raw_data, list):
                for item in raw_data:
                    if isinstance(item, dict) and "task_id" in item:
                        try:
                            task = DownloadTask.from_dict(item)
                            self.tasks[task.task_id] = task
                        except Exception as e:
                            print(f"[WARN] Error loading task {item.get('task_id')}: {e}")
            print(f"[INFO] Loaded {len(self.tasks)} saved download tasks from {self.tasks_file}")
        except Exception as e:
            print(f"[ERROR] Failed to load tasks from {self.tasks_file}: {e}")

    def save_tasks(self, force: bool = False) -> None:
        """Atomically saves tasks to tasks.json."""
        if not self.tasks_file:
            return

        # Debounce progress updates to avoid excessive disk writes
        now = time.time()
        if not force and (now - self._last_save_time < 2.5):
            return

        self._last_save_time = now

        try:
            data = [task.to_dict() for task in self.tasks.values()]
            tmp_file = f"{self.tasks_file}.tmp"
            os.makedirs(os.path.dirname(self.tasks_file), exist_ok=True)
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            try:
                os.replace(tmp_file, self.tasks_file)
            except Exception:
                time.sleep(0.05)
                try:
                    os.replace(tmp_file, self.tasks_file)
                except Exception:
                    with open(self.tasks_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    if os.path.exists(tmp_file):
                        try:
                            os.remove(tmp_file)
                        except Exception:
                            pass
        except Exception as e:
            print(f"[ERROR] Failed to save tasks to {self.tasks_file}: {e}")

    # ==================== Helper Methods ====================

    @staticmethod
    def _resolve_unique_filename(dest_dir: str, filename: str) -> str:
        """Appends a numbered suffix if a file with the same name already exists in target directory.

        Example: if video.mp4 exists -> video(1).mp4, if that exists -> video(2).mp4
        This prevents race conditions and erroneous 'already completed' triggers.
        """
        target = os.path.join(dest_dir, filename)
        if not os.path.exists(target):
            return filename  # No collision, use original name

        base, ext = os.path.splitext(filename)
        counter = 1
        while True:
            new_name = f"{base}({counter}){ext}"
            if not os.path.exists(os.path.join(dest_dir, new_name)):
                return new_name
            counter += 1

    def add_http_download(
        self,
        url: str,
        filename: Optional[str] = None,
        destination_folder: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        num_chunks: Optional[int] = None,
        auto_start: bool = True
    ) -> str:
        """Adds and starts a new multi-part HTTP download task."""
        task_id = str(uuid.uuid4())[:8]
        dest_dir = destination_folder or self.default_download_dir
        os.makedirs(dest_dir, exist_ok=True)

        if num_chunks is None:
            try:
                from app.core.config import load_network_settings
                num_chunks = load_network_settings().segments_per_download
            except Exception:
                num_chunks = 8

        if not filename:
            filename = url.split("/")[-1].split("?")[0] or f"download_{task_id}.bin"

        # Resolve collisions if file already exists (e.g. video(1).mp4)
        filename = self._resolve_unique_filename(dest_dir, filename)

        task = DownloadTask(
            task_id=task_id,
            url=url,
            destination_folder=dest_dir,
            filename=filename,
            task_type=TaskType.HTTP_FILE,
            headers=headers or {}
        )

        self.tasks[task_id] = task
        self.save_tasks(force=True)
        self.task_added.emit(task)

        if auto_start:
            self.start_http_worker(task, num_chunks)

        return task_id

    def start_http_worker(self, task: DownloadTask, num_chunks: Optional[int] = None) -> None:
        """Starts HTTP download engine QThread and connects signals."""
        if num_chunks is None or num_chunks <= 0:
            if task.chunks:
                num_chunks = len(task.chunks)
            else:
                try:
                    from app.core.config import load_network_settings
                    num_chunks = load_network_settings().segments_per_download
                except Exception:
                    num_chunks = 8
        worker = HttpChunkDownloader(task=task, num_chunks=num_chunks)

        # Signal connections
        worker.progress_updated.connect(self._on_worker_progress)
        worker.chunk_progress.connect(
            lambda cid, down, tot: self.task_chunk_progress.emit(task.task_id, cid, down, tot)
        )
        worker.status_changed.connect(self._on_worker_status_changed)
        worker.finished.connect(self._on_worker_finished)
        worker.error_occurred.connect(self._on_worker_error)

        self.workers[task.task_id] = worker
        worker.start()

    def add_media_download(
        self,
        url: str,
        title: Optional[str] = None,
        destination_folder: Optional[str] = None,
        format_id: Optional[str] = None,
        audio_only: bool = False,
        headers: Optional[Dict[str, str]] = None,
        auto_start: bool = True
    ) -> str:
        """Adds and starts a new yt-dlp media download task."""
        task_id = str(uuid.uuid4())[:8]
        dest_dir = destination_folder or self.default_download_dir
        os.makedirs(dest_dir, exist_ok=True)

        # Sanitize Windows invalid filename characters
        safe_title = re.sub(r'[\\/*?"<>|]', "", title).strip() if title else f"media_{task_id}"
        if not safe_title:
            safe_title = f"media_{task_id}"

        # Prevent collision with existing files
        safe_title = self._resolve_unique_media_title(dest_dir, safe_title)

        task = DownloadTask(
            task_id=task_id,
            url=url,
            destination_folder=dest_dir,
            filename=safe_title,
            task_type=TaskType.MEDIA_AUDIO if audio_only else TaskType.MEDIA_VIDEO,
            headers=headers or {}
        )

        self.tasks[task_id] = task
        self.save_tasks(force=True)
        self.task_added.emit(task)

        if auto_start:
            self.start_media_worker(task, format_id, audio_only)

        return task_id

    def _resolve_unique_media_title(self, dest_dir: str, title: str) -> str:
        """Collision prevention for media titles: checks common video/audio extensions."""
        VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v",
                      ".mp3", ".m4a", ".aac", ".opus", ".flac", ".ogg")

        def _title_exists(t: str) -> bool:
            if os.path.exists(os.path.join(dest_dir, t)):
                return True
            for ext in VIDEO_EXTS:
                if os.path.exists(os.path.join(dest_dir, t + ext)):
                    return True
            return False

        if not _title_exists(title):
            return title

        counter = 1
        while True:
            new_title = f"{title}({counter})"
            if not _title_exists(new_title):
                return new_title
            counter += 1

    def start_media_worker(self, task: DownloadTask, format_id: Optional[str] = None, audio_only: bool = False) -> None:
        """Starts yt-dlp media downloader engine."""
        worker = MediaDownloader(task=task, format_id=format_id, audio_only=audio_only)

        worker.progress_updated.connect(self._on_worker_progress)
        worker.status_changed.connect(self._on_worker_status_changed)
        worker.finished.connect(self._on_worker_finished)
        worker.error_occurred.connect(self._on_worker_error)

        self.workers[task.task_id] = worker
        worker.start()

    # ==================== Internal Worker Signal Handlers ====================

    def _on_worker_progress(self, data: dict) -> None:
        self.task_progress.emit(data)
        self.save_tasks(force=False)

    def _on_worker_status_changed(self, task_id: str, status_str: str) -> None:
        self.task_status_changed.emit(task_id, status_str)
        self.save_tasks(force=True)

    def _on_worker_finished(self, task_id: str, file_path: str) -> None:
        self.task_finished.emit(task_id, file_path)
        self.save_tasks(force=True)

    def _on_worker_error(self, task_id: str, err_msg: str) -> None:
        self.task_error.emit(task_id, err_msg)
        self.save_tasks(force=True)

    def pause_task(self, task_id: str) -> None:
        """Pauses a download task."""
        if task_id in self.workers:
            worker = self.workers[task_id]
            if hasattr(worker, "pause"):
                worker.pause()
        if task_id in self.tasks:
            self.tasks[task_id].status = DownloadStatus.PAUSED
            self.save_tasks(force=True)

    def resume_task(self, task_id: str) -> None:
        """Resumes a paused download task."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task.status == DownloadStatus.PAUSED:
                if task.task_type == TaskType.HTTP_FILE:
                    num_chunks = len(task.chunks) if task.chunks else None
                    self.start_http_worker(task, num_chunks=num_chunks)
                elif task.task_type in (TaskType.MEDIA_VIDEO, TaskType.MEDIA_AUDIO):
                    audio_only = (task.task_type == TaskType.MEDIA_AUDIO)
                    self.start_media_worker(task, audio_only=audio_only)

    def cancel_task(self, task_id: str) -> None:
        """Cancels and cleans up a task."""
        if task_id in self.workers:
            worker = self.workers[task_id]
            if hasattr(worker, "cancel"):
                worker.cancel()

    def remove_task(self, task_id: str, delete_file: bool = False) -> bool:
        """Cancels a task, removes it from memory, and deletes disk files if requested."""
        if task_id not in self.tasks:
            return False

        task = self.tasks[task_id]

        # 1. Stop active worker thread
        if task_id in self.workers:
            worker = self.workers.pop(task_id)
            if hasattr(worker, "cancel"):
                try:
                    worker.cancel()
                except Exception:
                    pass
            if hasattr(worker, "wait"):
                try:
                    worker.wait(300)
                except Exception:
                    pass

        # 2. Delete files from disk if requested
        if delete_file:
            candidates = set()
            if hasattr(task, "final_file_path") and task.final_file_path:
                candidates.add(task.final_file_path)
            if hasattr(task, "meta_file_path") and task.meta_file_path:
                candidates.add(task.meta_file_path)

            if task.destination_folder and task.filename:
                base_dest = os.path.join(task.destination_folder, task.filename)
                candidates.add(base_dest)
                candidates.add(f"{base_dest}.part")
                candidates.add(f"{base_dest}.ytdl")

                # If saved with extensionless title, check matching media files
                try:
                    if os.path.isdir(task.destination_folder):
                        for f in os.listdir(task.destination_folder):
                            if f == task.filename or f.startswith(f"{task.filename}."):
                                candidates.add(os.path.join(task.destination_folder, f))
                except Exception:
                    pass

            for chunk in getattr(task, "chunks", []):
                if getattr(chunk, "temp_file", None):
                    candidates.add(chunk.temp_file)

            for path in candidates:
                if path and os.path.exists(path) and not os.path.isdir(path):
                    try:
                        os.remove(path)
                    except Exception as e:
                        print(f"[WARN] Failed to delete file from disk {path}: {e}")

            # Clean up task temp directory completely
            if hasattr(task, "temp_dir") and task.temp_dir and os.path.exists(task.temp_dir):
                import shutil
                try:
                    shutil.rmtree(task.temp_dir, ignore_errors=True)
                except Exception as e:
                    print(f"[WARN] Failed to delete task temp dir {task.temp_dir}: {e}")

        # 3. Remove completely from memory / task pool
        self.tasks.pop(task_id, None)
        self.save_tasks(force=True)
        return True

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """Returns the download task object."""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[DownloadTask]:
        """Returns all saved tasks as a list."""
        return list(self.tasks.values())


