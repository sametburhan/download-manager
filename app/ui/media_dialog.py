"""
Download Manager - Bağımsız Medya Kalite Seçim ve IDM Tarzı Canlı İlerleme Penceresi (media_dialog.py)

Ana uygulama penceresinden bağımsız çalışır. İki aşamalıdır:
1. Aşama: yt-dlp ile çözünürlük, kalite ve ses formatı seçimi.
2. Aşama: 'Start Download' tıklandığında AYNI PENCEREDE IDM tarzı canlı ilerleme,
   anlık hız, kalan süre ve dosya boyutu izleme görünümü.
"""

import os
import subprocess
from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QProgressBar, QFileDialog,
    QStackedWidget, QGridLayout, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont

from app.core.media_downloader import MediaInfoExtractor
from app.core.models import DownloadStatus
from app.core.task_manager import TaskManager
from app.utils.icon_utils import get_app_icon, get_app_pixmap


class MediaQualityDialog(QDialog):
    """yt-dlp tabanlı medya format seçimi ve bağımsız IDM tarzı canlı indirme penceresi."""

    def __init__(
        self,
        url: str,
        initial_title: str = "",
        default_save_dir: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        page_url: Optional[str] = None,
        task_manager: Optional[TaskManager] = None,
        parent=None,
        auto_start_analysis: bool = True
    ):
        super().__init__(parent)
        self.url = url
        self.headers = headers or {}
        self.page_url = page_url or url
        self.default_save_dir = default_save_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        self.task_manager = task_manager
        self.extracted_info: Optional[Dict[str, Any]] = None
        self._fallback_tried = False
        self.extractor: Optional[MediaInfoExtractor] = None

        self.current_task_id: Optional[str] = None
        self.final_title: str = initial_title or "Media Download"
        self.final_dest: str = self.default_save_dir
        self.final_downloaded_path: str = ""
        self.is_completed: bool = False

        # Bağımsız üst düzey pencere (kendi görev çubuğu girdisi ve küçültme butonu olan)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setWindowTitle("Media Download - Quality Selection")
        self.setWindowIcon(get_app_icon())
        self.resize(600, 390)
        self.setMinimumWidth(560)
        self.setStyleSheet(self._get_styles())

        # QStackedWidget ile iki aşama: 0 -> Kalite Seçimi, 1 -> IDM İlerleme Görünümü
        self.stack = QStackedWidget(self)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.addWidget(self.stack)

        self.selection_page = self._create_selection_page(initial_title)
        self.progress_page = self._create_progress_page()

        self.stack.addWidget(self.selection_page)
        self.stack.addWidget(self.progress_page)
        self.stack.setCurrentIndex(0)

        if auto_start_analysis:
            self._start_analysis(self.url)

    def _get_styles(self) -> str:
        """Koyu Fluent tasarım stili."""
        return """
            QDialog {
                background-color: #0b0f19;
                color: #f8fafc;
            }
            QFrame#idmCard {
                background-color: #131b2e;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 12px;
            }
            QLabel {
                color: #e2e8f0;
            }
            QLineEdit, QComboBox {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 7px 10px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e293b;
                color: #f8fafc;
                selection-background-color: #0078d4;
                border: 1px solid #334155;
            }
            QPushButton {
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 7px 16px;
            }
            QPushButton#primaryBtn {
                background-color: #0078d4;
                color: #ffffff;
                border: none;
            }
            QPushButton#primaryBtn:hover {
                background-color: #1084d8;
            }
            QPushButton#primaryBtn:disabled {
                background-color: #334155;
                color: #64748b;
            }
            QPushButton.secondaryBtn {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
            }
            QPushButton.secondaryBtn:hover {
                background-color: #334155;
                color: #ffffff;
                border-color: #475569;
            }
            QPushButton.dangerBtn {
                background-color: #381b1b;
                color: #ff6b6b;
                border: 1px solid #5a2020;
            }
            QPushButton.dangerBtn:hover {
                background-color: #5a2020;
                color: #ffffff;
            }
            QProgressBar#neonProgress {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
            }
            QProgressBar#neonProgress::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0284c7, stop:0.5 #6366f1, stop:1 #a855f7);
                border-radius: 7px;
            }
        """

    # ==================== 1. AŞAMA: Format & Kalite Seçimi ====================

    def _create_selection_page(self, initial_title: str) -> QWidget:
        """Kullanıcının çözünürlük/ses seçtiği 1. aşama sayfası."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        # Başlık Satırı
        title_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_app_pixmap(22))
        title_row.addWidget(icon_lbl)

        title_lbl = QLabel("🎬 Download Video & Media")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        layout.addLayout(title_row)

        # URL Satırı
        display_url = self.url if len(self.url) <= 70 else f"{self.url[:67]}..."
        self.url_label = QLabel(f"🔗 URL: {display_url}")
        self.url_label.setStyleSheet("color: #00b4d8; font-size: 11px;")
        self.url_label.setToolTip(self.url)
        layout.addWidget(self.url_label)

        # Medya Başlığı
        self.title_label = QLabel(initial_title or "Resolving media streams...")
        self.title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #f1f5f9;")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        # Analiz Durumu Çubuğu
        self.status_bar = QProgressBar()
        self.status_bar.setRange(0, 0)
        self.status_bar.setFixedHeight(6)
        self.status_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #00b4d8;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.status_bar)

        # Format ve Kalite Seçimi
        layout.addWidget(QLabel("Select Download Quality & Format:", styleSheet="font-weight: 500; font-size: 12px; color: #cbd5e1;"))
        self.format_combo = QComboBox()
        self.format_combo.setEnabled(False)
        layout.addWidget(self.format_combo)

        # Kayıt Yeri
        layout.addWidget(QLabel("Save Folder:", styleSheet="font-weight: 500; font-size: 12px; color: #cbd5e1;"))
        dest_layout = QHBoxLayout()
        self.dest_input = QLineEdit(self.default_save_dir)
        dest_layout.addWidget(self.dest_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.setProperty("class", "secondaryBtn")
        browse_btn.clicked.connect(self._browse_folder)
        dest_layout.addWidget(browse_btn)
        layout.addLayout(dest_layout)

        layout.addStretch()

        # Butonlar
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("class", "secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.download_btn = QPushButton("⬇️ Start Download")
        self.download_btn.setObjectName("primaryBtn")
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._on_start_download_clicked)
        btn_layout.addWidget(self.download_btn)

        layout.addLayout(btn_layout)
        return widget

    # ==================== 2. AŞAMA: IDM Tarzı Canlı İlerleme Görünümü ====================

    def _create_progress_page(self) -> QWidget:
        """IDM indirme penceresi düzeninde canlı ilerleme sayfası."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        # Başlık ve Medya Adı
        header_layout = QHBoxLayout()
        self.prog_icon = QLabel("🎬")
        self.prog_icon.setFont(QFont("Segoe UI Emoji", 16))
        header_layout.addWidget(self.prog_icon)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        self.prog_title_label = QLabel("Media Download")
        self.prog_title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.prog_title_label.setStyleSheet("color: #ffffff;")
        self.prog_title_label.setWordWrap(True)
        text_box.addWidget(self.prog_title_label)

        self.prog_quality_badge = QLabel("[Video Stream]")
        self.prog_quality_badge.setStyleSheet("color: #00b4d8; font-size: 11px; font-weight: 600;")
        text_box.addWidget(self.prog_quality_badge)

        header_layout.addLayout(text_box)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # IDM Tarzı Bilgi Kartı (Grid)
        idm_card = QFrame()
        idm_card.setObjectName("idmCard")
        grid = QGridLayout(idm_card)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(7)

        lbl_style = "color: #94a3b8; font-weight: 500; font-size: 12px;"
        val_style = "color: #f1f5f9; font-weight: 600; font-size: 12px;"

        row = 0
        # Status
        grid.addWidget(QLabel("Status:", styleSheet=lbl_style), row, 0)
        self.status_val = QLabel("Connecting & fetching stream...")
        self.status_val.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")
        grid.addWidget(self.status_val, row, 1)

        row += 1
        # File Size
        grid.addWidget(QLabel("File size:", styleSheet=lbl_style), row, 0)
        self.size_val = QLabel("Estimating...")
        self.size_val.setStyleSheet(val_style)
        grid.addWidget(self.size_val, row, 1)

        row += 1
        # Downloaded
        grid.addWidget(QLabel("Downloaded:", styleSheet=lbl_style), row, 0)
        self.downloaded_val = QLabel("0 B ( 0.0% )")
        self.downloaded_val.setStyleSheet(val_style)
        grid.addWidget(self.downloaded_val, row, 1)

        row += 1
        # Transfer rate (Speed)
        grid.addWidget(QLabel("Transfer rate:", styleSheet=lbl_style), row, 0)
        self.speed_val = QLabel("0 B/s")
        self.speed_val.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")
        grid.addWidget(self.speed_val, row, 1)

        row += 1
        # Time left
        grid.addWidget(QLabel("Time left:", styleSheet=lbl_style), row, 0)
        self.eta_val = QLabel("--:--")
        self.eta_val.setStyleSheet(val_style)
        grid.addWidget(self.eta_val, row, 1)

        row += 1
        # Save Path
        grid.addWidget(QLabel("Save folder:", styleSheet=lbl_style), row, 0)
        self.path_val = QLabel(self.default_save_dir)
        self.path_val.setStyleSheet("color: #64748b; font-size: 11px;")
        self.path_val.setWordWrap(True)
        grid.addWidget(self.path_val, row, 1)

        row += 1
        # Resume capability
        grid.addWidget(QLabel("Resume capability:", styleSheet=lbl_style), row, 0)
        self.resume_val = QLabel("Yes")
        self.resume_val.setStyleSheet("color: #22c55e; font-weight: bold; font-size: 12px;")
        grid.addWidget(self.resume_val, row, 1)

        layout.addWidget(idm_card)

        # Büyük İlerleme Çubuğu
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("neonProgress")
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        # Butonlar Satırı
        btn_row = QHBoxLayout()

        # Sol Butonlar (Klasörü Aç / Videoyu Oynat)
        self.open_folder_btn = QPushButton("📁 Open Folder")
        self.open_folder_btn.setProperty("class", "secondaryBtn")
        self.open_folder_btn.clicked.connect(self._open_folder)
        btn_row.addWidget(self.open_folder_btn)

        self.play_video_btn = QPushButton("▶️ Play Video")
        self.play_video_btn.setProperty("class", "secondaryBtn")
        self.play_video_btn.setEnabled(False)
        self.play_video_btn.clicked.connect(self._play_video)
        btn_row.addWidget(self.play_video_btn)

        btn_row.addStretch()

        # Sağ Butonlar (Duraklat / İptal)
        self.pause_btn = QPushButton("⏸️ Pause")
        self.pause_btn.setProperty("class", "secondaryBtn")
        self.pause_btn.clicked.connect(self._toggle_pause_resume)
        btn_row.addWidget(self.pause_btn)

        self.cancel_btn = QPushButton("❌ Cancel")
        self.cancel_btn.setProperty("class", "dangerBtn")
        self.cancel_btn.clicked.connect(self._cancel_or_close)
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)
        return widget

    # ==================== Olay ve Aksiyon Mantıkları ====================

    def _on_start_download_clicked(self) -> None:
        """'Start Download' tıklandığında görevi başlatır ve 2. aşama ilerleme görünümüne geçer."""
        data = self.get_data()

        if self.task_manager is None:
            # TaskManager verilmediyse standart QDialog davranışı
            self.accept()
            return

        # 1. Görevi TaskManager üzerinden başlat
        task_id = self.task_manager.add_media_download(
            url=data["url"],
            title=data["title"],
            destination_folder=data["destination"],
            format_id=data.get("format_id"),
            audio_only=data.get("audio_only", False),
            headers=data.get("headers")
        )
        self.current_task_id = task_id
        self.final_title = data["title"] or "Media Stream"
        self.final_dest = data["destination"]

        # 2. İlerleme sayfasındaki etiketleri hazırla
        quality_label = self.format_combo.currentText()
        is_audio = data.get("audio_only", False)
        self.prog_icon.setText("🎵" if is_audio else "🎬")
        self.prog_title_label.setText(self.final_title)
        self.prog_quality_badge.setText(quality_label)
        self.path_val.setText(self.final_dest)
        self.path_val.setToolTip(self.final_dest)

        self.setWindowTitle(f"[0%] {self.final_title}")

        # 3. TaskManager sinyallerini bağla
        self.task_manager.task_progress.connect(self._on_progress_updated)
        self.task_manager.task_status_changed.connect(self._on_status_changed)
        self.task_manager.task_finished.connect(self._on_finished)
        self.task_manager.task_error.connect(self._on_error)

        # 4. İkinci sayfaya (IDM İlerleme Görünümü) geçiş yap
        self.stack.setCurrentIndex(1)

    @pyqtSlot(dict)
    def _on_progress_updated(self, data: dict) -> None:
        """Canlı indirme ilerlemesini arayüze yansıtır."""
        if data.get("task_id") != self.current_task_id:
            return

        pct = data.get("percent", 0.0)
        self.progress_bar.setValue(int(pct))
        self.setWindowTitle(f"[{int(pct)}%] {self.final_title}")

        down_bytes = data.get("downloaded_bytes", 0)
        tot_bytes = data.get("total_bytes", 0)
        speed_str = data.get("speed_str", "0 B/s")
        eta_str = data.get("eta_str", "--:--")

        self.status_val.setText(f"Receiving data ({pct:.1f}%)...")
        self.status_val.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")

        if tot_bytes > 0:
            self.size_val.setText(self._format_bytes(tot_bytes))
            self.downloaded_val.setText(f"{self._format_bytes(down_bytes)} ( {pct:.1f}% )")
        else:
            self.downloaded_val.setText(self._format_bytes(down_bytes))

        self.speed_val.setText(speed_str)
        self.eta_val.setText(f"{eta_str} left" if eta_str and eta_str != "--:--" else "--:--")

    @pyqtSlot(str, str)
    def _on_status_changed(self, task_id: str, status_str: str) -> None:
        """Durum değişimlerini günceller."""
        if task_id != self.current_task_id:
            return

        status_upper = status_str.upper()
        if status_upper == DownloadStatus.MERGING.value:
            self.status_val.setText("Merging video & audio streams (FFmpeg)...")
            self.status_val.setStyleSheet("color: #c084fc; font-weight: bold; font-size: 12px;")
            self.pause_btn.setEnabled(False)
        elif status_upper == DownloadStatus.PAUSED.value:
            self.status_val.setText("Paused")
            self.status_val.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 12px;")
            self.pause_btn.setText("▶️ Resume")
            self.pause_btn.setEnabled(True)
        elif status_upper == DownloadStatus.DOWNLOADING.value:
            self.status_val.setText("Downloading...")
            self.status_val.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")
            self.pause_btn.setText("⏸️ Pause")
            self.pause_btn.setEnabled(True)
        elif status_upper == DownloadStatus.FAILED.value:
            self.status_val.setText("Download Failed")
            self.status_val.setStyleSheet("color: #f87171; font-weight: bold; font-size: 12px;")
            self.pause_btn.setEnabled(False)

    @pyqtSlot(str, str)
    def _on_finished(self, task_id: str, final_path: str) -> None:
        """İndirme tamamlandığında görseli bitiş durumuna getirir."""
        if task_id != self.current_task_id:
            return

        self.is_completed = True
        self.final_downloaded_path = final_path

        self.progress_bar.setValue(100)
        self.setWindowTitle(f"[100%] Complete - {self.final_title}")
        self.status_val.setText("✅ Completed!")
        self.status_val.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 12px;")

        if final_path and os.path.exists(final_path):
            real_size = os.path.getsize(final_path)
            self.size_val.setText(self._format_bytes(real_size))
            self.downloaded_val.setText(f"{self._format_bytes(real_size)} ( 100% )")

        self.speed_val.setText("0 B/s")
        self.eta_val.setText("0s")

        self.play_video_btn.setEnabled(True)
        self.pause_btn.setVisible(False)
        self.cancel_btn.setText("✓ Done")
        self.cancel_btn.setProperty("class", "secondaryBtn")
        self.cancel_btn.setStyleSheet("background-color: #107c41; color: #ffffff; border: none;")

    @pyqtSlot(str, str)
    def _on_error(self, task_id: str, err_msg: str) -> None:
        """Hata durumunu yansıtır."""
        if task_id != self.current_task_id:
            return

        self.status_val.setText(f"❌ Error: {err_msg[:60]}...")
        self.status_val.setStyleSheet("color: #f87171; font-weight: bold; font-size: 12px;")
        self.status_val.setToolTip(err_msg)
        self.pause_btn.setEnabled(False)

    def _toggle_pause_resume(self) -> None:
        """Duraklat / Devam Et butonuna tıklandığında çalışır."""
        if not self.current_task_id or not self.task_manager:
            return
        task = self.task_manager.get_task(self.current_task_id)
        if not task:
            return

        if task.status == DownloadStatus.DOWNLOADING:
            self.task_manager.pause_task(self.current_task_id)
            self.pause_btn.setText("▶️ Resume")
            self.status_val.setText("Paused")
            self.status_val.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 12px;")
        elif task.status in (DownloadStatus.PAUSED, DownloadStatus.FAILED):
            self.task_manager.resume_task(self.current_task_id)
            self.pause_btn.setText("⏸️ Pause")
            self.status_val.setText("Resuming download...")
            self.status_val.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")

    def _open_folder(self) -> None:
        """İndirilenler klasörünü açar."""
        path = self.final_downloaded_path or os.path.join(self.final_dest, self.final_title)
        folder = self.final_dest if os.path.isdir(self.final_dest) else os.path.dirname(path)

        if os.path.exists(path) and not os.path.isdir(path):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        elif os.path.exists(folder):
            subprocess.Popen(f'explorer "{os.path.normpath(folder)}"')

    def _play_video(self) -> None:
        """İndirilen videoyu varsayılan medya oynatıcıda açar."""
        path = self.final_downloaded_path
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except Exception:
                subprocess.Popen(f'explorer "{os.path.normpath(path)}"')

    def closeEvent(self, event) -> None:
        """Pencere kapatılırken arkaplan extractor thread'ini güvenle sonlandırır."""
        if hasattr(self, "extractor") and self.extractor is not None:
            if self.extractor.isRunning():
                try:
                    self.extractor.terminate()
                    self.extractor.wait(500)
                except Exception:
                    pass
        super().closeEvent(event)

    def _cancel_or_close(self) -> None:
        """Kapat veya iptal et."""
        if not self.is_completed and self.current_task_id and self.task_manager:
            task = self.task_manager.get_task(self.current_task_id)
            if task and task.status in (DownloadStatus.DOWNLOADING, DownloadStatus.QUEUED, DownloadStatus.MERGING):
                self.task_manager.cancel_task(self.current_task_id)
        self.close()

    def _format_bytes(self, num_bytes: int) -> str:
        """Byte miktarını insan tarafından okunabilir birime çevirir."""
        if num_bytes <= 0:
            return "0 B"
        elif num_bytes < 1024:
            return f"{num_bytes} B"
        elif num_bytes < 1024 * 1024:
            return f"{num_bytes / 1024:.2f} KB"
        elif num_bytes < 1024 * 1024 * 1024:
            return f"{num_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"

    # ==================== Analiz ve Metadata Çekme ====================

    def _start_analysis(self, target_url: str) -> None:
        """Arka planda yt-dlp ile medya bilgilerini çekmeye başlar."""
        self.status_bar.setVisible(True)
        self.extractor = MediaInfoExtractor(target_url, headers=self.headers)
        self.extractor.metadata_ready.connect(self._on_metadata_ready)
        self.extractor.error_occurred.connect(self._on_metadata_error)
        self.extractor.start()

    def _on_metadata_ready(self, info: Dict[str, Any]) -> None:
        """Meta veriler alındığında arayüzü günceller."""
        self.extracted_info = info
        self.status_bar.setVisible(False)
        self.title_label.setText(info.get("title", "Video Stream"))

        self.format_combo.clear()

        # En üst kalite seçeneği
        self.format_combo.addItem("🏆 Best Video + Audio (Auto Highest Resolution)", "best")

        formats = info.get("formats", [])
        added_labels = set()

        # Çözünürlük formatlarını ekle
        for f in formats:
            if f.get("is_video"):
                lbl = f.get("label")
                fid = f.get("format_id")
                if lbl and lbl not in added_labels:
                    added_labels.add(lbl)
                    self.format_combo.addItem(f"🎬 {lbl}", fid)

        # Ses seçeneklerini ekle
        self.format_combo.addItem("🎵 Audio Only (MP3 192kbps)", "audio_mp3")

        for f in formats:
            if not f.get("is_video"):
                lbl = f.get("label")
                fid = f.get("format_id")
                if lbl and lbl not in added_labels:
                    added_labels.add(lbl)
                    self.format_combo.addItem(f"🎵 {lbl}", fid)

        self.format_combo.setEnabled(True)
        self.download_btn.setEnabled(True)

    def _on_metadata_error(self, err_msg: str) -> None:
        """Analiz hatası durumunda kullanıcıyı bilgilendirir veya fallback dener."""
        if not self._fallback_tried and self.page_url and self.page_url != self.url:
            self._fallback_tried = True
            self.title_label.setText("Trying page URL extractor fallback...")
            self._start_analysis(self.page_url)
            return

        self.status_bar.setVisible(False)
        self.title_label.setText(f"❌ Error: {err_msg}")
        self.title_label.setStyleSheet("color: #f87171;")

    def _browse_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Destination Folder", self.dest_input.text())
        if chosen:
            self.dest_input.setText(chosen)

    def get_data(self) -> Dict[str, Any]:
        """Seçilen indirme yapılandırmasını döndürür."""
        selected_data = self.format_combo.currentData()
        is_audio = (selected_data == "audio_mp3")
        format_id = None if selected_data in ("best", "audio_mp3") else selected_data

        title = self.extracted_info.get("title") if self.extracted_info else "media"

        return {
            "url": self.url,
            "title": title,
            "destination": self.dest_input.text().strip(),
            "format_id": format_id,
            "audio_only": is_audio,
            "headers": self.headers
        }
