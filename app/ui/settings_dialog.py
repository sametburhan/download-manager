"""
Download Manager - Ağ Ayarları Penceresi (settings_dialog.py)

Kullanıcının paylaştığı 'Network settings' arayüzüne birebir uygun olarak
tasarlanmıştır. Bağlantı zaman aşımı, parça (segment) sayısı, yeniden deneme limiti,
hız sınırı ve sistem/özel proxy yapılandırmalarını yönetir.
"""

import os
import subprocess
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QCheckBox, QComboBox, QLineEdit, QPushButton,
    QFrame, QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from app.core.config import NetworkSettings, load_network_settings, save_network_settings
from app.utils.icon_utils import get_app_icon


class NetworkSettingsDialog(QDialog):
    """Kullanıcı referans görseline birebir uygun Ağ Ayarları diyalogu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings: NetworkSettings = load_network_settings()

        self.setWindowTitle("Network settings")
        self.setWindowIcon(get_app_icon())
        self.resize(520, 560)
        self.setMinimumSize(480, 520)

        self._init_ui()
        self._load_values()
        self._apply_styles()

    def _init_ui(self) -> None:
        """Arayüz bileşenlerini ve düzenini kurar."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # 1. Başlık
        title_lbl = QLabel("Network settings")
        title_lbl.setFont(QFont("Segoe UI Variable Display", 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #f1f5f9; margin-bottom: 4px;")
        main_layout.addWidget(title_lbl)

        # 2. Üst Parametreler Izgarası (Timeout, Segments, Retries)
        top_grid = QGridLayout()
        top_grid.setHorizontalSpacing(16)
        top_grid.setVerticalSpacing(14)

        lbl_style = "color: #cbd5e1; font-size: 13px; font-weight: 400;"

        # Connection timeout in seconds
        lbl_timeout = QLabel("Connection timeout in seconds")
        lbl_timeout.setStyleSheet(lbl_style)
        top_grid.addWidget(lbl_timeout, 0, 0)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(1, 3600)
        self.spin_timeout.setFixedWidth(120)
        self.spin_timeout.setFixedHeight(32)
        top_grid.addWidget(self.spin_timeout, 0, 1, Qt.AlignmentFlag.AlignRight)

        # Segments per download
        lbl_segments = QLabel("Segments per download")
        lbl_segments.setStyleSheet(lbl_style)
        top_grid.addWidget(lbl_segments, 1, 0)

        self.spin_segments = QSpinBox()
        self.spin_segments.setRange(1, 32)
        self.spin_segments.setFixedWidth(120)
        self.spin_segments.setFixedHeight(32)
        top_grid.addWidget(self.spin_segments, 1, 1, Qt.AlignmentFlag.AlignRight)

        # Maximum retry limit
        lbl_retry = QLabel("Maximum retry limit")
        lbl_retry.setStyleSheet(lbl_style)
        top_grid.addWidget(lbl_retry, 2, 0)

        self.spin_retry = QSpinBox()
        self.spin_retry.setRange(1, 100)
        self.spin_retry.setFixedWidth(120)
        self.spin_retry.setFixedHeight(32)
        top_grid.addWidget(self.spin_retry, 2, 1, Qt.AlignmentFlag.AlignRight)

        # Download speed limit [KB/Sec ](0 unlimited)
        speed_row = QHBoxLayout()
        self.chk_speed_limit = QCheckBox("Download speed limit [KB/Sec ](0 unlimited)")
        self.chk_speed_limit.setStyleSheet(lbl_style)
        self.chk_speed_limit.toggled.connect(self._on_speed_limit_toggled)
        speed_row.addWidget(self.chk_speed_limit)

        speed_row.addStretch()

        self.spin_speed_limit = QSpinBox()
        self.spin_speed_limit.setRange(0, 1000000)
        self.spin_speed_limit.setFixedWidth(120)
        self.spin_speed_limit.setFixedHeight(32)
        speed_row.addWidget(self.spin_speed_limit)

        top_grid.addLayout(speed_row, 3, 0, 1, 2)

        main_layout.addLayout(top_grid)

        # Ayırıcı Çizgi
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #232b3e; border: none; height: 1px;")
        main_layout.addWidget(sep)

        # 3. Proxy Ayarları
        proxy_grid = QGridLayout()
        proxy_grid.setHorizontalSpacing(16)
        proxy_grid.setVerticalSpacing(12)

        # Proxy settings combo
        lbl_proxy = QLabel("Proxy settings")
        lbl_proxy.setStyleSheet(lbl_style)
        proxy_grid.addWidget(lbl_proxy, 0, 0)

        self.combo_proxy = QComboBox()
        self.combo_proxy.addItems([
            "Use system proxy settings",
            "No proxy",
            "Manual proxy configuration"
        ])
        self.combo_proxy.currentIndexChanged.connect(self._on_proxy_mode_changed)
        proxy_grid.addWidget(self.combo_proxy, 0, 1)

        # Proxy Host
        lbl_host = QLabel("Proxy Host")
        lbl_host.setStyleSheet(lbl_style)
        proxy_grid.addWidget(lbl_host, 1, 0)

        self.input_host = QLineEdit()
        self.input_host.setPlaceholderText("127.0.0.1")
        proxy_grid.addWidget(self.input_host, 1, 1)

        # Proxy Port
        lbl_port = QLabel("Proxy Port")
        lbl_port.setStyleSheet(lbl_style)
        proxy_grid.addWidget(lbl_port, 2, 0)

        self.spin_port = QSpinBox()
        self.spin_port.setRange(0, 65535)
        proxy_grid.addWidget(self.spin_port, 2, 1)

        # Proxy username
        lbl_user = QLabel("Proxy username")
        lbl_user.setStyleSheet(lbl_style)
        proxy_grid.addWidget(lbl_user, 3, 0)

        self.input_user = QLineEdit()
        proxy_grid.addWidget(self.input_user, 3, 1)

        # Proxy password
        lbl_pass = QLabel("Proxy password")
        lbl_pass.setStyleSheet(lbl_style)
        proxy_grid.addWidget(lbl_pass, 4, 0)

        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        proxy_grid.addWidget(self.input_pass, 4, 1)

        main_layout.addLayout(proxy_grid)

        # Open system proxy settings butonu
        btn_sys_proxy_layout = QHBoxLayout()
        btn_sys_proxy_layout.addStretch()
        self.btn_sys_proxy = QPushButton("Open system proxy settings")
        self.btn_sys_proxy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sys_proxy.clicked.connect(self._open_system_proxy_settings)
        btn_sys_proxy_layout.addWidget(self.btn_sys_proxy)
        main_layout.addLayout(btn_sys_proxy_layout)

        main_layout.addStretch()

        # 4. Alt Butonlar (Save / Cancel)
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()

        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("saveBtn")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_save_clicked)
        actions_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("cancelBtn")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        actions_layout.addWidget(self.btn_cancel)

        main_layout.addLayout(actions_layout)

    def _load_values(self) -> None:
        """Ayarları arayüz alanlarına aktarır."""
        s = self.settings
        self.spin_timeout.setValue(s.connection_timeout)
        self.spin_segments.setValue(s.segments_per_download)
        self.spin_retry.setValue(s.max_retries)

        self.chk_speed_limit.setChecked(s.speed_limit_enabled)
        self.spin_speed_limit.setValue(s.speed_limit_kbs)
        self.spin_speed_limit.setEnabled(s.speed_limit_enabled)

        # Proxy Modu Eşlemesi
        mode_map = {
            "system": 0,
            "none": 1,
            "manual": 2
        }
        self.combo_proxy.setCurrentIndex(mode_map.get(s.proxy_mode, 0))
        self.input_host.setText(s.proxy_host)
        self.spin_port.setValue(s.proxy_port)
        self.input_user.setText(s.proxy_user)
        self.input_pass.setText(s.proxy_pass)

        self._on_proxy_mode_changed(self.combo_proxy.currentIndex())

    def _on_speed_limit_toggled(self, checked: bool) -> None:
        self.spin_speed_limit.setEnabled(checked)

    def _on_proxy_mode_changed(self, index: int) -> None:
        """Proxy modu manual olduğunda alanları etkinleştirir."""
        is_manual = (index == 2)
        self.input_host.setEnabled(is_manual)
        self.spin_port.setEnabled(is_manual)
        self.input_user.setEnabled(is_manual)
        self.input_pass.setEnabled(is_manual)

    def _open_system_proxy_settings(self) -> None:
        """Windows sistem proxy ayarları sayfasını açar."""
        try:
            subprocess.Popen("start ms-settings:network-proxy", shell=True)
        except Exception:
            try:
                subprocess.Popen("rundll32.exe shell32.dll,Control_RunDLL inetcpl.cpl,,4")
            except Exception as e:
                print(f"Sistem proxy sayfası açılamadı: {e}")

    def _on_save_clicked(self) -> None:
        """Kullanıcının girdiği ayarları nesneye aktarıp kaydeder."""
        index_to_mode = {
            0: "system",
            1: "none",
            2: "manual"
        }

        self.settings.connection_timeout = self.spin_timeout.value()
        self.settings.segments_per_download = self.spin_segments.value()
        self.settings.max_retries = self.spin_retry.value()
        self.settings.speed_limit_enabled = self.chk_speed_limit.isChecked()
        self.settings.speed_limit_kbs = self.spin_speed_limit.value()

        self.settings.proxy_mode = index_to_mode.get(self.combo_proxy.currentIndex(), "system")
        self.settings.proxy_host = self.input_host.text().strip()
        self.settings.proxy_port = self.spin_port.value()
        self.settings.proxy_user = self.input_user.text().strip()
        self.settings.proxy_pass = self.input_pass.text().strip()

        save_network_settings(self.settings)
        self.accept()

    def _apply_styles(self) -> None:
        """Kullanıcı görseline sadık kalan modern Fluent Obsidian stilini uygular."""
        self.setStyleSheet("""
            QDialog {
                background-color: #171920;
                color: #e2e8f0;
            }
            QLabel {
                color: #cbd5e1;
            }
            QLineEdit, QComboBox {
                background-color: #212530;
                border: 1px solid #2e3547;
                border-radius: 4px;
                color: #f1f5f9;
                padding: 5px 8px;
                font-size: 13px;
                min-height: 28px;
            }
            QSpinBox {
                background-color: #212530;
                border: 1px solid #2e3547;
                border-radius: 4px;
                color: #f1f5f9;
                padding: 4px 44px 4px 10px;
                font-size: 13px;
                min-height: 28px;
            }
            QSpinBox:focus, QLineEdit:focus, QComboBox:focus {
                border: 1px solid #3b82f6;
                background-color: #262c3b;
            }
            QSpinBox:disabled, QLineEdit:disabled, QComboBox:disabled {
                background-color: #1a1d25;
                color: #555e70;
                border-color: #232733;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #212530;
                color: #f1f5f9;
                border: 1px solid #2e3547;
                selection-background-color: #3b82f6;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 1px solid #3b4256;
                background-color: #212530;
            }
            QCheckBox::indicator:checked {
                background-color: #2563eb;
                border-color: #3b82f6;
            }
            QPushButton#saveBtn {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #3b82f6;
                border-radius: 4px;
                padding: 6px 18px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton#saveBtn:hover {
                background-color: #1d4ed8;
            }
            QPushButton#cancelBtn {
                background-color: #212530;
                color: #cbd5e1;
                border: 1px solid #2e3547;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 13px;
            }
            QPushButton#cancelBtn:hover {
                background-color: #2c3242;
                color: #ffffff;
            }
            QPushButton {
                background-color: #212530;
                color: #cbd5e1;
                border: 1px solid #2e3547;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2c3242;
                color: #ffffff;
            }
        """)
