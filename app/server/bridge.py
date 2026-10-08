"""
Download Manager - PyQt6 & WebSocket Server Bridge Module

This class is QObject-based and uses PyQt6's 'pyqtSignal' mechanism.
It delivers events and data coming from the WebSocket server running in
the background (in a separate thread) safely (thread-safe) to the
PyQt6 Main Thread (GUI Thread).
"""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict, Any


class ServerBridge(QObject):
    """
    Bi-directional communication bridge between the WebSocket server
    and the PyQt6 GUI/Engine layer.
    """

    # 1. Download and Media Request Signals
    # Triggered when a new file download request arrives from the browser extension
    download_requested = pyqtSignal(dict)

    # Triggered when the browser extension detects a video/audio stream on a page
    media_detected = pyqtSignal(dict)

    # 2. Client Status Signals
    # Triggered with client ID when a new browser extension connects to the socket
    client_connected = pyqtSignal(str)

    # Triggered when a browser extension disconnects from the socket
    client_disconnected = pyqtSignal(str)

    # 3. Server Lifecycle and Logging Signals
    # Emitted when server starts or stops (is_running: bool, info: str)
    server_status_changed = pyqtSignal(bool, str)

    # Emitted to forward internal log/status messages to GUI (level: str, message: str)
    log_emitted = pyqtSignal(str, str)

    def __init__(self, parent: QObject = None):
        super().__init__(parent)

    def emit_download(self, data: Dict[str, Any]) -> None:
        """Forwards download request to GUI layer."""
        self.download_requested.emit(data)

    def emit_media(self, data: Dict[str, Any]) -> None:
        """Forwards media detection request to GUI layer."""
        self.media_detected.emit(data)

    def emit_connected(self, client_id: str) -> None:
        """Notifies new client connection."""
        self.client_connected.emit(client_id)

    def emit_disconnected(self, client_id: str) -> None:
        """Notifies client disconnection."""
        self.client_disconnected.emit(client_id)

    def emit_status(self, is_running: bool, message: str) -> None:
        """Notifies server status change."""
        self.server_status_changed.emit(is_running, message)

    def log(self, level: str, message: str) -> None:
        """Emits log message signal."""
        self.log_emitted.emit(level.upper(), message)

