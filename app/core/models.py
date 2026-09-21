"""
Download Manager - Veri Modelleri ve Durum Yönetimi (models.py)

Bu modül, indirme görevlerinin durumlarını (status), parçalarını (chunk)
ve tüm meta verilerini temsil eden tipli (dataclass) modelleri içerir.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import time
import os


class DownloadStatus(str, Enum):
    """İndirme görevinin mevcut durumunu belirten numaralandırma."""
    QUEUED = "QUEUED"              # Sırada bekliyor
    CONNECTING = "CONNECTING"      # Sunucuya bağlanıyor / Başlıklar okunuyor
    DOWNLOADING = "DOWNLOADING"    # İndiriliyor
    PAUSED = "PAUSED"              # Duraklatıldı
    MERGING = "MERGING"            # Parçalar birleştiriliyor
    COMPLETED = "COMPLETED"        # Başarıyla tamamlandı
    FAILED = "FAILED"              # Hata oluştu
    CANCELLED = "CANCELLED"        # Kullanıcı tarafından iptal edildi


class TaskType(str, Enum):
    """İndirilen görevin türü."""
    HTTP_FILE = "HTTP_FILE"        # Standart HTTP/HTTPS dosyası
    MEDIA_VIDEO = "MEDIA_VIDEO"    # yt-dlp ile indirilen video
    MEDIA_AUDIO = "MEDIA_AUDIO"    # yt-dlp ile indirilen ses/müzik


@dataclass
class ChunkInfo:
    """Tek bir indirme parçasının (chunk) detaylarını tutar."""
    chunk_id: int                  # Parça indeks numarası (0, 1, 2...)
    start_byte: int                # Parçanın başladığı byte ofseti
    end_byte: int                  # Parçanın bittiği byte ofseti
    downloaded_bytes: int = 0      # Şu ana kadar bu parça için inen miktar
    temp_file: str = ""            # Geçici .part dosyasının tam yolu
    is_completed: bool = False     # Bu parça bitti mi?

    @property
    def total_bytes(self) -> int:
        """Bu parçanın toplam byte büyüklüğü."""
        return self.end_byte - self.start_byte + 1

    @property
    def progress_percent(self) -> float:
        """Parçanın tamamlanma yüzdesi."""
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, (self.downloaded_bytes / self.total_bytes) * 100.0)

    def to_dict(self) -> Dict[str, Any]:
        """Serileştirme için sözlük temsili."""
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
        """Sözlükten ChunkInfo nesnesi oluşturur."""
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
    """Bir indirme görevinin tüm yaşam döngüsü meta verilerini tutar."""
    task_id: str
    url: str
    destination_folder: str
    filename: str
    task_type: TaskType = TaskType.HTTP_FILE
    status: DownloadStatus = DownloadStatus.QUEUED
    total_size: int = 0            # Bayt cinsinden dosya boyutu (0 = bilinmiyor)
    downloaded_size: int = 0       # Toplam inen miktar
    speed_bytes_per_sec: float = 0.0
    eta_seconds: Optional[int] = None
    is_resumable: bool = False     # Sunucu Range destekliyor mu?
    chunks: List[ChunkInfo] = field(default_factory=list)
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    headers: Dict[str, str] = field(default_factory=dict)

    @property
    def final_file_path(self) -> str:
        """Hedef dosyanın tam yolu."""
        return os.path.join(self.destination_folder, self.filename)

    @property
    def meta_file_path(self) -> str:
        """Pause/Resume durumunu saklayan meta veri dosyasının yolu."""
        return f"{self.final_file_path}.meta.json"

    @property
    def progress_percent(self) -> float:
        """Görevin toplam tamamlanma yüzdesi."""
        if self.total_size <= 0:
            return 0.0
        return min(100.0, (self.downloaded_size / self.total_size) * 100.0)

    @staticmethod
    def _format_bytes(size: int) -> str:
        """Byte miktarını insan tarafından okunabilir formata çevirir."""
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
        """İnen miktarı okunabilir birime çevirir (örn: 3.20 MB)."""
        return self._format_bytes(self.downloaded_size)

    @property
    def formatted_size_progress(self) -> str:
        """İndirme ilerlemesini 'X.XX MB / Y.YY MB' formatında döndürür.

        İndirme devam ediyorsa 'indirilen / toplam' biçiminde gösterir.
        Toplam bilinmiyorsa yalnızca indirilen miktarı gösterir.
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
        """Hızı insan tarafından okunabilir formata çevirir (örn: 5.2 MB/s)."""
        speed = self.speed_bytes_per_sec
        if speed < 1024:
            return f"{speed:.1f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        else:
            return f"{speed / (1024 * 1024):.2f} MB/s"

    @property
    def formatted_eta(self) -> str:
        """Kalan süreyi insan tarafından okunabilir formata çevirir (örn: 01:23)."""
        if self.eta_seconds is None or self.eta_seconds < 0 or self.eta_seconds > 86400:
            return "--:--"
        mins, secs = divmod(self.eta_seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    @property
    def formatted_total_size(self) -> str:
        """Toplam boyutu okunabilir birime çevirir (MB/GB). Bilinmiyorsa veya 0 ise diskteki boyutu tespit eder."""
        size = self.total_size
        if size <= 0 and self.downloaded_size > 0:
            size = self.downloaded_size

        # Eğer hala 0 ise veya dosya tamamlandıysa diskteki gerçek boyutu kontrol et
        if size <= 0:
            try:
                target_path = self.final_file_path
                if target_path and os.path.exists(target_path) and not os.path.isdir(target_path):
                    size = os.path.getsize(target_path)
                    self.total_size = size
                    self.downloaded_size = size
                else:
                    # Hedef klasörde temel isme uyan olası uzantıları kontrol et (.mp4, .mkv, .webm, .mp3)
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
        """Dosya uzantısına veya görev türüne göre kategori adını belirler."""
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
        """Kategoriye uygun görsel emoji/simge."""
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
        """Görevin eklendiği zamandan bugüne geçen göreceli süreyi verir."""
        diff = time.time() - self.created_at
        if diff < 60:
            return "Just now"
        elif diff < 3600:
            mins = int(diff // 60)
            return f"{mins} mins ago"
        elif diff < 86400:
            hours = int(diff // 3600)
            return f"{hours} hours ago"
        else:
            days = int(diff // 86400)
            return f"{days} days ago"

    def to_dict(self) -> Dict[str, Any]:
        """Görev bilgilerini JSON serileştirme için sözlüğe çevirir."""
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
        """Sözlükten DownloadTask nesnesi oluşturur."""
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

        # Eğer uygulama kapanırken aktif indirme durumundaysa, yeniden açılışta güvenli şekilde PAUSED olarak ayarla
        if status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING, DownloadStatus.MERGING, DownloadStatus.QUEUED):
            status = DownloadStatus.PAUSED

        chunks_data = data.get("chunks", [])
        chunks = [ChunkInfo.from_dict(c) for c in chunks_data] if chunks_data else []

        task = cls(
            task_id=data.get("task_id", ""),
            url=data.get("url", ""),
            destination_folder=data.get("destination_folder", ""),
            filename=data.get("filename", "download"),
            task_type=task_type,
            status=status,
            total_size=int(data.get("total_size", 0)),
            downloaded_size=int(data.get("downloaded_size", 0)),
            speed_bytes_per_sec=0.0,
            eta_seconds=None,
            is_resumable=bool(data.get("is_resumable", False)),
            chunks=chunks,
            error_message=data.get("error_message"),
            created_at=float(data.get("created_at", time.time())),
            completed_at=float(data.get("completed_at")) if data.get("completed_at") else None,
            headers=data.get("headers", {})
        )

        # Eğer dosya diskte zaten mevcut ve tam boyuttaysa durumunu COMPLETED olarak güncelle
        if task.status != DownloadStatus.COMPLETED and task.total_size > 0:
            target = task.final_file_path
            if target and os.path.exists(target) and not os.path.isdir(target):
                actual_size = os.path.getsize(target)
                if actual_size >= task.total_size:
                    task.status = DownloadStatus.COMPLETED
                    task.downloaded_size = actual_size

        return task
