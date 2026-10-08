"""
Download Manager - Data Models and State Management (models.py)

This module contains typed dataclass models and enums representing
download tasks, lifecycle states (status), segments (chunks), and metadata.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import time
import os


class DownloadStatus(str, Enum):
    """Enumeration defining download task lifecycle states."""
    QUEUED = "QUEUED"              # Waiting in queue
    CONNECTING = "CONNECTING"      # Connecting to server / fetching headers
    DOWNLOADING = "DOWNLOADING"    # Actively downloading data
    PAUSED = "PAUSED"              # Paused by user or system
    MERGING = "MERGING"            # Assembling downloaded chunks into destination file
    COMPLETED = "COMPLETED"        # Download and merge completed successfully
    FAILED = "FAILED"              # Terminated due to error
    CANCELLED = "CANCELLED"        # Cancelled by user


class TaskType(str, Enum):
    """Type of download task."""
    HTTP_FILE = "HTTP_FILE"        # Standard HTTP/HTTPS file
    MEDIA_VIDEO = "MEDIA_VIDEO"    # Video stream fetched via yt-dlp
    MEDIA_AUDIO = "MEDIA_AUDIO"    # Audio stream extracted via yt-dlp


@dataclass
class ChunkInfo:
    """Holds details for a single segmented download chunk."""
    chunk_id: int                  # Chunk index number (0, 1, 2...)
    start_byte: int                # Starting byte offset
    end_byte: int                  # Ending byte offset
    downloaded_bytes: int = 0      # Bytes downloaded so far for this chunk
    temp_file: str = ""            # Full path to temporary .part file
    is_completed: bool = False     # Whether this chunk has finished downloading

    @property
    def total_bytes(self) -> int:
        """Total byte size of this chunk segment."""
        return self.end_byte - self.start_byte + 1

    @property
    def progress_percent(self) -> float:
        """Completion percentage of this chunk."""
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, (self.downloaded_bytes / self.total_bytes) * 100.0)

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary representation for serialization."""
        return {
            "chunk_id": self.chunk_id,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "downloaded_bytes": self.downloaded_bytes,
            "temp_file": self.temp_file,
            "is_completed": self.is_completed
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChunkInfo":
        """Constructs a ChunkInfo object from dictionary data."""
        return cls(
            chunk_id=data["chunk_id"],
            start_byte=data["start_byte"],
            end_byte=data["end_byte"],
            downloaded_bytes=data.get("downloaded_bytes", 0),
            temp_file=data.get("temp_file", ""),
            is_completed=data.get("is_completed", False)
        )


@dataclass
class DownloadTask:
    """Holds complete lifecycle metadata and metrics for a download task."""
    task_id: str
    url: str
    destination_folder: str
    filename: str
    task_type: TaskType = TaskType.HTTP_FILE
    status: DownloadStatus = DownloadStatus.QUEUED
    total_size: int = 0            # File size in bytes (0 = unknown)
    downloaded_size: int = 0       # Total bytes downloaded so far
    speed_bytes_per_sec: float = 0.0
    eta_seconds: Optional[int] = None
    is_resumable: bool = False     # Whether server supports HTTP Range requests
    chunks: List[ChunkInfo] = field(default_factory=list)
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    headers: Dict[str, str] = field(default_factory=dict)

    @property
    def final_file_path(self) -> str:
        """Full path to destination target file."""
        return os.path.join(self.destination_folder, self.filename)

    @property
    def temp_dir(self) -> str:
        """Directory dedicated to storing task temporary chunks."""
        from app.core.config import get_temp_dir
        return os.path.join(get_temp_dir(), self.task_id)

    @property
    def meta_file_path(self) -> str:
        """Path to metadata file saving pause/resume states."""
        temp_meta = os.path.join(self.temp_dir, f"{self.filename}.meta.json")
        legacy_meta = f"{self.final_file_path}.meta.json"
        if not os.path.exists(temp_meta) and os.path.exists(legacy_meta):
            return legacy_meta
        return temp_meta

    @property
    def progress_percent(self) -> float:
        """Total completion percentage of download task."""
        if self.total_size <= 0:
            return 0.0
        return min(100.0, (self.downloaded_size / self.total_size) * 100.0)

    @staticmethod
    def _format_bytes(size: int) -> str:
        """Formats bytes into human-readable unit string."""
        if size <= 0:
            return "0 B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"

    @property
    def formatted_downloaded_size(self) -> str:
        """Formats downloaded bytes (e.g. 3.20 MB)."""
        return self._format_bytes(self.downloaded_size)

    @property
    def formatted_size_progress(self) -> str:
        """Returns download progress formatted as 'X.XX MB / Y.YY MB'.

        If download is in progress, displays 'downloaded / total'.
        If total size is unknown, displays only downloaded bytes.
        """
        dl = self.downloaded_size
        tot = self.total_size
        if tot > 0:
            return f"{self._format_bytes(dl)} / {self._format_bytes(tot)}"
        elif dl > 0:
            return self._format_bytes(dl)
        return "Unknown"

    @property
    def formatted_speed(self) -> str:
        """Formats transfer speed into human-readable string (e.g. 5.2 MB/s)."""
        speed = self.speed_bytes_per_sec
        if speed < 1024:
            return f"{speed:.1f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        else:
            return f"{speed / (1024 * 1024):.2f} MB/s"

    @property
    def formatted_eta(self) -> str:
        """Formats remaining time estimate (e.g. 01:23)."""
        if self.eta_seconds is None or self.eta_seconds < 0 or self.eta_seconds > 86400:
            return "--:--"
        mins, secs = divmod(self.eta_seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    @property
    def formatted_total_size(self) -> str:
        """Formats total file size (MB/GB). Detects disk size if unknown."""
        size = self.total_size
        if size <= 0 and self.downloaded_size > 0:
            size = self.downloaded_size
            self.total_size = size

        # If still 0 and file exists on disk, determine actual size
        if size <= 0:
            try:
                target_path = self.final_file_path
                if target_path and os.path.exists(target_path) and not os.path.isdir(target_path):
                    size = os.path.getsize(target_path)
                    self.total_size = size
                    self.downloaded_size = size
                else:
                    # Check matching base extensions in target folder (.mp4, .mkv, .webm, .mp3)
                    base = os.path.splitext(self.filename)[0]
                    dest = self.destination_folder
                    if dest and os.path.isdir(dest):
                        for ext in (".mp4", ".mkv", ".webm", ".mp3", ".m4a"):
                            cand = os.path.join(dest, base + ext)
                            if os.path.exists(cand) and not os.path.isdir(cand):
                                size = os.path.getsize(cand)
                                self.total_size = size
                                self.downloaded_size = size
                                self.filename = os.path.basename(cand)
                                break
            except Exception:
                pass

        if size <= 0:
            return "Unknown"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"

    @property
    def category(self) -> str:
        """Determines category name based on file extension or task type."""
        if self.task_type == TaskType.MEDIA_VIDEO:
            return "Video"
        elif self.task_type == TaskType.MEDIA_AUDIO:
            return "Music"

        ext = os.path.splitext(self.filename)[1].replace(".", "").lower()
        if ext in ("png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "ico"):
            return "Image"
        elif ext in ("mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"):
            return "Music"
        elif ext in ("mp4", "mkv", "avi", "mov", "flv", "wmv", "webm", "m4v"):
            return "Video"
        elif ext in ("exe", "msi", "apk", "dmg", "pkg", "deb", "rpm", "appimage", "iso"):
            return "Apps"
        elif ext in ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "epub"):
            return "Document"
        elif ext in ("zip", "rar", "7z", "tar", "gz", "bz2", "xz"):
            return "Compressed"
        else:
            return "Other"

    @property
    def category_icon(self) -> str:
        """Emoji icon representing task category."""
        cat = self.category
        icons = {
            "Image": "🖼️",
            "Music": "🎵",
            "Video": "🎬",
            "Apps": "📱",
            "Document": "📄",
            "Compressed": "🗜️",
            "Other": "📦"
        }
        return icons.get(cat, "📦")

    @property
    def formatted_date_added(self) -> str:
        """Returns relative time since task was created."""
        from datetime import datetime
        now = time.time()
        diff = max(0.0, now - self.created_at)
        if diff < 60:
            return "Just now"
        elif diff < 3600:
            mins = int(diff // 60)
            return "1 min ago" if mins == 1 else f"{mins} mins ago"

        task_dt = datetime.fromtimestamp(self.created_at)
        now_dt = datetime.now()
        if task_dt.date() == now_dt.date():
            return f"Today {task_dt.strftime('%H:%M')}"
        elif (now_dt.date() - task_dt.date()).days == 1:
            return f"Yesterday {task_dt.strftime('%H:%M')}"
        else:
            days = (now_dt.date() - task_dt.date()).days
            if days < 7:
                return f"{days} days ago"
            return task_dt.strftime("%Y-%m-%d %H:%M")

    def to_dict(self) -> Dict[str, Any]:
        """Serializes task data to a JSON-compatible dictionary."""
        return {
            "task_id": self.task_id,
            "url": self.url,
            "destination_folder": self.destination_folder,
            "filename": self.filename,
            "task_type": self.task_type.value if hasattr(self.task_type, "value") else str(self.task_type),
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "total_size": self.total_size,
            "downloaded_size": self.downloaded_size,
            "is_resumable": self.is_resumable,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "headers": self.headers,
            "chunks": [c.to_dict() for c in self.chunks] if self.chunks else []
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DownloadTask":
        """Constructs a DownloadTask object from dictionary data."""
        raw_type = data.get("task_type", "HTTP_FILE")
        try:
            task_type = TaskType(raw_type)
        except Exception:
            task_type = TaskType.HTTP_FILE

        raw_status = data.get("status", "QUEUED")
        try:
            status = DownloadStatus(raw_status)
        except Exception:
            status = DownloadStatus.PAUSED

        # If application was closed during an active download, restore safely as PAUSED
        if status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING, DownloadStatus.MERGING, DownloadStatus.QUEUED):
            status = DownloadStatus.PAUSED

        total_size = 0
        try:
            total_size = int(data.get("total_size") or 0)
        except Exception:
            total_size = 0

        downloaded_size = 0
        try:
            downloaded_size = int(data.get("downloaded_size") or 0)
        except Exception:
            downloaded_size = 0

        created_at = time.time()
        try:
            if data.get("created_at") is not None:
                created_at = float(data["created_at"])
        except Exception:
            created_at = time.time()

        completed_at = None
        try:
            if data.get("completed_at") is not None:
                completed_at = float(data["completed_at"])
        except Exception:
            completed_at = None

        # If task completed or completed_at exists, preserve COMPLETED status
        if completed_at is not None and status not in (DownloadStatus.FAILED, DownloadStatus.CANCELLED):
            status = DownloadStatus.COMPLETED

        # Guarantee size consistency for completed tasks
        if status == DownloadStatus.COMPLETED:
            if total_size <= 0 and downloaded_size > 0:
                total_size = downloaded_size
            elif downloaded_size <= 0 and total_size > 0:
                downloaded_size = total_size

        chunks_data = data.get("chunks", [])
        chunks = [ChunkInfo.from_dict(c) for c in chunks_data] if chunks_data else []

        task = cls(
            task_id=data.get("task_id", ""),
            url=data.get("url", ""),
            destination_folder=data.get("destination_folder", ""),
            filename=data.get("filename", "download"),
            task_type=task_type,
            status=status,
            total_size=total_size,
            downloaded_size=downloaded_size,
            speed_bytes_per_sec=0.0,
            eta_seconds=None,
            is_resumable=bool(data.get("is_resumable", False)),
            chunks=chunks,
            error_message=data.get("error_message"),
            created_at=created_at,
            completed_at=completed_at,
            headers=data.get("headers", {})
        )

        # If task is not marked COMPLETED but file exists with expected full size on disk, mark COMPLETED
        if task.status != DownloadStatus.COMPLETED and task.total_size > 0:
            target = task.final_file_path
            if target and os.path.exists(target) and not os.path.isdir(target):
                actual_size = os.path.getsize(target)
                if actual_size >= task.total_size:
                    task.status = DownloadStatus.COMPLETED
                    task.downloaded_size = actual_size

        return task
