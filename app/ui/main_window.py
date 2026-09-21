"""
Download Manager - Ana Kullanıcı Arayüzü Penceresi (main_window.py)

Download Manager tasarımına uygun olarak geliştirilen bu ana pencere;
koyu obsidyen neon teması, canlı arama çubuğu, kategori ağacı (All, Finished, Unfinished, Medya kategorileri),
responsive indirme tablosu (özel ikonlu dosya adı, mini ilerleme çubuklu durum hücresi, hız, kalan süre, tarih),
ayrıntılı indirme penceresi entegrasyonu ve sistem tepsisi arka plan desteğini bir arada sunar.
"""

import os
import subprocess
from typing import Dict, Optional, List, Any
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QTreeWidget, QTreeWidgetItem, QLineEdit, QProgressBar,
    QMenu, QStatusBar, QToolBar, QMessageBox, QInputDialog,
    QCheckBox, QSplitter, QFrame, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt, QSize, pyqtSlot, QPoint
from PyQt6.QtGui import QFont, QIcon, QAction, QColor, QKeySequence, QShortcut

from app.core.models import DownloadTask, DownloadStatus, TaskType
from app.core.task_manager import TaskManager
from app.server.bridge import ServerBridge
from app.ui.components.progress_card import DownloadCardWidget
from app.ui.compact_download_window import CompactDownloadWindow
from app.ui.download_detail_window import DownloadDetailWindow
from app.ui.media_dialog import MediaQualityDialog
from app.ui.settings_dialog import NetworkSettingsDialog
from app.ui.delete_dialog import DeleteDownloadsDialog
from app.core.autostart import is_autostart_enabled, set_autostart
from app.utils.icon_utils import get_app_icon, get_app_pixmap


class FileNameCellWidget(QWidget):
    """Tablo için solunda kategori ikonu, üstünde kalın dosya adı ve altında kategori etiketi olan hücre."""

    def __init__(self, filename: str, category: str, icon_str: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        # Kategori İkonu
        self.icon_lbl = QLabel(icon_str)
        self.icon_lbl.setFont(QFont("Segoe UI Emoji", 15))
        self.icon_lbl.setFixedSize(28, 28)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("background-color: #1a202e; border-radius: 6px; padding: 2px;")
        layout.addWidget(self.icon_lbl)

        # Başlık ve Kategori (Dikey Düzen)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.name_lbl = QLabel(filename)
        self.name_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.name_lbl.setStyleSheet("color: #f1f5f9;")
        text_layout.addWidget(self.name_lbl)

        self.cat_lbl = QLabel(category)
        self.cat_lbl.setFont(QFont("Segoe UI", 8))
        self.cat_lbl.setStyleSheet("color: #64748b; font-weight: 500;")
        text_layout.addWidget(self.cat_lbl)

        layout.addLayout(text_layout)
        layout.addStretch()

    def update_info(self, filename: str, category: str, icon_str: str) -> None:
        """Dosya adı, kategori ve ikonunu dinamik olarak günceller."""
        self.name_lbl.setText(filename)
        self.cat_lbl.setText(category)
        self.icon_lbl.setText(icon_str)


class StatusCellWidget(QWidget):
    """Tablo için indirme durumunu yüzde ve mini neon gradyan ilerleme çubuğuyla gösteren hücre."""

    def __init__(self, status: DownloadStatus, percent: float = 0.0, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        self.label = QLabel()
        self.label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.update_status(status.value, percent)

    def update_status(self, status_str: str, percent: float) -> None:
        pct = int(percent)
        status_upper = status_str.upper()

        if status_upper == DownloadStatus.DOWNLOADING.value:
            self.label.setText(f"{pct}% Downloading")
            self.label.setStyleSheet("color: #a855f7;")
            self.progress_bar.setValue(pct)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #1e2433;
                    border: none;
                    border-radius: 2px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #38bdf8, stop:0.5 #818cf8, stop:1 #c084fc);
                    border-radius: 2px;
                }
            """)
            self.progress_bar.setVisible(True)
        elif status_upper == DownloadStatus.PAUSED.value:
            self.label.setText(f"{pct}% Paused")
            self.label.setStyleSheet("color: #f59e0b;")
            self.progress_bar.setValue(pct)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #1e2433;
                    border: none;
                    border-radius: 2px;
                }
                QProgressBar::chunk {
                    background-color: #f59e0b;
                    border-radius: 2px;
                }
            """)
            self.progress_bar.setVisible(True)
        elif status_upper == DownloadStatus.COMPLETED.value:
            self.label.setText("Finished")
            self.label.setStyleSheet("color: #94a3b8;")
            self.progress_bar.setVisible(False)
        elif status_upper == DownloadStatus.QUEUED.value:
            self.label.setText("Added")
            self.label.setStyleSheet("color: #94a3b8;")
            self.progress_bar.setVisible(False)
        elif status_upper == DownloadStatus.CONNECTING.value:
            self.label.setText("Connecting...")
            self.label.setStyleSheet("color: #38bdf8;")
            self.progress_bar.setVisible(False)
        elif status_upper == DownloadStatus.MERGING.value:
            self.label.setText("Merging...")
            self.label.setStyleSheet("color: #818cf8;")
            self.progress_bar.setVisible(False)
        elif status_upper == DownloadStatus.FAILED.value:
            self.label.setText("Failed")
            self.label.setStyleSheet("color: #ef4444;")
            self.progress_bar.setVisible(False)
        else:
            self.label.setText(status_str.capitalize())
            self.label.setStyleSheet("color: #94a3b8;")
            self.progress_bar.setVisible(False)


