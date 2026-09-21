"""
Aşama 1 Otomatik Doğrulama Testi (WebSocket + Protocol + Bridge Entegrasyonu)

Bu script, bağımsız olarak WebSocket sunucusunu bir QThread içinde başlatır,
simüle edilmiş bir tarayıcı eklentisi gibi sokete bağlanır, farklı senaryolarda
mesajlar gönderir ve sunucunun yanıtları ile PyQt sinyallerinin doğruluğunu test eder.
"""

import sys
import os
import json
import asyncio
import unittest

# Proje ana dizinini Python arama yoluna ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
import websockets

from app.server.protocol import ProtocolParser, ActionType
from app.server.bridge import ServerBridge
from app.server.ws_server import WebSocketServerThread


class TestWebSocketBridgeIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.bridge = ServerBridge()
        cls.port = 6801  # Testler için izole bir port
        cls.ws_thread = WebSocketServerThread(host="127.0.0.1", port=cls.port, bridge=cls.bridge)
        cls.ws_thread.start()

        # Sunucunun başlaması için kısa bir bekleme
        cls.app.processEvents()
        import time
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.ws_thread.stop()
        cls.ws_thread.wait()

    def test_01_protocol_parser_valid_download(self):
        """Protokol ayrıştırıcısının geçerli bir indirme isteğini doğru parse ettiğini test eder."""
        raw_json = json.dumps({
            "action": "DOWNLOAD_URL",
            "payload": {
                "url": "https://example.com/archive.zip",
                "filename": "archive.zip",
                "referrer": "https://example.com"
            }
        })
        result = ProtocolParser.parse_message(raw_json)
        self.assertTrue(result["success"])
        self.assertEqual(result["action"], ActionType.DOWNLOAD_URL)
        self.assertEqual(result["data"].url, "https://example.com/archive.zip")
        self.assertEqual(result["data"].filename, "archive.zip")

    def test_02_protocol_parser_invalid_json(self):
        """Bozuk JSON gönderildiğinde sunucunun çökmeden hata döndürdüğünü test eder."""
        raw_bad = "{bu_gecersiz_bir_json_verisidir"
        result = ProtocolParser.parse_message(raw_bad)
        self.assertFalse(result["success"])
        self.assertEqual(result["action"], "INVALID_JSON")
        self.assertIn("JSON parse error", result["error"])

    def test_03_protocol_parser_invalid_url(self):
        """Eksik veya geçersiz protokol içeren URL'lerin reddedildiğini test eder."""
        raw_json = json.dumps({
            "action": "DOWNLOAD_URL",
            "payload": {
                "url": "javascript:alert(1)"
            }
        })
        result = ProtocolParser.parse_message(raw_json)
        self.assertFalse(result["success"])
        self.assertIn("Valid URL address was not provided", result["error"])

    def test_04_websocket_live_communication(self):
        """Canlı WebSocket soketine bağlanıp istek-yanıt ve PyQt sinyal akışını test eder."""
        received_signals = []

        def on_download(data):
            received_signals.append(("download", data))

        def on_media(data):
            received_signals.append(("media", data))

        self.bridge.download_requested.connect(on_download)
        self.bridge.media_detected.connect(on_media)

        async def run_client_simulation():
            uri = f"ws://127.0.0.1:{self.port}"
            async with websockets.connect(uri) as ws:
                # 1. Ping testi
                await ws.send(json.dumps({"action": "PING"}))
                resp1 = json.loads(await ws.recv())
                self.assertEqual(resp1.get("status"), "PONG")

                # 2. DOWNLOAD_URL testi
                download_msg = {
                    "action": "DOWNLOAD_URL",
                    "payload": {
                        "url": "https://speed.hetzner.de/100MB.bin",
                        "filename": "100MB.bin"
                    }
                }
                await ws.send(json.dumps(download_msg))
                resp2 = json.loads(await ws.recv())
                self.assertEqual(resp2.get("status"), "ACCEPTED")

                # 3. MEDIA_DETECTED testi
                media_msg = {
                    "action": "MEDIA_DETECTED",
                    "payload": {
                        "page_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                        "title": "Rick Astley - Never Gonna Give You Up"
                    }
                }
                await ws.send(json.dumps(media_msg))
                resp3 = json.loads(await ws.recv())
                self.assertEqual(resp3.get("status"), "ACCEPTED")

        # Asenkron istemci testini çalıştır
        asyncio.run(run_client_simulation())

        # PyQt event queue'yu işle
        self.app.processEvents()

        # Sinyallerin PyQt bridge tarafından yakalandığını doğrula
        self.assertEqual(len(received_signals), 2)
        self.assertEqual(received_signals[0][0], "download")
        self.assertEqual(received_signals[0][1]["url"], "https://speed.hetzner.de/100MB.bin")
        self.assertEqual(received_signals[1][0], "media")
        print("\n[OK] All Stage 1 integration tests passed successfully!")


if __name__ == "__main__":
    unittest.main()
