"""
Download Manager - Görev Yöneticisi (task_manager.py)

Bu sınıf, tüm aktif, duraklatılmış ve tamamlanmış indirmelerin merkezi
koordinasyon noktasıdır. Arayüzden veya WebSocket sunucusundan gelen indirme
isteklerini kuyruğa alır, uygun motoru (HTTP veya yt-dlp) QThread olarak
başlatır ve sinyalleri tek noktadan GUI'ye dağıtır.
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
    """İndirme motorlarını yöneten merkezi yönetici sınıf."""

    task_added = pyqtSignal(object)           # DownloadTask nesnesi
    task_progress = pyqtSignal(dict)          # İlerleme sözlüğü
    task_chunk_progress = pyqtSignal(str, int, int, int) # task_id, chunk_id, inen, toplam
    task_status_changed = pyqtSignal(str, str)# task_id, durum
    task_finished = pyqtSignal(str, str)      # task_id, dosya_yolu
    task_error = pyqtSignal(str, str)         # task_id, hata

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

    # ==================== Görev Kalıcılığı (Persistence) ====================

    def load_tasks(self) -> None:
        """Kayıtlı görevleri tasks.json dosyasından okuyup belleğe yükler."""
        if not self.tasks_file or not os.path.exists(self.tasks_file):
            return

        try:
            with open(self.tasks_file, "r", encoding="utf-8") as f:
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
        """Kayıtlı görevleri tasks.json dosyasına atomik olarak kaydeder."""
        if not self.tasks_file:
            return

        # Çok sık disk yazımını önlemek için ilerleme güncellemelerinde debouncing uygula
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
            os.replace(tmp_file, self.tasks_file)
        except Exception as e:
            print(f"[ERROR] Failed to save tasks to {self.tasks_file}: {e}")

    # ==================== Yardımcı Metotlar ====================

    @staticmethod
    def _resolve_unique_filename(dest_dir: str, filename: str) -> str:
        """Eğer hedef klasörde aynı isimli dosya mevcutsa numaralı suföks ekler.

        Örnek: video.mp4 varsa -> video(1).mp4, o da varsa -> video(2).mp4
        Bu sayede aynı isimli dosya yeniden indirildiğinde
        anlık 'tamamlandı' hatası yaşanmaz.
        """
        target = os.path.join(dest_dir, filename)
        if not os.path.exists(target):
            return filename  # Çakışma yok, aynı ismi kullan

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
        """Yeni bir çok parçalı HTTP indirme görevi ekler ve başlatır."""
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

        # Aynı isimli dosya varsa çakışmayı önlemek için yeni isim ver (video(1).mp4 vb.)
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

    def start_http_worker(self, task: DownloadTask, num_chunks: int = 8) -> None:
        """HTTP indirme motoru QThread'ini başlatır ve sinyallerini bağlar."""
        worker = HttpChunkDownloader(task=task, num_chunks=num_chunks)

        # Sinyal bağlantıları
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
        """Yeni bir yt-dlp medya indirme görevi ekler ve başlatır."""
        task_id = str(uuid.uuid4())[:8]
        dest_dir = destination_folder or self.default_download_dir
        os.makedirs(dest_dir, exist_ok=True)

        # Windows geçersiz dosya adı karakterlerini temizle
        safe_title = re.sub(r'[\\/*?"<>|]', "", title).strip() if title else f"media_{task_id}"
        if not safe_title:
            safe_title = f"media_{task_id}"

        # Aynı isimli medya dosyası varsa çakışmayı önle
        # Medya dosyalarında uzantı genellikle yt-dlp tarafından belirlenir;
        # bu yüzden bilinen video uzantılarını da kontrol ederek çakışmayı önle
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
        """Medya başlıkları için çakışma önleme: yaygın video/ses uzantıları kontrol edilir."""
        VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v",
                      ".mp3", ".m4a", ".aac", ".opus", ".flac", ".ogg")

        # Eğer başlığın herhangi bir uzantıda dosyası varsa numara ekle
        def _title_exists(t: str) -> bool:
            # Uzantsız haliyle veya bilinen uzantılardan biriyle mevcut mu?
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
        """yt-dlp medya indirme motorunu başlatır."""
        worker = MediaDownloader(task=task, format_id=format_id, audio_only=audio_only)

        worker.progress_updated.connect(self._on_worker_progress)
        worker.status_changed.connect(self._on_worker_status_changed)
        worker.finished.connect(self._on_worker_finished)
        worker.error_occurred.connect(self._on_worker_error)

        self.workers[task.task_id] = worker
        worker.start()

    # ==================== Dahili İş Parçacığı Sinyal İşleyicileri ====================

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
        """Görevi duraklatır."""
        if task_id in self.workers:
            worker = self.workers[task_id]
            if hasattr(worker, "pause"):
                worker.pause()
        if task_id in self.tasks:
            self.tasks[task_id].status = DownloadStatus.PAUSED
            self.save_tasks(force=True)

    def resume_task(self, task_id: str) -> None:
        """Duraklatılmış görevi kaldığı yerden devam ettirir."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task.status == DownloadStatus.PAUSED:
                if task.task_type == TaskType.HTTP_FILE:
                    self.start_http_worker(task)
                elif task.task_type in (TaskType.MEDIA_VIDEO, TaskType.MEDIA_AUDIO):
                    audio_only = (task.task_type == TaskType.MEDIA_AUDIO)
                    self.start_media_worker(task, audio_only=audio_only)

    def cancel_task(self, task_id: str) -> None:
        """Görevi iptal eder ve temizler."""
        if task_id in self.workers:
            worker = self.workers[task_id]
            if hasattr(worker, "cancel"):
                worker.cancel()

    def remove_task(self, task_id: str, delete_file: bool = False) -> bool:
        """Görevi iptal eder, bellekten kaldırır ve talep edildiyse diskteki dosyaları siler."""
        if task_id not in self.tasks:
            return False

        task = self.tasks[task_id]

        # 1. Aktif çalışan iş parçacığını durdur
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

        # 2. Kalıcı silme talep edildiyse dosyaları diskten sil
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

                # Eğer uzantısız başlıkla kaydedildiyse aynı isimli medya dosyalarını kontrol et
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

        # 3. Bellekten / görev havuzundan tamamen çıkar
        self.tasks.pop(task_id, None)
        self.save_tasks(force=True)
        return True

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """Görev nesnesini döndürür."""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[DownloadTask]:
        """Tüm kayıtlı görevleri liste olarak döndürür."""
        return list(self.tasks.values())

