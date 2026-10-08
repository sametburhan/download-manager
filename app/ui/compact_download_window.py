"""
Download Manager - Compact Floating Download and Live Progress Window (compact_download_window.py)

Designed to match the modern Windows 11 reference design.
Operates in two stages:
1. Stage: URL, save directory, filename, and pre-download server file size query.
2. Stage: When 'Download' is clicked, live progress, real-time speed, and chunked download view in the SAME WINDOW.
Even if the window is closed or minimized, downloading continues uninterrupted in the background.
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
    """Determines whether the URL is a video stream (YouTube, HLS m3u8, etc.)."""
    lower = url.lower().strip()
    if any(domain in lower for domain in ("youtube.com", "youtu.be", "vimeo.com", "dailymotion.com")):
        return True
    if any(ext in lower for ext in (".m3u8", ".mpd", "master.m3u8", "playlist.m3u8")):
        return True
    return False


def apply_dark_title_bar(window: QWidget) -> None:
    """Switches the window title bar to dark theme on Windows 10/11."""
    try:
        import ctypes
        hwnd = int(window.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
        )
        if res != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:
        pass


class CompactDownloadWindow(QDialog):
    """
    Modern IDM-style compact download and progress window.
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

        # Window properties (Windows 11 header, dark acrylic styling)
        self.setWindowTitle("Add download")
        self.setWindowIcon(get_app_icon())
        self.setMinimumWidth(580)
        self.resize(580, 240)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(self._get_style_sheet())

        self._init_ui(initial_url, initial_filename)
        self._connect_task_manager()

        if initial_url:
            self._query_file_size_async(initial_url)
        else:
            self._check_clipboard()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        apply_dark_title_bar(self)

    def _init_ui(self, initial_url: str, initial_filename: str) -> None:
        """Builds the modern dark acrylic layout from the reference design."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 16, 18, 16)
        self.main_layout.setSpacing(12)

        # ------------------- 1. QUERY BODY (QUERY MODE) -------------------
        self.query_widget = QWidget()
        query_layout = QHBoxLayout(self.query_widget)
        query_layout.setContentsMargins(0, 2, 0, 2)
        query_layout.setSpacing(14)

        # Left Input Fields (URL, Folder, Filename)
        inputs_layout = QVBoxLayout()
        inputs_layout.setSpacing(8)

        # A) URL Row + Clipboard Button
        url_container = QFrame()
        url_container.setObjectName("inputContainer")
        url_layout = QHBoxLayout(url_container)
        url_layout.setContentsMargins(10, 0, 8, 0)
        url_layout.setSpacing(6)

        self.url_input = QLineEdit(initial_url)
        self.url_input.setPlaceholderText("https://...")
        self.url_input.setStyleSheet("border: none; background: transparent;")
        self.url_input.textChanged.connect(self._on_url_changed)
        url_layout.addWidget(self.url_input)

        self.btn_paste = QPushButton("📋")
        self.btn_paste.setObjectName("embeddedActionBtn")
        self.btn_paste.setToolTip("Paste clipboard contents")
        self.btn_paste.setFixedSize(26, 26)
        self.btn_paste.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_paste.clicked.connect(self._paste_from_clipboard)
        url_layout.addWidget(self.btn_paste)

        inputs_layout.addWidget(url_container)

        # B) Save Folder Row + Browse Icon
        dest_container = QFrame()
        dest_container.setObjectName("inputContainer")
        dest_layout = QHBoxLayout(dest_container)
        dest_layout.setContentsMargins(10, 0, 8, 0)
        dest_layout.setSpacing(6)

        self.dest_input = QLineEdit(self.default_save_dir)
        self.dest_input.setStyleSheet("border: none; background: transparent;")
        dest_layout.addWidget(self.dest_input)

        self.btn_browse = QPushButton("📁")
        self.btn_browse.setObjectName("embeddedActionBtn")
        self.btn_browse.setToolTip("Select destination folder")
        self.btn_browse.setFixedSize(26, 26)
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self._browse_folder)
        dest_layout.addWidget(self.btn_browse)

        inputs_layout.addWidget(dest_container)

        # C) Filename Row
        file_container = QFrame()
        file_container.setObjectName("inputContainer")
        file_layout = QHBoxLayout(file_container)
        file_layout.setContentsMargins(10, 0, 8, 0)

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

        # Right Info Panel (Modern File Size Card)
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(0, 0, 0, 0)
        right_panel.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.size_card = QFrame()
        self.size_card.setObjectName("sizeCard")
        size_card_layout = QVBoxLayout(self.size_card)
        size_card_layout.setContentsMargins(14, 12, 14, 12)
        size_card_layout.setSpacing(6)

        # Header and Refresh Button
        header_box = QHBoxLayout()
        header_box.setSpacing(6)
        self.size_icon = QLabel("📦")
        self.size_icon.setStyleSheet("font-size: 13px; background: transparent;")
        header_box.addWidget(self.size_icon)

        size_title = QLabel("FILE SIZE")
        size_title.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: bold; letter-spacing: 0.6px; background: transparent;")
        header_box.addWidget(size_title)
        header_box.addStretch()

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setObjectName("refreshBtn")
        self.btn_refresh.setToolTip("Re-query file size")
        self.btn_refresh.setFixedSize(22, 22)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(lambda: self._query_file_size_async(self.url_input.text()))
        header_box.addWidget(self.btn_refresh)
        size_card_layout.addLayout(header_box)

        # Large and clear size indicator
        self.size_label = QLabel("Querying...")
        self.size_label.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.size_label.setStyleSheet("color: #38bdf8; background: transparent;")
        size_card_layout.addWidget(self.size_label)

        # Status and quota explanation
        self.check_icon = QLabel("Connecting to server...")
        self.check_icon.setStyleSheet("color: #64748b; font-size: 11px; background: transparent;")
        size_card_layout.addWidget(self.check_icon)

        right_panel.addWidget(self.size_card)
        query_layout.addLayout(right_panel, stretch=2)

        self.main_layout.addWidget(self.query_widget)

        # ------------------- 2. PROGRESS BODY (PROGRESS MODE - STITCH MODERN IDM) -------------------
        self.progress_widget = QWidget()
        self.progress_widget.setVisible(False)
        prog_layout = QVBoxLayout(self.progress_widget)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(10)

        # Tabbed Layout: [ ⓘ Info ] [ ⚙ Settings ]
        self.prog_tab_widget = QTabWidget()
        self.prog_tab_widget.setObjectName("detailTabs")

        # ----------------- TAB 1: INFO -----------------
        info_tab = QWidget()
        info_layout = QVBoxLayout(info_tab)
        info_layout.setContentsMargins(4, 10, 4, 4)
        info_layout.setSpacing(12)

        # A) Metadata Card (Stitch Modern Grid Card)
        self.meta_card = QFrame()
        self.meta_card.setObjectName("metadataCard")
        meta_grid = QGridLayout(self.meta_card)
        meta_grid.setContentsMargins(20, 16, 20, 16)
        meta_grid.setHorizontalSpacing(24)
        meta_grid.setVerticalSpacing(10)
        meta_grid.setColumnMinimumWidth(0, 130)

        lbl_style = "color: #64748b; font-weight: 500; font-size: 12px; background: transparent;"
        val_style = "color: #f8fafc; font-weight: 600; font-size: 12px; background: transparent;"

        # Row 0: Name
        meta_grid.addWidget(QLabel("Name:", styleSheet=lbl_style), 0, 0)
        self.name_val = QLabel("")
        self.name_val.setStyleSheet(val_style)
        self.name_val.setWordWrap(True)
        meta_grid.addWidget(self.name_val, 0, 1)
        self.prog_filename_lbl = self.name_val  # Backward compatibility

        # Row 1: Status
        meta_grid.addWidget(QLabel("Status:", styleSheet=lbl_style), 1, 0)
        self.status_val = QLabel("● Downloading")
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

        # B) Main Neon Progress Bar (Stitch Slim Neon Bar)
        self.prog_bar = QProgressBar()
        self.prog_bar.setObjectName("neonProgressBar")
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setFixedHeight(8)
        info_layout.addWidget(self.prog_bar)

        # C) Parts Toggle Button and Actions
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0, 2, 0, 2)
        ctrl_layout.setSpacing(10)

        self.toggle_part_btn = QPushButton("˄ Parts Info")
        self.toggle_part_btn.setObjectName("togglePartBtn")
        self.toggle_part_btn.setFlat(True)
        self.toggle_part_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_part_btn.clicked.connect(self._toggle_part_info)
        ctrl_layout.addWidget(self.toggle_part_btn)

        ctrl_layout.addStretch()

        self.btn_pause_resume = QPushButton("⏸ Pause")
        self.btn_pause_resume.setObjectName("progActionPillBtn")
        self.btn_pause_resume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause_resume.clicked.connect(self._toggle_pause_resume)
        ctrl_layout.addWidget(self.btn_pause_resume)

        self.btn_open_file = QPushButton("📁 Open Folder")
        self.btn_open_file.setObjectName("progSecondaryPillBtn")
        self.btn_open_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_file.clicked.connect(self._open_target_folder)
        ctrl_layout.addWidget(self.btn_open_file)

        self.btn_hide_to_tray = QPushButton("✕ Close")
        self.btn_hide_to_tray.setObjectName("progClosePillBtn")
        self.btn_hide_to_tray.setToolTip("Hide window (Download continues uninterrupted in the background)")
        self.btn_hide_to_tray.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hide_to_tray.clicked.connect(self.hide)
        ctrl_layout.addWidget(self.btn_hide_to_tray)

        info_layout.addLayout(ctrl_layout)

        # D) Dynamic Connection Segment and Status Panel (Collapsible)
        try:
            from app.core.config import load_network_settings
            initial_chunks = load_network_settings().segments_per_download
        except Exception:
            initial_chunks = 8
        initial_chunks = max(1, initial_chunks)

        self.part_container = QWidget()
        part_layout = QVBoxLayout(self.part_container)
        part_layout.setContentsMargins(0, 0, 0, 0)
        part_layout.setSpacing(8)

        # Live Segment Bar
        self.segments_layout = QHBoxLayout()
        self.segments_layout.setSpacing(4)
        part_layout.addLayout(self.segments_layout)

        # Live Parts Table (# | STATUS | DOWNLOADED | TOTAL)
        self.part_table = QTableWidget(0, 4)
        self.part_table.setObjectName("partTable")
        self.part_table.setHorizontalHeaderLabels(["#", "STATUS", "DOWNLOADED", "TOTAL"])
        self.part_table.verticalHeader().setVisible(False)
        self.part_table.verticalHeader().setDefaultSectionSize(26)
        self.part_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.part_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.part_table.setShowGrid(False)
        self.part_table.setFixedHeight(150)
        self.part_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.part_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.part_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.part_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        part_layout.addWidget(self.part_table)

        info_layout.addWidget(self.part_container)

        # E) Footer Status Bar
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(2, 6, 2, 2)
        self.footer_status_lbl = QLabel("● Initializing download...")
        self.footer_status_lbl.setObjectName("footerStatusLbl")
        self.footer_status_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 500; background: transparent;")
        footer_layout.addWidget(self.footer_status_lbl)

        footer_layout.addStretch()

        self.footer_engine_lbl = QLabel(f"{initial_chunks} {'Connection' if initial_chunks == 1 else 'Connections'} • Download Manager")
        self.footer_engine_lbl.setObjectName("footerEngineLbl")
        self.footer_engine_lbl.setStyleSheet("color: #475569; font-size: 11px; font-weight: 500; background: transparent;")
        footer_layout.addWidget(self.footer_engine_lbl)

        info_layout.addLayout(footer_layout)

        self._init_chunk_views(initial_chunks)

        self.prog_tab_widget.addTab(info_tab, "ⓘ Info")

        # ----------------- TAB 2: SETTINGS -----------------
        settings_tab = QWidget()
        set_layout = QVBoxLayout(settings_tab)
        set_layout.setContentsMargins(4, 10, 4, 6)
        set_layout.setSpacing(12)

        self.settings_card = QFrame()
        self.settings_card.setObjectName("settingsCard")
        set_card_layout = QVBoxLayout(self.settings_card)
        set_card_layout.setContentsMargins(20, 18, 20, 18)
        set_card_layout.setSpacing(14)

        # Download Folder
        folder_group = QVBoxLayout()
        folder_lbl = QLabel("Destination Download Folder:")
        folder_lbl.setStyleSheet(lbl_style)
        folder_group.addWidget(folder_lbl)

        folder_row = QHBoxLayout()
        self.folder_path_display = QLineEdit(self.default_save_dir)
        self.folder_path_display.setReadOnly(True)
        self.folder_path_display.setStyleSheet("background-color: #101625; border: 1px solid #1a2336; border-radius: 6px; padding: 6px 10px; color: #f1f5f9; font-size: 12px;")
        folder_row.addWidget(self.folder_path_display)

        btn_browse_set = QPushButton("📁")
        btn_browse_set.setToolTip("Change Folder")
        btn_browse_set.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse_set.setStyleSheet("background-color: #151d2f; border: 1px solid #1a2336; border-radius: 6px; padding: 6px 12px; color: #fff;")
        btn_browse_set.clicked.connect(self._browse_folder_settings)
        folder_row.addWidget(btn_browse_set)
        folder_group.addLayout(folder_row)
        set_card_layout.addLayout(folder_group)

        # Connection Count
        conn_group = QHBoxLayout()
        conn_lbl = QLabel("Connection (Segment) Count:")
        conn_lbl.setStyleSheet(lbl_style)
        conn_group.addWidget(conn_lbl)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 32)
        self.conn_spin.setValue(initial_chunks)
        self.conn_spin.setFixedWidth(90)
        self.conn_spin.setFixedHeight(30)
        self.conn_spin.setStyleSheet("background-color: #101625; border: 1px solid #1a2336; border-radius: 6px; padding: 4px 8px; color: #f1f5f9; font-size: 12px;")
        self.conn_spin.valueChanged.connect(self._on_conn_spin_changed)
        conn_group.addWidget(self.conn_spin)
        conn_group.addStretch()
        set_card_layout.addLayout(conn_group)

        # Speed Limiter (Speed Limiter - IDM feature)
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
        self.spin_speed_limit.setStyleSheet("background-color: #101625; border: 1px solid #1a2336; border-radius: 6px; padding: 4px 8px; color: #f1f5f9; font-size: 12px;")
        self.chk_speed_limit.toggled.connect(self.spin_speed_limit.setEnabled)
        speed_group.addWidget(self.spin_speed_limit)
        speed_group.addStretch()
        set_card_layout.addLayout(speed_group)

        # Completion Options
        self.chk_autoclose = QCheckBox("Automatically close this window when download completes")
        self.chk_autoclose.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        set_card_layout.addWidget(self.chk_autoclose)

        self.chk_open_file = QCheckBox("Open file when download completes")
        self.chk_open_file.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        set_card_layout.addWidget(self.chk_open_file)

        set_layout.addWidget(self.settings_card)
        set_layout.addStretch()
        self.prog_tab_widget.addTab(settings_tab, "⚙ Settings")

        prog_layout.addWidget(self.prog_tab_widget)
        self.main_layout.addWidget(self.progress_widget)

        # ------------------- 4. ALT EYLEM BUTONLARI (QUERY MODE) -------------------
        self.buttons_widget = QWidget()
        btn_layout = QHBoxLayout(self.buttons_widget)
        btn_layout.setContentsMargins(0, 6, 0, 0)
        btn_layout.setSpacing(10)

        # 'Add' Button (Adds to queue without starting immediately)
        self.btn_add = QPushButton("Add")
        self.btn_add.setObjectName("secondaryBtn")
        self.btn_add.setFixedWidth(80)
        self.btn_add.setFixedHeight(38)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self._on_add_clicked)
        btn_layout.addWidget(self.btn_add)

        # 'Download' Button (Starts download immediately)
        self.btn_download = QPushButton("Download")
        self.btn_download.setObjectName("downloadBtn")
        self.btn_download.setFixedWidth(145)
        self.btn_download.setFixedHeight(38)
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.clicked.connect(self._on_download_clicked)
        btn_layout.addWidget(self.btn_download)

        btn_layout.addStretch()

        # 'Cancel' Butonu
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setFixedHeight(38)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_cancel)

        self.main_layout.addWidget(self.buttons_widget)

    def _init_chunk_bars(self, count: int = 8) -> None:
        """Maintained for backward compatibility."""
        pass

    def _on_conn_spin_changed(self, value: int) -> None:
        """Saves new segment count to settings and updates preview if not currently downloading."""
        try:
            from app.core.config import load_network_settings, save_network_settings
            settings = load_network_settings()
            settings.segments_per_download = value
            save_network_settings(settings)
            if not self.is_progress_mode:
                self._init_chunk_views(value)
        except Exception:
            pass

    def _init_chunk_views(self, count: Optional[int] = None) -> None:
        """Resets and dynamically builds IDM-style segment indicator boxes and table rows."""
        if count is None or count <= 0:
            try:
                from app.core.config import load_network_settings
                count = load_network_settings().segments_per_download
            except Exception:
                count = 8
        count = max(1, count)

        # 1. Clear existing boxes
        if hasattr(self, "segments_layout"):
            while self.segments_layout.count():
                item = self.segments_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
        self._segment_boxes = []

        # 2. Add count segment indicator boxes
        for _ in range(count):
            box = QLabel()
            box.setFixedHeight(12)
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            box.setStyleSheet("background-color: #101728; border: 1px solid #1a2336; border-radius: 3px;")
            self._segment_boxes.append(box)
            if hasattr(self, "segments_layout"):
                self.segments_layout.addWidget(box)

        # 3. Setup table rows
        if hasattr(self, "part_table"):
            self.part_table.setRowCount(count)
            for i in range(count):
                item_num = QTableWidgetItem(str(i + 1))
                item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_num.setForeground(QColor("#64748b"))

                item_status = QTableWidgetItem("● Idle")
                item_status.setForeground(QColor("#64748b"))

                item_down = QTableWidgetItem("--")
                item_down.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item_down.setForeground(QColor("#f1f5f9"))

                item_tot = QTableWidgetItem("--")
                item_tot.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item_tot.setForeground(QColor("#64748b"))

                self.part_table.setItem(i, 0, item_num)
                self.part_table.setItem(i, 1, item_status)
                self.part_table.setItem(i, 2, item_down)
                self.part_table.setItem(i, 3, item_tot)

        # 4. Update footer label
        if hasattr(self, "footer_engine_lbl"):
            label_conn = "Connection" if count == 1 else "Connections"
            self.footer_engine_lbl.setText(f"{count} {label_conn} • Download Manager")

    def _toggle_part_info(self) -> None:
        """Toggles the parts panel open or closed."""
        self._is_part_info_expanded = not self._is_part_info_expanded
        self.part_container.setVisible(self._is_part_info_expanded)
        self.toggle_part_btn.setText("˄ Parts Info" if self._is_part_info_expanded else "˅ Parts Info")
        if self._is_part_info_expanded:
            self.resize(620, 580)
        else:
            self.resize(620, 360)

    def _browse_folder_settings(self) -> None:
        """Folder selection from the settings tab."""
        chosen = QFileDialog.getExistingDirectory(self, "Select Destination Folder", self.folder_path_display.text())
        if chosen:
            self.folder_path_display.setText(chosen)
            self.dest_input.setText(chosen)
            if self.current_task_id:
                task = self.task_manager.get_task(self.current_task_id)
                if task:
                    task.destination_folder = chosen

    def _connect_task_manager(self) -> None:
        """Listens for TaskManager signals."""
        self.task_manager.task_progress.connect(self._on_task_progress)
        self.task_manager.task_chunk_progress.connect(self._on_task_chunk_progress)
        self.task_manager.task_status_changed.connect(self._on_task_status_changed)
        self.task_manager.task_finished.connect(self._on_task_finished)

    # ==================== Actions and Network Query ====================

    def _on_url_changed(self, url: str) -> None:
        """Estimates filename and queries file size when URL changes."""
        url = url.strip()
        if not self.filename_input.text() or self.filename_input.text() == "file.bin":
            clean = url.split("?")[0].split("#")[0]
            name = clean.split("/")[-1]
            if name and "." in name:
                self.filename_input.setText(name)

        if url.startswith(("http://", "https://", "file://")):
            # Query after 400ms debounce
            QTimer.singleShot(400, lambda: self._query_file_size_async(url))

    def _query_file_size_async(self, url: str) -> None:
        """Determines file size via server HEAD/GET request or local disk inspection."""
        if not url:
            self._update_size_ui(0, status_msg="Please enter URL")
            return

        url = url.strip()

        # 1. Local File (file:// or direct Windows path C:\...)
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
                    self._update_size_ui(sz, status_msg="✓ Local file ready")
                    return
                except Exception:
                    pass
            self.size_icon.setText("📦")
            self._update_size_ui(-1, status_msg="Local file not found")
            return

        if not url.startswith(("http://", "https://", "ftp://")):
            self._update_size_ui(0, status_msg="Invalid URL")
            return

        if is_video_stream_url(url):
            self.size_icon.setText("🎬")
            self.size_label.setText("Video Stream")
            self.size_label.setStyleSheet("color: #38bdf8; font-size: 13px; font-weight: bold; background: transparent;")
            self.check_icon.setText("🎬 Online video detected")
            self.check_icon.setStyleSheet("color: #38bdf8; font-size: 11px; background: transparent;")
            return

        self.size_icon.setText("📦")
        self.size_label.setText("Querying...")
        self.size_label.setStyleSheet("color: #38bdf8; font-size: 15px; font-weight: bold; background: transparent;")
        self.check_icon.setText("Connecting to server...")
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
                    # Attempt 1: HEAD request for size and Range support
                    try:
                        resp = client.head(url, headers=browser_headers)
                        if resp.status_code == 200:
                            if "Content-Length" in resp.headers and resp.headers["Content-Length"].isdigit():
                                size = int(resp.headers["Content-Length"])
                                is_resumable = resp.headers.get("Accept-Ranges", "").lower() == "bytes"
                                status_text = "Resume supported" if is_resumable else "Ready to download"
                        elif resp.status_code == 404:
                            QTimer.singleShot(0, lambda: self._update_size_ui(-1, status_msg="404 Not Found"))
                            return
                    except Exception:
                        pass

                    # Attempt 2: GET Stream with Range: bytes=0-0 if HEAD fails or provides no size
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
                                             status_text = "Resume supported"
                                elif get_resp.status_code == 200:
                                    if "Content-Length" in get_resp.headers and get_resp.headers["Content-Length"].isdigit():
                                        size = int(get_resp.headers["Content-Length"])
                                        is_resumable = get_resp.headers.get("Accept-Ranges", "").lower() == "bytes"
                                        status_text = "Resume supported" if is_resumable else "Ready to download"
                                elif get_resp.status_code == 404:
                                    QTimer.singleShot(0, lambda: self._update_size_ui(-1, status_msg="404 Not Found"))
                                    return
                        except Exception:
                            pass

                    # Update in UI thread
                    final_size = size
                    final_resumable = is_resumable
                    final_status = status_text
                    QTimer.singleShot(0, lambda: self._update_size_ui(final_size, is_resumable=final_resumable, status_msg=final_status))
            except Exception:
                QTimer.singleShot(0, lambda: self._update_size_ui(-1, status_msg="Connection timed out"))

        threading.Thread(target=worker, daemon=True).start()

    def _update_size_ui(self, size_bytes: int, is_resumable: bool = False, status_msg: str = "") -> None:
        self.total_size_bytes = max(0, size_bytes)
        self._is_resumable = is_resumable

        if size_bytes > 0:
            if size_bytes < 1024 * 1024:
                formatted = f"{size_bytes / 1024:.2f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                formatted = f"{size_bytes / (1024 * 1024):.2f} MB"
            else:
                formatted = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

            self.size_label.setText(formatted)
            self.size_label.setStyleSheet("color: #38bdf8; font-size: 15px; font-weight: bold; background: transparent;")
            msg = status_msg or ("✓ Resume supported" if is_resumable else "✓ Server ready")
            self.check_icon.setText(msg)
            self.check_icon.setStyleSheet("color: #94a3b8; font-size: 11px; background: transparent;")

        elif size_bytes == 0:
            self.size_label.setText("Unknown")
            self.size_label.setStyleSheet("color: #f59e0b; font-size: 13px; font-weight: bold; background: transparent;")
            self.check_icon.setText(status_msg or "Dynamic stream / no size info")
            self.check_icon.setStyleSheet("color: #94a3b8; font-size: 10px; background: transparent;")

        else:  # Negative (error / 404 / 403)
            self.size_label.setText("Unreachable")
            self.size_label.setStyleSheet("color: #ef4444; font-size: 13px; font-weight: bold; background: transparent;")
            self.check_icon.setText(status_msg or "Check address")
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

    # ==================== Start and Morph to Progress ====================

    def _on_add_clicked(self) -> None:
        """Silently adds to queue (auto_start=False) and closes window."""
        url = self.url_input.text().strip()
        filename = sanitize_filename(self.filename_input.text().strip())
        dest = self.dest_input.text().strip() or self.default_save_dir

        if not url:
            return

        if not filename:
            clean = url.split("?")[0].split("#")[0]
            name = clean.split("/")[-1]
            if name:
                try:
                    name = urllib.parse.unquote(name)
                except Exception:
                    pass
                filename = sanitize_filename(name) or "download.bin"

        if is_video_stream_url(url):
            self.task_manager.add_media_download(
                url=url,
                title=filename or None,
                destination_folder=dest,
                auto_start=False
            )
        else:
            self.task_manager.add_http_download(
                url=url,
                filename=filename,
                destination_folder=dest,
                auto_start=False
            )
        self.accept()

    def _on_download_clicked(self) -> None:
        """Starts download in the SAME WINDOW when Download is clicked and switches to progress mode."""
        url = self.url_input.text().strip()
        filename = sanitize_filename(self.filename_input.text().strip())
        dest = self.dest_input.text().strip() or self.default_save_dir

        if not url:
            return

        if not filename:
            clean = url.split("?")[0].split("#")[0]
            name = clean.split("/")[-1]
            if name:
                try:
                    name = urllib.parse.unquote(name)
                except Exception:
                    pass
                filename = sanitize_filename(name) or "download.bin"

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

        # 1. Start task in TaskManager using configured segments
        try:
            from app.core.config import load_network_settings
            num_chunks = load_network_settings().segments_per_download
        except Exception:
            num_chunks = 8

        self.current_task_id = self.task_manager.add_http_download(
            url=url,
            filename=filename,
            destination_folder=dest,
            num_chunks=num_chunks,
            auto_start=True
        )

        # 2. Morph window to live progress mode
        self._morph_to_progress_mode(filename)

    def _morph_to_progress_mode(self, filename: str) -> None:
        """Transitions the window into IDM-style live progress mode."""
        self.is_progress_mode = True
        self.prog_filename = filename
        self.setWindowTitle(f"0% - {filename}")

        # Hide inputs and Add/Download buttons
        self.query_widget.setVisible(False)
        self.buttons_widget.setVisible(False)

        # Initialize metadata display fields
        self.name_val.setText(filename)
        self.status_val.setText("● Downloading")
        self.status_val.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 12px; background: transparent;")
        if self.total_size_bytes > 0:
            self.size_val.setText(self._format_bytes(self.total_size_bytes))
        else:
            self.size_val.setText("Unknown")
        self.downloaded_val.setText("0 B ( 0 % )")
        self.speed_val.setText("0 B/s")
        self.eta_val.setText("--:--")

        task = self.task_manager.get_task(self.current_task_id) if self.current_task_id else None
        is_resumable = task.is_resumable if task else self._is_resumable
        self.resume_val.setText("Yes" if is_resumable else "No")
        self.resume_val.setStyleSheet(
            "color: #10b981; font-weight: bold; font-size: 12px; background: transparent;"
            if is_resumable else
            "color: #ef4444; font-weight: bold; font-size: 12px; background: transparent;"
        )

        if hasattr(self, "footer_status_lbl"):
            self.footer_status_lbl.setText("● Connecting to server...")
            self.footer_status_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 500; background: transparent;")

        # Reset parts table and segments based on task chunks or configured count
        task = self.task_manager.get_task(self.current_task_id) if self.current_task_id else None
        if task and task.chunks:
            chunk_count = len(task.chunks)
        else:
            try:
                from app.core.config import load_network_settings
                chunk_count = load_network_settings().segments_per_download
            except Exception:
                chunk_count = 8

        self._init_chunk_views(chunk_count)

        # Show live progress body and resize window
        self.progress_widget.setVisible(True)
        self.resize(620, 580)

    def _on_task_progress(self, data: dict) -> None:
        """Updates UI fields when live progress data arrives."""
        if not self.is_progress_mode or data.get("task_id") != self.current_task_id:
            return

        task = self.task_manager.get_task(self.current_task_id) if self.current_task_id else None
        if task and task.chunks and len(task.chunks) != len(self._segment_boxes):
            self._init_chunk_views(len(task.chunks))

        pct = int(data.get("percent", 0))
        self.prog_bar.setValue(pct)
        self.setWindowTitle(f"{pct}% - {self.prog_filename}")

        down_bytes = data.get("downloaded_bytes", 0)
        tot_bytes = data.get("total_bytes", self.total_size_bytes)
        speed = data.get("speed_str", "0 B/s")
        eta = data.get("eta_str", "--:--")

        self.size_val.setText(self._format_bytes(tot_bytes) if tot_bytes > 0 else "Unknown")
        if tot_bytes > 0:
            self.downloaded_val.setText(f"{self._format_bytes(down_bytes)} ( {pct}% )")
        else:
            self.downloaded_val.setText(self._format_bytes(down_bytes))

        self.speed_val.setText(speed)
        eta_txt = f"{eta} left" if eta and eta != "--:--" else (eta or "--:--")
        self.eta_val.setText(eta_txt)

        if hasattr(self, "footer_status_lbl"):
            self.footer_status_lbl.setText(f"● Downloading at {speed} • {eta_txt}")
            self.footer_status_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 500; background: transparent;")

    def _on_task_chunk_progress(self, task_id: str, chunk_id: int, downloaded: int, total: int) -> None:
        if task_id != self.current_task_id:
            return

        task = self.task_manager.get_task(task_id) if hasattr(self, "task_manager") else None
        if task and task.chunks and len(task.chunks) != len(self._segment_boxes):
            self._init_chunk_views(len(task.chunks))
        elif chunk_id >= len(self._segment_boxes):
            self._init_chunk_views(chunk_id + 1)

        # Update table
        if chunk_id < self.part_table.rowCount():
            is_done = (downloaded >= total > 0)
            status_txt = "● Completed" if is_done else "● Receiving Data"

            item_status = self.part_table.item(chunk_id, 1)
            if item_status:
                item_status.setText(status_txt)
                if is_done:
                    item_status.setForeground(QColor("#10b981"))
                else:
                    item_status.setForeground(QColor("#38bdf8"))

            item_down = self.part_table.item(chunk_id, 2)
            if item_down:
                item_down.setText(self._format_bytes(downloaded))

            item_tot = self.part_table.item(chunk_id, 3)
            if item_tot:
                item_tot.setText(self._format_bytes(total) if total > 0 else "--")

        # Update segment boxes
        if chunk_id < len(self._segment_boxes):
            box = self._segment_boxes[chunk_id]
            if downloaded >= total > 0:
                box.setStyleSheet("background-color: #10b981; border: 1px solid #34d399; border-radius: 3px;")
            else:
                box.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #06b6d4); border: 1px solid #0284c7; border-radius: 3px;")

    def _on_task_status_changed(self, task_id: str, status_str: str) -> None:
        if task_id == self.current_task_id:
            if status_str == DownloadStatus.PAUSED.value:
                self.btn_pause_resume.setText("▶ Resume")
                self.status_val.setText("● Paused")
                self.status_val.setStyleSheet("color: #f59e0b; font-weight: 600; font-size: 12px; background: transparent;")
                if hasattr(self, "footer_status_lbl"):
                    self.footer_status_lbl.setText("● Download paused by user")
                    self.footer_status_lbl.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: 500; background: transparent;")
                for box in self._segment_boxes:
                    box.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 3px;")
                for row in range(self.part_table.rowCount()):
                    item_st = self.part_table.item(row, 1)
                    if item_st and "Receiving" in item_st.text():
                        item_st.setText("● Paused")
                        item_st.setForeground(QColor("#f59e0b"))
            elif status_str == DownloadStatus.DOWNLOADING.value:
                self.btn_pause_resume.setText("⏸ Pause")
                self.status_val.setText("● Downloading")
                self.status_val.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 12px; background: transparent;")
                if hasattr(self, "footer_status_lbl"):
                    self.footer_status_lbl.setText("● Downloading...")
                    self.footer_status_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 500; background: transparent;")
            elif status_str == DownloadStatus.MERGING.value:
                self.status_val.setText("● Merging Chunks...")
                self.status_val.setStyleSheet("color: #a855f7; font-weight: 600; font-size: 12px; background: transparent;")
                if hasattr(self, "footer_status_lbl"):
                    self.footer_status_lbl.setText("● Merging chunks into single file...")
                    self.footer_status_lbl.setStyleSheet("color: #a855f7; font-size: 11px; font-weight: 500; background: transparent;")

    def _on_task_finished(self, task_id: str, final_path: str) -> None:
        if task_id == self.current_task_id:
            self.prog_bar.setValue(100)
            self.setWindowTitle(f"100% - {self.prog_filename}")
            self.status_val.setText("● Completed")
            self.status_val.setStyleSheet("color: #10b981; font-weight: 600; font-size: 12px; background: transparent;")
            self.speed_val.setText("0 B/s")
            self.eta_val.setText("Finished")
            self.btn_pause_resume.setEnabled(False)

            if hasattr(self, "footer_status_lbl"):
                self.footer_status_lbl.setText("● Download completed successfully")
                self.footer_status_lbl.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 500; background: transparent;")

            # Mark all table rows completed
            for row in range(self.part_table.rowCount()):
                item_st = self.part_table.item(row, 1)
                if item_st:
                    item_st.setText("● Completed")
                    item_st.setForeground(QColor("#10b981"))

            # Color all segments green
            for box in self._segment_boxes:
                box.setStyleSheet("background-color: #10b981; border: 1px solid #34d399; border-radius: 3px;")

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
        """Converts byte count to human-readable format."""
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
        """When window is closed, download continues in background; window is only hidden."""
        if self.is_progress_mode:
            self.hide()
            event.ignore()
        else:
            event.accept()

    def _get_style_sheet(self) -> str:
        """Modern dark QSS styles matching the Stitch reference interface."""
        return """
            QDialog {
                background-color: #0b0f19;
                border: 1px solid #161e31;
                border-radius: 12px;
            }
            QTabWidget#detailTabs {
                background: transparent;
                border: none;
            }
            QTabWidget#detailTabs::pane {
                border: none;
                background: transparent;
            }
            QTabWidget#detailTabs QTabBar {
                background: transparent;
            }
            QTabWidget#detailTabs QTabBar::tab {
                background-color: transparent;
                color: #64748b;
                border: 1px solid transparent;
                border-radius: 14px;
                padding: 6px 18px;
                margin-right: 8px;
                font-family: "Segoe UI", sans-serif;
                font-weight: 600;
                font-size: 12px;
            }
            QTabWidget#detailTabs QTabBar::tab:selected {
                background-color: #131c31;
                color: #ffffff;
                border: 1px solid #2563eb;
            }
            QTabWidget#detailTabs QTabBar::tab:hover:!selected {
                background-color: #0f1524;
                color: #94a3b8;
                border: 1px solid #1e293b;
            }
            QFrame#metadataCard {
                background-color: #0d121f;
                border: 1px solid #161e31;
                border-radius: 10px;
            }
            QFrame#settingsCard {
                background-color: #0d121f;
                border: 1px solid #161e31;
                border-radius: 10px;
            }
            QProgressBar#neonProgressBar {
                background-color: #0d121f;
                border: 1px solid #161e31;
                border-radius: 4px;
                min-height: 8px;
                max-height: 8px;
                text-align: center;
            }
            QProgressBar#neonProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0284c7, stop:0.5 #3b82f6, stop:1 #8b5cf6);
                border-radius: 3px;
            }
            QPushButton#togglePartBtn {
                color: #94a3b8;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 600;
                border: none;
                background: transparent;
                text-align: left;
                padding: 4px 0px;
            }
            QPushButton#togglePartBtn:hover {
                color: #38bdf8;
            }
            QPushButton#progActionPillBtn {
                background-color: #111726;
                border: 1px solid #1d4ed8;
                color: #60a5fa;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 600;
                border-radius: 8px;
                padding: 6px 16px;
            }
            QPushButton#progActionPillBtn:hover {
                background-color: #1e293b;
                border-color: #2563eb;
                color: #93c5fd;
            }
            QPushButton#progSecondaryPillBtn {
                background-color: #111726;
                border: 1px solid #1a2336;
                color: #cbd5e1;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 600;
                border-radius: 8px;
                padding: 6px 16px;
            }
            QPushButton#progSecondaryPillBtn:hover {
                background-color: #1e293b;
                border-color: #2d3b55;
                color: #ffffff;
            }
            QPushButton#progClosePillBtn {
                background-color: #111726;
                border: 1px solid #1a2336;
                color: #cbd5e1;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 600;
                border-radius: 8px;
                padding: 6px 16px;
            }
            QPushButton#progClosePillBtn:hover {
                background-color: #ef4444;
                border-color: #dc2626;
                color: #ffffff;
            }
            QTableWidget#partTable {
                background-color: #0d121f;
                border: 1px solid #161e31;
                border-radius: 8px;
                gridline-color: transparent;
                color: #cbd5e1;
                font-family: "Segoe UI", sans-serif;
                font-size: 11px;
                selection-background-color: #162035;
                outline: none;
            }
            QTableWidget#partTable QHeaderView::section {
                background-color: #0d121f;
                color: #64748b;
                border: none;
                border-bottom: 1px solid #161e31;
                padding: 6px 8px;
                font-weight: bold;
                font-size: 10px;
                letter-spacing: 0.8px;
            }
            QTableWidget#partTable::item {
                padding: 3px 8px;
                border-bottom: 1px solid #111726;
            }
            QTableWidget#partTable::item:selected {
                background-color: #162035;
                color: #f8fafc;
            }
            QFrame#inputContainer {
                background-color: #121826;
                border: 1px solid #1f2b3e;
                border-radius: 8px;
                min-height: 38px;
                max-height: 38px;
            }
            QFrame#inputContainer:hover {
                border: 1px solid #334460;
                background-color: #151d2e;
            }
            QFrame#inputContainer:focus-within {
                border: 1px solid #3b82f6;
                background-color: #151d2e;
            }
            QLineEdit {
                color: #f1f5f9;
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }
            QPushButton#embeddedActionBtn {
                background: transparent;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                color: #cbd5e1;
            }
            QPushButton#embeddedActionBtn:hover {
                background-color: #243048;
                color: #ffffff;
            }
            QFrame#sizeCard {
                background-color: #131926;
                border: 1px solid #1f2b3e;
                border-radius: 10px;
                min-width: 175px;
            }
            QFrame#sizeCard:hover {
                border: 1px solid #2e3e5c;
                background-color: #161e30;
            }
            QPushButton#refreshBtn {
                background-color: #1d4ed8;
                border: none;
                border-radius: 4px;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#refreshBtn:hover {
                background-color: #2563eb;
            }
            QPushButton#downloadBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #7c3aed);
                border: 1px solid #6366f1;
                color: #ffffff;
                font-family: "Segoe UI", sans-serif;
                font-weight: bold;
                font-size: 13px;
                border-radius: 8px;
                padding: 8px 18px;
            }
            QPushButton#downloadBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #8b5cf6);
                border: 1px solid #a78bfa;
            }
            QPushButton#downloadBtn:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #6d28d9);
            }
            QPushButton#secondaryBtn {
                background-color: #131825;
                border: 1px solid #1f2a3e;
                color: #cbd5e1;
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
                font-weight: 600;
                border-radius: 8px;
                padding: 7px 16px;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #1e2638;
                color: #ffffff;
                border-color: #384666;
            }
            QPushButton#secondaryBtn:pressed {
                background-color: #10141f;
            }
            QPushButton#closeBtn {
                background-color: #131825;
                border: 1px solid #1f2a3e;
                color: #94a3b8;
                font-family: "Segoe UI", sans-serif;
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
            QPushButton#iconBtn {
                background-color: #131825;
                border: 1px solid #1f2a3e;
                border-radius: 6px;
                font-size: 12px;
                color: #94a3b8;
            }
            QPushButton#iconBtn:hover {
                background-color: #1e2638;
                color: #ffffff;
            }
        """
