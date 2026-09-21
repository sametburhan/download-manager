"""
Download Manager - QThread Tabanlı Asenkron WebSocket Sunucusu

Bu modül, tarayıcı eklentisinden gelen bağlantıları dinleyen bağımsız bir
QThread iş parçacığıdır. Kendi izole asyncio event loop'unu çalıştırarak
PyQt6 ana arayüzünü (GUI Main Thread) asla dondurmaz veya kilitlenmeye sokmaz.
"""

import asyncio
import logging
from typing import Optional, Set
from PyQt6.QtCore import QThread

import websockets
from websockets.server import WebSocketServerProtocol

from app.server.protocol import ProtocolParser, ActionType
from app.server.bridge import ServerBridge


class WebSocketServerThread(QThread):
    """
    WebSocket sunucusunu arka planda çalıştıran QThread sınıfı.
    Tüm ağ operasyonlarını asyncio içinde çözer ve sonuçları ServerBridge ile GUI'ye bildirir.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6800, bridge: Optional[ServerBridge] = None):
        super().__init__()
        self.host = host
        self.port = port
        self.bridge = bridge or ServerBridge()

        # Thread ve Asyncio döngü yönetimi
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._server = None
        self._is_running = False
        self._connected_clients: Set[WebSocketServerProtocol] = set()

    def run(self) -> None:
        """
        QThread başlatıldığında (start() çağrıldığında) bu metot ayrı bir iş parçacığında yürütülür.
        Burada izole bir asyncio event loop oluşturulur ve websockets sunucusu dinlemeye başlar.
        """
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._is_running = True

        try:
            self.loop.run_until_complete(self._start_server())
            self.loop.run_forever()
        except Exception as exc:
            self.bridge.log("ERROR", f"WebSocket sunucusu çalışma hatası: {str(exc)}")
            self.bridge.emit_status(False, f"Sunucu hatası: {str(exc)}")
        finally:
            self._cleanup_loop()
            self._is_running = False
            self.bridge.emit_status(False, "WebSocket sunucusu kapatıldı.")

    async def _start_server(self) -> None:
        """Asyncio içinde websockets.serve ile soket dinlemesini başlatır."""
        try:
            self._server = await websockets.serve(
                self._handle_client,
                self.host,
                self.port,
                ping_interval=20,  # 20 saniyede bir ping atarak bağlantıyı canlı tutar
                ping_timeout=10
            )
            info_msg = f"Sunucu aktif: ws://{self.host}:{self.port}"
            self.bridge.log("INFO", info_msg)
            self.bridge.emit_status(True, info_msg)
        except OSError as exc:
            err_msg = f"Port ({self.port}) açılamadı: {str(exc)}. Başka bir uygulama kullanıyor olabilir."
            self.bridge.log("ERROR", err_msg)
            self.bridge.emit_status(False, err_msg)
            raise

    async def _handle_client(self, websocket: WebSocketServerProtocol) -> None:
        """
        Bağlanan her bir tarayıcı eklentisi (istemci) için çalışan asenkron işleyici coroutine.
        """
        client_address = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        self._connected_clients.add(websocket)
        self.bridge.log("INFO", f"Yeni tarayıcı eklentisi bağlandı: {client_address}")
        self.bridge.emit_connected(client_address)

        try:
            async for raw_message in websocket:
                # 1. Gelen mesajı protokol parser ile doğrula ve ayrıştır
                parse_result = ProtocolParser.parse_message(raw_message)

                if not parse_result["success"]:
                    # Hatalı/geçersiz istek durumunda istemciye bilgilendirici hata dön
                    err_reply = ProtocolParser.create_response("ERROR", parse_result["error"])
                    await websocket.send(err_reply)
                    self.bridge.log("WARNING", f"Geçersiz mesaj alındı ({client_address}): {parse_result['error']}")
                    continue

                action = parse_result["action"]
                data = parse_result["data"]

                # 2. Eyleme göre uygun PyQt6 sinyalini tetikle ve istemciye onay (ACK) dön
                if action == ActionType.DOWNLOAD_URL:
                    req_dict = data.to_dict()
                    self.bridge.emit_download(req_dict)
                    ack = ProtocolParser.create_response(
                        status="ACCEPTED",
                        message="Download task forwarded to desktop application."
                    )
                    await websocket.send(ack)
                    self.bridge.log("INFO", f"Download request received: {req_dict.get('url')}")

                elif action == ActionType.MEDIA_DETECTED:
                    media_dict = data.to_dict()
                    self.bridge.emit_media(media_dict)
                    ack = ProtocolParser.create_response(
                        status="ACCEPTED",
                        message="Media stream captured and forwarded to desktop application."
                    )
                    await websocket.send(ack)
                    self.bridge.log("INFO", f"Media detected: {media_dict.get('title') or media_dict.get('page_url')}")

                elif action == ActionType.PING:
                    # Canlılık kontrolüne yanıt
                    pong = ProtocolParser.create_response(status="PONG", message="Server alive.")
                    await websocket.send(pong)

        except websockets.exceptions.ConnectionClosedOK:
            self.bridge.log("INFO", f"İstemci bağlantıyı normal şekilde sonlandırdı: {client_address}")
        except websockets.exceptions.ConnectionClosedError as exc:
            self.bridge.log("WARNING", f"İstemci bağlantısı beklenmedik şekilde koptu ({client_address}): {exc}")
        except Exception as exc:
            self.bridge.log("ERROR", f"İstemci işleme hatası ({client_address}): {str(exc)}")
        finally:
            self._connected_clients.discard(websocket)
            self.bridge.emit_disconnected(client_address)
            self.bridge.log("INFO", f"İstemci ayrıldı: {client_address}")

    def stop(self) -> None:
        """
        Sunucuyu dışarıdan (GUI veya uygulama kapanışında) güvenli bir şekilde
        durdurmak için çağrılır. QThread'i kırmadan asyncio döngüsünü kapatır.
        """
        if not self._is_running or not self.loop:
            return

        self.bridge.log("INFO", "WebSocket sunucusu kapatılıyor...")

        # Asenkron durdurma işlemini asyncio event loop iş parçacığına enjekte et
        asyncio.run_coroutine_threadsafe(self._stop_server_async(), self.loop)
        self.wait(2000)  # QThread'in temiz bir şekilde sonlanması için 2 saniye bekle

    async def _stop_server_async(self) -> None:
        """Asyncio döngüsü içinde çalışan durdurma coroutine'i."""
        # 1. Bağlı olan tüm istemcilerin soketlerini kapat
        if self._connected_clients:
            close_tasks = [client.close(1001, "Sunucu kapanıyor") for client in list(self._connected_clients)]
            await asyncio.gather(*close_tasks, return_exceptions=True)
            self._connected_clients.clear()

        # 2. Websocket sunucusunu kapat
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # 3. Loop'u durdur
        if self.loop and self.loop.is_running():
            self.loop.stop()

    def _cleanup_loop(self) -> None:
        """Event loop ve arkada kalan görevleri (tasks) temizler."""
        if not self.loop:
            return

        try:
            pending_tasks = asyncio.all_tasks(self.loop)
            for task in pending_tasks:
                task.cancel()
            if pending_tasks:
                self.loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
            self.loop.close()
        except Exception as exc:
            pass
