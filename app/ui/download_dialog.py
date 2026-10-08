"""
Download Manager - Add New Download Dialog (download_dialog.py)

This dialog allows the user to configure URL, target save directory,
and concurrent chunk count manually or when passed from the browser extension.
Features automatic URL detection from the system clipboard.
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
    """Dialog for configuring and starting a new download."""

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

        # 1. Determine URL (from parameter or clipboard)
        if initial_url:
            self.url_input.setText(initial_url)
        else:
            self._check_clipboard()

        if initial_filename:
            self.filename_input.setText(initial_filename)
        elif self.url_input.text():
            self._guess_filename(self.url_input.text())

    def _init_ui(self) -> None:
        """Constructs dialog UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("📥 New Download Task")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        layout.addWidget(title)

        # 1. URL Field
        layout.addWidget(QLabel("Download URL Address:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/file.zip")
        self.url_input.textChanged.connect(self._guess_filename)
        layout.addWidget(self.url_input)

        # 2. File Name Field
        layout.addWidget(QLabel("File Name:"))
        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("file.zip")
        layout.addWidget(self.filename_input)

        # 3. Destination Folder Field
        layout.addWidget(QLabel("Destination Folder:"))
        dest_layout = QHBoxLayout()
        self.dest_input = QLineEdit(self.default_save_dir)
        dest_layout.addWidget(self.dest_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_folder)
        dest_layout.addWidget(browse_btn)
        layout.addLayout(dest_layout)

        # 4. Chunk Count Selection
        try:
            from app.core.config import load_network_settings
            cfg_chunks = load_network_settings().segments_per_download
        except Exception:
            cfg_chunks = 8

        chunk_layout = QHBoxLayout()
        chunk_layout.addWidget(QLabel("Concurrent Segments:"))
        self.chunk_combo = QComboBox()
        options = [4, 8, 16, 32]
        if cfg_chunks not in options:
            options.append(cfg_chunks)
            options.sort()
        for opt in options:
            label = f"{opt} Segments (Recommended)" if opt == cfg_chunks else f"{opt} Segments"
            self.chunk_combo.addItem(label, opt)
        idx = options.index(cfg_chunks) if cfg_chunks in options else 1
        self.chunk_combo.setCurrentIndex(idx)
        chunk_layout.addWidget(self.chunk_combo)
        chunk_layout.addStretch()
        layout.addLayout(chunk_layout)

        # 5. Buttons
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
        """Automatically pastes URL if clipboard contains http/https link."""
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text.startswith(("http://", "https://", "ftp://")):
            self.url_input.setText(text)
            self._guess_filename(text)

    def _guess_filename(self, url: str) -> None:
        """Guesses file name from URL."""
        if not self.filename_input.text() or self.filename_input.text() == "file.bin":
            clean_url = url.split("?")[0].split("#")[0]
            guessed = clean_url.split("/")[-1]
            if guessed and "." in guessed:
                self.filename_input.setText(guessed)
            else:
                self.filename_input.setText("file.bin")

    def _browse_folder(self) -> None:
        """Opens folder selection dialog."""
        chosen = QFileDialog.getExistingDirectory(self, "Select Destination Folder", self.dest_input.text())
        if chosen:
            self.dest_input.setText(chosen)

    def get_data(self) -> Dict[str, Any]:
        """Returns user inputs as dictionary."""
        num_chunks = self.chunk_combo.currentData()
        if num_chunks is None:
            chunk_map = {0: 4, 1: 8, 2: 16, 3: 32}
            num_chunks = chunk_map.get(self.chunk_combo.currentIndex(), 8)

        return {
            "url": self.url_input.text().strip(),
            "filename": self.filename_input.text().strip() or "file.bin",
            "destination": self.dest_input.text().strip(),
            "num_chunks": num_chunks
        }

