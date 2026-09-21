"""
Download Manager - İndirme Görev Kartı Bileşeni (progress_card.py)

Bu bileşen, her bir aktif veya tamamlanmış indirme görevi için IDM tarzı
çok parçalı ilerleme çubuğu, anlık hız, kalan süre ve eylem butonlarını
barındıran modern bir PyQt6 kart widget'ıdır.
"""

import os
import subprocess
from typing import Dict, Any, List
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from app.core.models import DownloadTask, DownloadStatus, TaskType


class DownloadCardWidget(QFrame):
    """Her bir indirme görevinin görsel temsilini sağlayan kart widget'ı."""

    # Dış dünyaya fırlatılan kullanıcı eylem sinyalleri
    pause_requested = pyqtSignal(str)          # task_id
    resume_requested = pyqtSignal(str)         # task_id
    cancel_requested = pyqtSignal(str)         # task_id

    def __init__(self, task: DownloadTask, parent=None):
        super().__init__(parent)
        self.task = task
        self.setObjectName("cardFrame")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._chunk_bars: List[QProgressBar] = []

        self._init_ui()
        self.update_from_task()

    def _init_ui(self) -> None:
        """Kart arayüzünü oluşturur."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # 1. Üst Satır: Dosya Türü Rozeti + Dosya Adı + Durum Rozeti
        top_layout = QHBoxLayout()

        # Uzantı rozeti (örn: [ZIP], [MP4])
        ext = os.path.splitext(self.task.filename)[1].replace(".", "").upper()
        if not ext:
            if self.task.task_type == TaskType.MEDIA_VIDEO:
                ext = "MP4"
            elif self.task.task_type == TaskType.MEDIA_AUDIO:
                ext = "MP3"
            else:
                ext = "FILE"
        self.badge_label = QLabel(ext[:5])
        self.badge_label.setStyleSheet("""
            background-color: #0078d4;
            color: #ffffff;
            font-size: 10px;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 4px;
        """)
        top_layout.addWidget(self.badge_label)

        # Dosya adı
        self.name_label = QLabel(self.task.filename)
        self.name_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.name_label.setStyleSheet("color: #ffffff;")
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top_layout.addWidget(self.name_label)

        # Durum rozeti
        self.status_label = QLabel(self.task.status.value)
        self.status_label.setStyleSheet("""
            background-color: #2b2b2b;
            color: #a0a0a0;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        """)
        top_layout.addWidget(self.status_label)

        layout.addLayout(top_layout)

        # 2. Ana İlerleme Çubuğu
        self.main_progress = QProgressBar()
        self.main_progress.setRange(0, 100)
        self.main_progress.setValue(int(self.task.progress_percent))
        layout.addWidget(self.main_progress)

        # 3. IDM Tarzı Mini Parça (Chunk) Görselleştirici Konteyneri
        self.chunks_container = QWidget()
        self.chunks_layout = QHBoxLayout(self.chunks_container)
        self.chunks_layout.setContentsMargins(0, 0, 0, 0)
        self.chunks_layout.setSpacing(3)
        layout.addWidget(self.chunks_container)

        # Parça çubuklarını başlat
        self._init_chunk_indicators()

        # 4. Alt Satır: Hız, Boyut, ETA ve Kontrol Butonları
        bottom_layout = QHBoxLayout()

        # İstatistikler etiketi
        self.stats_label = QLabel("0 KB / 0 KB | 0 KB/s | Remaining: --:--")
        self.stats_label.setStyleSheet("color: #a0a0a0; font-size: 12px;")
        bottom_layout.addWidget(self.stats_label)

        bottom_layout.addStretch()

        # Duraklat / Devam Et Butonu
        self.pause_resume_btn = QPushButton("⏸️ Pause")
        self.pause_resume_btn.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        self.pause_resume_btn.clicked.connect(self._on_pause_resume_clicked)
        bottom_layout.addWidget(self.pause_resume_btn)

        # Klasörü Aç Butonu
        self.open_folder_btn = QPushButton("📁 Open Folder")
        self.open_folder_btn.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        self.open_folder_btn.clicked.connect(self._open_folder)
        bottom_layout.addWidget(self.open_folder_btn)

        # İptal / Sil Butonu
        self.cancel_btn = QPushButton("❌")
        self.cancel_btn.setToolTip("Cancel / Delete Task")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #381b1b;
                color: #ff6b6b;
                border: 1px solid #5a2020;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #5a2020;
            }
        """)
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.task.task_id))
        bottom_layout.addWidget(self.cancel_btn)

        layout.addLayout(bottom_layout)

    def _init_chunk_indicators(self) -> None:
        """IDM benzeri parça segmentlerini oluşturur."""
        # Eski çubukları temizle
        for bar in self._chunk_bars:
            bar.deleteLater()
        self._chunk_bars.clear()

        # Görevin kaç parçası varsa o kadar mini bar oluştur (varsayılan: 8)
        chunk_count = len(self.task.chunks) if self.task.chunks else 8
        for i in range(chunk_count):
            cbar = QProgressBar()
            cbar.setRange(0, 100)
            cbar.setValue(0)
            cbar.setTextVisible(False)
            cbar.setFixedHeight(5)
            cbar.setStyleSheet("""
                QProgressBar {
                    background-color: #2e2e2e;
                    border: none;
                    border-radius: 2px;
                }
                QProgressBar::chunk {
                    background-color: #00b4d8;
                    border-radius: 2px;
                }
            """)
            self.chunks_layout.addWidget(cbar)
            self._chunk_bars.append(cbar)

    def update_from_task(self) -> None:
        """Kart üzerindeki verileri mevcut görev durumuna göre yeniler."""
        self.update_task_info(self.task)

    def update_task_info(self, task: DownloadTask) -> None:
        """Görev nesnesi güncellendiğinde kart üzerindeki etiket ve istatistikleri yeniler."""
        self.task = task
        ext = os.path.splitext(self.task.filename)[1].replace(".", "").upper()
        if not ext:
            if self.task.task_type == TaskType.MEDIA_VIDEO:
                ext = "MP4"
            elif self.task.task_type == TaskType.MEDIA_AUDIO:
                ext = "MP3"
            else:
                ext = "FILE"
        self.badge_label.setText(ext[:5])
        self.name_label.setText(self.task.filename)
        self.main_progress.setValue(int(self.task.progress_percent))
        self.update_status(self.task.status.value)
        self._update_stats_text()

    def update_progress(self, data: Dict[str, Any]) -> None:
        """İndirme motorundan gelen anlık ilerleme paketini uygular."""
        percent = int(data.get("percent", 0))
        self.main_progress.setValue(percent)

        down_bytes = data.get("downloaded_bytes", 0)
        tot_bytes = data.get("total_bytes", 0)
        speed_str = data.get("speed_str", "0 B/s")
        eta_str = data.get("eta_str", "--:--")

        down_mb = down_bytes / (1024 * 1024)
        tot_mb = tot_bytes / (1024 * 1024) if tot_bytes > 0 else 0

        self.stats_label.setText(
            f"{down_mb:.1f} MB / {tot_mb:.1f} MB  •  ⚡ {speed_str}  •  ⏳ Remaining: {eta_str}"
        )

    def update_chunk_progress(self, chunk_id: int, downloaded: int, total: int) -> None:
        """Tek bir parçanın mini ilerleme göstergesini günceller."""
        if 0 <= chunk_id < len(self._chunk_bars):
            if total > 0:
                pct = int((downloaded / total) * 100)
                self._chunk_bars[chunk_id].setValue(min(100, max(0, pct)))

    def update_status(self, status_str: str) -> None:
        """Durum rozetini ve buton metinlerini günceller."""
        self.status_label.setText(status_str)

        if status_str == DownloadStatus.DOWNLOADING.value:
            self.status_label.setStyleSheet("background-color: #0e3a1f; color: #38ef7d; padding: 3px 8px; border-radius: 4px; font-weight: bold;")
            self.pause_resume_btn.setText("⏸️ Pause")
            self.pause_resume_btn.setEnabled(True)
        elif status_str == DownloadStatus.PAUSED.value:
            self.status_label.setStyleSheet("background-color: #3d2c00; color: #fbbf24; padding: 3px 8px; border-radius: 4px; font-weight: bold;")
            self.pause_resume_btn.setText("▶️ Resume")
            self.pause_resume_btn.setEnabled(True)
        elif status_str == DownloadStatus.MERGING.value:
            self.status_label.setStyleSheet("background-color: #2b1a3d; color: #c084fc; padding: 3px 8px; border-radius: 4px; font-weight: bold;")
            self.pause_resume_btn.setText("⏳ Merging...")
            self.pause_resume_btn.setEnabled(False)
        elif status_str == DownloadStatus.COMPLETED.value:
            self.status_label.setStyleSheet("background-color: #133b24; color: #4ade80; padding: 3px 8px; border-radius: 4px; font-weight: bold;")
            self.main_progress.setValue(100)
            self.pause_resume_btn.setText("✅ Completed")
            self.pause_resume_btn.setEnabled(False)
            for bar in self._chunk_bars:
                bar.setValue(100)
        elif status_str == DownloadStatus.FAILED.value:
            self.status_label.setStyleSheet("background-color: #3b1313; color: #f87171; padding: 3px 8px; border-radius: 4px; font-weight: bold;")
            self.pause_resume_btn.setText("🔄 Retry")
            self.pause_resume_btn.setEnabled(True)

    def _update_stats_text(self) -> None:
        down_mb = self.task.downloaded_size / (1024 * 1024)
        tot_mb = self.task.total_size / (1024 * 1024) if self.task.total_size > 0 else 0
        self.stats_label.setText(
            f"{down_mb:.1f} MB / {tot_mb:.1f} MB  •  ⚡ {self.task.formatted_speed}  •  ⏳ Remaining: {self.task.formatted_eta}"
        )

    def _on_pause_resume_clicked(self) -> None:
        """Duraklat veya Devam Et butonuna tıklandığında çalışır."""
        if self.task.status == DownloadStatus.DOWNLOADING:
            self.pause_requested.emit(self.task.task_id)
        elif self.task.status in (DownloadStatus.PAUSED, DownloadStatus.FAILED):
            self.resume_requested.emit(self.task.task_id)

    def _open_folder(self) -> None:
        """Dosyanın bulunduğu klasörü Windows Gezgini'nde açar ve dosyayı seçer."""
        final_path = os.path.normpath(self.task.final_file_path)
        folder = os.path.normpath(self.task.destination_folder)

        if os.path.exists(final_path):
            # Dosyayı seçili olarak aç
            subprocess.Popen(f'explorer /select,"{final_path}"')
        elif os.path.exists(folder):
            # Henüz dosya inmediyse doğrudan klasörü aç
            subprocess.Popen(f'explorer "{folder}"')
