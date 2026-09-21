"""
Download Manager - Delete Downloads Confirmation Dialog (delete_dialog.py)
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton, QWidget
)
from PyQt6.QtCore import Qt
from app.utils.icon_utils import get_app_icon


class DeleteDownloadsDialog(QDialog):
    """
    Kullanıcının indirmeleri listeden (bellekten) veya kalıcı olarak diskten
    silmesini sağlayan onay penceresi.
    """

    def __init__(self, count: int = 1, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.count = count

        self.setWindowTitle("Delete downloads")
        self.setWindowIcon(get_app_icon())
        self.setModal(True)
        self.setFixedSize(450, 165)
        self.setStyleSheet(self._get_styles())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(16)

        # 1. Başlık / Onay Sorusunu İçeren Etiket
        self.msg_label = QLabel("Are you sure you want to delete selected downloads?")
        self.msg_label.setObjectName("confirmQuestion")
        self.msg_label.setWordWrap(True)
        layout.addWidget(self.msg_label)

        # 2. Kalıcı Silme (Diskten Silme) Onay Kutusu
        self.chk_delete_files = QCheckBox("Delete files from disk")
        self.chk_delete_files.setObjectName("deleteFilesChk")
        self.chk_delete_files.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.chk_delete_files)

        layout.addStretch()

        # 3. Butonlar Satırı (Sağa Yaslı: Delete & Cancel)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("confirmDeleteBtn")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_delete)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("cancelBtn")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    @property
    def delete_from_disk(self) -> bool:
        """Kullanıcının 'Delete files from disk' kutusunu işaretleyip işaretlemediğini döndürür."""
        return self.chk_delete_files.isChecked()

    def _get_styles(self) -> str:
        """Referans görseldeki koyu Fluent arayüz stili."""
        return """
            QDialog {
                background-color: #141720;
                color: #f1f5f9;
                font-family: "Segoe UI Variable Display", "Segoe UI", -apple-system, sans-serif;
            }
            QLabel#confirmQuestion {
                color: #e2e8f0;
                font-size: 14px;
                font-weight: 400;
                line-height: 1.4;
            }
            QCheckBox#deleteFilesChk {
                color: #94a3b8;
                font-size: 13px;
                spacing: 10px;
            }
            QCheckBox#deleteFilesChk:hover {
                color: #cbd5e1;
            }
            QCheckBox#deleteFilesChk::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #3b82f6;
                background-color: #1e2538;
            }
            QCheckBox#deleteFilesChk::indicator:hover {
                border-color: #60a5fa;
                background-color: #263047;
            }
            QCheckBox#deleteFilesChk::indicator:checked {
                background-color: #0284c7;
                border: 1px solid #38bdf8;
            }
            QPushButton {
                font-size: 13px;
                font-weight: 500;
                border-radius: 4px;
                padding: 7px 22px;
                min-width: 70px;
            }
            QPushButton#confirmDeleteBtn {
                background-color: #212530;
                color: #f8fafc;
                border: 1px solid #334155;
            }
            QPushButton#confirmDeleteBtn:hover {
                background-color: #e11d48;
                border-color: #f43f5e;
                color: #ffffff;
            }
            QPushButton#confirmDeleteBtn:pressed {
                background-color: #be123c;
            }
            QPushButton#cancelBtn {
                background-color: #212530;
                color: #cbd5e1;
                border: 1px solid #334155;
            }
            QPushButton#cancelBtn:hover {
                background-color: #2b3548;
                border-color: #475569;
                color: #ffffff;
            }
            QPushButton#cancelBtn:pressed {
                background-color: #171c26;
            }
        """
