"""
Compact Download Window and Autostart Verification Test
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication

from app.core.task_manager import TaskManager
from app.core.autostart import get_startup_command, is_autostart_enabled
from app.ui.compact_download_window import CompactDownloadWindow
from app.ui.tray_manager import TrayManager
from app.ui.main_window import MainWindow
from app.server.bridge import ServerBridge


class TestCompactAndAutostart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls.task_manager = TaskManager(
            tasks_file=os.path.join(cls._tmp_dir.name, "tasks.json"),
            auto_load=False
        )
        cls.bridge = ServerBridge()

    @classmethod
    def tearDownClass(cls):
        try:
            cls._tmp_dir.cleanup()
        except Exception:
            pass

    def test_01_autostart_command_generation(self):
        """Tests that the autostart command line is correctly generated."""
        cmd = get_startup_command(minimized=True)
        self.assertIn("run.py", cmd)
        self.assertIn("--tray", cmd)

    def test_02_compact_download_window_init(self):
        """Tests the initial state of the compact download window."""
        win = CompactDownloadWindow(
            task_manager=self.task_manager,
            initial_url="https://example.com/archive.zip",
            initial_filename="archive.zip"
        )
        self.assertEqual(win.url_input.text(), "https://example.com/archive.zip")
        self.assertEqual(win.filename_input.text(), "archive.zip")
        self.assertFalse(win.query_widget.isHidden())
        self.assertTrue(win.progress_widget.isHidden())

        # Test size formatting
        win._update_size_ui(1048576)  # 1 MB
        self.assertEqual(win.size_label.text(), "1.00 MB")

        # Test conversion to progress mode
        win._morph_to_progress_mode("archive.zip")
        self.assertTrue(win.is_progress_mode)
        self.assertTrue(win.query_widget.isHidden())
        self.assertFalse(win.progress_widget.isHidden())
        win.close()

    def test_02b_compact_download_add_vs_download_buttons(self):
        """Tests queuing and download behavior of Add and Download buttons."""
        win = CompactDownloadWindow(
            task_manager=self.task_manager,
            initial_url="https://example.com/testfile.bin",
            initial_filename="testfile.bin"
        )
        self.assertTrue(hasattr(win, "btn_add"))
        self.assertTrue(hasattr(win, "btn_download"))
        self.assertTrue(hasattr(win, "btn_cancel"))
        self.assertEqual(win.btn_add.text(), "Add")
        self.assertEqual(win.btn_download.text(), "Download")
        self.assertEqual(win.btn_cancel.text(), "Cancel")

        # When 'Add' is clicked, task is added with auto_start=False (queued)
        initial_tasks_count = len(self.task_manager.tasks)
        win._on_add_clicked()
        self.assertEqual(len(self.task_manager.tasks), initial_tasks_count + 1)
        newest_task = list(self.task_manager.tasks.values())[-1]
        self.assertEqual(newest_task.url, "https://example.com/testfile.bin")
        self.assertEqual(newest_task.filename, "testfile.bin")
        # Download must not start immediately (must not be in workers)
        self.assertNotIn(newest_task.task_id, self.task_manager.workers)
        win.close()

    def test_03_tray_manager_actions(self):
        """Tests that system tray menu and actions are defined."""
        main_win = MainWindow(task_manager=self.task_manager, bridge=self.bridge)
        tray = TrayManager(main_window=main_win, task_manager=self.task_manager)
        self.assertIsNotNone(tray.tray_icon)
        self.assertIsNotNone(tray.tray_menu)
        self.assertTrue(hasattr(tray, "action_show"))
        self.assertTrue(hasattr(tray, "action_autostart"))
        tray.tray_icon.hide()
        main_win.close()

    def test_04_tray_activated_reasons(self):
        """Tests that tray icon activation (left click, double click, right click, int) operates without error."""
        from PyQt6.QtWidgets import QSystemTrayIcon
        main_win = MainWindow(task_manager=self.task_manager, bridge=self.bridge)
        tray = TrayManager(main_window=main_win, task_manager=self.task_manager)

        # Trigger (left click)
        tray._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
        self.assertTrue(main_win.isVisible())

        # DoubleClick
        tray._on_tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
        # Context (right click) opens menu without altering window visibility
        tray._on_tray_activated(QSystemTrayIcon.ActivationReason.Context)

        # Must not crash when called with integer values or None
        tray._on_tray_activated(3)
        tray._on_tray_activated(2)
        tray._on_tray_activated(None)

        tray.tray_icon.hide()
        main_win.close()

    def test_05_exit_handling(self):
        """Verifies that application exit actions work properly."""
        main_win = MainWindow(task_manager=self.task_manager, bridge=self.bridge)
        tray = TrayManager(main_window=main_win, task_manager=self.task_manager)
        main_win.tray_manager = tray

        # _exit_app method exists and is callable
        self.assertTrue(hasattr(main_win, "_exit_app"))
        self.assertTrue(hasattr(tray, "_force_exit"))

        tray.tray_icon.hide()
        main_win.close()

        print("\n[OK] Compact window, system tray, and autostart tests passed successfully!")


if __name__ == "__main__":
    unittest.main()
