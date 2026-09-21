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
        # System Proxy -> Host pasif
        dialog.combo_proxy.setCurrentIndex(0)
        self.assertFalse(dialog.input_host.isEnabled())

        # Manual Proxy -> Host aktif
        dialog.combo_proxy.setCurrentIndex(2)
        self.assertTrue(dialog.input_host.isEnabled())
        self.assertTrue(dialog.spin_port.isEnabled())

        dialog.close()
        print("\n[OK] Tum Network Settings ayar ve arayuz testleri basariyla gecti!")


if __name__ == "__main__":
    unittest.main()
