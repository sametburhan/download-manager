"""
Download Manager - HTTP Range Çok Parçalı İndirme Motoru (http_downloader.py)

Bu modül, HTTP 'Range' başlığını kullanarak dosyaları eşzamanlı iş parçacıklarına
(threads) böler, her parçayı bağımsız olarak indirir, duraklatma/devam ettirme
(Pause/Resume) işlemlerini yönetir ve tamamlandığında parçaları hedef dosyada birleştirir.
"""

import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal
import httpx

from app.core.models import DownloadTask, DownloadStatus, ChunkInfo, TaskType
from app.utils.file_utils import sanitize_filename, merge_chunks, cleanup_temp_files


class HttpChunkDownloader(QThread):
    """
    QThread tabanlı HTTP çok parçalı indirme motoru.
    PyQt6 arayüzünü kilitlemeden arka planda çalışır ve pyqtSignal ile anlık durum bildirir.
    """

    # Sinyaller (PyQt Signal mekanizması)
    progress_updated = pyqtSignal(dict)           # İlerleme, hız, ETA sözlüğü
    chunk_progress = pyqtSignal(int, int, int)    # chunk_id, inen_byte, toplam_byte
    status_changed = pyqtSignal(str, str)         # task_id, yeni_durum (enum string)
    finished = pyqtSignal(str, str)               # task_id, tamamlanan_dosya_yolu
    error_occurred = pyqtSignal(str, str)         # task_id, hata_mesaji

    def __init__(
        self,
        task: DownloadTask,
        num_chunks: int = 8,
        chunk_buffer_size: int = 64 * 1024,  # 64 KB okuma tamponu
        parent=None
    ):
        super().__init__(parent)
        self.task = task
        self.num_chunks = max(1, num_chunks)
        self.chunk_buffer_size = chunk_buffer_size

        # İş parçacığı kontrol bayrakları ve kilitleri
        self._is_paused = False
        self._is_cancelled = False
        self._lock = threading.Lock()

        # Hız ve ETA hesaplama değişkenleri
        self._last_calc_time = time.time()
        self._last_downloaded_bytes = 0

    # ==================== Dışarıdan Çağrılan Kontrol Metotları ====================

    def pause(self) -> None:
        """İndirmeyi güvenli bir şekilde duraklatır ve mevcut durumu kaydeder."""
        with self._lock:
            self._is_paused = True
        self.task.status = DownloadStatus.PAUSED
        self._save_meta_file()
        self.status_changed.emit(self.task.task_id, DownloadStatus.PAUSED.value)

    def cancel(self) -> None:
        """İndirmeyi iptal eder ve geçici dosyaları temizler."""
        with self._lock:
            self._is_cancelled = True
        self.task.status = DownloadStatus.CANCELLED
        self.status_changed.emit(self.task.task_id, DownloadStatus.CANCELLED.value)

    # ==================== QThread Ana Yürütme Döngüsü ====================

    def run(self) -> None:
        """QThread.start() çağrıldığında çalışan ana fonksiyon."""
        self._is_paused = False
        self._is_cancelled = False

        try:
            self.task.status = DownloadStatus.CONNECTING
            self.status_changed.emit(self.task.task_id, DownloadStatus.CONNECTING.value)

            if self.task.url.startswith("file://"):
                import urllib.request
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

                self.task.status = DownloadStatus.COMPLETED
                self.task.completed_at = time.time()
                self.status_changed.emit(self.task.task_id, DownloadStatus.COMPLETED.value)
                self.finished.emit(self.task.task_id, self.task.final_file_path)
                return

            # 1. Sunucu başlıklarını ve Range desteğini sorgula
            self._inspect_server()

            # 2. Parça (Chunk) sınırlarını hazırla veya mevcut durumdan yükle
            self._setup_chunks()

            if self._is_paused or self._is_cancelled:
                self._save_meta_file()
                return

            # 3. İndirmeyi başlat
            self.task.status = DownloadStatus.DOWNLOADING
            self.status_changed.emit(self.task.task_id, DownloadStatus.DOWNLOADING.value)

            self._download_all_chunks()

            # Duraklatıldıysa veya iptal edildiyse çık
            if self._is_paused or self._is_cancelled:
                self._save_meta_file()
                if self._is_cancelled:
                    self._cleanup_all()
                return

            # 4. Tüm parçalar bittiyse birleştirme aşamasına geç
            self.task.status = DownloadStatus.MERGING
            self.status_changed.emit(self.task.task_id, DownloadStatus.MERGING.value)

            chunk_paths = [chunk.temp_file for chunk in self.task.chunks]
            merge_chunks(chunk_paths, self.task.final_file_path)

            # Geçici dosyaları temizle
            cleanup_temp_files(chunk_paths, self.task.meta_file_path)

            # 5. Başarıyla tamamlandı
            self.task.status = DownloadStatus.COMPLETED
            self.task.completed_at = time.time()
            self.status_changed.emit(self.task.task_id, DownloadStatus.COMPLETED.value)
            self.finished.emit(self.task.task_id, self.task.final_file_path)

        except Exception as exc:
            self.task.status = DownloadStatus.FAILED
            self.task.error_message = str(exc)
            self.status_changed.emit(self.task.task_id, DownloadStatus.FAILED.value)
            self.error_occurred.emit(self.task.task_id, str(exc))

    # ==================== İç Mantık ve Ağ Operasyonları ====================

    def _inspect_server(self) -> None:
        """Sunucuya HEAD veya test GET isteği atarak boyut ve Range desteğini belirler."""
        req_headers = dict(self.task.headers)
        # Bazı sunucular HEAD isteğini engellediği için Range: bytes=0-0 ile GET deniyoruz
        req_headers["Range"] = "bytes=0-0"

        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            try:
                response = client.get(self.task.url, headers=req_headers)
            except httpx.RequestError as err:
                raise ConnectionError(f"Sunucuya bağlanılamadı: {str(err)}")

            if response.status_code == 206:
                # Sunucu 206 Partial Content döndü, yani Range destekleniyor!
                self.task.is_resumable = True
                content_range = response.headers.get("Content-Range", "")
                # Format: "bytes 0-0/1234567"
                if "/" in content_range:
                    total_str = content_range.split("/")[-1]
                    if total_str.isdigit():
                        self.task.total_size = int(total_str)
            elif response.status_code in (200, 302):
                # Sunucu 200 OK döndü. Accept-Ranges başlığını kontrol et
                accept_ranges = response.headers.get("Accept-Ranges", "").lower()
                self.task.is_resumable = (accept_ranges == "bytes")
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    self.task.total_size = int(content_length)
                else:
                    self.task.total_size = 0
            else:
                raise RuntimeError(f"Sunucu beklenmeyen HTTP yanıtı döndü: {response.status_code}")

            # Dosya adını Content-Disposition başlığından çıkarma imkanı varsa kullan
            content_disp = response.headers.get("Content-Disposition", "")
            if "filename=" in content_disp:
                extracted_name = content_disp.split("filename=")[-1].strip('"\'; ')
                if extracted_name:
                    self.task.filename = sanitize_filename(extracted_name)

    def _setup_chunks(self) -> None:
        """Mevcut bir meta dosyası varsa yükler, yoksa parçaları dinamik hesaplar."""
        # 1. Pause/Resume için kayıtlı meta dosyası var mı?
        if os.path.exists(self.task.meta_file_path):
            try:
                with open(self.task.meta_file_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    chunks_data = meta.get("chunks", [])

                if chunks_data:
                    self.task.total_size = meta.get("total_size", self.task.total_size)
                    self.task.is_resumable = meta.get("is_resumable", self.task.is_resumable)
                    self.task.chunks = [ChunkInfo.from_dict(c) for c in chunks_data]

                    # Disk üzerindeki gerçek parça boyutlarını güncelle
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
                # Meta dosyası bozulmuşsa baştan başla
                pass

        # 2. Yeni parça yapılandırması
        self.task.chunks.clear()

        # Eğer Range desteklenmiyorsa veya dosya boyutu bilinmiyorsa TEK parça çalıştır
        if not self.task.is_resumable or self.task.total_size <= 0:
            part_file = f"{self.task.final_file_path}.part0"
            chunk = ChunkInfo(
                chunk_id=0,
                start_byte=0,
                end_byte=self.task.total_size - 1 if self.task.total_size > 0 else 0,
                temp_file=part_file
            )
            self.task.chunks.append(chunk)
            self._save_meta_file()
            return

        # Range destekleniyor: Dosyayı num_chunks adedine böl
        chunk_size = self.task.total_size // self.num_chunks
        for i in range(self.num_chunks):
            start = i * chunk_size
            # Son parça dosyanın son byte'ına kadar kapsar
            end = self.task.total_size - 1 if i == self.num_chunks - 1 else (i + 1) * chunk_size - 1
            part_file = f"{self.task.final_file_path}.part{i}"

            chunk = ChunkInfo(
                chunk_id=i,
                start_byte=start,
                end_byte=end,
                temp_file=part_file
            )
            self.task.chunks.append(chunk)

        self._save_meta_file()

    def _download_all_chunks(self) -> None:
        """ThreadPoolExecutor ile tüm parçaları eşzamanlı iş parçacıklarında indirir."""
        # Henüz tamamlanmamış parçaları filtrele
        incomplete_chunks = [c for c in self.task.chunks if not c.is_completed]
        if not incomplete_chunks:
            return

        # Eşzamanlı parça indiricilerini başlat
        with ThreadPoolExecutor(max_workers=len(incomplete_chunks)) as executor:
            futures = [executor.submit(self._download_chunk_worker, chunk) for chunk in incomplete_chunks]
            for future in as_completed(futures):
                future.result()  # İstisnaları (exception) yakalamak için result() çağrılır

    def _download_chunk_worker(self, chunk: ChunkInfo) -> None:
        """Tek bir parçayı HTTP Range ile indiren işçi fonksiyon."""
        if chunk.is_completed or self._is_paused or self._is_cancelled:
            return

        # Kalan byte aralığını belirle (Resume mantığı)
        current_start = chunk.start_byte + chunk.downloaded_bytes
        if current_start > chunk.end_byte and chunk.total_bytes > 0:
            chunk.is_completed = True
            return

        req_headers = dict(self.task.headers)
        if self.task.is_resumable and chunk.total_bytes > 0:
            req_headers["Range"] = f"bytes={current_start}-{chunk.end_byte}"

        # Dosyayı varsa kaldığı yerden devam modunda ("ab"), yoksa "wb" modunda aç
        mode = "ab" if chunk.downloaded_bytes > 0 and os.path.exists(chunk.temp_file) else "wb"

        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            with client.stream("GET", self.task.url, headers=req_headers) as response:
                if response.status_code not in (200, 206):
                    raise RuntimeError(f"Parça #{chunk.chunk_id} indirilemedi. HTTP Kodu: {response.status_code}")

                with open(chunk.temp_file, mode) as f:
                    for data_block in response.iter_bytes(chunk_size=self.chunk_buffer_size):
                        # Duraklatıldı veya iptal edildiyse derhal çık
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
        """Hız, kalan süre ve ilerleme sinyallerini hesaplayıp GUI'ye fırlatır."""
        now = time.time()
        elapsed = now - self._last_calc_time

        # Her 200 ms'de bir hız ve ETA hesapla
        if elapsed >= 0.2:
            with self._lock:
                bytes_diff = self.task.downloaded_size - self._last_downloaded_bytes
                speed = bytes_diff / elapsed if elapsed > 0 else 0
                self.task.speed_bytes_per_sec = speed

                # Kalan süre (ETA) hesabı
                if speed > 0 and self.task.total_size > self.task.downloaded_size:
                    remaining_bytes = self.task.total_size - self.task.downloaded_size
                    self.task.eta_seconds = int(remaining_bytes / speed)
                else:
                    self.task.eta_seconds = None

                self._last_calc_time = now
                self._last_downloaded_bytes = self.task.downloaded_size

            # Sinyalleri yayınla
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
        """Pause/Resume durumunu meta JSON dosyasına yazar."""
        try:
            # Disk üzerindeki gerçek parça boyutlarını senkronize et
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
            with open(self.task.meta_file_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2)
        except Exception:
            pass

    def _cleanup_all(self) -> None:
        """İptal edilen görevin tüm artık dosyalarını siler."""
        chunk_paths = [c.temp_file for c in self.task.chunks]
        cleanup_temp_files(chunk_paths, self.task.meta_file_path)
        if os.path.exists(self.task.final_file_path):
            try:
                os.remove(self.task.final_file_path)
            except OSError:
                pass
