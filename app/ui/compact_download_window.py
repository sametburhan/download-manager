"""
Download Manager - Kompakt Yüzen İndirme ve Canlı İlerleme Penceresi (compact_download_window.py)

Kullanıcının paylaştığı modern Windows 11 referans tasarımına birebir uygun olarak
tasarlanmıştır. İki aşamalı çalışır:
1. Aşama: URL, kayıt yeri, dosya adı ve henüz indirmeden sunucudan çekilen dosya boyutu sorgusu.
2. Aşama: 'Download' tıklandığında AYNI PENCEREDE canlı ilerleme, anlık hız ve parçalı indirme görünümü.
Pencere kapatılsa veya simge durumuna küçültülse dahi indirme arka planda kesintisiz devam eder.
"""

import os
import subprocess
import threading
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QProgressBar, QFileDialog,
    QApplication, QFrame, QSizePolicy, QTabWidget,
    QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QIcon

import httpx

from app.core.models import DownloadTask, DownloadStatus, TaskType
from app.core.task_manager import TaskManager
from app.utils.file_utils import sanitize_filename
from app.utils.icon_utils import get_app_icon, get_app_pixmap


def is_video_stream_url(url: str) -> bool:
    """URL'nin bir video akışı (YouTube, HLS m3u8 vb.) olup olmadığını belirler."""
    lower = url.lower().strip()
    if any(domain in lower for domain in ("youtube.com", "youtu.be", "vimeo.com", "dailymotion.com")):
        return True
    if any(ext in lower for ext in (".m3u8", ".mpd", "master.m3u8", "playlist.m3u8")):
        return True
    return False


