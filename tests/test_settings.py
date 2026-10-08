"""
Network Settings and Configuration Tests (test_settings.py)

This test suite:
1. Verifies NetworkSettings data model defaults and JSON save/load operations.
2. Tests NetworkSettingsDialog UI fields (Timeout, Segments, Retries, Speed Limit, Proxy).
3. Tests dynamic enable/disable logic for speed limiter and proxy fields.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from app.core.config import NetworkSettings, load_network_settings, save_network_settings, get_config_file_path
from app.ui.settings_dialog import NetworkSettingsDialog


class TestNetworkSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_01_default_settings(self):
        """Verifies default network settings values."""
        s = NetworkSettings()
        self.assertEqual(s.connection_timeout, 30)
        self.assertEqual(s.segments_per_download, 8)
        self.assertEqual(s.max_retries, 10)
        self.assertFalse(s.speed_limit_enabled)
        self.assertEqual(s.speed_limit_kbs, 2600)
        self.assertEqual(s.proxy_mode, "system")

    def test_02_save_and_load_settings(self):
        """Verifies settings can be saved to and loaded from JSON file."""
        s = NetworkSettings(
            connection_timeout=45,
            segments_per_download=16,
            max_retries=15,
            speed_limit_enabled=True,
            speed_limit_kbs=5000,
            proxy_mode="manual",
            proxy_host="192.168.1.100",
            proxy_port=8080,
            proxy_user="testuser",
            proxy_pass="secret"
        )
        saved = save_network_settings(s)
        self.assertTrue(saved)

        loaded = load_network_settings()
        self.assertEqual(loaded.connection_timeout, 45)
        self.assertEqual(loaded.segments_per_download, 16)
        self.assertEqual(loaded.max_retries, 15)
        self.assertTrue(loaded.speed_limit_enabled)
        self.assertEqual(loaded.speed_limit_kbs, 5000)
        self.assertEqual(loaded.proxy_mode, "manual")
        self.assertEqual(loaded.proxy_host, "192.168.1.100")
        self.assertEqual(loaded.proxy_port, 8080)
        self.assertEqual(loaded.proxy_user, "testuser")
        self.assertEqual(loaded.proxy_pass, "secret")

        # Revert to defaults
        save_network_settings(NetworkSettings())

    def test_03_settings_dialog_ui_components(self):
        """Verifies presence of NetworkSettingsDialog components and fields matching user reference."""
        dialog = NetworkSettingsDialog()

        self.assertEqual(dialog.windowTitle(), "Network settings")
        self.assertEqual(dialog.spin_timeout.value(), 30)
        self.assertEqual(dialog.spin_segments.value(), 8)
        self.assertEqual(dialog.spin_retry.value(), 10)

        # Speed Limiter Field
        dialog.chk_speed_limit.setChecked(False)
        self.assertFalse(dialog.spin_speed_limit.isEnabled())
        dialog.chk_speed_limit.setChecked(True)
        self.assertTrue(dialog.spin_speed_limit.isEnabled())

        # Proxy Mode Switching
        # System Proxy -> Host and Type disabled
        dialog.combo_proxy.setCurrentIndex(0)
        self.assertFalse(dialog.combo_proxy_type.isEnabled())
        self.assertFalse(dialog.input_host.isEnabled())

        # Manual Proxy -> Host and Type enabled
        dialog.combo_proxy.setCurrentIndex(2)
        self.assertTrue(dialog.combo_proxy_type.isEnabled())
        self.assertTrue(dialog.input_host.isEnabled())
        self.assertTrue(dialog.spin_port.isEnabled())

        # Proxy Type options
        types = [dialog.combo_proxy_type.itemText(i) for i in range(dialog.combo_proxy_type.count())]
        self.assertIn("HTTP", types)
        self.assertIn("HTTPS", types)
        self.assertIn("SOCKS4", types)
        self.assertIn("SOCKS5", types)

        dialog.close()

    def test_04_socks_proxy_settings_and_urls(self):
        """Tests saving SOCKS4 and SOCKS5 proxy settings, URL generation, and transport creation."""
        from app.core.http_downloader import HttpChunkDownloader
        from app.core.media_downloader import get_ytdl_base_opts
        from httpx_socks import SyncProxyTransport

        # SOCKS5 Test
        s5 = NetworkSettings(
            proxy_mode="manual",
            proxy_type="SOCKS5",
            proxy_host="127.0.0.1",
            proxy_port=1080,
            proxy_user="user",
            proxy_pass="pass"
        )
        save_network_settings(s5)
        loaded5 = load_network_settings()
        self.assertEqual(loaded5.proxy_type, "SOCKS5")
        self.assertEqual(loaded5.proxy_mode, "manual")

        proxy_url_5 = HttpChunkDownloader._get_proxy_url()
        self.assertEqual(proxy_url_5, "socks5://user:pass@127.0.0.1:1080")

        client5 = HttpChunkDownloader._create_http_client()
        self.assertIsInstance(client5._transport, SyncProxyTransport)
        client5.close()

        opts5 = get_ytdl_base_opts()
        self.assertEqual(opts5.get("proxy"), "socks5://user:pass@127.0.0.1:1080")

        # SOCKS4 Test
        s4 = NetworkSettings(
            proxy_mode="manual",
            proxy_type="SOCKS4",
            proxy_host="127.0.0.1",
            proxy_port=1080
        )
        save_network_settings(s4)
        loaded4 = load_network_settings()
        self.assertEqual(loaded4.proxy_type, "SOCKS4")

        proxy_url_4 = HttpChunkDownloader._get_proxy_url()
        self.assertEqual(proxy_url_4, "socks4://127.0.0.1:1080")

        client4 = HttpChunkDownloader._create_http_client()
        self.assertIsInstance(client4._transport, SyncProxyTransport)
        client4.close()

        opts4 = get_ytdl_base_opts()
        self.assertEqual(opts4.get("proxy"), "socks4://127.0.0.1:1080")

        # Revert to defaults
        save_network_settings(NetworkSettings())

    def test_06_segments_per_download_dynamic_application(self):
        """Tests that changing segments_per_download to 6 dynamically shapes download engine and UI windows."""
        import tempfile
        from app.core.models import DownloadTask
        from app.core.http_downloader import HttpChunkDownloader
        from app.core.task_manager import TaskManager
        from app.ui.compact_download_window import CompactDownloadWindow
        from app.ui.download_detail_window import DownloadDetailWindow

        # 1. Set segments to 6 in settings
        custom_settings = NetworkSettings(segments_per_download=6)
        save_network_settings(custom_settings)
        loaded = load_network_settings()
        self.assertEqual(loaded.segments_per_download, 6)

        # 2. HttpChunkDownloader defaults to 6
        task = DownloadTask(task_id="t_seg_6", url="http://example.com/test.zip", destination_folder=".", filename="test.zip")
        downloader = HttpChunkDownloader(task=task)
        self.assertEqual(downloader.num_chunks, 6)

        with tempfile.TemporaryDirectory() as tmpdir:
            tm = TaskManager(tasks_file=os.path.join(tmpdir, "tasks.json"), auto_load=False)

            # 3. TaskManager.start_http_worker defaults to 6
            task2 = DownloadTask(task_id="t_tm_6", url="http://example.com/test2.zip", destination_folder=tmpdir, filename="test2.zip")
            tm.tasks[task2.task_id] = task2
            tm.start_http_worker(task2)
            self.assertIn("t_tm_6", tm.workers)
            self.assertEqual(tm.workers["t_tm_6"].num_chunks, 6)
            tm.remove_task("t_tm_6")

            # 4. CompactDownloadWindow shapes to 6 segments
            compact_win = CompactDownloadWindow(
                task_manager=tm,
                initial_url="http://example.com/file6.zip",
                initial_filename="file6.zip"
            )
            self.assertEqual(len(compact_win._segment_boxes), 6)
            self.assertEqual(compact_win.part_table.rowCount(), 6)
            self.assertIn("6 Connections", compact_win.footer_engine_lbl.text())
            self.assertEqual(compact_win.conn_spin.value(), 6)

            # 5. DownloadDetailWindow shapes to 6 segments
            detail_win = DownloadDetailWindow(task=task, task_manager=tm)
            self.assertEqual(len(detail_win._segment_boxes), 6)
            self.assertEqual(detail_win.part_table.rowCount(), 6)
            detail_win.close()

            # 6. Adjust conn_spin in CompactDownloadWindow to 12 -> shapes to 12
            compact_win.conn_spin.setValue(12)
            self.assertEqual(load_network_settings().segments_per_download, 12)
            self.assertEqual(len(compact_win._segment_boxes), 12)
            self.assertEqual(compact_win.part_table.rowCount(), 12)
            self.assertIn("12 Connections", compact_win.footer_engine_lbl.text())
            compact_win.close()

        # Revert to defaults
        save_network_settings(NetworkSettings())
        print("\n[OK] All Network Settings and UI tests passed successfully!")


if __name__ == "__main__":
    unittest.main()
