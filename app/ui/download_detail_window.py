"""
Download Manager - Ayrıntılı İndirme ve Parça Bilgisi Penceresi (download_detail_window.py)

Bu pencere, görev detaylarını, canlı neon ilerleme çubuğunu, parça/bağlantı (chunk) segment
görselleştiricisini (8 segment), parça bazlı indirme tablosunu ve görev ayarlarını barındırır.
"""

import os
from typing import Dict, Any, List, Optional
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QTabWidget, QGridLayout, QFrame, QSpinBox,
    QLineEdit, QCheckBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont, QColor

from app.core.models import DownloadTask, DownloadStatus, ChunkInfo
from app.core.task_manager import TaskManager
from app.utils.icon_utils import get_app_icon, get_app_pixmap


class DownloadDetailWindow(QDialog):
    """Ayrıntılı görev izleme ve bağlantı segmenti penceresi."""

    def __init__(self, task: DownloadTask, task_manager: TaskManager, parent=None):
        super().__init__(parent)
        self.task = task
        self.task_manager = task_manager

        self.setObjectName("downloadDetailDialog")
        self.setWindowIcon(get_app_icon())
        self.resize(520, 560)
        self.setMinimumSize(460, 480)

        self._segment_boxes: List[QLabel] = []
        self._is_part_info_expanded = True

        self._init_ui()
        self._update_all_from_task()
        self._connect_signals()

    def _init_ui(self) -> None:
        """Arayüz bileşenlerini ve sekmeleri kurar."""
        self.setWindowTitle(f"{int(self.task.progress_percent)}%-{self.task.filename}")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # 1. Başlık Çubuğu: Logo + Dosya Adı
        header_layout = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_app_pixmap(24))
        header_layout.addWidget(icon_lbl)

        self.title_lbl = QLabel(f"{int(self.task.progress_percent)}%-{self.task.filename}")
        self.title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet("color: #f1f5f9;")
        header_layout.addWidget(self.title_lbl)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # 2. Sekmeler (Info / Settings)
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("detailTabs")

        # --- INFO SEKME ---
        info_tab = QWidget()
        info_layout = QVBoxLayout(info_tab)
        info_layout.setContentsMargins(10, 14, 10, 10)
        info_layout.setSpacing(12)

        # Metadata Grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        lbl_style = "color: #94a3b8; font-weight: 500; font-size: 12px;"
        val_style = "color: #f8fafc; font-weight: 600; font-size: 12px;"

        row = 0
        # Name
        grid.addWidget(QLabel("Name:", styleSheet=lbl_style), row, 0)
        self.name_val = QLabel(self.task.filename)
        self.name_val.setStyleSheet(val_style)
        self.name_val.setWordWrap(True)
        grid.addWidget(self.name_val, row, 1)

        row += 1
        # Status
        grid.addWidget(QLabel("Status:", styleSheet=lbl_style), row, 0)
        self.status_val = QLabel(self.task.status.value)
        self.status_val.setStyleSheet(val_style)
        grid.addWidget(self.status_val, row, 1)

        row += 1
        # Size
        grid.addWidget(QLabel("Size:", styleSheet=lbl_style), row, 0)
        self.size_val = QLabel(self.task.formatted_total_size)
        self.size_val.setStyleSheet(val_style)
        grid.addWidget(self.size_val, row, 1)

        row += 1
        # Downloaded
        grid.addWidget(QLabel("Downloaded:", styleSheet=lbl_style), row, 0)
        self.downloaded_val = QLabel(self._format_bytes(self.task.downloaded_size))
        self.downloaded_val.setStyleSheet(val_style)
        grid.addWidget(self.downloaded_val, row, 1)

        row += 1
        # Speed
        grid.addWidget(QLabel("Speed:", styleSheet=lbl_style), row, 0)
        self.speed_val = QLabel(self.task.formatted_speed)
        self.speed_val.setStyleSheet(val_style)
        grid.addWidget(self.speed_val, row, 1)

        row += 1
        # Remaining Time
        grid.addWidget(QLabel("Remaining Time:", styleSheet=lbl_style), row, 0)
        self.eta_val = QLabel(self.task.formatted_eta)
        self.eta_val.setStyleSheet(val_style)
        grid.addWidget(self.eta_val, row, 1)

        row += 1
        # Resume Support
        grid.addWidget(QLabel("Resume Support:", styleSheet=lbl_style), row, 0)
        self.resume_val = QLabel("Yes" if self.task.is_resumable else "Checking...")
        self.resume_val.setStyleSheet("color: #22c55e; font-weight: bold;" if self.task.is_resumable else "color: #94a3b8;")
        grid.addWidget(self.resume_val, row, 1)

        info_layout.addLayout(grid)

        # Neon Parlak İlerleme Çubuğu
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("neonProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(int(self.task.progress_percent))
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setStyleSheet("""
            QProgressBar#neonProgressBar {
                background-color: #1a202c;
                border-radius: 6px;
                border: none;
            }
            QProgressBar#neonProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #38bdf8, stop:0.5 #818cf8, stop:1 #c084fc);
                border-radius: 6px;
            }
        """)
        info_layout.addWidget(self.progress_bar)

        # Kontrol Butonları ve Part Info Aç/Kapa
        ctrl_layout = QHBoxLayout()
        self.toggle_part_btn = QPushButton("˄ Part Info")
        self.toggle_part_btn.setFlat(True)
        self.toggle_part_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_part_btn.setStyleSheet("color: #cbd5e1; font-weight: bold; border: none; text-align: left; padding: 4px 0;")
        self.toggle_part_btn.clicked.connect(self._toggle_part_info)
        ctrl_layout.addWidget(self.toggle_part_btn)

        ctrl_layout.addStretch()

        self.pause_resume_btn = QPushButton("⏸ Pause" if self.task.status == DownloadStatus.DOWNLOADING else "▶ Resume")
        self.pause_resume_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_resume_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 5px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }
        """)
        self.pause_resume_btn.clicked.connect(self._toggle_pause_resume)
        ctrl_layout.addWidget(self.pause_resume_btn)

        self.close_btn = QPushButton("✕ Close")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 5px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #ef4444;
                color: #ffffff;
                border-color: #dc2626;
            }
        """)
        self.close_btn.clicked.connect(self.close)
        ctrl_layout.addWidget(self.close_btn)

        info_layout.addLayout(ctrl_layout)

        # 3. Parça Bilgisi Paneli (Açılır / Kapanır)
        self.part_container = QWidget()
        part_layout = QVBoxLayout(self.part_container)
        part_layout.setContentsMargins(0, 4, 0, 0)
        part_layout.setSpacing(10)

        # Canlı Yeşil Segment Göstergeleri (8 Segment)
        segments_layout = QHBoxLayout()
        segments_layout.setSpacing(6)
        for i in range(8):
            box = QLabel()
            box.setFixedHeight(14)
            box.setSizePolicy(QSizePolicy_Expanding := box.sizePolicy().horizontalPolicy(), box.sizePolicy().verticalPolicy())
            box.setStyleSheet("background-color: #1e293b; border-radius: 3px;")
            self._segment_boxes.append(box)
            segments_layout.addWidget(box)
        part_layout.addLayout(segments_layout)

        # Parça Tablosu (# | Status | Downloaded | Total)
        self.part_table = QTableWidget(0, 4)
        self.part_table.setHorizontalHeaderLabels(["#", "Status", "Downloaded", "Total"])
        self.part_table.verticalHeader().setVisible(False)
        self.part_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.part_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.part_table.setShowGrid(False)
        self.part_table.setStyleSheet("""
            QTableWidget {
                background-color: #11141e;
                border: 1px solid #1e2538;
                border-radius: 6px;
                gridline-color: transparent;
                color: #cbd5e1;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #161b2a;
                color: #94a3b8;
                border: none;
                padding: 5px;
                font-weight: bold;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px 6px;
                border-bottom: 1px solid #171f30;
            }
        """)
        self.part_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.part_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.part_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.part_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        part_layout.addWidget(self.part_table)
        info_layout.addWidget(self.part_container)

        self.tab_widget.addTab(info_tab, "ⓘ Info")

        # --- SETTINGS SEKME ---
        settings_tab = QWidget()
        set_layout = QVBoxLayout(settings_tab)
        set_layout.setContentsMargins(16, 16, 16, 16)
        set_layout.setSpacing(14)

        # İndirme Klasörü
        folder_group = QVBoxLayout()
        folder_lbl = QLabel("Destination Download Folder:")
        folder_lbl.setStyleSheet(lbl_style)
        folder_group.addWidget(folder_lbl)

        folder_row = QHBoxLayout()
        self.folder_input = QLineEdit(self.task.destination_folder)
        self.folder_input.setReadOnly(True)
        self.folder_input.setStyleSheet("background-color: #171b26; border: 1px solid #232b3e; border-radius: 6px; padding: 6px; color: #f1f5f9;")
        folder_row.addWidget(self.folder_input)

        btn_browse = QPushButton("📁")
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.setStyleSheet("background-color: #1e2538; border: 1px solid #28334a; border-radius: 6px; padding: 6px 12px; color: #fff;")
        btn_browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(btn_browse)
        folder_group.addLayout(folder_row)
        set_layout.addLayout(folder_group)

        # Maksimum Eşzamanlı Bağlantı Sayısı
        conn_group = QHBoxLayout()
        conn_lbl = QLabel("Connection (Segment) Count:")
        conn_lbl.setStyleSheet(lbl_style)
        conn_group.addWidget(conn_lbl)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 32)
        self.conn_spin.setValue(8)
        self.conn_spin.setFixedWidth(100)
        self.conn_spin.setFixedHeight(32)
        self.conn_spin.setStyleSheet("background-color: #171b26; border: 1px solid #232b3e; border-radius: 6px; padding: 4px 44px 4px 10px; color: #f1f5f9; min-height: 28px;")
        conn_group.addWidget(self.conn_spin)
        conn_group.addStretch()
        set_layout.addLayout(conn_group)

        # Otomatik Kapatma Seçeneği
        self.chk_autoclose = QCheckBox("Automatically close this window when download completes")
        self.chk_autoclose.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        set_layout.addWidget(self.chk_autoclose)

        set_layout.addStretch()
        self.tab_widget.addTab(settings_tab, "⚙ Settings")

        main_layout.addWidget(self.tab_widget)

    def _connect_signals(self) -> None:
        """TaskManager sinyallerini pencereye bağlar."""
        self.task_manager.task_progress.connect(self._on_task_progress)
        self.task_manager.task_chunk_progress.connect(self._on_chunk_progress)
        self.task_manager.task_status_changed.connect(self._on_status_changed)
        self.task_manager.task_finished.connect(self._on_task_finished)

    def _toggle_part_info(self) -> None:
        """Parça panelini açar veya kapatır."""
        self._is_part_info_expanded = not self._is_part_info_expanded
        self.part_container.setVisible(self._is_part_info_expanded)
        self.toggle_part_btn.setText("˄ Part Info" if self._is_part_info_expanded else "˅ Part Info")

    def _toggle_pause_resume(self) -> None:
        """Görevi duraklatır veya devam ettirir."""
        if self.task.status == DownloadStatus.DOWNLOADING:
            self.task_manager.pause_task(self.task.task_id)
            self.pause_resume_btn.setText("▶ Resume")
        elif self.task.status in (DownloadStatus.PAUSED, DownloadStatus.QUEUED, DownloadStatus.FAILED):
            self.task_manager.resume_task(self.task.task_id)
            self.pause_resume_btn.setText("⏸ Pause")

    def _browse_folder(self) -> None:
        """İndirme klasörü seçer."""
        folder = QFileDialog.getExistingDirectory(self, "Hedef Klasör Seç", self.task.destination_folder)
        if folder:
            self.task.destination_folder = folder
            self.folder_input.setText(folder)

    def _update_all_from_task(self) -> None:
        """Tüm arayüz alanlarını mevcut görev nesnesine göre günceller."""
        pct = int(self.task.progress_percent)
        title_str = f"{pct}%-{self.task.filename}"
        self.setWindowTitle(title_str)
        self.title_lbl.setText(title_str)

        self.name_val.setText(self.task.filename)
        self.status_val.setText(self.task.status.value.capitalize())
        self.size_val.setText(self.task.formatted_total_size)
        self.downloaded_val.setText(self._format_bytes(self.task.downloaded_size))
        self.speed_val.setText(self.task.formatted_speed)
        self.eta_val.setText(self.task.formatted_eta)

        if self.task.is_resumable:
            self.resume_val.setText("Yes")
            self.resume_val.setStyleSheet("color: #22c55e; font-weight: bold;")
        else:
            self.resume_val.setText("No / Unknown")
            self.resume_val.setStyleSheet("color: #f59e0b;")

        self.progress_bar.setValue(pct)

        # Segment ve parça tablosu
        self._sync_chunks_view()

    def _sync_chunks_view(self) -> None:
        """Parçaları tabloya ve segment kutularına doldurur."""
        chunks = self.task.chunks
        chunk_count = len(chunks) if chunks else 8

        self.part_table.setRowCount(chunk_count)
        for i in range(chunk_count):
            if chunks and i < len(chunks):
                c = chunks[i]
                status_txt = "Completed" if c.is_completed else ("Receiving Data" if self.task.status == DownloadStatus.DOWNLOADING else "Idle")
                down_txt = self._format_bytes(c.downloaded_bytes)
                tot_txt = self._format_bytes(c.total_bytes)
                active = not c.is_completed and self.task.status == DownloadStatus.DOWNLOADING
                done = c.is_completed
            else:
                status_txt = "Receiving Data" if self.task.status == DownloadStatus.DOWNLOADING else "Idle"
                down_txt = "--"
                tot_txt = "--"
                active = (self.task.status == DownloadStatus.DOWNLOADING)
                done = False

            # Tablo hücreleri
            self.part_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.part_table.setItem(i, 1, QTableWidgetItem(status_txt))
            self.part_table.setItem(i, 2, QTableWidgetItem(down_txt))
            self.part_table.setItem(i, 3, QTableWidgetItem(tot_txt))

            # Segment kutusu rengi
            if i < len(self._segment_boxes):
                box = self._segment_boxes[i]
                if done:
                    box.setStyleSheet("background-color: #15803d; border-radius: 3px;")  # Koyu yeşil (Tamamlandı)
                elif active:
                    box.setStyleSheet("background-color: #22c55e; border-radius: 3px; border: 1px solid #4ade80;")  # Parlak yeşil
                else:
                    box.setStyleSheet("background-color: #1e293b; border-radius: 3px;")

    @pyqtSlot(dict)
    def _on_task_progress(self, data: dict) -> None:
        if data.get("task_id") != self.task.task_id:
            return

        pct = int(data.get("percent", 0))
        title_str = f"{pct}%-{self.task.filename}"
        self.setWindowTitle(title_str)
        self.title_lbl.setText(title_str)

        self.progress_bar.setValue(pct)
        self.downloaded_val.setText(self._format_bytes(data.get("downloaded_bytes", 0)))
        self.size_val.setText(self._format_bytes(data.get("total_bytes", self.task.total_size)))
        self.speed_val.setText(data.get("speed_str", "0 B/s"))
        self.eta_val.setText(data.get("eta_str", "--:--"))

    @pyqtSlot(str, int, int, int)
    def _on_chunk_progress(self, task_id: str, chunk_id: int, downloaded: int, total: int) -> None:
        if task_id != self.task.task_id:
            return

        if chunk_id < self.part_table.rowCount():
            is_done = (downloaded >= total > 0)
            status_txt = "Completed" if is_done else "Receiving Data"
            self.part_table.setItem(chunk_id, 1, QTableWidgetItem(status_txt))
            self.part_table.setItem(chunk_id, 2, QTableWidgetItem(self._format_bytes(downloaded)))
            self.part_table.setItem(chunk_id, 3, QTableWidgetItem(self._format_bytes(total)))

        if chunk_id < len(self._segment_boxes):
            box = self._segment_boxes[chunk_id]
            if downloaded >= total > 0:
                box.setStyleSheet("background-color: #15803d; border-radius: 3px;")
            else:
                box.setStyleSheet("background-color: #22c55e; border-radius: 3px; border: 1px solid #4ade80;")

    @pyqtSlot(str, str)
    def _on_status_changed(self, task_id: str, status_str: str) -> None:
        if task_id != self.task.task_id:
            return

        self.status_val.setText(status_str.capitalize())
        if status_str == DownloadStatus.DOWNLOADING.value:
            self.pause_resume_btn.setText("⏸ Pause")
        elif status_str == DownloadStatus.PAUSED.value:
            self.pause_resume_btn.setText("▶ Resume")
            # Segmentleri bekleme durumuna çek
            for box in self._segment_boxes:
                box.setStyleSheet("background-color: #1e293b; border-radius: 3px;")

    @pyqtSlot(str, str)
    def _on_task_finished(self, task_id: str, final_path: str) -> None:
        if task_id != self.task.task_id:
            return

        self.status_val.setText("Completed")
        self.progress_bar.setValue(100)
        self.speed_val.setText("0 B/s")
        self.eta_val.setText("Finished")
        self.pause_resume_btn.setEnabled(False)

        # Tüm segmentleri yeşile boya
        for box in self._segment_boxes:
            box.setStyleSheet("background-color: #22c55e; border-radius: 3px;")

        if self.chk_autoclose.isChecked():
            self.close()

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
