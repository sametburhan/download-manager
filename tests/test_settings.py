"""
Ağ Ayarları ve Yapılandırma Testleri (test_settings.py)

Bu test dosyası:
1. NetworkSettings veri modelinin varsayılanlarını ve JSON kaydetme/yükleme işlemlerini doğrular.
2. NetworkSettingsDialog arayüzünün görseldeki alanlarını (Timeout, Segments, Retries, Speed Limit, Proxy) test eder.
3. Hız sınırı ve proxy alanlarının dinamik aktifleşme/pasifleşme mantığını test eder.
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
        """Varsayılan ağ ayarları değerlerini doğrular."""
        s = NetworkSettings()
        self.assertEqual(s.connection_timeout, 30)
        self.assertEqual(s.segments_per_download, 8)
        self.assertEqual(s.max_retries, 10)
        self.assertFalse(s.speed_limit_enabled)
        self.assertEqual(s.speed_limit_kbs, 2600)
        self.assertEqual(s.proxy_mode, "system")

    def test_02_save_and_load_settings(self):
        """Ayarların JSON dosyasına kaydedilip geri yüklenebildiğini doğrular."""
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

        # Varsayılana geri al
        save_network_settings(NetworkSettings())

    def test_03_settings_dialog_ui_components(self):
        """NetworkSettingsDialog bileşenlerinin ve kullanıcı görselindeki alanların varlığını doğrular."""
        dialog = NetworkSettingsDialog()

        self.assertEqual(dialog.windowTitle(), "Network settings")
        self.assertEqual(dialog.spin_timeout.value(), 30)
        self.assertEqual(dialog.spin_segments.value(), 8)
        self.assertEqual(dialog.spin_retry.value(), 10)

        # Hız Sınırı Alanı
        dialog.chk_speed_limit.setChecked(False)
        self.assertFalse(dialog.spin_speed_limit.isEnabled())
        dialog.chk_speed_limit.setChecked(True)
        self.assertTrue(dialog.spin_speed_limit.isEnabled())

        # Proxy Modu Değişimi
        # System Proxy -> Host ve Type pasif
        dialog.combo_proxy.setCurrentIndex(0)
        self.assertFalse(dialog.combo_proxy_type.isEnabled())
        self.assertFalse(dialog.input_host.isEnabled())

        # Manual Proxy -> Host ve Type aktif
        dialog.combo_proxy.setCurrentIndex(2)
        self.assertTrue(dialog.combo_proxy_type.isEnabled())
        self.assertTrue(dialog.input_host.isEnabled())
        self.assertTrue(dialog.spin_port.isEnabled())

        # Proxy Type seçenekleri
        types = [dialog.combo_proxy_type.itemText(i) for i in range(dialog.combo_proxy_type.count())]
        self.assertIn("HTTP", types)
        self.assertIn("HTTPS", types)
        self.assertIn("SOCKS4", types)
        self.assertIn("SOCKS5", types)

        dialog.close()

    def test_04_socks_proxy_settings_and_urls(self):
        """SOCKS4 ve SOCKS5 proxy ayarlarının kaydedilmesi, URL üretimi ve transport oluşturulmasını test eder."""
        from app.core.http_downloader import HttpChunkDownloader
        from app.core.media_downloader import get_ytdl_base_opts
        from httpx_socks import SyncProxyTransport

        # SOCKS5 Testi
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

        # SOCKS4 Testi
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

        # Varsayılana geri al
        save_network_settings(NetworkSettings())
        print("\n[OK] All Network Settings and UI tests passed successfully!")


if __name__ == "__main__":
    unittest.main()
