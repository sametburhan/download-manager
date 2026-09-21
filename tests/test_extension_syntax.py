"""
Aşama 4 Tarayıcı Eklentisi Doğrulama ve Bütünlük Testi

Bu test:
1. extension/manifest.json dosyasının geçerli bir Manifest V3 olduğunu ve tüm referans dosyalarının diskte bulunduğunu teyit eder.
2. background.js, popup.html, popup.js ve ikon dosyalarının varlığını ve bütünlüğünü denetler.
3. background.js'in göndereceği exact JSON paketlerini WebSocket sunucusuna simüle ederek uçtan uca kabul edildiğini doğrular.
"""

import sys
import os
import json
import asyncio
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
import websockets

from app.server.bridge import ServerBridge
from app.server.ws_server import WebSocketServerThread


class TestExtensionIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.ext_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "extension"))

        # Test için izole bir WebSocket sunucusu
        cls.port = 6802
        cls.bridge = ServerBridge()
        cls.ws_thread = WebSocketServerThread(host="127.0.0.1", port=cls.port, bridge=cls.bridge)
        cls.ws_thread.start()

        import time
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        cls.ws_thread.stop()
        cls.ws_thread.wait()

    def test_01_manifest_v3_structure(self):
        """manifest.json dosyasının geçerliliğini ve Manifest V3 standartlarını doğrular."""
        manifest_path = os.path.join(self.ext_dir, "manifest.json")
        self.assertTrue(os.path.exists(manifest_path))

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual(manifest.get("manifest_version"), 3)
        self.assertIn("downloads", manifest.get("permissions", []))
        self.assertIn("webRequest", manifest.get("permissions", []))
        self.assertIn("contextMenus", manifest.get("permissions", []))
        self.assertIn("<all_urls>", manifest.get("host_permissions", []))

        # Referans verilen dosyaların diskte varlığını kontrol et
        bg_worker = manifest.get("background", {}).get("service_worker")
        self.assertTrue(os.path.exists(os.path.join(self.ext_dir, bg_worker)))

        popup_html = manifest.get("action", {}).get("default_popup")
        self.assertTrue(os.path.exists(os.path.join(self.ext_dir, popup_html)))

        icons = manifest.get("icons", {})
        for size, icon_rel in icons.items():
            icon_full = os.path.join(self.ext_dir, icon_rel)
            self.assertTrue(os.path.exists(icon_full), f"İkon bulunamadı: {icon_full}")

    def test_02_extension_scripts_exist(self):
        """background.js ve popup dosyalarının içerik kontrolü."""
        bg_path = os.path.join(self.ext_dir, "background.js")
        popup_html_path = os.path.join(self.ext_dir, "popup", "popup.html")
        popup_js_path = os.path.join(self.ext_dir, "popup", "popup.js")
        popup_css_path = os.path.join(self.ext_dir, "popup", "popup.css")
        content_js_path = os.path.join(self.ext_dir, "content.js")

        self.assertGreater(os.path.getsize(bg_path), 500)
        self.assertGreater(os.path.getsize(popup_js_path), 200)
        self.assertGreater(os.path.getsize(popup_css_path), 200)

        with open(popup_html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
            self.assertIn("clearMediaBtn", html_content)

        with open(popup_js_path, "r", encoding="utf-8") as f:
            pjs_content = f.read()
            self.assertIn("CLEAR_TAB_MEDIA", pjs_content)
            self.assertIn("parsePlatformMedia", pjs_content)

        with open(bg_path, "r", encoding="utf-8") as f:
            bg_content = f.read()
            self.assertIn("CLEAR_TAB_MEDIA", bg_content)
            self.assertIn("parsePlatformMedia", bg_content)

        with open(content_js_path, "r", encoding="utf-8") as f:
            content_js = f.read()
            self.assertIn("CLEAR_PAGE_MEDIA", content_js)
            self.assertIn("isYouTubeVideo", content_js)

    def test_03_simulate_extension_ws_interception(self):
        """background.js tarafından fırlatılan indirme ve medya paketlerinin sunucu yanıtlarını doğrular."""
        received_downloads = []
        received_medias = []

        self.bridge.download_requested.connect(lambda d: received_downloads.append(d))
        self.bridge.media_detected.connect(lambda d: received_medias.append(d))

        async def simulate_browser():
            uri = f"ws://127.0.0.1:{self.port}"
            async with websockets.connect(uri) as ws:
                # 1. Heartbeat
                await ws.send(json.dumps({"action": "PING", "payload": {}}))
                pong = json.loads(await ws.recv())
                self.assertEqual(pong.get("status"), "PONG")

                # 2. background.js chrome.downloads.onCreated simülasyonu
                dl_packet = {
                    "action": "DOWNLOAD_URL",
                    "payload": {
                        "url": "https://releases.ubuntu.com/22.04/ubuntu-22.04.iso",
                        "filename": "ubuntu-22.04.iso",
                        "referrer": "https://releases.ubuntu.com/",
                        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
                    },
                    "timestamp": 1725800000
                }
                await ws.send(json.dumps(dl_packet))
                ack1 = json.loads(await ws.recv())
                self.assertEqual(ack1.get("status"), "ACCEPTED")

                # 3. background.js webRequest medya akışı koklama simülasyonu
                media_packet = {
                    "action": "MEDIA_DETECTED",
                    "payload": {
                        "page_url": "https://video.example.com/stream/master.m3u8",
                        "media_src": "https://video.example.com/stream/master.m3u8",
                        "mime_type": "application/x-mpegURL",
                        "title": "Canli Yayin Akisi"
                    },
                    "timestamp": 1725800001
                }
                await ws.send(json.dumps(media_packet))
                ack2 = json.loads(await ws.recv())
                self.assertEqual(ack2.get("status"), "ACCEPTED")

        asyncio.run(simulate_browser())
        self.app.processEvents()

        # Sinyallerin PyQt tarafında yakalandığını kontrol et
        self.assertEqual(len(received_downloads), 1)
        self.assertEqual(received_downloads[0]["filename"], "ubuntu-22.04.iso")

        self.assertEqual(len(received_medias), 1)
        self.assertIn("master.m3u8", received_medias[0]["page_url"])

    def test_04_auto_capture_deactivation_logic(self):
        """Automatic Download Interception deaktif durum kontrolü ve İngilizce uyarıların varlığını doğrular."""
        bg_path = os.path.join(self.ext_dir, "background.js")
        popup_js_path = os.path.join(self.ext_dir, "popup", "popup.js")
        popup_css_path = os.path.join(self.ext_dir, "popup", "popup.css")
        popup_html_path = os.path.join(self.ext_dir, "popup", "popup.html")
        content_js_path = os.path.join(self.ext_dir, "content.js")

        with open(bg_path, "r", encoding="utf-8") as f:
            bg_content = f.read()
            self.assertIn("autoCaptureEnabled", bg_content)
            self.assertIn("AUTO_CAPTURE_DISABLED", bg_content)
            self.assertIn('"OFF"', bg_content)

        with open(popup_js_path, "r", encoding="utf-8") as f:
            popup_js = f.read()
            self.assertIn("autoCaptureToggle", popup_js)
            self.assertIn("highlightAutoCaptureRow", popup_js)
            self.assertIn("Automatic Download Interception is disabled!", popup_js)
            self.assertIn("Enable Switch ⚠️", popup_js)

        with open(content_js_path, "r", encoding="utf-8") as f:
            content_js = f.read()
            self.assertIn("autoCaptureEnabled", content_js)
            self.assertIn("Please enable Interception!", content_js)

        with open(popup_html_path, "r", encoding="utf-8") as f:
            popup_html = f.read()
            self.assertIn('id="autoCaptureCard"', popup_html)

        with open(popup_css_path, "r", encoding="utf-8") as f:
            popup_css = f.read()
            self.assertIn("pulseWarning", popup_css)
            self.assertIn("highlight-pulse", popup_css)

    def test_05_startup_guard_and_interception_filters(self):
        """background.js dosyasında tarayıcı açılış koruması ve eski indirme filtrelerini doğrular."""
        bg_path = os.path.join(self.ext_dir, "background.js")
        with open(bg_path, "r", encoding="utf-8") as f:
            bg_content = f.read()

        self.assertIn("isStartingUp", bg_content)
        self.assertIn("STARTUP_GRACE_PERIOD_MS", bg_content)
        self.assertIn("endStartupGracePeriod", bg_content)
        self.assertIn("processedDownloadIds", bg_content)
        self.assertIn('"in_progress"', bg_content)
        self.assertIn("bytesReceived", bg_content)
        self.assertIn("onStartup", bg_content)

    def test_06_clear_and_suppression_lifecycle(self):
        """Eklentide 'Temizle' (clear) sonrasi eski videolarin baskilanmasi ve yeni videolarin yakalanmasini dogrular."""
        bg_path = os.path.join(self.ext_dir, "background.js")
        popup_js_path = os.path.join(self.ext_dir, "popup", "popup.js")
        content_js_path = os.path.join(self.ext_dir, "content.js")

        with open(bg_path, "r", encoding="utf-8") as f:
            bg = f.read()
            self.assertIn("clearedMediaUrlsByTab", bg)
            self.assertIn("googlevideo.com", bg)
            self.assertIn("/videoplayback", bg)
            self.assertIn("RESCAN_TAB_MEDIA", bg)
            self.assertIn("updateTabBadge(tabId)", bg)

        with open(content_js_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("clearedMediaKeys", content)
            self.assertIn("resetCleared", content)

        with open(popup_js_path, "r", encoding="utf-8") as f:
            popup = f.read()
            self.assertIn("currentDisplayedMedia", popup)
            self.assertIn("clearedUrls", popup)
            self.assertIn("RESCAN_TAB_MEDIA", popup)

    def test_07_context_menu_and_file_protocol(self):
        """Context menu eklenti kodu, pending queue ve file:// URL sunucu iletimini dogrular."""
        bg_path = os.path.join(self.ext_dir, "background.js")
        with open(bg_path, "r", encoding="utf-8") as f:
            bg = f.read()

        self.assertIn("pendingMessages", bg)
        self.assertIn("flushPendingMessages", bg)
        self.assertIn("setupContextMenu", bg)
        self.assertIn("dm_download_link", bg)

        manifest_path = os.path.join(self.ext_dir, "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertIn("notifications", manifest.get("permissions", []))

        # file:// URL gonderimi simülasyonu
        received = []
        self.bridge.download_requested.connect(lambda d: received.append(d))

        async def test_file_url():
            uri = f"ws://127.0.0.1:{self.port}"
            async with websockets.connect(uri) as ws:
                file_packet = {
                    "action": "DOWNLOAD_URL",
                    "payload": {
                        "url": "file:///C:/Users/samet/Desktop/download%20manager/website/assets/DownloadManagerSetup.exe",
                        "filename": "DownloadManagerSetup.exe",
                        "referrer": "file:///C:/Users/samet/Desktop/download%20manager/website/index.html",
                        "user_agent": "Mozilla/5.0 Chrome/120.0.0.0"
                    }
                }
                await ws.send(json.dumps(file_packet))
                res = json.loads(await ws.recv())
                self.assertEqual(res.get("status"), "ACCEPTED")

        asyncio.run(test_file_url())
        self.app.processEvents()
        self.assertGreaterEqual(len(received), 1)
        self.assertEqual(received[-1]["filename"], "DownloadManagerSetup.exe")
        self.assertTrue(received[-1]["url"].startswith("file://"))

        print("\n[OK] Tum Asama 4 eklenti, temizleme ve iletisim testleri basariyla gecti!")


if __name__ == "__main__":
    unittest.main()

