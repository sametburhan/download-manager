"""
Download Manager - System Tray Manager (tray_manager.py)

Enables uninterrupted background operation in Windows taskbar notification area (System Tray).
Prevents application from terminating when the window is closed, displays notifications,
and manages autostart settings.
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
    """System tray icon and background lifecycle manager."""

    def __init__(self, main_window, task_manager, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.task_manager = task_manager

        self._init_tray()

    def _init_tray(self) -> None:
        """Sets up tray icon and right-click context menu."""
        # 1. Load icon
        icon = get_app_icon()
        if not icon.isNull():
            self.tray_icon = QSystemTrayIcon(icon, self.main_window)
        else:
            self.tray_icon = QSystemTrayIcon(self.main_window)

        self.tray_icon.setToolTip("Download Manager (Active in background)")

        # 2. Build context menu
        self.tray_menu = QMenu()

        # Show / Hide Action
        self.action_show = QAction("🖥️ Show Main Window", self)
        self.action_show.triggered.connect(self._toggle_window_visibility)
        self.tray_menu.addAction(self.action_show)

        # Add New Download Action
        self.action_add = QAction("➕ Add New Download...", self)
        self.action_add.triggered.connect(self.main_window._open_add_dialog)
        self.tray_menu.addAction(self.action_add)

        self.tray_menu.addSeparator()

        # Run on Windows Startup (Checkable)
        self.action_autostart = QAction("⚙️ Start with Windows", self)
        self.action_autostart.setCheckable(True)
        self.action_autostart.setChecked(is_autostart_enabled())
        self.action_autostart.toggled.connect(self._on_autostart_toggled)
        self.tray_menu.addAction(self.action_autostart)

        self.tray_menu.addSeparator()

        # Pause / Resume All
        self.action_pause_all = QAction("⏸️ Pause All", self)
        self.action_pause_all.triggered.connect(self.main_window._pause_all_tasks)
        self.tray_menu.addAction(self.action_pause_all)

        self.action_resume_all = QAction("▶️ Resume All", self)
        self.action_resume_all.triggered.connect(self.main_window._resume_all_tasks)
        self.tray_menu.addAction(self.action_resume_all)

        self.tray_menu.addSeparator()

        # Exit Completely
        self.action_exit = QAction("🚪 Exit", self)
        self.action_exit.triggered.connect(self._force_exit)
        self.tray_menu.addAction(self.action_exit)

        self.tray_icon.setContextMenu(self.tray_menu)

        # Toggle window when tray icon is clicked
        self.tray_icon.activated.connect(self._on_tray_activated)
        # Open window when notification balloon is clicked
        self.tray_icon.messageClicked.connect(self._toggle_window_visibility)
        self.tray_icon.show()

    @pyqtSlot(QSystemTrayIcon.ActivationReason)
    @pyqtSlot(int)
    @pyqtSlot()
    def _on_tray_activated(self, reason=None) -> None:
        """Triggered when user clicks the tray icon."""
        try:
            # Context (1) / Right-click menu is opened by Qt directly.
            # Trigger (3) / Left-click or DoubleClick (2) brings window forward/toggles.
            if reason in (
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick,
                3, 2, None
            ):
                self._toggle_window_visibility()
        except Exception:
            # Safe fallback on platform differences
            self._toggle_window_visibility()

    def _toggle_window_visibility(self) -> None:
        """Toggles main window visibility."""
        if not self.main_window.isVisible() or self.main_window.isMinimized():
            self.main_window.showNormal()
            self.main_window.activateWindow()
            self.main_window.raise_()
        else:
            self.main_window.hide()

    def _on_autostart_toggled(self, checked: bool) -> None:
        """Triggered when user toggles 'Start with Windows'."""
        success = set_autostart(checked, run_minimized=True)
        if not success:
            self.action_autostart.setChecked(not checked)
        else:
            msg = "Download Manager added to Windows startup." if checked else "Removed from Windows startup."
            self.show_notification("Auto Start", msg)

    def show_notification(self, title: str, message: str) -> None:
        """Displays Windows notification toast/balloon."""
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )

    def _force_exit(self) -> None:
        """Completely exits application when Exit is selected from context menu."""
        try:
            self.tray_icon.hide()
        except Exception:
            pass
        self.main_window._is_forced_exit = True
        self.main_window.close()
        QApplication.quit()