class MainWindow(QMainWindow):
    """Download Manager modern PyQt6 ana penceresi."""

    def __init__(self, task_manager: TaskManager, bridge: ServerBridge, parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        self.bridge = bridge

        # Geriye dönük uyumluluk ve testler için kart referansları
        self.cards: Dict[str, DownloadCardWidget] = {}
        # task_id -> row_index eşlemesi
        self.task_rows: Dict[str, int] = {}
        # row_index -> task_id eşlemesi
        self.row_tasks: Dict[int, str] = {}
        # Açık detay pencereleri
        self.detail_windows: Dict[str, DownloadDetailWindow] = {}

        self.current_category_filter = "ALL"
        self.current_search_query = ""
        self._client_count = 0
        self._is_forced_exit = False
        self._tray_notified = False
        self._active_compact_windows: List[QWidget] = []
        self._active_media_windows: List[QWidget] = []
        self.tray_manager = None

        self.setWindowTitle("Download Manager")
        self.setWindowIcon(get_app_icon())
        self.resize(1080, 680)
        self.setMinimumSize(850, 520)

        self._init_ui()
        self._connect_signals()
        self._load_initial_tasks()

    @property
    def current_filter(self) -> str:
        """Geriye dönük uyumluluk ve testler için filtre anahtarı."""
        return self.current_category_filter

    @current_filter.setter
    def current_filter(self, val: str) -> None:
        self.current_category_filter = val

    def _init_ui(self) -> None:
        """Arayüz bileşenlerini ve responsive düzeni kurar."""
        # 1. Üst Menü Çubuğu (MenuBar)
        self._create_menubar()

        # 2. Üst Araç Çubuğu ve Arama (Toolbar)
        self._create_top_toolbar()

        # 3. Ana Gövde: Sol Kategori Ağacı + Sağ Responsive Tablo
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Bölücü (Splitter) ile responsive genişleme
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # --- SOL KENAR ÇUBUĞU (Kategori Ağacı) ---
        self.sidebar_tree = QTreeWidget()
        self.sidebar_tree.setObjectName("sidebarTree")
        self.sidebar_tree.setHeaderHidden(True)
        self.sidebar_tree.setFixedWidth(210)
        self.sidebar_tree.setIndentation(18)
        self.sidebar_tree.setAnimated(True)

        self._populate_sidebar_tree()
        self.sidebar_tree.itemClicked.connect(self._on_sidebar_item_clicked)
        self.sidebar_tree.currentItemChanged.connect(self._on_sidebar_current_item_changed)
        splitter.addWidget(self.sidebar_tree)

        # --- SAĞ İÇERİK ALANI (Tablo ve Boş Durum) ---
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        # Ana İndirme Tablosu
        self.downloads_table = QTableWidget(0, 7)
        self.downloads_table.setObjectName("downloadsTable")
        self.downloads_table.setHorizontalHeaderLabels([
            "", "Name", "Size", "Status", "Speed", "Time Left", "Date Added"
        ])
        self.downloads_table.verticalHeader().setVisible(False)
        self.downloads_table.setShowGrid(False)
        self.downloads_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.downloads_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.downloads_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.downloads_table.customContextMenuRequested.connect(self._show_context_menu)
        self.downloads_table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        # Klavyeden Delete tuşu kısayolu
        self.shortcut_delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.downloads_table)
        self.shortcut_delete.activated.connect(self._on_delete_clicked)

        # Sütun Genişlikleri ve Responsive Davranış
        header = self.downloads_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.downloads_table.setColumnWidth(0, 38)  # Checkbox sütunu

        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # İsim sütunu responsive esner
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.downloads_table.setColumnWidth(2, 155)  # Size (wider for "X.XX MB / Y.YY MB")
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.downloads_table.setColumnWidth(3, 145)  # Status
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.downloads_table.setColumnWidth(4, 95)  # Speed
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.downloads_table.setColumnWidth(5, 105)  # Time Left
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.downloads_table.setColumnWidth(6, 115)  # Date Added

        table_layout.addWidget(self.downloads_table)

        # Boş Durum (Empty State) Bilgisi
        self.empty_label = QLabel("🚀 No download tasks yet.\nClick '+ Add URL' above or start a download from your browser.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #64748b; font-size: 13px; padding: 60px; line-height: 1.6;")
        table_layout.addWidget(self.empty_label)

        splitter.addWidget(table_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

        # 4. Alt Durum Çubuğu (Status Bar)
        self._create_statusbar()

    def _create_menubar(self) -> None:
        """Üst Windows menü çubuğunu oluşturur."""
        menubar = self.menuBar()

        # File Menüsü
        file_menu = menubar.addMenu("File")
        act_add = QAction("➕ Add URL...", self)
        act_add.setShortcut("Ctrl+N")
        act_add.triggered.connect(lambda: self._open_add_dialog())
        file_menu.addAction(act_add)

        act_media = QAction("🎬 Add Video / Media...", self)
        act_media.setShortcut("Ctrl+M")
        act_media.triggered.connect(lambda: self._open_media_dialog())
        file_menu.addAction(act_media)

        file_menu.addSeparator()

        act_open_dir = QAction("📁 Open Downloads Folder", self)
        act_open_dir.triggered.connect(self._open_default_folder)
        file_menu.addAction(act_open_dir)

        file_menu.addSeparator()

        act_exit = QAction("✕ Exit", self)
        act_exit.triggered.connect(self._exit_app)
        file_menu.addAction(act_exit)

        # Tasks Menüsü
        tasks_menu = menubar.addMenu("Tasks")
        act_start_all = QAction("▶️ Start / Resume All", self)
        act_start_all.triggered.connect(self._resume_all_tasks)
        tasks_menu.addAction(act_start_all)

        act_pause_all = QAction("⏸️ Pause All", self)
        act_pause_all.triggered.connect(self._pause_all_tasks)
        tasks_menu.addAction(act_pause_all)

        act_stop_all = QAction("⏹️ Stop All", self)
        act_stop_all.triggered.connect(self._stop_all_tasks)
        tasks_menu.addAction(act_stop_all)

        tasks_menu.addSeparator()

        act_sel_all = QAction("☑️ Select All", self)
        act_sel_all.triggered.connect(lambda: self._select_all_rows(True))
        tasks_menu.addAction(act_sel_all)

        act_desel_all = QAction("◻️ Deselect All", self)
        act_desel_all.triggered.connect(lambda: self._select_all_rows(False))
        tasks_menu.addAction(act_desel_all)

        tasks_menu.addSeparator()

        act_delete = QAction("🗑️ Delete...", self)
        act_delete.setShortcut("Delete")
        act_delete.triggered.connect(self._on_delete_clicked)
        tasks_menu.addAction(act_delete)

        # Tools Menüsü
        tools_menu = menubar.addMenu("Tools")
        act_settings = QAction("⚙️ Network Settings...", self)
        act_settings.triggered.connect(self._open_settings_dialog)
        tools_menu.addAction(act_settings)

        tools_menu.addSeparator()

        self.act_autostart = QAction("🚀 Start with Windows (Autostart)", self, checkable=True)
        self.act_autostart.setChecked(is_autostart_enabled())
        self.act_autostart.triggered.connect(self._toggle_autostart)
        tools_menu.addAction(self.act_autostart)

        # Help Menüsü
        help_menu = menubar.addMenu("Help")
        act_about = QAction("ℹ️ About Download Manager", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _create_top_toolbar(self) -> None:
        """Üst modern araç çubuğu ve canlı arama kutusunu kurar."""
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        # Sağ tık menüsünü kapat (aksi hâlde menü çubuğunun yanında kare artefakt çıkar)
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.addToolBar(toolbar)

        # + Add URL Hap Butonu
        btn_add = QPushButton("➕ Add URL")
        btn_add.setObjectName("addUrlBtn")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(lambda: self._open_add_dialog())
        toolbar.addWidget(btn_add)

        # 🗑️ Delete Butonu — Add URL'nin hemen yanında
        self.btn_delete = QPushButton("🗑 Delete")
        self.btn_delete.setObjectName("toolDeleteBtn")
        self.btn_delete.setToolTip("Delete selected downloads (from list or permanently from disk)")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        toolbar.addWidget(self.btn_delete)

        # 🎬 Video Download Butonu
        btn_media = QPushButton("🎬 Video Download")
        btn_media.setObjectName("toolActionBtn")
        btn_media.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_media.clicked.connect(lambda: self._open_media_dialog())
        toolbar.addWidget(btn_media)

        toolbar.addSeparator()

        # Eylem Butonları
        btn_start_queue = QPushButton("▷ Start Queue")
        btn_start_queue.setObjectName("toolActionBtn")
        btn_start_queue.clicked.connect(self._resume_all_tasks)
        toolbar.addWidget(btn_start_queue)

        btn_stop_queue = QPushButton("□ Stop Queue")
        btn_stop_queue.setObjectName("toolActionBtn")
        btn_stop_queue.clicked.connect(self._pause_all_tasks)
        toolbar.addWidget(btn_stop_queue)

        btn_stop_all = QPushButton("□ Stop All")
        btn_stop_all.setObjectName("toolActionBtn")
        btn_stop_all.clicked.connect(self._stop_all_tasks)
        toolbar.addWidget(btn_stop_all)

        btn_settings = QPushButton("⚙ Settings")
        btn_settings.setObjectName("toolActionBtn")
        btn_settings.clicked.connect(self._open_settings_dialog)
        toolbar.addWidget(btn_settings)

        # Arama Kutusunu Sağa Yaslamak İçin Esnek Boşluk
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # 🔍 Canlı Arama Kutusu
        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("searchBar")
        self.search_bar.setPlaceholderText("🔍 Search in the List")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(self._on_search_text_changed)
        toolbar.addWidget(self.search_bar)

    def _populate_sidebar_tree(self) -> None:
        """Sol taraftaki hiyerarşik kategori ağacını doldurur."""
        self.sidebar_tree.clear()
        self.sidebar_items = {}

        # 1. Kök: All (Tümü)
        self.item_all = QTreeWidgetItem(self.sidebar_tree, ["📁 All"])
        self.item_all.setData(0, Qt.ItemDataRole.UserRole, "ALL")
        self.sidebar_items["ALL"] = (self.item_all, "📁 All")

        # Alt Kategoriler
        categories = [
            ("🖼️ Image", "Image"),
            ("🎵 Music", "Music"),
            ("🎬 Video", "Video"),
            ("📱 Apps", "Apps"),
            ("📄 Document", "Document"),
            ("🗜️ Compressed", "Compressed"),
            ("📦 Other", "Other")
        ]
        for label, cat_key in categories:
            child = QTreeWidgetItem(self.item_all, [label])
            child.setData(0, Qt.ItemDataRole.UserRole, cat_key)
            self.sidebar_items[cat_key] = (child, label)

        self.item_all.setExpanded(True)

        # 2. Finished
        self.item_finished = QTreeWidgetItem(self.sidebar_tree, ["📁 Finished"])
        self.item_finished.setData(0, Qt.ItemDataRole.UserRole, "FINISHED")
        self.sidebar_items["FINISHED"] = (self.item_finished, "📁 Finished")

        # 3. Unfinished
        self.item_unfinished = QTreeWidgetItem(self.sidebar_tree, ["📁 Unfinished"])
        self.item_unfinished.setData(0, Qt.ItemDataRole.UserRole, "UNFINISHED")
        self.sidebar_items["UNFINISHED"] = (self.item_unfinished, "📁 Unfinished")

        self.sidebar_tree.setCurrentItem(self.item_all)
        self.current_category_filter = "ALL"
        self._update_category_counts()

    def _load_initial_tasks(self) -> None:
        """TaskManager içinde önceden kaydedilmiş görevleri tabloya ekler."""
        all_tasks = self.task_manager.get_all_tasks()
        sorted_tasks = sorted(all_tasks, key=lambda t: getattr(t, "created_at", 0))
        for task in sorted_tasks:
            self._on_task_added(task)
        self._update_category_counts()
        self._apply_filter()

    def _update_category_counts(self) -> None:
        """Kenar çubuğundaki her kategorinin yanındaki sayaçları (sayıları) günceller."""
        if not hasattr(self, "sidebar_items") or not self.sidebar_items:
            return

        all_tasks = self.task_manager.get_all_tasks()
        counts = {
            "ALL": len(all_tasks),
            "FINISHED": sum(1 for t in all_tasks if t.status == DownloadStatus.COMPLETED),
            "UNFINISHED": sum(1 for t in all_tasks if t.status != DownloadStatus.COMPLETED),
            "Image": sum(1 for t in all_tasks if t.category == "Image"),
            "Music": sum(1 for t in all_tasks if t.category == "Music"),
            "Video": sum(1 for t in all_tasks if t.category == "Video"),
            "Apps": sum(1 for t in all_tasks if t.category == "Apps"),
            "Document": sum(1 for t in all_tasks if t.category == "Document"),
            "Compressed": sum(1 for t in all_tasks if t.category == "Compressed"),
            "Other": sum(1 for t in all_tasks if t.category == "Other"),
        }

        for key, (tree_item, base_label) in self.sidebar_items.items():
            cnt = counts.get(key, 0)
            tree_item.setText(0, f"{base_label} ({cnt})")

    def _create_statusbar(self) -> None:
        """Alt durum çubuğu ve ağ hızı metriklerini kurar."""
        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)

        # Sunucu Durum Rozeti
        self.status_server_lbl = QLabel("🟢 Server Listening (ws://127.0.0.1:6800)")
        self.status_server_lbl.setStyleSheet("color: #38ef7d; margin-left: 8px; font-weight: bold;")
        status_bar.addWidget(self.status_server_lbl)

        status_bar.addPermanentWidget(QLabel("|"))

        # Eklenti bağlantı sayısı
        self.status_clients_lbl = QLabel("🌐 Extension: 0")
        self.status_clients_lbl.setStyleSheet("color: #94a3b8; margin-right: 12px;")
        status_bar.addPermanentWidget(self.status_clients_lbl)

        status_bar.addPermanentWidget(QLabel("|"))

        # Toplam İndirme Hızı ve Görev Sayısı
        self.status_count_lbl = QLabel("☰ 0")
        self.status_count_lbl.setStyleSheet("color: #94a3b8; font-weight: bold; margin-right: 8px;")
        status_bar.addPermanentWidget(self.status_count_lbl)

        self.status_speed_lbl = QLabel("⚡ 0 B/s")
        self.status_speed_lbl.setStyleSheet("color: #38bdf8; font-weight: bold; margin-right: 12px;")
        status_bar.addPermanentWidget(self.status_speed_lbl)

    def _connect_signals(self) -> None:
        """TaskManager ve ServerBridge sinyallerini bağlar."""
        self.task_manager.task_added.connect(self._on_task_added)
        self.task_manager.task_progress.connect(self._on_task_progress)
        self.task_manager.task_chunk_progress.connect(self._on_task_chunk_progress)
        self.task_manager.task_status_changed.connect(self._on_task_status_changed)
        self.task_manager.task_finished.connect(self._on_task_finished)
        self.task_manager.task_error.connect(self._on_task_error)

        self.bridge.server_status_changed.connect(self._on_ws_status_changed)
        self.bridge.client_connected.connect(self._on_ws_client_connected)
        self.bridge.client_disconnected.connect(self._on_ws_client_disconnected)
        self.bridge.download_requested.connect(self._on_ext_download_requested)
        self.bridge.media_detected.connect(self._on_ext_media_detected)

    # ==================== Tablo ve Görev Yönetimi ====================

    @pyqtSlot(DownloadTask)
    def _on_task_added(self, task: DownloadTask) -> None:
        """Yeni görev eklendiğinde tabloya satır ve uyumluluk kartını ekler."""
        self.empty_label.setVisible(False)

        # Geriye dönük uyumluluk ve testler için card nesnesi
        card = DownloadCardWidget(task, parent=self)
        card.pause_requested.connect(self.task_manager.pause_task)
        card.resume_requested.connect(self.task_manager.resume_task)
        card.cancel_requested.connect(self._remove_task)
        self.cards[task.task_id] = card

        # Tabloya yeni satır ekle
        row = self.downloads_table.rowCount()
        self.downloads_table.insertRow(row)
        self.downloads_table.setRowHeight(row, 48)

        self.task_rows[task.task_id] = row
        self.row_tasks[row] = task.task_id

        # Sütun 0: Checkbox
        chk_item = QTableWidgetItem()
        chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        chk_item.setCheckState(Qt.CheckState.Unchecked)
        chk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        chk_item.setData(Qt.ItemDataRole.UserRole, task.task_id)
        self.downloads_table.setItem(row, 0, chk_item)

        # Sütun 1: İsim Hücresi (İkon + Ad + Kategori)
        name_cell = FileNameCellWidget(
            filename=task.filename,
            category=task.category,
            icon_str=task.category_icon
        )
        self.downloads_table.setCellWidget(row, 1, name_cell)

        # Sütun 2: Boyut
        size_item = QTableWidgetItem(task.formatted_total_size)
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        size_item.setForeground(QColor("#cbd5e1"))
        self.downloads_table.setItem(row, 2, size_item)

        # Sütun 3: Durum Hücresi (Yüzde + Mini Neon Çubuk)
        status_cell = StatusCellWidget(task.status, task.progress_percent)
        self.downloads_table.setCellWidget(row, 3, status_cell)

        # Sütun 4: Hız
        speed_item = QTableWidgetItem(task.formatted_speed if task.status == DownloadStatus.DOWNLOADING else "")
        speed_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        speed_item.setForeground(QColor("#38bdf8"))
        self.downloads_table.setItem(row, 4, speed_item)

        # Sütun 5: Kalan Süre
        eta_item = QTableWidgetItem(task.formatted_eta if task.status == DownloadStatus.DOWNLOADING else "")
        eta_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        eta_item.setForeground(QColor("#94a3b8"))
        self.downloads_table.setItem(row, 5, eta_item)

        # Sütun 6: Eklenme Tarihi
        date_item = QTableWidgetItem(task.formatted_date_added)
        date_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        date_item.setForeground(QColor("#64748b"))
        self.downloads_table.setItem(row, 6, date_item)

        self._apply_filter()
        self._update_total_metrics()
        self._update_category_counts()

    @pyqtSlot(dict)
    def _on_task_progress(self, data: dict) -> None:
        """Progress bilgisini hem uyumluluk kartına hem de tablodaki hücrelere yansıtır."""
        task_id = data.get("task_id")
        if task_id in self.cards:
            self.cards[task_id].update_progress(data)

        row = self.task_rows.get(task_id)
        if row is not None and row < self.downloads_table.rowCount():
            pct = data.get("percent", 0.0)
            status_widget = self.downloads_table.cellWidget(row, 3)
            if isinstance(status_widget, StatusCellWidget):
                status_widget.update_status(DownloadStatus.DOWNLOADING.value, pct)

            task = self.task_manager.get_task(task_id)

            # Sütun 2: Canlı indirilen / toplam boyutu göster (X.XX MB / Y.YY MB)
            size_item = self.downloads_table.item(row, 2)
            if size_item:
                if task:
                    size_text = task.formatted_size_progress
                else:
                    # Fallback: sinyal verisinden hesapla
                    dl = data.get("downloaded_bytes", 0)
                    tot = data.get("total_bytes", 0)
                    if tot > 0:
                        from app.core.models import DownloadTask as _DT
                        size_text = f"{_DT._format_bytes(_DT, dl)} / {_DT._format_bytes(_DT, tot)}"
                    elif dl > 0:
                        from app.core.models import DownloadTask as _DT
                        size_text = _DT._format_bytes(_DT, dl)
                    else:
                        size_text = "Unknown"
                size_item.setText(size_text)

            speed_item = self.downloads_table.item(row, 4)
            if speed_item:
                speed_item.setText(data.get("speed_str", ""))

            eta_item = self.downloads_table.item(row, 5)
            if eta_item:
                eta_str = data.get("eta_str", "")
                eta_item.setText(f"{eta_str} left" if eta_str and eta_str != "--:--" else "")

        self._update_total_metrics()

    @pyqtSlot(str, int, int, int)
    def _on_task_chunk_progress(self, task_id: str, chunk_id: int, downloaded: int, total: int) -> None:
        """Parça ilerlemesini karta iletir."""
        if task_id in self.cards:
            self.cards[task_id].update_chunk_progress(chunk_id, downloaded, total)

    @pyqtSlot(str, str)
    def _on_task_status_changed(self, task_id: str, status_str: str) -> None:
        """Durum değişimini tabloya ve karta yansıtır."""
        if task_id in self.cards:
            self.cards[task_id].update_status(status_str)

        row = self.task_rows.get(task_id)
        if row is not None and row < self.downloads_table.rowCount():
            task = self.task_manager.get_task(task_id)
            pct = task.progress_percent if task else 0.0
            status_widget = self.downloads_table.cellWidget(row, 3)
            if isinstance(status_widget, StatusCellWidget):
                status_widget.update_status(status_str, pct)
                self._update_category_counts()

            if task:
                name_cell = self.downloads_table.cellWidget(row, 1)
                if isinstance(name_cell, FileNameCellWidget):
                    name_cell.update_info(task.filename, task.category, task.category_icon)

                size_item = self.downloads_table.item(row, 2)
                if size_item:
                    # Aktif veya duraklatılmış indirmelerde "indirilen / toplam" formatı
                    active_statuses = (
                        DownloadStatus.DOWNLOADING.value,
                        DownloadStatus.PAUSED.value,
                        DownloadStatus.CONNECTING.value,
                        DownloadStatus.MERGING.value,
                    )
                    if status_str in active_statuses and task.downloaded_size > 0:
                        size_item.setText(task.formatted_size_progress)
                    else:
                        size_item.setText(task.formatted_total_size)

            if status_str != DownloadStatus.DOWNLOADING.value:
                speed_item = self.downloads_table.item(row, 4)
                if speed_item:
                    speed_item.setText("")
                eta_item = self.downloads_table.item(row, 5)
                if eta_item:
                    eta_item.setText("")

        self._apply_filter()
        self._update_total_metrics()

    @pyqtSlot(str, str)
    def _on_task_finished(self, task_id: str, final_path: str) -> None:
        """Tamamlanan görevi günceller."""
        task = self.task_manager.get_task(task_id)
        if task:
            # Diskteki dosya boyutunu ve adını teyit et
            if final_path and os.path.exists(final_path):
                task.filename = os.path.basename(final_path)
                real_size = os.path.getsize(final_path)
                if real_size > 0:
                    task.total_size = real_size
                    task.downloaded_size = real_size
            elif task.total_size <= 0 and task.downloaded_size > 0:
                task.total_size = task.downloaded_size

        if task_id in self.cards:
            self.cards[task_id].update_status(DownloadStatus.COMPLETED.value)
            if task and hasattr(self.cards[task_id], "update_task_info"):
                self.cards[task_id].update_task_info(task)

        row = self.task_rows.get(task_id)
        if row is not None and row < self.downloads_table.rowCount():
            # Sütun 1: İsim, Kategori ve İkon güncelle
            name_cell = self.downloads_table.cellWidget(row, 1)
            if isinstance(name_cell, FileNameCellWidget) and task:
                name_cell.update_info(task.filename, task.category, task.category_icon)

            # Sütun 2: Boyut güncelle!
            size_item = self.downloads_table.item(row, 2)
            if size_item and task:
                size_item.setText(task.formatted_total_size)

            status_widget = self.downloads_table.cellWidget(row, 3)
            if isinstance(status_widget, StatusCellWidget):
                status_widget.update_status(DownloadStatus.COMPLETED.value, 100.0)

            speed_item = self.downloads_table.item(row, 4)
            if speed_item:
                speed_item.setText("")
            eta_item = self.downloads_table.item(row, 5)
            if eta_item:
                eta_item.setText("")

        self._apply_filter()
        self._update_total_metrics()

    @pyqtSlot(str, str)
    def _on_task_error(self, task_id: str, error_msg: str) -> None:
        """Hata durumunu yansıtır."""
        if task_id in self.cards:
            self.cards[task_id].update_status(DownloadStatus.FAILED.value)

        row = self.task_rows.get(task_id)
        if row is not None and row < self.downloads_table.rowCount():
            status_widget = self.downloads_table.cellWidget(row, 3)
            if isinstance(status_widget, StatusCellWidget):
                status_widget.update_status(DownloadStatus.FAILED.value, 0.0)

    def _get_selected_task_ids(self) -> List[str]:
        """İşaretli (checkbox) veya seçili satırlardaki tüm task_id'leri döndürür."""
        selected_ids: List[str] = []

        # 1. Checkbox sütunu (0. sütun) işaretlenmiş satırlar
        for r in range(self.downloads_table.rowCount()):
            item = self.downloads_table.item(r, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                tid = item.data(Qt.ItemDataRole.UserRole) or self.row_tasks.get(r)
                if tid and tid not in selected_ids:
                    selected_ids.append(tid)

        # 2. Eğer onay kutusu işaretli satır yoksa, seçili satırlar (highlight)
        if not selected_ids:
            for item in self.downloads_table.selectedItems():
                r = item.row()
                tid = self.row_tasks.get(r)
                if tid and tid not in selected_ids:
                    selected_ids.append(tid)

        # 3. Eğer yine boşsa, aktif odaklanmış satır
        if not selected_ids:
            curr_row = self.downloads_table.currentRow()
            if curr_row >= 0:
                tid = self.row_tasks.get(curr_row)
                if tid and tid not in selected_ids:
                    selected_ids.append(tid)

        return selected_ids

    def _on_delete_clicked(self) -> None:
        """Kullanıcının seçtiği indirmeleri silmek için DeleteDownloadsDialog onay penceresini açar."""
        task_ids = self._get_selected_task_ids()
        if not task_ids:
            QMessageBox.information(
                self,
                "Delete downloads",
                "No downloads selected.\nPlease select downloads from the list using the checkbox or row selection."
            )
            return

        dialog = DeleteDownloadsDialog(count=len(task_ids), parent=self)
        if dialog.exec() == DeleteDownloadsDialog.DialogCode.Accepted:
            delete_files = dialog.delete_from_disk
            self._delete_tasks_batch(task_ids, delete_files=delete_files)

    def _delete_tasks_batch(self, task_ids: List[str], delete_files: bool = False) -> None:
        """Birden fazla görevi bellekten, tablodan ve (seçildiyse) diskten siler."""
        rows_to_remove = []
        for tid in task_ids:
            # 1. TaskManager'dan kaldır (ve gerekirse dosyaları diskten sil)
            self.task_manager.remove_task(tid, delete_file=delete_files)

            # 2. Uyumluluk kartını kaldır
            if tid in self.cards:
                card = self.cards.pop(tid)
                card.deleteLater()

            # 3. Detay penceresini kapat
            if tid in self.detail_windows:
                win = self.detail_windows.pop(tid)
                win.close()

            # 4. Tablodaki satır indeksini kaydet
            row = self.task_rows.get(tid)
            if row is not None:
                rows_to_remove.append(row)

        # Tablodan silerken indeks kaymalarını engellemek için ters sırada sil
        for r in sorted(set(rows_to_remove), reverse=True):
            if r < self.downloads_table.rowCount():
                self.downloads_table.removeRow(r)

        self._rebuild_row_indexes()
        self._apply_filter()
        self._update_total_metrics()
        self._update_category_counts()

    def _remove_task(self, task_id: str, delete_file: bool = False) -> None:
        """Tek bir görevi iptal edip tablodan ve listeden siler."""
        self._delete_tasks_batch([task_id], delete_files=delete_file)

    def _rebuild_row_indexes(self) -> None:
        """Satır silinmelerinden sonra indeks haritasını yeniden oluşturur."""
        self.task_rows.clear()
        self.row_tasks.clear()
        for r in range(self.downloads_table.rowCount()):
            chk_item = self.downloads_table.item(r, 0)
            tid = chk_item.data(Qt.ItemDataRole.UserRole) if chk_item else None
            if not tid:
                # Hücre 1'deki task_id veya card eşlemesiyle bul
                for t_id, card in self.cards.items():
                    name_cell = self.downloads_table.cellWidget(r, 1)
                    if isinstance(name_cell, FileNameCellWidget) and name_cell.name_lbl.text() == card.task.filename:
                        tid = t_id
                        break
            if tid:
                self.task_rows[tid] = r
                self.row_tasks[r] = tid

    def _update_total_metrics(self) -> None:
        """Toplam aktif hız ve görev sayısını durum çubuğuna yansıtır."""
        total_speed_bps = 0.0
        active_count = 0
        all_tasks = self.task_manager.get_all_tasks()

        for task in all_tasks:
            if task.status == DownloadStatus.DOWNLOADING:
                total_speed_bps += task.speed_bytes_per_sec
                active_count += 1

        if total_speed_bps < 1024:
            speed_str = f"{total_speed_bps:.1f} B/s"
        elif total_speed_bps < 1024 * 1024:
            speed_str = f"{total_speed_bps / 1024:.1f} KB/s"
        else:
            speed_str = f"{total_speed_bps / (1024 * 1024):.2f} MB/s"

        self.status_count_lbl.setText(f"☰ {len(all_tasks)}")
        self.status_speed_lbl.setText(f"⚡ {speed_str}")

    # ==================== Filtreleme ve Arama ====================

    def _on_sidebar_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Kategori ağacında tıklanan öğeye göre tabloyu filtreler."""
        if not item:
            return
        cat_key = item.data(0, Qt.ItemDataRole.UserRole)
        if cat_key:
            self.current_category_filter = cat_key
            self._apply_filter()

    def _on_sidebar_current_item_changed(self, current: Optional[QTreeWidgetItem], previous: Optional[QTreeWidgetItem]) -> None:
        """Klavye veya programatik seçim değişimini filtreye yansıtır."""
        if not current:
            return
        cat_key = current.data(0, Qt.ItemDataRole.UserRole)
        if cat_key:
            self.current_category_filter = cat_key
            self._apply_filter()

    def _on_search_text_changed(self, text: str) -> None:
        """Arama kutusuna yazıldıkça anında filtreleme yapar."""
        self.current_search_query = text.strip().lower()
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Kategori seçimi ve arama metnini birleştirerek satırları gizler/gösterir."""
        visible_count = 0
        query = self.current_search_query

        for task_id, card in self.cards.items():
            task = card.task
            matches_cat = True

            # Kategori / Durum filtresi
            if self.current_category_filter == "ALL":
                matches_cat = True
            elif self.current_category_filter == "FINISHED":
                matches_cat = (task.status == DownloadStatus.COMPLETED)
            elif self.current_category_filter == "UNFINISHED":
                matches_cat = (task.status != DownloadStatus.COMPLETED)
            elif self.current_category_filter == "DOWNLOADING":
                matches_cat = (task.status == DownloadStatus.DOWNLOADING)
            elif self.current_category_filter == "PAUSED":
                matches_cat = (task.status == DownloadStatus.PAUSED)
            elif self.current_category_filter == "COMPLETED":
                matches_cat = (task.status == DownloadStatus.COMPLETED)
            elif self.current_category_filter == "MEDIA":
                matches_cat = (task.task_type in (TaskType.MEDIA_VIDEO, TaskType.MEDIA_AUDIO))
            else:
                matches_cat = (task.category.lower() == self.current_category_filter.lower())

            # Arama filtresi
            matches_search = True
            if query:
                matches_search = (query in task.filename.lower() or query in task.category.lower())

            is_visible = matches_cat and matches_search

            # Tablo satırını gizle/göster
            row = self.task_rows.get(task_id)
            if row is not None and row < self.downloads_table.rowCount():
                self.downloads_table.setRowHidden(row, not is_visible)

            # Testler ve kart uyumluluğu için
            card.setVisible(is_visible)

            if is_visible:
                visible_count += 1

        if len(self.cards) == 0:
            self.empty_label.setText("🚀 No download tasks yet.\nClick '+ Add URL' above or start a download from your browser.")
        elif visible_count == 0:
            cat_display = self.current_category_filter
            self.empty_label.setText(
                f"📁 No downloads found in '{cat_display}' category.\n"
                f"Select 'All' from the sidebar to view all {len(self.cards)} download(s)."
            )

        self.empty_label.setVisible(visible_count == 0)
        self.downloads_table.setVisible(visible_count > 0 or len(self.cards) > 0)

    # ==================== Kullanıcı Etkileşimleri ve Diyaloglar ====================

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        """Satıra çift tıklandığında ayrıntılı detay penceresini açar."""
        task_id = self.row_tasks.get(row)
        if not task_id:
            return

        task = self.task_manager.get_task(task_id)
        if not task:
            return

        self._open_task_detail(task)

    def _open_task_detail(self, task: DownloadTask) -> None:
        """Detay penceresini oluşturur veya öne getirir."""
        if task.task_id in self.detail_windows and self.detail_windows[task.task_id].isVisible():
            win = self.detail_windows[task.task_id]
            win.activateWindow()
            win.raise_()
            return

        detail_win = DownloadDetailWindow(task=task, task_manager=self.task_manager, parent=self)
        self.detail_windows[task.task_id] = detail_win
        detail_win.show()
        detail_win.activateWindow()

    def _show_context_menu(self, pos: QPoint) -> None:
        """Tablo üzerinde sağ tıklama menüsü."""
        item = self.downloads_table.itemAt(pos)
        if not item:
            return

        row = item.row()
        task_id = self.row_tasks.get(row)
        if not task_id:
            return
        task = self.task_manager.get_task(task_id)
        if not task:
            return

        menu = QMenu(self)

        act_detail = menu.addAction("🔍 View Details")
        act_detail.triggered.connect(lambda: self._open_task_detail(task))

        menu.addSeparator()

        if task.status == DownloadStatus.DOWNLOADING:
            act_pause = menu.addAction("⏸ Pause")
            act_pause.triggered.connect(lambda: self.task_manager.pause_task(task.task_id))
        else:
            act_resume = menu.addAction("▶ Resume")
            act_resume.triggered.connect(lambda: self.task_manager.resume_task(task.task_id))

        act_open_file = menu.addAction("📁 Open File / Show in Folder")
        act_open_file.triggered.connect(lambda: self._open_task_folder(task))

        menu.addSeparator()

        act_delete = menu.addAction("🗑 Delete Task...")
        act_delete.triggered.connect(self._on_delete_clicked)

        menu.exec(self.downloads_table.viewport().mapToGlobal(pos))

    def _open_task_folder(self, task: DownloadTask) -> None:
        """Dosyanın bulunduğu klasörü Windows Gezgini'nde açar ve dosyayı seçer."""
        if os.path.exists(task.final_file_path):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(task.final_file_path)}"')
        else:
            dest = os.path.normpath(task.destination_folder)
            os.makedirs(dest, exist_ok=True)
            subprocess.Popen(f'explorer "{dest}"')

    def _select_all_rows(self, checked: bool) -> None:
        """Tüm satırlardaki onay kutularını işaretler veya kaldırır."""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for r in range(self.downloads_table.rowCount()):
            item = self.downloads_table.item(r, 0)
            if item:
                item.setCheckState(state)

    def _open_add_dialog(self, initial_url: str = "", filename: str = "") -> None:
        """Referanstaki kompakt yüzen indirme penceresini açar."""
        # Halihazırda aynı URL için açık olan pencere varsa tekrar açmak yerine öne getir
        if initial_url:
            clean_url = initial_url.strip()
            for w in list(self._active_compact_windows):
                try:
                    if hasattr(w, "url_input") and w.url_input.text().strip() == clean_url:
                        w.setWindowState(w.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
                        w.show()
                        w.raise_()
                        w.activateWindow()
                        return
                except Exception:
                    pass

        compact_win = CompactDownloadWindow(
            task_manager=self.task_manager,
            initial_url=initial_url,
            initial_filename=filename,
            default_save_dir=self.task_manager.default_download_dir,
            parent=None
        )
        compact_win.destroyed.connect(
            lambda: self._active_compact_windows.remove(compact_win)
            if compact_win in self._active_compact_windows
            else None
        )
        compact_win.setWindowState(compact_win.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        compact_win.show()
        compact_win.raise_()
        compact_win.activateWindow()
        self._active_compact_windows.append(compact_win)

    def _open_media_dialog(
        self,
        initial_url: str = "",
        title: str = "",
        headers: Optional[Dict[str, str]] = None,
        page_url: Optional[str] = None
    ) -> None:
        """Video ve medya indirme diyaloğunu açar."""
        if not initial_url:
            url, ok = QInputDialog.getText(self, "Download Video / Media", "Enter media URL (YouTube, HLS m3u8, etc.):")
            if not ok or not url.strip():
                return
            initial_url = url.strip()

        # Halihazırda aynı medya URL'si için açık olan diyalog varsa öne getir
        if initial_url:
            clean_url = initial_url.strip()
            for d in list(self._active_media_windows):
                try:
                    if hasattr(d, "url") and d.url.strip() == clean_url:
                        d.setWindowState(d.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
                        d.show()
                        d.raise_()
                        d.activateWindow()
                        return
                except Exception:
                    pass

        dialog = MediaQualityDialog(
            url=initial_url,
            initial_title=title,
            default_save_dir=self.task_manager.default_download_dir,
            headers=headers,
            page_url=page_url,
            task_manager=self.task_manager,
            parent=None
        )
        self._active_media_windows.append(dialog)
        dialog.destroyed.connect(lambda: self._active_media_windows.remove(dialog) if dialog in self._active_media_windows else None)
        dialog.setWindowState(dialog.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()


    def _pause_all_tasks(self) -> None:
        """Tüm aktif indirmeleri duraklatır."""
        for task in self.task_manager.get_all_tasks():
            if task.status == DownloadStatus.DOWNLOADING:
                self.task_manager.pause_task(task.task_id)

    def _resume_all_tasks(self) -> None:
        """Tüm duraklatılmış görevleri başlatır."""
        for task in self.task_manager.get_all_tasks():
            if task.status in (DownloadStatus.PAUSED, DownloadStatus.QUEUED):
                self.task_manager.resume_task(task.task_id)

    def _stop_all_tasks(self) -> None:
        """Tüm görevleri durdurur."""
        self._pause_all_tasks()

    def _open_default_folder(self) -> None:
        """İndirilenler klasörünü açar."""
        dest = os.path.normpath(self.task_manager.default_download_dir)
        os.makedirs(dest, exist_ok=True)
        subprocess.Popen(f'explorer "{dest}"')

    def _toggle_autostart(self) -> None:
        """Windows ile başlatmayı açar veya kapatır."""
        new_state = not is_autostart_enabled()
        set_autostart(new_state, run_minimized=True)
        self.act_autostart.setChecked(new_state)
        if self.tray_manager and hasattr(self.tray_manager, "action_autostart"):
            self.tray_manager.action_autostart.setChecked(new_state)

    def _open_settings_dialog(self) -> None:
        """Kullanıcı referans görseline uygun Ağ Ayarları (Network settings) penceresini açar."""
        dialog = NetworkSettingsDialog(parent=self)
        dialog.exec()

    def _show_about(self) -> None:
        """Hakkında penceresini gösterir."""
        from app import __version__
        QMessageBox.about(
            self,
            "About Download Manager",
            "<h3>Download Manager</h3>"
            "<p>Advanced Multi-Segment Download Manager & Media Sniffer</p>"
            f"<p>Version {__version__} Pro</p>"
        )

    def _exit_app(self) -> None:
        """Uygulamadan tamamen çıkar."""
        self._is_forced_exit = True
        if hasattr(self, "tray_manager") and self.tray_manager and hasattr(self.tray_manager, "tray_icon"):
            try:
                self.tray_manager.tray_icon.hide()
            except Exception:
                pass
        self.close()
        QApplication.quit()

    # ==================== WebSocket Sinyal Dinleyicileri ====================

    def _on_ws_status_changed(self, is_running: bool, msg: str) -> None:
        if is_running:
            self.status_server_lbl.setText("🟢 Server Listening (ws://127.0.0.1:6800)")
            self.status_server_lbl.setStyleSheet("color: #38ef7d; margin-left: 8px; font-weight: bold;")
        else:
            self.status_server_lbl.setText("🔴 Server Stopped")
            self.status_server_lbl.setStyleSheet("color: #f87171; margin-left: 8px; font-weight: bold;")

    def _on_ws_client_connected(self, client_id: str) -> None:
        self._client_count += 1
        self.status_clients_lbl.setText(f"🌐 Extension: {self._client_count}")
        self.status_server_lbl.setText("🟢 Server Listening (ws://127.0.0.1:6800)")
        self.status_server_lbl.setStyleSheet("color: #38ef7d; margin-left: 8px; font-weight: bold;")

    def _on_ws_client_disconnected(self, client_id: str) -> None:
        self._client_count = max(0, self._client_count - 1)
        self.status_clients_lbl.setText(f"🌐 Extension: {self._client_count}")

    def _on_ext_download_requested(self, data: dict) -> None:
        """Tarayıcıdan indirme isteği geldiğinde kompakt pencereyi açar."""
        url = data.get("url", "")
        filename = data.get("filename", "")
        self._open_add_dialog(initial_url=url, filename=filename)

    def _on_ext_media_detected(self, data: dict) -> None:
        """Tarayıcıdan video akışı yakalandığında indirme penceresini ana uygulamadan bağımsız açar."""
        url = data.get("url") or data.get("media_src") or data.get("page_url") or ""
        page_url = data.get("page_url") or url
        title = data.get("title", "")
        referrer = data.get("referrer", "")
        headers = {}
        if referrer:
            headers["Referer"] = referrer
        if data.get("user_agent"):
            headers["User-Agent"] = data.get("user_agent")
        self._open_media_dialog(initial_url=url, title=title, headers=headers, page_url=page_url)

    def closeEvent(self, event) -> None:
        """Pencere kapatıldığında arka planda çalışmaya devam eder."""
        if not self._is_forced_exit and self.tray_manager:
            event.ignore()
            self.hide()
            if not self._tray_notified:
                self.tray_manager.show_notification(
                    "Download Manager",
                    "Application is running in the background (system tray). Click the icon to restore."
                )
                self._tray_notified = True
        else:
            if hasattr(self, "tray_manager") and self.tray_manager and hasattr(self.tray_manager, "tray_icon"):
                try:
                    self.tray_manager.tray_icon.hide()
                except Exception:
                    pass
            event.accept()
            if self._is_forced_exit:
                QApplication.quit()
