"""
Download Manager - QThread Based Asynchronous WebSocket Server

This module is an independent QThread listening for incoming connections
from the browser extension. By running its own isolated asyncio event loop,
it never blocks or freezes the PyQt6 GUI Main Thread.
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
    QThread class running the WebSocket server in the background.
    Handles all network operations inside asyncio and dispatches results to GUI via ServerBridge.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6800, bridge: Optional[ServerBridge] = None):
        super().__init__()
        self.host = host
        self.port = port
        self.bridge = bridge or ServerBridge()

        # Thread and Asyncio loop management
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._server = None
        self._is_running = False
        self._connected_clients: Set[WebSocketServerProtocol] = set()

    def run(self) -> None:
        """
        Executed in a separate worker thread when start() is called.
        Creates an isolated asyncio event loop and begins listening for websockets connections.
        """
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._is_running = True

        try:
            self.loop.run_until_complete(self._start_server())
            self.loop.run_forever()
        except Exception as exc:
            self.bridge.log("ERROR", f"WebSocket server run error: {str(exc)}")
            self.bridge.emit_status(False, f"Server error: {str(exc)}")
        finally:
            self._cleanup_loop()
            self._is_running = False
            self.bridge.emit_status(False, "WebSocket server stopped.")

    async def _start_server(self) -> None:
        """Starts socket listener inside asyncio using websockets.serve."""
        try:
            self._server = await websockets.serve(
                self._handle_client,
                self.host,
                self.port,
                ping_interval=20,  # Ping every 20s to keep connection alive
                ping_timeout=10
            )
            info_msg = f"Server active: ws://{self.host}:{self.port}"
            self.bridge.log("INFO", info_msg)
            self.bridge.emit_status(True, info_msg)
        except OSError as exc:
            err_msg = f"Could not open port ({self.port}): {str(exc)}. Another application might be using it."
            self.bridge.log("ERROR", err_msg)
            self.bridge.emit_status(False, err_msg)
            raise

    async def _handle_client(self, websocket: WebSocketServerProtocol) -> None:
        """
        Asynchronous handler coroutine running for each connected browser extension (client).
        """
        client_address = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        self._connected_clients.add(websocket)
        self.bridge.log("INFO", f"New browser extension connected: {client_address}")
        self.bridge.emit_connected(client_address)

        try:
            async for raw_message in websocket:
                # 1. Validate and parse incoming message using protocol parser
                parse_result = ProtocolParser.parse_message(raw_message)

                if not parse_result["success"]:
                    # Return error response to client on invalid request
                    err_reply = ProtocolParser.create_response("ERROR", parse_result["error"])
                    await websocket.send(err_reply)
                    self.bridge.log("WARNING", f"Invalid message received ({client_address}): {parse_result['error']}")
                    continue

                action = parse_result["action"]
                data = parse_result["data"]

                # 2. Trigger appropriate PyQt6 signal and respond with ACK to client
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
                    # Heartbeat response
                    pong = ProtocolParser.create_response(status="PONG", message="Server alive.")
                    await websocket.send(pong)

        except websockets.exceptions.ConnectionClosedOK:
            self.bridge.log("INFO", f"Client closed connection normally: {client_address}")
        except websockets.exceptions.ConnectionClosedError as exc:
            self.bridge.log("WARNING", f"Client connection closed unexpectedly ({client_address}): {exc}")
        except Exception as exc:
            self.bridge.log("ERROR", f"Client processing error ({client_address}): {str(exc)}")
        finally:
            self._connected_clients.discard(websocket)
            self.bridge.emit_disconnected(client_address)
            self.bridge.log("INFO", f"Client disconnected: {client_address}")

    def stop(self) -> None:
        """
        Called to safely stop the server externally (GUI or application shutdown).
        Terminates the asyncio event loop cleanly without crashing QThread.
        """
        if not self._is_running or not self.loop:
            return

        self.bridge.log("INFO", "WebSocket server shutting down...")

        # Inject async stop task into asyncio event loop thread
        asyncio.run_coroutine_threadsafe(self._stop_server_async(), self.loop)
        self.wait(2000)  # Wait up to 2 seconds for QThread to finish cleanly

    async def _stop_server_async(self) -> None:
        """Stop coroutine executing inside asyncio loop."""
        # 1. Close all connected client sockets
        if self._connected_clients:
            close_tasks = [client.close(1001, "Server shutting down") for client in list(self._connected_clients)]
            await asyncio.gather(*close_tasks, return_exceptions=True)
            self._connected_clients.clear()

        # 2. Close websocket server
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # 3. Stop loop
        if self.loop and self.loop.is_running():
            self.loop.stop()

    def _cleanup_loop(self) -> None:
        """Cleans up event loop and any remaining pending tasks."""
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

