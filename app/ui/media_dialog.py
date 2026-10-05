"""
Download Manager - Modern Stitch Tasarımlı Medya Kalite Seçim ve Canlı İndirme Penceresi (media_dialog.py)

Ana uygulama penceresinden bağımsız çalışır. İki aşamalıdır:
1. Aşama: yt-dlp ile çözünürlük, kalite ve ses formatı seçimi (Stitch Desktop Modal tasarımı).
2. Aşama: 'Start Download' tıklandığında AYNI PENCEREDE IDM tarzı canlı ilerleme,
   anlık hız, kalan süre ve dosya boyutu izleme görünümü.
"""

import os
import shutil
import subprocess
from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QProgressBar, QFileDialog,
    QStackedWidget, QGridLayout, QFrame, QCheckBox, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSlot, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QPixmap, QImage

from app.core.media_downloader import MediaInfoExtractor
from app.core.models import DownloadStatus
from app.core.task_manager import TaskManager
from app.utils.icon_utils import get_app_icon, get_app_pixmap


class ThumbnailLoaderThread(QThread):
    """Küçük resmi arka planda indirip arayüze aktaran iş parçacığı."""
    loaded = pyqtSignal(bytes)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            import urllib.request
            req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = resp.read()
                self.loaded.emit(data)
        except Exception:
            pass


