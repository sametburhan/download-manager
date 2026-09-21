"""
Download Manager - Sistem Tepsisi (System Tray) Yöneticisi (tray_manager.py)

Uygulamanın Windows görev çubuğu bildirim alanında (System Tray) arka planda
kesintisiz çalışmasını sağlar. Pencere kapatıldığında uygulamanın kapanmasını
önler, bildirimler gösterir ve başlangıç ayarlarını yönetir.
"""

import os
from typing import Optional
from PyQt6.QtWidgets import (
    QSystemTrayIcon, QMenu, QApplication
)
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QObject, pyqtSlot

from app.core.autostart import is_autostart_enabled, set_autostart
from app.utils.icon_utils import get_app_icon


class TrayManager(QObject):
    """Sistem tepsisi simgesi ve arka plan yaşam döngüsü yöneticisi."""

    def __init__(self, main_window, task_manager, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.task_manager = task_manager

        self._init_tray()

    def _init_tray(self) -> None:
        """Tepsi simgesini ve sağ tık menüsünü kurar."""
        # 1. İkonu yükle
        icon = get_app_icon()
        if not icon.isNull():
            self.tray_icon = QSystemTrayIcon(icon, self.main_window)
        else:
            self.tray_icon = QSystemTrayIcon(self.main_window)

        self.tray_icon.setToolTip("Download Manager (Active in background)")

        # 2. Menüyü oluştur
        self.tray_menu = QMenu()

        # Göster / Gizle Eylemi
        self.action_show = QAction("🖥️ Show Main Window", self)
        self.action_show.triggered.connect(self._toggle_window_visibility)
        self.tray_menu.addAction(self.action_show)

        # Yeni İndirme Eylemi
        self.action_add = QAction("➕ Add New Download...", self)
        self.action_add.triggered.connect(self.main_window._open_add_dialog)
        self.tray_menu.addAction(self.action_add)

        self.tray_menu.addSeparator()

        # Windows Başlangıcında Otomatik Çalıştır (Checkable)
        self.action_autostart = QAction("⚙️ Start with Windows", self)
        self.action_autostart.setCheckable(True)
        self.action_autostart.setChecked(is_autostart_enabled())
        self.action_autostart.toggled.connect(self._on_autostart_toggled)
        self.tray_menu.addAction(self.action_autostart)

        self.tray_menu.addSeparator()

        # Tümünü Duraklat / Başlat
        self.action_pause_all = QAction("⏸️ Pause All", self)
        self.action_pause_all.triggered.connect(self.main_window._pause_all_tasks)
        self.tray_menu.addAction(self.action_pause_all)

        self.action_resume_all = QAction("▶️ Resume All", self)
        self.action_resume_all.triggered.connect(self.main_window._resume_all_tasks)
        self.tray_menu.addAction(self.action_resume_all)

        self.tray_menu.addSeparator()

        # Tamamen Çıkış Yap
        self.action_exit = QAction("🚪 Exit", self)
        self.action_exit.triggered.connect(self._force_exit)
        self.tray_menu.addAction(self.action_exit)

        self.tray_icon.setContextMenu(self.tray_menu)

        # Simgeye tıklandığında pencereyi aç/kapa
        self.tray_icon.activated.connect(self._on_tray_activated)
        # Bildirim baloncuğuna tıklandığında pencereyi aç
        self.tray_icon.messageClicked.connect(self._toggle_window_visibility)
        self.tray_icon.show()

    @pyqtSlot(QSystemTrayIcon.ActivationReason)
    @pyqtSlot(int)
    @pyqtSlot()
    def _on_tray_activated(self, reason=None) -> None:
        """Kullanıcı tepsi simgesine tıkladığında çalışır."""
        try:
            # Context (1) / Sağ tık menüsü Qt tarafından doğrudan açılır.
            # Trigger (3) / Sol tık veya DoubleClick (2) / Çift tık pencereyi öne getirir/gizler.
            if reason in (
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick,
                3, 2, None
            ):
                self._toggle_window_visibility()
        except Exception:
            # Herhangi bir platform mesaj uyuşmazlığında güvenli geri dönüş
            self._toggle_window_visibility()

    def _toggle_window_visibility(self) -> None:
        """Ana pencerenin görünürlüğünü değiştirir."""
        if not self.main_window.isVisible() or self.main_window.isMinimized():
            self.main_window.showNormal()
            self.main_window.activateWindow()
            self.main_window.raise_()
        else:
            self.main_window.hide()

    def _on_autostart_toggled(self, checked: bool) -> None:
        """Kullanıcı 'Windows ile Başlat' seçeneğini değiştirdiğinde çalışır."""
        success = set_autostart(checked, run_minimized=True)
        if not success:
            self.action_autostart.setChecked(not checked)
        else:
            msg = "Download Manager added to Windows startup." if checked else "Removed from Windows startup."
            self.show_notification("Auto Start", msg)

    def show_notification(self, title: str, message: str) -> None:
        """Windows bildirim baloncuğu gösterir."""
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )

    def _force_exit(self) -> None:
        """Kullanıcı sağ tık menüsünden Çıkış dediğinde uygulamayı tamamen kapatır."""
        try:
            self.tray_icon.hide()
        except Exception:
            pass
        self.main_window._is_forced_exit = True
        self.main_window.close()
        QApplication.quit()
