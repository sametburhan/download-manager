"""
Download Manager - Yeni İndirme Ekleme Diyaloğu (download_dialog.py)

Bu pencere, kullanıcının elle veya tarayıcı eklentisinden iletilen URL'yi,
hedef kayıt dizinini ve eşzamanlı parça sayısını belirlemesini sağlar.
Panodan (clipboard) otomatik URL algılama özelliğine sahiptir.
"""

import os
from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class AddDownloadDialog(QDialog):
    """Yeni indirme ekleme ve yapılandırma penceresi."""

    def __init__(
        self,
        initial_url: str = "",
        initial_filename: str = "",
        default_save_dir: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Start New Download")
        self.setFixedWidth(540)
        self.default_save_dir = default_save_dir or os.path.join(os.path.expanduser("~"), "Downloads")

        self._init_ui()

        # 1. URL belirleme (Parametreden veya Panodan)
        if initial_url:
            self.url_input.setText(initial_url)
        else:
            self._check_clipboard()

        if initial_filename:
            self.filename_input.setText(initial_filename)
        elif self.url_input.text():
            self._guess_filename(self.url_input.text())

    def _init_ui(self) -> None:
        """Diyalog arayüzünü oluşturur."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("📥 New Download Task")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        layout.addWidget(title)

        # 1. URL Alanı
        layout.addWidget(QLabel("Download URL Address:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/file.zip")
        self.url_input.textChanged.connect(self._guess_filename)
        layout.addWidget(self.url_input)

        # 2. Dosya Adı Alanı
        layout.addWidget(QLabel("File Name:"))
        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("file.zip")
        layout.addWidget(self.filename_input)

        # 3. Kayıt Yeri Alanı
        layout.addWidget(QLabel("Destination Folder:"))
        dest_layout = QHBoxLayout()
        self.dest_input = QLineEdit(self.default_save_dir)
        dest_layout.addWidget(self.dest_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_folder)
        dest_layout.addWidget(browse_btn)
        layout.addLayout(dest_layout)

        # 4. Parça Sayısı Seçimi (Chunks)
        chunk_layout = QHBoxLayout()
        chunk_layout.addWidget(QLabel("Concurrent Segments:"))
        self.chunk_combo = QComboBox()
        self.chunk_combo.addItems(["4 Segments", "8 Segments (Recommended)", "16 Segments", "32 Segments"])
        self.chunk_combo.setCurrentIndex(1)  # 8 parça varsayılan
        chunk_layout.addWidget(self.chunk_combo)
        chunk_layout.addStretch()
        layout.addLayout(chunk_layout)

        # 5. Butonlar
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.start_btn = QPushButton("🚀 Download Now")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.start_btn)

        layout.addLayout(btn_layout)

    def _check_clipboard(self) -> None:
        """Panoda http/https bağlantısı varsa otomatik olarak yapıştırır."""
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text.startswith(("http://", "https://", "ftp://")):
            self.url_input.setText(text)
            self._guess_filename(text)

    def _guess_filename(self, url: str) -> None:
        """URL'den dosya adını tahmin eder."""
        if not self.filename_input.text() or self.filename_input.text() == "file.bin":
            clean_url = url.split("?")[0].split("#")[0]
            guessed = clean_url.split("/")[-1]
            if guessed and "." in guessed:
                self.filename_input.setText(guessed)
            else:
                self.filename_input.setText("file.bin")

    def _browse_folder(self) -> None:
        """Klasör seçim penceresini açar."""
        chosen = QFileDialog.getExistingDirectory(self, "Select Destination Folder", self.dest_input.text())
        if chosen:
            self.dest_input.setText(chosen)

    def get_data(self) -> Dict[str, Any]:
        """Kullanıcının girdiği verileri sözlük olarak döndürür."""
        chunk_map = {0: 4, 1: 8, 2: 16, 3: 32}
        num_chunks = chunk_map.get(self.chunk_combo.currentIndex(), 8)

        return {
            "url": self.url_input.text().strip(),
            "filename": self.filename_input.text().strip() or "file.bin",
            "destination": self.dest_input.text().strip(),
            "num_chunks": num_chunks
        }