class CompactDownloadWindow(QDialog):
    """
    IDM tarzı modern kompakt indirme ve ilerleme penceresi.
    """

    def __init__(
        self,
        task_manager: TaskManager,
        initial_url: str = "",
        initial_filename: str = "",
        default_save_dir: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.task_manager = task_manager
        self.default_save_dir = default_save_dir or self.task_manager.default_download_dir

        self.current_task_id: Optional[str] = None
        self.total_size_bytes: int = 0
        self.is_progress_mode = False
        self.prog_filename: str = initial_filename
        self._is_resumable: bool = False
        self._chunk_bars: List[QProgressBar] = []
        self._segment_boxes: List[QLabel] = []
        self._is_part_info_expanded: bool = True

        # Pencere Özellikleri (Windows 11 Başlıklı, akrilik koyu tasarım)
        self.setWindowTitle("Add download")
        self.setWindowIcon(get_app_icon())
        self.setMinimumWidth(560)
        self.resize(560, 240)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(self._get_style_sheet())

        self._init_ui(initial_url, initial_filename)
        self._connect_task_manager()

        if initial_url:
            self._query_file_size_async(initial_url)
        else:
            self._check_clipboard()

    def _init_ui(self, initial_url: str, initial_filename: str) -> None:
        """Referans görseldeki koyu akrilik modern düzeni kurar."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 16, 18, 16)
        self.main_layout.setSpacing(12)

        # ------------------- 1. SORGULAMA GÖVDESİ (QUERY MODE) -------------------
        self.query_widget = QWidget()
        query_layout = QHBoxLayout(self.query_widget)
        query_layout.setContentsMargins(0, 2, 0, 2)
        query_layout.setSpacing(14)

        # Sol Giriş Alanları (URL, Klasör, Dosya Adı)
        inputs_layout = QVBoxLayout()
        inputs_layout.setSpacing(8)

        # A) URL Satırı + Pano Butonu
        url_container = QFrame()
        url_container.setObjectName("inputContainer")
        url_layout = QHBoxLayout(url_container)
        url_layout.setContentsMargins(8, 0, 8, 0)

        self.url_input = QLineEdit(initial_url)
        self.url_input.setPlaceholderText("https://...")
        self.url_input.setStyleSheet("border: none; background: transparent;")
        self.url_input.textChanged.connect(self._on_url_changed)
        url_layout.addWidget(self.url_input)

        self.btn_paste = QPushButton("📋")
        self.btn_paste.setToolTip("Paste from clipboard")
        self.btn_paste.setFixedSize(24, 24)
        self.btn_paste.setStyleSheet("background: transparent; border: none; font-size: 13px;")
        self.btn_paste.clicked.connect(self._paste_from_clipboard)
        url_layout.addWidget(self.btn_paste)

        inputs_layout.addWidget(url_container)

        # B) Kayıt Klasörü Satırı + Gözat İkonu
        dest_container = QFrame()
        dest_container.setObjectName("inputContainer")
        dest_layout = QHBoxLayout(dest_container)
        dest_layout.setContentsMargins(8, 0, 8, 0)

        self.dest_input = QLineEdit(self.default_save_dir)
        self.dest_input.setStyleSheet("border: none; background: transparent;")
        dest_layout.addWidget(self.dest_input)

        self.btn_browse = QPushButton("📁")
        self.btn_browse.setToolTip("Select folder")
        self.btn_browse.setFixedSize(24, 24)
        self.btn_browse.setStyleSheet("background: transparent; border: none; font-size: 13px;")
        self.btn_browse.clicked.connect(self._browse_folder)
        dest_layout.addWidget(self.btn_browse)

        inputs_layout.addWidget(dest_container)

        # C) Dosya Adı Satırı
        file_container = QFrame()
        file_container.setObjectName("inputContainer")
        file_layout = QHBoxLayout(file_container)
        file_layout.setContentsMargins(8, 0, 8, 0)

        if not initial_filename and initial_url:
            clean = initial_url.split("?")[0].split("#")[0]
            name = clean.split("/")[-1]
            if name and "." in name:
                try:
                    name = urllib.parse.unquote(name)
                except Exception:
                    pass
                initial_filename = name

        self.filename_input = QLineEdit(initial_filename)
        self.filename_input.setPlaceholderText("filename.ext")
        self.filename_input.setStyleSheet("border: none; background: transparent;")
        file_layout.addWidget(self.filename_input)

        inputs_layout.addWidget(file_container)
        query_layout.addLayout(inputs_layout, stretch=3)

        # Sağ Bilgi Paneli (Modern Dosya Boyutu Kartı - Kotayı net gösterir)
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(0, 0, 0, 0)
        right_panel.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.size_card = QFrame()
        self.size_card.setObjectName("sizeCard")
        size_card_layout = QVBoxLayout(self.size_card)
        size_card_layout.setContentsMargins(14, 12, 14, 12)
        size_card_layout.setSpacing(6)

        # Başlık ve Yenile Butonu
        header_box = QHBoxLayout()
        header_box.setSpacing(4)
        self.size_icon = QLabel("📦")
        self.size_icon.setStyleSheet("font-size: 13px; background: transparent;")
        header_box.addWidget(self.size_icon)

        size_title = QLabel("DOSYA BOYUTU")
        size_title.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; background: transparent;")
        header_box.addWidget(size_title)
        header_box.addStretch()

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setToolTip("Boyutu yeniden sorgula")
        self.btn_refresh.setFixedSize(22, 22)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                color: #94a3b8;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #232838;
                color: #ffffff;
            }
        """)
        self.btn_refresh.clicked.connect(lambda: self._query_file_size_async(self.url_input.text()))
        header_box.addWidget(self.btn_refresh)
        size_card_layout.addLayout(header_box)

        # Büyük ve Net Boyut Göstergesi
        self.size_label = QLabel("Sorgulanıyor...")
        self.size_label.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.size_label.setStyleSheet("color: #38bdf8; background: transparent;")
        size_card_layout.addWidget(self.size_label)

        # Durum ve Kota Açıklaması
        self.check_icon = QLabel("Sunucuya bağlanılıyor...")
        self.check_icon.setStyleSheet("color: #64748b; font-size: 11px; background: transparent;")
        size_card_layout.addWidget(self.check_icon)

        right_panel.addWidget(self.size_card)
        query_layout.addLayout(right_panel, stretch=2)

        self.main_layout.addWidget(self.query_widget)

        # ------------------- 3. İLERLEME GÖVDESİ (PROGRESS MODE - IDM STYLE) -------------------
        self.progress_widget = QWidget()
        self.progress_widget.setVisible(False)
        prog_layout = QVBoxLayout(self.progress_widget)
        prog_layout.setContentsMargins(0, 2, 0, 2)
        prog_layout.setSpacing(10)

        # Sekmeli Yapı: [ ⓘ Info ] [ ⚙ Settings ]
        self.prog_tab_widget = QTabWidget()
        self.prog_tab_widget.setObjectName("detailTabs")

        # ----------------- TAB 1: INFO -----------------
        info_tab = QWidget()
        info_layout = QVBoxLayout(info_tab)
        info_layout.setContentsMargins(10, 12, 10, 10)
        info_layout.setSpacing(10)

        # A) Metadata Kartı (Referanstaki IDM Grid Yapısı)
        self.meta_card = QFrame()
        self.meta_card.setObjectName("metadataCard")
        meta_grid = QGridLayout(self.meta_card)
        meta_grid.setContentsMargins(14, 12, 14, 12)
        meta_grid.setHorizontalSpacing(18)
        meta_grid.setVerticalSpacing(7)

        lbl_style = "color: #94a3b8; font-weight: 500; font-size: 12px; background: transparent;"
        val_style = "color: #f8fafc; font-weight: 600; font-size: 12px; background: transparent;"

        # Row 0: Name
        meta_grid.addWidget(QLabel("Name:", styleSheet=lbl_style), 0, 0)
        self.name_val = QLabel("")
        self.name_val.setStyleSheet(val_style)
        self.name_val.setWordWrap(True)
        meta_grid.addWidget(self.name_val, 0, 1)
        self.prog_filename_lbl = self.name_val  # Geriye dönük uyumluluk

        # Row 1: Status
        meta_grid.addWidget(QLabel("Status:", styleSheet=lbl_style), 1, 0)
        self.status_val = QLabel("Starting...")
        self.status_val.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 12px; background: transparent;")
        meta_grid.addWidget(self.status_val, 1, 1)

        # Row 2: Size
        meta_grid.addWidget(QLabel("Size:", styleSheet=lbl_style), 2, 0)
        self.size_val = QLabel("--")
        self.size_val.setStyleSheet(val_style)
        meta_grid.addWidget(self.size_val, 2, 1)

        # Row 3: Downloaded
        meta_grid.addWidget(QLabel("Downloaded:", styleSheet=lbl_style), 3, 0)
        self.downloaded_val = QLabel("0 B ( 0 % )")
        self.downloaded_val.setStyleSheet(val_style)
        meta_grid.addWidget(self.downloaded_val, 3, 1)

        # Row 4: Speed
        meta_grid.addWidget(QLabel("Speed:", styleSheet=lbl_style), 4, 0)
        self.speed_val = QLabel("0 B/s")
        self.speed_val.setStyleSheet(val_style)
        meta_grid.addWidget(self.speed_val, 4, 1)

        # Row 5: Time Left
        meta_grid.addWidget(QLabel("Time Left:", styleSheet=lbl_style), 5, 0)
        self.eta_val = QLabel("--:--")
        self.eta_val.setStyleSheet(val_style)
        meta_grid.addWidget(self.eta_val, 5, 1)

        # Row 6: Resume Support
        meta_grid.addWidget(QLabel("Resume Support:", styleSheet=lbl_style), 6, 0)
        self.resume_val = QLabel("Checking...")
        self.resume_val.setStyleSheet("color: #22c55e; font-weight: bold; font-size: 12px; background: transparent;")
        meta_grid.addWidget(self.resume_val, 6, 1)

        info_layout.addWidget(self.meta_card)

        # B) Ana Neon İlerleme Çubuğu
        self.prog_bar = QProgressBar()
        self.prog_bar.setObjectName("neonProgressBar")
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setFixedHeight(12)
        info_layout.addWidget(self.prog_bar)

        # C) Parça Geçiş Butonu ve Aksiyonlar
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0, 2, 0, 2)

        self.toggle_part_btn = QPushButton("˄ Parts Info")
        self.toggle_part_btn.setObjectName("togglePartBtn")
        self.toggle_part_btn.setFlat(True)
        self.toggle_part_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_part_btn.clicked.connect(self._toggle_part_info)
        ctrl_layout.addWidget(self.toggle_part_btn)

        ctrl_layout.addStretch()

        self.btn_pause_resume = QPushButton("⏸ Pause")
        self.btn_pause_resume.setObjectName("secondaryBtn")
        self.btn_pause_resume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause_resume.clicked.connect(self._toggle_pause_resume)
        ctrl_layout.addWidget(self.btn_pause_resume)

        self.btn_open_file = QPushButton("📁 Open Folder")
        self.btn_open_file.setObjectName("secondaryBtn")
        self.btn_open_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_file.clicked.connect(self._open_target_folder)
        ctrl_layout.addWidget(self.btn_open_file)

        self.btn_hide_to_tray = QPushButton("✕ Close")
        self.btn_hide_to_tray.setObjectName("closeBtn")
        self.btn_hide_to_tray.setToolTip("Pencereyi gizle (İndirme arka planda kesintisiz devam eder)")
        self.btn_hide_to_tray.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hide_to_tray.clicked.connect(self.hide)
        ctrl_layout.addWidget(self.btn_hide_to_tray)

        info_layout.addLayout(ctrl_layout)

        # D) 8 Parçalı Bağlantı ve İndirme Durumu Paneli (Katlanabilir)
        self.part_container = QWidget()
        part_layout = QVBoxLayout(self.part_container)
        part_layout.setContentsMargins(0, 2, 0, 0)
        part_layout.setSpacing(8)

        # Canlı 8-Bağlantı Segment Çubuğu
        segments_layout = QHBoxLayout()
        segments_layout.setSpacing(4)
        for _ in range(8):
            box = QLabel()
            box.setFixedHeight(12)
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            box.setStyleSheet("background-color: #1e293b; border-radius: 2px;")
            self._segment_boxes.append(box)
            segments_layout.addWidget(box)
        part_layout.addLayout(segments_layout)

        # Canlı Parça Tablosu (# | Status | Downloaded | Total)
        self.part_table = QTableWidget(8, 4)
        self.part_table.setObjectName("partTable")
        self.part_table.setHorizontalHeaderLabels(["#", "Status", "Downloaded", "Total"])
        self.part_table.verticalHeader().setVisible(False)
        self.part_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.part_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.part_table.setShowGrid(False)
        self.part_table.setFixedHeight(150)
        self.part_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.part_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.part_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.part_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self._init_chunk_views(8)
        part_layout.addWidget(self.part_table)

        info_layout.addWidget(self.part_container)
        self.prog_tab_widget.addTab(info_tab, "ⓘ Info")

        # ----------------- TAB 2: SETTINGS -----------------
        settings_tab = QWidget()
        set_layout = QVBoxLayout(settings_tab)
        set_layout.setContentsMargins(14, 14, 14, 14)
        set_layout.setSpacing(12)

        # İndirme Klasörü
        folder_group = QVBoxLayout()
        folder_lbl = QLabel("Destination Download Folder:")
        folder_lbl.setStyleSheet(lbl_style)
        folder_group.addWidget(folder_lbl)

        folder_row = QHBoxLayout()
        self.folder_path_display = QLineEdit(self.default_save_dir)
        self.folder_path_display.setReadOnly(True)
        self.folder_path_display.setStyleSheet("background-color: #171b26; border: 1px solid #232b3e; border-radius: 6px; padding: 6px; color: #f1f5f9;")
        folder_row.addWidget(self.folder_path_display)

        btn_browse_set = QPushButton("📁")
        btn_browse_set.setToolTip("Klasör Değiştir")
        btn_browse_set.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse_set.setStyleSheet("background-color: #1e2538; border: 1px solid #28334a; border-radius: 6px; padding: 6px 12px; color: #fff;")
        btn_browse_set.clicked.connect(self._browse_folder_settings)
        folder_row.addWidget(btn_browse_set)
        folder_group.addLayout(folder_row)
        set_layout.addLayout(folder_group)

        # Bağlantı Sayısı
        conn_group = QHBoxLayout()
        conn_lbl = QLabel("Connection (Segment) Count:")
        conn_lbl.setStyleSheet(lbl_style)
        conn_group.addWidget(conn_lbl)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 32)
        self.conn_spin.setValue(8)
        self.conn_spin.setFixedWidth(90)
        self.conn_spin.setFixedHeight(30)
        self.conn_spin.setStyleSheet("background-color: #171b26; border: 1px solid #232b3e; border-radius: 6px; padding: 4px 8px; color: #f1f5f9;")
        conn_group.addWidget(self.conn_spin)
        conn_group.addStretch()
        set_layout.addLayout(conn_group)

        # Hız Sınırlayıcı (Speed Limiter - IDM özelliği)
        speed_group = QHBoxLayout()
        self.chk_speed_limit = QCheckBox("Speed Limiter (KB/s):")
        self.chk_speed_limit.setStyleSheet(lbl_style)
        speed_group.addWidget(self.chk_speed_limit)

        self.spin_speed_limit = QSpinBox()
        self.spin_speed_limit.setRange(10, 1000000)
        self.spin_speed_limit.setValue(2600)
        self.spin_speed_limit.setFixedWidth(110)
        self.spin_speed_limit.setFixedHeight(30)
        self.spin_speed_limit.setEnabled(False)
        self.spin_speed_limit.setStyleSheet("background-color: #171b26; border: 1px solid #232b3e; border-radius: 6px; padding: 4px 8px; color: #f1f5f9;")
        self.chk_speed_limit.toggled.connect(self.spin_speed_limit.setEnabled)
        speed_group.addWidget(self.spin_speed_limit)
        speed_group.addStretch()
        set_layout.addLayout(speed_group)

        # Tamamlanma Seçenekleri
        self.chk_autoclose = QCheckBox("Automatically close this window when download completes")
        self.chk_autoclose.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        set_layout.addWidget(self.chk_autoclose)

        self.chk_open_file = QCheckBox("Open file when download completes")
        self.chk_open_file.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        set_layout.addWidget(self.chk_open_file)

        set_layout.addStretch()
        self.prog_tab_widget.addTab(settings_tab, "⚙ Settings")

        prog_layout.addWidget(self.prog_tab_widget)
        self.main_layout.addWidget(self.progress_widget)

        # ------------------- 4. ALT EYLEM BUTONLARI (QUERY MODE) -------------------
        self.buttons_widget = QWidget()
        btn_layout = QHBoxLayout(self.buttons_widget)
        btn_layout.setContentsMargins(0, 6, 0, 0)
        btn_layout.setSpacing(10)

        # 'Add' Butonu
        self.btn_add = QPushButton("Add")
        self.btn_add.setObjectName("secondaryBtn")
        self.btn_add.setFixedWidth(80)
        self.btn_add.clicked.connect(self._on_add_clicked)
        btn_layout.addWidget(self.btn_add)

        # 'Download' Butonu (Referanstaki Mor-Mavi Neon Gradyan)
        self.btn_download = QPushButton("Download")
        self.btn_download.setObjectName("downloadBtn")
        self.btn_download.setFixedWidth(130)
        self.btn_download.clicked.connect(self._on_download_clicked)
        btn_layout.addWidget(self.btn_download)

        btn_layout.addStretch()

        # 'Cancel' Butonu
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_cancel)

        self.main_layout.addWidget(self.buttons_widget)

    def _init_chunk_bars(self, count: int = 8) -> None:
        """Geriye dönük uyumluluk için korunur."""
        pass

    def _init_chunk_views(self, count: int = 8) -> None:
        """IDM tarzı 8 parça segment kutularını ve tablo satırlarını sıfırlar."""
        for box in self._segment_boxes:
            box.setStyleSheet("background-color: #1e293b; border-radius: 2px;")

        self.part_table.setRowCount(count)
        for i in range(count):
            item_num = QTableWidgetItem(str(i + 1))
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_status = QTableWidgetItem("Idle")
            item_down = QTableWidgetItem("--")
            item_down.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_tot = QTableWidgetItem("--")
            item_tot.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.part_table.setItem(i, 0, item_num)
            self.part_table.setItem(i, 1, item_status)
            self.part_table.setItem(i, 2, item_down)
            self.part_table.setItem(i, 3, item_tot)

    def _toggle_part_info(self) -> None:
        """Parça panelini açar veya kapatır."""
        self._is_part_info_expanded = not self._is_part_info_expanded
        self.part_container.setVisible(self._is_part_info_expanded)
        self.toggle_part_btn.setText("˄ Parts Info" if self._is_part_info_expanded else "˅ Parts Info")
        if self._is_part_info_expanded:
            self.resize(560, 520)
        else:
            self.adjustSize()

    def _browse_folder_settings(self) -> None:
        """Ayarlar sekmesinden klasör seçimi."""
        chosen = QFileDialog.getExistingDirectory(self, "Select Destination Folder", self.folder_path_display.text())
        if chosen:
            self.folder_path_display.setText(chosen)
            self.dest_input.setText(chosen)
            if self.current_task_id:
                task = self.task_manager.get_task(self.current_task_id)
                if task:
                    task.destination_folder = chosen

    def _connect_task_manager(self) -> None:
        """TaskManager sinyallerini dinler."""
        self.task_manager.task_progress.connect(self._on_task_progress)
        self.task_manager.task_chunk_progress.connect(self._on_task_chunk_progress)
        self.task_manager.task_status_changed.connect(self._on_task_status_changed)
        self.task_manager.task_finished.connect(self._on_task_finished)

    # ==================== Eylemler ve Ağ Sorgusu ====================

    def _on_url_changed(self, url: str) -> None:
        """URL değiştiğinde dosya adını tahmin eder ve boyutu sorgular."""
        url = url.strip()
        if not self.filename_input.text() or self.filename_input.text() == "file.bin":
            clean = url.split("?")[0].split("#")[0]
            name = clean.split("/")[-1]
            if name and "." in name:
                self.filename_input.setText(name)

        if url.startswith(("http://", "https://", "file://")):
            # Debounce ile 400ms sonra sorgula
            QTimer.singleShot(400, lambda: self._query_file_size_async(url))

    def _query_file_size_async(self, url: str) -> None:
        """Sunucuya HEAD/GET atarak veya yerel dosya ise diskten okuyarak dosya boyutunu belirler."""
        if not url:
            self._update_size_ui(0, status_msg="URL giriniz")
            return

        url = url.strip()

        # 1. Yerel Dosya (file:// veya doğrudan Windows yolu C:\...)
        if url.startswith("file://") or (len(url) > 2 and url[1] == ":" and ("\\" in url or "/" in url)):
            local_path = url
            if url.startswith("file://"):
                local_path = urllib.request.url2pathname(url.replace("file://", ""))
                if local_path.startswith("/") and len(local_path) > 2 and local_path[2] == ":":
                    local_path = local_path[1:]
                local_path = urllib.parse.unquote(local_path)

            if os.path.exists(local_path):
                try:
                    sz = os.path.getsize(local_path)
                    self.size_icon.setText("📦")
                    self._update_size_ui(sz, status_msg="✓ Yerel dosya hazır")
                    return
                except Exception:
                    pass
            self.size_icon.setText("📦")
            self._update_size_ui(-1, status_msg="Yerel dosya bulunamadı")
            return

        if not url.startswith(("http://", "https://", "ftp://")):
            self._update_size_ui(0, status_msg="Geçersiz URL")
            return

        if is_video_stream_url(url):
            self.size_icon.setText("🎬")
            self.size_label.setText("Video Akışı")
            self.size_label.setStyleSheet("color: #38bdf8; font-size: 13px; font-weight: bold; background: transparent;")
            self.check_icon.setText("🎬 Çevrimiçi video algılandı")
            self.check_icon.setStyleSheet("color: #38bdf8; font-size: 11px; background: transparent;")
            return

        self.size_icon.setText("📦")
        self.size_label.setText("Sorgulanıyor...")
        self.size_label.setStyleSheet("color: #cbd5e1; font-size: 13px; font-weight: bold; background: transparent;")
        self.check_icon.setText("Sunucuya bağlanılıyor...")
        self.check_icon.setStyleSheet("color: #64748b; font-size: 11px; background: transparent;")

        def worker():
            size = 0
            is_resumable = False
            status_text = ""
            browser_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Encoding": "identity",
            }

            try:
                with httpx.Client(follow_redirects=True, timeout=8.0) as client:
                    # 1. Deneme: HEAD isteği ile boyut ve Range kontrolü
                    try:
                        resp = client.head(url, headers=browser_headers)
                        if resp.status_code == 200:
                            if "Content-Length" in resp.headers and resp.headers["Content-Length"].isdigit():
                                size = int(resp.headers["Content-Length"])
                                is_resumable = resp.headers.get("Accept-Ranges", "").lower() == "bytes"
                                status_text = "Kaldığı yerden devam edebilir" if is_resumable else "İndirmeye hazır"
                        elif resp.status_code == 404:
                            QTimer.singleShot(0, lambda: self._update_size_ui(-1, status_msg="404 Bulunamadı"))
                            return
                    except Exception:
                        pass

                    # 2. Deneme: HEAD başarısızsa veya boyut vermediyse GET Stream ile Range: bytes=0-0
                    if size <= 0:
                        range_headers = dict(browser_headers)
                        range_headers["Range"] = "bytes=0-0"
                        try:
                            with client.stream("GET", url, headers=range_headers) as get_resp:
                                if get_resp.status_code == 206:
                                    cr = get_resp.headers.get("Content-Range", "")
                                    if "/" in cr:
                                        tot_str = cr.split("/")[-1].strip()
                                        if tot_str.isdigit():
                                            size = int(tot_str)
                                            is_resumable = True
                                            status_text = "Kaldığı yerden devam edebilir"
                                elif get_resp.status_code == 200:
                                    if "Content-Length" in get_resp.headers and get_resp.headers["Content-Length"].isdigit():
                                        size = int(get_resp.headers["Content-Length"])
                                        is_resumable = get_resp.headers.get("Accept-Ranges", "").lower() == "bytes"
                                        status_text = "Kaldığı yerden devam edebilir" if is_resumable else "İndirmeye hazır"
                                elif get_resp.status_code == 404:
                                    QTimer.singleShot(0, lambda: self._update_size_ui(-1, status_msg="404 Bulunamadı"))
                                    return
                        except Exception:
                            pass

                    # UI iş parçacığında güncelle
                    final_size = size
                    final_resumable = is_resumable
                    final_status = status_text
                    QTimer.singleShot(0, lambda: self._update_size_ui(final_size, is_resumable=final_resumable, status_msg=final_status))
            except Exception:
                QTimer.singleShot(0, lambda: self._update_size_ui(-1, status_msg="Bağlantı zaman aşımı"))

        threading.Thread(target=worker, daemon=True).start()

    def _update_size_ui(self, size_bytes: int, is_resumable: bool = False, status_msg: str = "") -> None:
        self.total_size_bytes = max(0, size_bytes)

        if size_bytes > 0:
            if size_bytes < 1024 * 1024:
                formatted = f"{size_bytes / 1024:.2f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                formatted = f"{size_bytes / (1024 * 1024):.2f} MB"
            else:
                formatted = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

            self.size_label.setText(formatted)
            self.size_label.setStyleSheet("color: #22c55e; font-size: 15px; font-weight: bold; background: transparent;")
            msg = status_msg or ("✓ Kaldığı yerden devam edebilir" if is_resumable else "✓ İndirmeye hazır")
            self.check_icon.setText(msg)
            self.check_icon.setStyleSheet("color: #22c55e; font-size: 11px; background: transparent;")

        elif size_bytes == 0:
            self.size_label.setText("Bilinmiyor")
            self.size_label.setStyleSheet("color: #f59e0b; font-size: 13px; font-weight: bold; background: transparent;")
            self.check_icon.setText(status_msg or "Dinamik akış / kota bilgisi yok")
            self.check_icon.setStyleSheet("color: #94a3b8; font-size: 10px; background: transparent;")

        else:  # Negative (error / 404 / 403)
            self.size_label.setText("Ulaşılamadı")
            self.size_label.setStyleSheet("color: #ef4444; font-size: 13px; font-weight: bold; background: transparent;")
            self.check_icon.setText(status_msg or "Adresi kontrol edin")
            self.check_icon.setStyleSheet("color: #ef4444; font-size: 10px; background: transparent;")

    def _paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text().strip()
        if text:
            self.url_input.setText(text)

    def _check_clipboard(self) -> None:
        text = QApplication.clipboard().text().strip()
        if text.startswith(("http://", "https://")):
            self.url_input.setText(text)

    def _browse_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Destination Folder", self.dest_input.text())
        if chosen:
            self.dest_input.setText(chosen)

    # ==================== Başlatma ve İlerlemeye Dönüşüm ====================

    def _on_add_clicked(self) -> None:
        """Kuyruğa sessizce ekler ve pencereyi kapatır."""
        url = self.url_input.text().strip()
        filename = sanitize_filename(self.filename_input.text().strip())
        dest = self.dest_input.text().strip()

        if url:
            if is_video_stream_url(url):
                self.task_manager.add_media_download(
                    url=url,
                    title=filename or None,
                    destination_folder=dest,
                    auto_start=True
                )
            else:
                self.task_manager.add_http_download(
                    url=url,
                    filename=filename,
                    destination_folder=dest,
                    auto_start=True
                )
            self.accept()

    def _on_download_clicked(self) -> None:
        """Download butonuna basıldığında AYNI PENCEREDE indirmeyi başlatır ve ilerleme moduna geçer."""
        url = self.url_input.text().strip()
        filename = sanitize_filename(self.filename_input.text().strip())
        dest = self.dest_input.text().strip()

        if not url:
            return

        if is_video_stream_url(url):
            from app.ui.media_dialog import MediaQualityDialog
            dlg = MediaQualityDialog(
                url=url,
                initial_title=filename,
                default_save_dir=dest,
                task_manager=self.task_manager,
                parent=None
            )
            dlg.show()
            dlg.activateWindow()
            dlg.raise_()
            self.accept()
            return

        # 1. Görevi TaskManager'a başlat
        self.current_task_id = self.task_manager.add_http_download(
            url=url,
            filename=filename,
            destination_folder=dest,
            num_chunks=8,
            auto_start=True
        )

        # 2. Pencereyi Canlı İlerleme Moduna Dönüştür
        self._morph_to_progress_mode(filename)

    def _morph_to_progress_mode(self, filename: str) -> None:
        """Aynı pencereyi IDM tarzı canlı ilerleme moduna sokar."""
        self.is_progress_mode = True
        self.prog_filename = filename
        self.setWindowTitle(f"0% - {filename}")

        # Girişleri ve Add/Download butonlarını gizle
        self.query_widget.setVisible(False)
        self.buttons_widget.setVisible(False)

        # Meta veri alanlarını başlangıç durumuna ayarla
        self.name_val.setText(filename)
        self.status_val.setText("Downloading")
        self.status_val.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 12px; background: transparent;")
        if self.total_size_bytes > 0:
            self.size_val.setText(self._format_bytes(self.total_size_bytes))
        else:
            self.size_val.setText("Bilinmiyor")
        self.downloaded_val.setText("0 B ( 0 % )")
        self.speed_val.setText("0 B/s")
        self.eta_val.setText("--:--")

        task = self.task_manager.get_task(self.current_task_id) if self.current_task_id else None
        is_resumable = task.is_resumable if task else self._is_resumable
        self.resume_val.setText("Yes" if is_resumable else "No")
        self.resume_val.setStyleSheet("color: #22c55e; font-weight: bold; font-size: 12px; background: transparent;" if is_resumable else "color: #ef4444; font-weight: bold; font-size: 12px; background: transparent;")

        # Parça tablosunu ve segmentleri sıfırla
        self._init_chunk_views(8)

        # Canlı ilerleme gövdesini aç ve pencereyi genişlet
        self.progress_widget.setVisible(True)
        self.resize(560, 520)

    def _on_task_progress(self, data: dict) -> None:
        """Canlı indirme verisi geldiğinde UI alanlarını besler."""
        if not self.is_progress_mode or data.get("task_id") != self.current_task_id:
            return

        pct = int(data.get("percent", 0))
        self.prog_bar.setValue(pct)
        self.setWindowTitle(f"{pct}% - {self.prog_filename}")

        down_bytes = data.get("downloaded_bytes", 0)
        tot_bytes = data.get("total_bytes", self.total_size_bytes)
        speed = data.get("speed_str", "0 B/s")
        eta = data.get("eta_str", "--:--")

        self.size_val.setText(self._format_bytes(tot_bytes))
        if tot_bytes > 0:
            self.downloaded_val.setText(f"{self._format_bytes(down_bytes)} ( {pct}% )")
        else:
            self.downloaded_val.setText(self._format_bytes(down_bytes))

        self.speed_val.setText(speed)
        self.eta_val.setText(f"{eta} left" if eta and eta != "--:--" else (eta or "--:--"))

    def _on_task_chunk_progress(self, task_id: str, chunk_id: int, downloaded: int, total: int) -> None:
        if task_id != self.current_task_id:
            return

        # Tablo güncelleme
        if chunk_id < self.part_table.rowCount():
            is_done = (downloaded >= total > 0)
            status_txt = "Completed" if is_done else "Receiving Data"

            item_status = self.part_table.item(chunk_id, 1)
            if item_status:
                item_status.setText(status_txt)
                if is_done:
                    item_status.setForeground(QColor("#22c55e"))
                else:
                    item_status.setForeground(QColor("#38bdf8"))

            item_down = self.part_table.item(chunk_id, 2)
            if item_down:
                item_down.setText(self._format_bytes(downloaded))

            item_tot = self.part_table.item(chunk_id, 3)
            if item_tot:
                item_tot.setText(self._format_bytes(total))

        # Segment kutusu güncelleme
        if chunk_id < len(self._segment_boxes):
            box = self._segment_boxes[chunk_id]
            if downloaded >= total > 0:
                box.setStyleSheet("background-color: #15803d; border-radius: 2px;")
            else:
                box.setStyleSheet("background-color: #22c55e; border-radius: 2px; border: 1px solid #4ade80;")

    def _on_task_status_changed(self, task_id: str, status_str: str) -> None:
        if task_id == self.current_task_id:
            if status_str == DownloadStatus.PAUSED.value:
                self.btn_pause_resume.setText("▶ Resume")
                self.status_val.setText("Paused")
                self.status_val.setStyleSheet("color: #f59e0b; font-weight: 600; font-size: 12px; background: transparent;")
                for box in self._segment_boxes:
                    box.setStyleSheet("background-color: #1e293b; border-radius: 2px;")
            elif status_str == DownloadStatus.DOWNLOADING.value:
                self.btn_pause_resume.setText("⏸ Pause")
                self.status_val.setText("Downloading")
                self.status_val.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 12px; background: transparent;")
            elif status_str == DownloadStatus.MERGING.value:
                self.status_val.setText("Merging Chunks...")
                self.status_val.setStyleSheet("color: #a855f7; font-weight: 600; font-size: 12px; background: transparent;")

    def _on_task_finished(self, task_id: str, final_path: str) -> None:
        if task_id == self.current_task_id:
            self.prog_bar.setValue(100)
            self.setWindowTitle(f"100% - {self.prog_filename}")
            self.status_val.setText("Completed")
            self.status_val.setStyleSheet("color: #22c55e; font-weight: 600; font-size: 12px; background: transparent;")
            self.speed_val.setText("0 B/s")
            self.eta_val.setText("Finished")
            self.btn_pause_resume.setEnabled(False)

            # Tüm tablo satırlarını tamamlandı yap
            for row in range(self.part_table.rowCount()):
                item_st = self.part_table.item(row, 1)
                if item_st:
                    item_st.setText("Completed")
                    item_st.setForeground(QColor("#22c55e"))

            # Tüm segmentleri yeşile boya
            for box in self._segment_boxes:
                box.setStyleSheet("background-color: #22c55e; border-radius: 2px;")

            if self.chk_open_file.isChecked():
                self._open_file(final_path)
            elif self.chk_autoclose.isChecked():
                self.close()

    def _toggle_pause_resume(self) -> None:
        if not self.current_task_id:
            return
        task = self.task_manager.get_task(self.current_task_id)
        if task:
            if task.status == DownloadStatus.DOWNLOADING:
                self.task_manager.pause_task(self.current_task_id)
            elif task.status in (DownloadStatus.PAUSED, DownloadStatus.QUEUED, DownloadStatus.FAILED):
                self.task_manager.resume_task(self.current_task_id)

    def _open_target_folder(self) -> None:
        folder = os.path.normpath(self.dest_input.text().strip())
        if os.path.exists(folder):
            subprocess.Popen(f'explorer "{folder}"')

    def _open_file(self, file_path: str) -> None:
        if file_path and os.path.exists(file_path):
            try:
                os.startfile(file_path)
            except Exception:
                pass

    @staticmethod
    def _format_bytes(byte_count: int) -> str:
        """Boyutu okunabilir formata dönüştürür."""
        if byte_count <= 0:
            return "0 B"
        elif byte_count < 1024:
            return f"{byte_count} B"
        elif byte_count < 1024 * 1024:
            return f"{byte_count / 1024:.2f} KB"
        elif byte_count < 1024 * 1024 * 1024:
            return f"{byte_count / (1024 * 1024):.2f} MB"
        else:
            return f"{byte_count / (1024 * 1024 * 1024):.2f} GB"

    def closeEvent(self, event) -> None:
        """Pencere kapatıldığında indirme arka planda asla kesilmez, sadece pencere gizlenir."""
        if self.is_progress_mode:
            self.hide()
            event.ignore()
        else:
            event.accept()

    def _get_style_sheet(self) -> str:
        """Kullanıcının paylaştığı referans arayüzün özel QSS stilleri."""
        return """
            QDialog {
                background-color: #0f1117;
                border: 1px solid #1e2433;
                border-radius: 12px;
            }
            QTabWidget#detailTabs::pane {
                border: 1px solid #232838;
                border-radius: 10px;
                background-color: #171a23;
                padding: 4px;
            }
            QTabWidget#detailTabs QTabBar::tab {
                background-color: #12151e;
                color: #94a3b8;
                border: 1px solid #1e2433;
                border-radius: 8px;
                padding: 6px 18px;
                margin-right: 6px;
                font-weight: 600;
                font-size: 12px;
            }
            QTabWidget#detailTabs QTabBar::tab:selected {
                background-color: #232838;
                color: #ffffff;
                border: 1px solid #3b4258;
            }
            QTabWidget#detailTabs QTabBar::tab:hover {
                background-color: #1a1e2b;
                color: #f1f5f9;
            }
            QFrame#metadataCard {
                background-color: #11141e;
                border: 1px solid #1e2538;
                border-radius: 8px;
            }
            QProgressBar#neonProgressBar {
                background-color: #0d1017;
                border: 1px solid #1e2433;
                border-radius: 6px;
                text-align: center;
            }
            QProgressBar#neonProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #38bdf8, stop:0.5 #6366f1, stop:1 #a855f7);
                border-radius: 5px;
            }
            QPushButton#togglePartBtn {
                color: #cbd5e1;
                font-size: 12px;
                font-weight: 600;
                border: none;
                background: transparent;
                text-align: left;
                padding: 4px 2px;
            }
            QPushButton#togglePartBtn:hover {
                color: #38bdf8;
            }
            QTableWidget#partTable {
                background-color: #11141e;
                border: 1px solid #1e2538;
                border-radius: 6px;
                gridline-color: transparent;
                color: #cbd5e1;
                font-size: 11px;
            }
            QTableWidget#partTable QHeaderView::section {
                background-color: #161b2a;
                color: #94a3b8;
                border: none;
                padding: 5px 8px;
                font-weight: bold;
                font-size: 11px;
            }
            QTableWidget#partTable::item {
                padding: 3px 6px;
                border-bottom: 1px solid #171f30;
            }
            QPushButton#closeBtn {
                background-color: #171a23;
                border: 1px solid #272f44;
                color: #94a3b8;
                font-size: 12px;
                font-weight: 600;
                border-radius: 8px;
                padding: 6px 14px;
            }
            QPushButton#closeBtn:hover {
                background-color: #ef4444;
                color: #ffffff;
                border-color: #dc2626;
            }
            QFrame#inputContainer {
                background-color: #171a23;
                border: 1px solid #232838;
                border-radius: 8px;
                min-height: 38px;
                max-height: 38px;
            }
            QFrame#inputContainer:hover {
                border: 1px solid #333c52;
                background-color: #1c202c;
            }
            QFrame#sizeCard {
                background-color: #171a23;
                border: 1px solid #232838;
                border-radius: 10px;
                min-width: 155px;
            }
            QFrame#sizeCard:hover {
                border: 1px solid #333c52;
                background-color: #1a1e2a;
            }
            QLineEdit {
                color: #f1f5f9;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
            }
            QPushButton#downloadBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e3a8a, stop:1 #581c87);
                border: 1px solid #818cf8;
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                border-radius: 8px;
                padding: 8px 16px;
            }
            QPushButton#downloadBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #7c3aed);
                border: 1px solid #a5b4fc;
            }
            QPushButton#secondaryBtn {
                background-color: #171a23;
                border: 1px solid #272f44;
                color: #94a3b8;
                font-size: 12px;
                font-weight: 600;
                border-radius: 8px;
                padding: 7px 14px;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #212738;
                color: #f8fafc;
                border-color: #384564;
            }
            QPushButton#iconBtn {
                background-color: #171a23;
                border: 1px solid #272f44;
                border-radius: 6px;
                font-size: 12px;
                color: #94a3b8;
            }
            QPushButton#iconBtn:hover {
                background-color: #252b3d;
                color: #ffffff;
            }
        """
