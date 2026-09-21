"""
Download Manager - PyQt6 ve WebSocket Sunucusu Köprü (Bridge) Modülü

Bu sınıf, QObject tabanlı olup PyQt6'nın 'pyqtSignal' mekanizmasını kullanır.
Arka planda (ayrı bir iş parçacığında) çalışan WebSocket sunucusundan gelen olayları
ve verileri doğrudan PyQt6 Ana İş Parçacığına (GUI Thread) güvenli (thread-safe)
bir şekilde iletir.
"""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict, Any


class ServerBridge(QObject):
    """
    WebSocket sunucusu ile PyQt6 GUI/Motor katmanı arasındaki
    çift yönlü haberleşme köprüsü.
    """

    # 1. İndirme ve Medya İstek Sinyalleri
    # Tarayıcı eklentisinden yeni bir dosya indirme isteği geldiğinde tetiklenir
    download_requested = pyqtSignal(dict)

    # Tarayıcı eklentisi bir sayfada video/ses akışı yakaladığında tetiklenir
    media_detected = pyqtSignal(dict)

    # 2. İstemci Durum Sinyalleri
    # Yeni bir tarayıcı eklentisi sokete bağlandığında istemci kimliği ile tetiklenir
    client_connected = pyqtSignal(str)

    # Tarayıcı eklentisi soket bağlantısını kapattığında tetiklenir
    client_disconnected = pyqtSignal(str)

    # 3. Sunucu Yaşam Döngüsü ve Log Sinyalleri
    # Sunucu başladığında veya durduğunda (is_running: bool, info: str)
    server_status_changed = pyqtSignal(bool, str)

    # Uygulama içi log/durum mesajlarını GUI'ye yazdırmak için (seviye: str, mesaj: str)
    log_emitted = pyqtSignal(str, str)

    def __init__(self, parent: QObject = None):
        super().__init__(parent)

    def emit_download(self, data: Dict[str, Any]) -> None:
        """İndirme isteğini GUI katmanına aktarır."""
        self.download_requested.emit(data)

    def emit_media(self, data: Dict[str, Any]) -> None:
        """Medya yakalama isteğini GUI katmanına aktarır."""
        self.media_detected.emit(data)

    def emit_connected(self, client_id: str) -> None:
        """Yeni istemci bağlantısını bildirir."""
        self.client_connected.emit(client_id)

    def emit_disconnected(self, client_id: str) -> None:
        """İstemci ayrılışını bildirir."""
        self.client_disconnected.emit(client_id)

    def emit_status(self, is_running: bool, message: str) -> None:
        """Sunucu durum değişimini bildirir."""
        self.server_status_changed.emit(is_running, message)

    def log(self, level: str, message: str) -> None:
        """Log mesajını sinyal olarak fırlatır."""
        self.log_emitted.emit(level.upper(), message)