class QualityOptionCard(QFrame):
    """Modern Stitch tarzı interaktif kalite seçim kartı."""
    clicked = pyqtSignal(str)

    def __init__(self, key: str, icon_text: str, title: str, subtitle: str, tag: str, size: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._is_selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("qualityOptionCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        # Üst Satır: İkon Rozeti ve Radyo Gösterge Noktası
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        self.icon_badge = QLabel(icon_text)
        self.icon_badge.setFixedSize(30, 30)
        self.icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_badge.setFont(QFont("Segoe UI Emoji", 12))
        top_row.addWidget(self.icon_badge)

        top_row.addStretch()

        self.indicator_dot = QLabel()
        self.indicator_dot.setFixedSize(12, 12)
        top_row.addWidget(self.indicator_dot)

        layout.addLayout(top_row)

        # Başlık ve Alt Başlık
        self.title_lbl = QLabel(title)
        self.title_lbl.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        layout.addWidget(self.title_lbl)

        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setFont(QFont("Inter", 8))
        layout.addWidget(self.sub_lbl)

        layout.addSpacing(2)

        # Ayırıcı Çizgi
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); height: 1px; border: none;")
        layout.addWidget(div)

        # Alt Satır: Etiket ve Dosya Boyutu
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 2, 0, 0)
        self.tag_lbl = QLabel(tag)
        self.tag_lbl.setFont(QFont("Inter", 8))
        footer_row.addWidget(self.tag_lbl)

        footer_row.addStretch()

        self.size_lbl = QLabel(size)
        self.size_lbl.setFont(QFont("Inter", 8, QFont.Weight.DemiBold))
        footer_row.addWidget(self.size_lbl)

        layout.addLayout(footer_row)
        self.update_style()

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self.update_style()

    def update_info(self, tag: Optional[str] = None, size: Optional[str] = None):
        if tag is not None:
            self.tag_lbl.setText(tag)
        if size is not None:
            self.size_lbl.setText(size)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)

    def update_style(self):
        if self._is_selected:
            self.setStyleSheet("""
                QFrame#qualityOptionCard {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f2c4c, stop:1 #0a1728);
                    border: 1.5px solid #0ea5e9;
                    border-radius: 12px;
                }
            """)
            self.icon_badge.setStyleSheet("""
                background: rgba(14, 165, 233, 0.25);
                border: 1px solid rgba(14, 165, 233, 0.5);
                border-radius: 6px;
                color: #38bdf8;
            """)
            self.indicator_dot.setStyleSheet("""
                background-color: #38bdf8;
                border: none;
                border-radius: 6px;
            """)
            self.title_lbl.setStyleSheet("color: #ffffff; font-weight: bold; background: transparent;")
            self.sub_lbl.setStyleSheet("color: #94a3b8; background: transparent;")
            self.tag_lbl.setStyleSheet("color: #38bdf8; background: transparent; font-weight: 500;")
            self.size_lbl.setStyleSheet("color: #ffffff; background: transparent; font-weight: bold;")
        else:
            self.setStyleSheet("""
                QFrame#qualityOptionCard {
                    background-color: #0d1527;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                }
                QFrame#qualityOptionCard:hover {
                    background-color: #131e36;
                    border: 1px solid rgba(255, 255, 255, 0.18);
                }
            """)
            self.icon_badge.setStyleSheet("""
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                color: #cbd5e1;
            """)
            self.indicator_dot.setStyleSheet("""
                background-color: transparent;
                border: 1.5px solid #475569;
                border-radius: 6px;
            """)
            self.title_lbl.setStyleSheet("color: #e2e8f0; font-weight: 600; background: transparent;")
            self.sub_lbl.setStyleSheet("color: #64748b; background: transparent;")
            self.tag_lbl.setStyleSheet("color: #94a3b8; background: transparent;")
            self.size_lbl.setStyleSheet("color: #cbd5e1; background: transparent;")


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
        self._thumb_thread: Optional[ThumbnailLoaderThread] = None

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
        self.setWindowTitle("Media Download · Quality & Format Selection")
        self.setWindowIcon(get_app_icon())
        self.resize(680, 530)
        self.setMinimumWidth(620)
        self.setStyleSheet(self._get_styles())

        # QStackedWidget ile iki aşama: 0 -> Kalite Seçimi, 1 -> IDM İlerleme Görünümü
        self.stack = QStackedWidget(self)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.addWidget(self.stack)

        self.selection_page = self._create_selection_page(initial_title)
        self.progress_page = self._create_progress_page()

        self.stack.addWidget(self.selection_page)
        self.stack.addWidget(self.progress_page)
        self.stack.setCurrentIndex(0)

        self._update_free_space()

        if auto_start_analysis:
            self._start_analysis(self.url)

    def _get_styles(self) -> str:
        """Stitch Modern Cyber-Slate koyu tasarım stili."""
        return """
            QDialog {
                background-color: #0b1220;
                color: #f8fafc;
                font-family: "Inter", "Segoe UI", -apple-system, sans-serif;
            }
            QFrame#mediaSummaryCard {
                background-color: #0d1527;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            QFrame#idmCard {
                background-color: #0d1527;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                padding: 12px;
            }
            QLabel {
                color: #e2e8f0;
                background: transparent;
                border: none;
            }
            QFrame#idmCard QLabel {
                background: transparent;
                border: none;
            }
            QFrame#saveFolderBox {
                background-color: #0d1527;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 2px 6px;
            }
            QFrame#saveFolderBox:hover {
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QLineEdit {
                background-color: transparent;
                color: #f8fafc;
                border: none;
                padding: 6px 4px;
                font-size: 12px;
            }
            QComboBox {
                background-color: #0d1527;
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
                min-width: 140px;
            }
            QComboBox:hover {
                border-color: #38bdf8;
                background-color: #131e36;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #0d1527;
                color: #f8fafc;
                selection-background-color: #0284c7;
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 4px;
            }
            QCheckBox {
                color: #94a3b8;
                font-size: 12px;
                spacing: 8px;
                background: transparent;
            }
            QCheckBox:hover {
                color: #cbd5e1;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #3b4256;
                background-color: #0d1527;
            }
            QCheckBox::indicator:checked {
                background-color: #0284c7;
                border-color: #38bdf8;
            }
            QPushButton {
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                padding: 7px 16px;
            }
            QPushButton#primaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0ea5e9);
                color: #ffffff;
                border: 1px solid rgba(56, 189, 248, 0.4);
                border-radius: 10px;
                padding: 8px 22px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton#primaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:1 #38bdf8);
                border-color: #38bdf8;
            }
            QPushButton#primaryBtn:disabled {
                background: #1e293b;
                color: #64748b;
                border-color: rgba(255, 255, 255, 0.05);
            }
            QPushButton.secondaryBtn {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 8px 18px;
                font-size: 12px;
            }
            QPushButton.secondaryBtn:hover {
                background-color: #334155;
                color: #ffffff;
                border-color: rgba(255, 255, 255, 0.2);
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
                background-color: #070b14;
                border: 1px solid #1e293b;
                border-radius: 8px;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
            }
            QProgressBar#neonProgress::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0284c7, stop:0.5 #38bdf8, stop:1 #06b6d4);
                border-radius: 7px;
            }
        """

    # ==================== 1. AŞAMA: Format & Kalite Seçimi ====================

    def _create_selection_page(self, initial_title: str) -> QWidget:
        """Kullanıcının çözünürlük/ses seçtiği 1. aşama sayfası (Stitch UI)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(14)

        # 1. Medya Özet Kartı (Media Summary Card)
        summary_card = QFrame()
        summary_card.setObjectName("mediaSummaryCard")
        sum_layout = QHBoxLayout(summary_card)
        sum_layout.setContentsMargins(14, 12, 14, 12)
        sum_layout.setSpacing(16)

        # Sol: Küçük Resim / Video İkon Kutusu
        self.thumb_container = QFrame()
        self.thumb_container.setFixedSize(124, 76)
        self.thumb_container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0c1a30, stop:1 #050811);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }
        """)
        thumb_box_layout = QVBoxLayout(self.thumb_container)
        thumb_box_layout.setContentsMargins(4, 4, 4, 4)

        # Üst badge satırı (Platform)
        thumb_top = QHBoxLayout()
        self.platform_badge = QLabel("VIDEO")
        self.platform_badge.setStyleSheet("""
            background-color: rgba(225, 29, 72, 0.9);
            color: #ffffff;
            font-size: 9px;
            font-weight: bold;
            border-radius: 3px;
            padding: 1px 4px;
        """)
        thumb_top.addWidget(self.platform_badge)
        thumb_top.addStretch()
        thumb_box_layout.addLayout(thumb_top)

        # Merkez ikon / resim
        self.thumb_img_lbl = QLabel("▶")
        self.thumb_img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_img_lbl.setStyleSheet("color: #38bdf8; font-size: 20px; font-weight: bold; background: transparent;")
        thumb_box_layout.addWidget(self.thumb_img_lbl, 1)

        # Alt badge satırı (Süre)
        thumb_bot = QHBoxLayout()
        thumb_bot.addStretch()
        self.duration_badge = QLabel("--:--")
        self.duration_badge.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.8);
            color: #ffffff;
            font-size: 10px;
            font-weight: 600;
            border-radius: 3px;
            padding: 1px 4px;
        """)
        thumb_bot.addWidget(self.duration_badge)
        thumb_box_layout.addLayout(thumb_bot)

        sum_layout.addWidget(self.thumb_container)

        # Sağ: Video Başlığı, Durum Pili ve Link
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        self.status_pill = QLabel("● Link Verified")
        self.status_pill.setStyleSheet("""
            background: rgba(16, 185, 129, 0.12);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.25);
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 600;
        """)
        status_row.addWidget(self.status_pill)

        self.avail_lbl = QLabel("1080p MP4 Available")
        self.avail_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 500;")
        status_row.addWidget(self.avail_lbl)
        status_row.addStretch()
        info_layout.addLayout(status_row)

        self.title_label = QLabel(initial_title or "Resolving media streams...")
        self.title_label.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #f8fafc;")
        self.title_label.setWordWrap(True)
        info_layout.addWidget(self.title_label)

        display_url = self.url if len(self.url) <= 65 else f"{self.url[:62]}..."
        self.url_label = QLabel(f"🔗 {display_url}")
        self.url_label.setStyleSheet("color: #38bdf8; font-size: 11px;")
        self.url_label.setToolTip(self.url)
        info_layout.addWidget(self.url_label)

        # Analiz Durumu Çubuğu
        self.status_bar = QProgressBar()
        self.status_bar.setRange(0, 0)
        self.status_bar.setFixedHeight(4)
        self.status_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 2px;
            }
        """)
        info_layout.addWidget(self.status_bar)

        sum_layout.addLayout(info_layout, 1)
        layout.addWidget(summary_card)

        # 2. Kalite Seçim Başlığı ve Custom Formats Dropdown
        format_hdr = QHBoxLayout()
        hdr_lbl = QLabel("DOWNLOAD QUALITY & FORMAT")
        hdr_lbl.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        hdr_lbl.setStyleSheet("color: #94a3b8; letter-spacing: 0.5px;")
        format_hdr.addWidget(hdr_lbl)

        format_hdr.addStretch()

        self.format_combo = QComboBox()
        self.format_combo.setEnabled(False)
        self.format_combo.currentIndexChanged.connect(self._on_format_combo_changed)
        format_hdr.addWidget(self.format_combo)
        layout.addLayout(format_hdr)

        # 3. Üçlü Kalite Kartları (1x3 Grid)
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.card_best = QualityOptionCard(
            key="best",
            icon_text="⭐",
            title="Best Quality",
            subtitle="Auto Highest Resolution",
            tag="1080p FHD - MP4",
            size="Estimating..."
        )
        self.card_best.clicked.connect(self._select_card)
        cards_layout.addWidget(self.card_best)

        self.card_hd = QualityOptionCard(
            key="height_720",
            icon_text="🎬",
            title="Standard HD",
            subtitle="Balanced Size & Speed",
            tag="720p HD - MP4",
            size="Estimating..."
        )
        self.card_hd.clicked.connect(self._select_card)
        cards_layout.addWidget(self.card_hd)

        self.card_audio = QualityOptionCard(
            key="audio_mp3",
            icon_text="🎵",
            title="Audio Only",
            subtitle="MP3 / High Quality",
            tag="192 kbps",
            size="Estimating..."
        )
        self.card_audio.clicked.connect(self._select_card)
        cards_layout.addWidget(self.card_audio)

        layout.addLayout(cards_layout)
        self.card_best.set_selected(True)

        # 4. Kayıt Klasörü Bölümü
        save_hdr = QHBoxLayout()
        save_lbl = QLabel("SAVE FOLDER")
        save_lbl.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        save_lbl.setStyleSheet("color: #94a3b8; letter-spacing: 0.5px;")
        save_hdr.addWidget(save_lbl)

        save_hdr.addStretch()

        self.free_space_lbl = QLabel("Free Space: -- GB")
        self.free_space_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        save_hdr.addWidget(self.free_space_lbl)
        layout.addLayout(save_hdr)

        save_box = QFrame()
        save_box.setObjectName("saveFolderBox")
        save_box_layout = QHBoxLayout(save_box)
        save_box_layout.setContentsMargins(8, 2, 4, 2)
        save_box_layout.setSpacing(8)

        folder_icon = QLabel("📁")
        folder_icon.setFont(QFont("Segoe UI Emoji", 11))
        save_box_layout.addWidget(folder_icon)

        self.dest_input = QLineEdit(self.default_save_dir)
        self.dest_input.textChanged.connect(lambda: self._update_free_space())
        save_box_layout.addWidget(self.dest_input, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setProperty("class", "secondaryBtn")
        browse_btn.clicked.connect(self._browse_folder)
        save_box_layout.addWidget(browse_btn)

        layout.addWidget(save_box)

        # 5. Ek Seçenekler Satırı
        options_row = QHBoxLayout()
        self.open_folder_chk = QCheckBox("Show file in folder when download is complete")
        self.open_folder_chk.setChecked(True)
        options_row.addWidget(self.open_folder_chk)

        options_row.addStretch()

        engine_lbl = QLabel("Engine: yt-dlp + FFmpeg")
        engine_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        options_row.addWidget(engine_lbl)
        layout.addLayout(options_row)

        layout.addStretch()

        # 6. Alt Eylem Butonları (Cancel / Start Download)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("class", "secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.download_btn = QPushButton("⬇ Start Download")
        self.download_btn.setObjectName("primaryBtn")
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._on_start_download_clicked)
        btn_layout.addWidget(self.download_btn)

        layout.addLayout(btn_layout)
        return widget

    def _update_free_space(self, folder_path: Optional[str] = None) -> None:
        """Kayıt klasörünün bulunduğu diskteki boş alanı hesaplar."""
        path = folder_path or (self.dest_input.text() if hasattr(self, "dest_input") else self.default_save_dir)
        try:
            drive = os.path.splitdrive(os.path.abspath(path))[0] or path
            usage = shutil.disk_usage(drive)
            free_gb = usage.free / (1024 ** 3)
            self.free_space_lbl.setText(f"Free Space: <b style='color: #cbd5e1;'>{free_gb:.1f} GB</b>")
        except Exception:
            self.free_space_lbl.setText("Free Space: <b style='color: #cbd5e1;'>-- GB</b>")

    def _select_card(self, key: str) -> None:
        """Kullanıcı 3 ana karttan birine tıkladığında seçim durumunu günceller."""
        self.card_best.set_selected(key == "best")
        self.card_hd.set_selected(key == "height_720")
        self.card_audio.set_selected(key == "audio_mp3")

        # format_combo ile senkronize et
        for idx in range(self.format_combo.count()):
            if self.format_combo.itemData(idx) == key:
                self.format_combo.blockSignals(True)
                self.format_combo.setCurrentIndex(idx)
                self.format_combo.blockSignals(False)
                break

    def _on_format_combo_changed(self, index: int) -> None:
        """Custom Formats açılır menüsünden seçim yapıldığında kartları günceller."""
        data = self.format_combo.currentData()
        self.card_best.set_selected(data == "best")
        self.card_hd.set_selected(data == "height_720")
        self.card_audio.set_selected(data == "audio_mp3")

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

        lbl_style = "color: #94a3b8; font-weight: 500; font-size: 12px; background: transparent; border: none;"
        val_style = "color: #f1f5f9; font-weight: 600; font-size: 12px; background: transparent; border: none;"

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
        btn_row.setSpacing(10)

        self.open_folder_btn = QPushButton("📁 Open Folder")
        self.open_folder_btn.setProperty("class", "secondaryBtn")
        self.open_folder_btn.clicked.connect(self._open_folder)
        btn_row.addWidget(self.open_folder_btn)

        self.play_video_btn = QPushButton("▶ Play Video")
        self.play_video_btn.setProperty("class", "secondaryBtn")
        self.play_video_btn.setEnabled(False)
        self.play_video_btn.clicked.connect(self._play_video)
        btn_row.addWidget(self.play_video_btn)

        btn_row.addStretch()

        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setProperty("class", "secondaryBtn")
        self.pause_btn.clicked.connect(self._toggle_pause)
        btn_row.addWidget(self.pause_btn)

        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setProperty("class", "dangerBtn")
        self.cancel_btn.clicked.connect(self._cancel_download)
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)
        return widget

    # ==================== Olay ve Durum İşleyicileri ====================

    def _browse_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Destination Folder", self.dest_input.text())
        if chosen:
            self.dest_input.setText(chosen)
            self._update_free_space(chosen)

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

        # Süre ve Platform Rozeti
        dur = info.get("duration", 0)
        if dur and dur > 0:
            h, rem = divmod(int(dur), 3600)
            m, s = divmod(rem, 60)
            self.duration_badge.setText(f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}")
        else:
            self.duration_badge.setText("--:--")

        u_low = self.url.lower()
        if "youtube" in u_low or "youtu.be" in u_low:
            self.platform_badge.setText("YouTube")
        elif "vimeo" in u_low:
            self.platform_badge.setText("Vimeo")
        else:
            self.platform_badge.setText("VIDEO")

        # Küçük resim (thumbnail) yükleme
        thumb_url = info.get("thumbnail")
        if thumb_url:
            self._thumb_thread = ThumbnailLoaderThread(thumb_url, parent=self)
            self._thumb_thread.loaded.connect(self._on_thumbnail_loaded)
            self._thumb_thread.start()

        # Format seçeneklerini topla
        formats = info.get("formats", [])
        self.format_combo.blockSignals(True)
        self.format_combo.clear()

        # En üst kalite seçeneği (MP4)
        self.format_combo.addItem("🏆 Best Video + Audio (MP4 - Highest Quality)", "best")

        best_fmt = None
        hd_fmt = None
        audio_fmt = None
        added_labels = set()

        # Çözünürlük formatlarını ekle (4K ve 2K extractor içinde filtrelendi)
        for f in formats:
            if f.get("is_video"):
                h = f.get("height", 0)
                lbl = f.get("label")
                fid = f.get("format_id")
                if lbl and lbl not in added_labels:
                    added_labels.add(lbl)
                    self.format_combo.addItem(f"🎬 {lbl}", fid)
                    if not best_fmt:
                        best_fmt = f
                    if h == 720 and not hd_fmt:
                        hd_fmt = f
            else:
                if not audio_fmt:
                    audio_fmt = f

        # Ses seçeneği
        self.format_combo.addItem("🎵 Audio Only (MP3 192kbps)", "audio_mp3")

        for f in formats:
            if not f.get("is_video"):
                lbl = f.get("label")
                fid = f.get("format_id")
                if lbl and lbl not in added_labels:
                    added_labels.add(lbl)
                    self.format_combo.addItem(f"🎵 {lbl}", fid)

        self.format_combo.blockSignals(False)
        self.format_combo.setEnabled(True)
        self.download_btn.setEnabled(True)

        # Kart bilgilerini güncelle
        if best_fmt:
            h = best_fmt.get("height", 1080)
            sz = best_fmt.get("filesize") or 0
            sz_str = f"~{sz / (1024*1024):.1f} MB" if sz > 0 else "Best"
            self.card_best.update_info(f"{h}p FHD - MP4", sz_str)
            self.avail_lbl.setText(f"{h}p Available")

        if hd_fmt:
            sz = hd_fmt.get("filesize") or 0
            sz_str = f"~{sz / (1024*1024):.1f} MB" if sz > 0 else "HD"
            self.card_hd.update_info("720p HD - MP4", sz_str)
        else:
            self.card_hd.update_info("720p HD - MP4", "Auto")

        if audio_fmt:
            sz = audio_fmt.get("filesize") or 0
            sz_str = f"~{sz / (1024*1024):.1f} MB" if sz > 0 else "Audio"
            self.card_audio.update_info("MP3 / 192 kbps", sz_str)

    def _on_thumbnail_loaded(self, data: bytes) -> None:
        """İndirilen küçük resmi arayüze ölçekleyip yerleştirir."""
        try:
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                scaled = pixmap.scaled(
                    self.thumb_container.width(),
                    self.thumb_container.height(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.thumb_img_lbl.setPixmap(scaled)
        except Exception:
            pass

    def _on_metadata_error(self, err_msg: str) -> None:
        """Analiz hatası durumunda kullanıcıyı bilgilendirir veya fallback dener."""
        if not self._fallback_tried and self.page_url and self.page_url != self.url:
            self._fallback_tried = True
            self.title_label.setText("Trying page URL extractor fallback...")
            self._start_analysis(self.page_url)
            return

        self.status_bar.setVisible(False)
        self.status_pill.setText("❌ Extraction Failed")
        self.status_pill.setStyleSheet("""
            background: rgba(239, 68, 68, 0.12);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.25);
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 600;
        """)
        self.title_label.setText(f"❌ Error: {err_msg}")
        self.title_label.setStyleSheet("color: #f87171;")

    def get_data(self) -> Dict[str, Any]:
        """Seçilen indirme yapılandırmasını döndürür."""
        selected_data = self.format_combo.currentData()
        is_audio = (selected_data == "audio_mp3")
        format_id = None if selected_data in ("best", "audio_mp3") else selected_data

        title = self.extracted_info.get("title") if self.extracted_info else self.final_title

        return {
            "url": self.url,
            "title": title,
            "destination": self.dest_input.text().strip(),
            "format_id": format_id,
            "audio_only": is_audio,
            "headers": self.headers
        }

    def _on_start_download_clicked(self) -> None:
        """'Start Download' tıklandığında indirmeyi başlatır ve 2. aşama IDM görünümüne geçer."""
        data = self.get_data()
        if not self.task_manager:
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

        pct = float(data.get("percent", 0.0))
        speed_str = data.get("speed_str", "--")
        eta_str = data.get("eta_str", "--:--")
        downloaded = data.get("downloaded_bytes", 0)
        total = data.get("total_bytes", 0)

        self.progress_bar.setValue(int(pct))
        self.setWindowTitle(f"[{int(pct)}%] {self.final_title}")

        self.status_val.setText(f"Downloading ( {pct:.1f}% )...")
        self.speed_val.setText(speed_str)
        self.eta_val.setText(eta_str)
        self.downloaded_val.setText(f"{self._format_bytes(downloaded)} ( {pct:.1f}% )")

        if total > 0:
            self.size_val.setText(self._format_bytes(total))

    @pyqtSlot(str, str)
    def _on_status_changed(self, task_id: str, new_status: str) -> None:
        """Durum değişimlerini yansıtır."""
        if task_id != self.current_task_id:
            return

        if new_status == DownloadStatus.PAUSED.value:
            self.status_val.setText("⏸ Paused")
            self.status_val.setStyleSheet("color: #f59e0b; font-weight: bold; font-size: 12px;")
            self.pause_btn.setText("▶ Resume")
        elif new_status == DownloadStatus.DOWNLOADING.value:
            self.status_val.setText("⬇ Downloading...")
            self.status_val.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")
            self.pause_btn.setText("⏸ Pause")
        elif new_status == DownloadStatus.CANCELLED.value:
            self.status_val.setText("✕ Cancelled")
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

        # Eğer kullanıcı "Show file in folder" kutusunu işaretlediyse dosyayı klasörde göster
        if hasattr(self, "open_folder_chk") and self.open_folder_chk.isChecked() and final_path and os.path.exists(final_path):
            try:
                subprocess.Popen(f'explorer /select,"{os.path.normpath(final_path)}"')
            except Exception:
                pass

    @pyqtSlot(str, str)
    def _on_error(self, task_id: str, err_msg: str) -> None:
        """Hata durumunu yansıtır."""
        if task_id != self.current_task_id:
            return

        self.status_val.setText(f"❌ Error: {err_msg[:60]}...")
        self.status_val.setStyleSheet("color: #f87171; font-weight: bold; font-size: 12px;")
        self.status_val.setToolTip(err_msg)
        self.pause_btn.setEnabled(False)

    def _toggle_pause(self) -> None:
        """Duraklat / Devam Et eylemi."""
        if not self.task_manager or not self.current_task_id:
            return
        task = self.task_manager.get_task(self.current_task_id)
        if not task:
            return

        if task.status == DownloadStatus.DOWNLOADING:
            self.task_manager.pause_task(self.current_task_id)
        elif task.status == DownloadStatus.PAUSED:
            self.task_manager.resume_task(self.current_task_id)

    def _cancel_download(self) -> None:
        """İndirmeyi iptal eder veya pencereyi kapatır."""
        if self.is_completed:
            self.accept()
            return

        if self.task_manager and self.current_task_id:
            self.task_manager.cancel_task(self.current_task_id)
        self.reject()

    def _open_folder(self) -> None:
        """Dosyanın indirildiği hedef klasörü açar."""
        target = self.final_downloaded_path if (self.final_downloaded_path and os.path.exists(self.final_downloaded_path)) else self.final_dest
        if os.path.isfile(target):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(target)}"')
        else:
            os.makedirs(target, exist_ok=True)
            subprocess.Popen(f'explorer "{os.path.normpath(target)}"')

    def _play_video(self) -> None:
        """İndirilen medyayı sistemin varsayılan oynatıcısında açar."""
        if self.final_downloaded_path and os.path.exists(self.final_downloaded_path):
            os.startfile(os.path.normpath(self.final_downloaded_path))

    @staticmethod
    def _format_bytes(bytes_count: int) -> str:
        """Bayt miktarını insan tarafından okunabilir formata dönüştürür."""
        if bytes_count <= 0:
            return "0 B"
        elif bytes_count < 1024 * 1024:
            return f"{bytes_count / 1024:.1f} KB"
        elif bytes_count < 1024 * 1024 * 1024:
            return f"{bytes_count / (1024 * 1024):.2f} MB"
        else:
            return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"
