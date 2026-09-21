"""
Download Manager - WebSocket Protokol ve Mesaj Ayrıştırma Modülü

Bu modül, tarayıcı eklentisinden gelen ham JSON verilerini doğrular (validate),
güvenli bir şekilde ayrıştırır (parse) ve standart veri modellerine dönüştürür.
Hatalı veya kötü niyetli paketlere karşı dayanıklılık sağlar.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import json
import time


class ActionType:
    """Tarayıcı eklentisinden gelebilecek izin verilen eylem türleri."""
    DOWNLOAD_URL = "DOWNLOAD_URL"       # Normal dosya indirme isteği
    MEDIA_DETECTED = "MEDIA_DETECTED"   # Sayfada yakalanan video/ses akışı
    PING = "PING"                       # Canlılık kontrolü (Heartbeat)


@dataclass
class DownloadRequest:
    """Standart dosya indirme istek modeli."""
    url: str
    filename: Optional[str] = None
    referrer: Optional[str] = None
    user_agent: Optional[str] = None
    cookies: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Model verisini sözlük (dict) formatına çevirir."""
        return {
            "url": self.url,
            "filename": self.filename,
            "referrer": self.referrer,
            "user_agent": self.user_agent,
            "cookies": self.cookies,
            "headers": self.headers,
            "timestamp": self.timestamp,
        }


@dataclass
class MediaRequest:
    """Video / Ses yakalama istek modeli (yt-dlp veya doğrudan akış için)."""
    page_url: str
    media_src: Optional[str] = None
    title: Optional[str] = None
    mime_type: Optional[str] = None
    thumbnail: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Model verisini sözlük (dict) formatına çevirir."""
        return {
            "page_url": self.page_url,
            "media_src": self.media_src,
            "title": self.title,
            "mime_type": self.mime_type,
            "thumbnail": self.thumbnail,
            "timestamp": self.timestamp,
        }


class ProtocolParser:
    """
    Tarayıcı eklentisinden gelen ham metinleri (JSON) analiz eden ve
    uygun nesnelere dönüştüren yardımcı sınıf.
    """

    @staticmethod
    def parse_message(raw_data: str) -> Dict[str, Any]:
        """
        Ham JSON dizesini parse eder ve eylem tipine göre doğrulanmış nesne döndürür.

        Dönüş Formatı:
        {
            "success": bool,
            "action": str,
            "data": DownloadRequest | MediaRequest | str | None,
            "error": str | None
        }
        """
        if not raw_data or not isinstance(raw_data, str):
            return {
                "success": False,
                "action": "UNKNOWN",
                "data": None,
                "error": "Boş veya geçersiz veri tipi gönderildi."
            }

        # 1. JSON sözdizimi doğrulama
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            return {
                "success": False,
                "action": "INVALID_JSON",
                "data": None,
                "error": f"JSON parse error: {str(exc)}"
            }

        if not isinstance(payload, dict):
            return {
                "success": False,
                "action": "INVALID_FORMAT",
                "data": None,
                "error": "Root object must be a JSON dictionary (dict)."
            }

        action = payload.get("action", "").upper()
        data_block = payload.get("payload", {})

        # 2. Eylem tipine göre ayrıştırma
        if action == ActionType.DOWNLOAD_URL:
            url = data_block.get("url")
            if not url or not isinstance(url, str) or not url.startswith(("http://", "https://", "ftp://", "file://")):
                return {
                    "success": False,
                    "action": action,
                    "data": None,
                    "error": "Valid URL address was not provided (http/https/ftp/file required)."
                }

            download_req = DownloadRequest(
                url=url.strip(),
                filename=data_block.get("filename"),
                referrer=data_block.get("referrer"),
                user_agent=data_block.get("user_agent"),
                cookies=data_block.get("cookies"),
                headers=data_block.get("headers") if isinstance(data_block.get("headers"), dict) else {},
                timestamp=payload.get("timestamp", time.time())
            )
            return {
                "success": True,
                "action": action,
                "data": download_req,
                "error": None
            }

        elif action == ActionType.MEDIA_DETECTED:
            page_url = data_block.get("page_url") or data_block.get("url")
            if not page_url:
                return {
                    "success": False,
                    "action": action,
                    "data": None,
                    "error": "Page URL (page_url) is required for media detection."
                }

            media_req = MediaRequest(
                page_url=page_url.strip(),
                media_src=data_block.get("media_src"),
                title=data_block.get("title"),
                mime_type=data_block.get("mime_type"),
                thumbnail=data_block.get("thumbnail"),
                timestamp=payload.get("timestamp", time.time())
            )
            return {
                "success": True,
                "action": action,
                "data": media_req,
                "error": None
            }

        elif action == ActionType.PING:
            # Heartbeat isteği
            return {
                "success": True,
                "action": action,
                "data": "PONG",
                "error": None
            }

        else:
            return {
                "success": False,
                "action": action,
                "data": None,
                "error": f"Unsupported action type: '{action}'"
            }

    @staticmethod
    def create_response(status: str, message: str, task_id: Optional[str] = None) -> str:
        """
        Tarayıcı eklentisine geri gönderilecek JSON yanıt paketini oluşturur.
        """
        response_dict = {
            "status": status,
            "message": message,
            "timestamp": time.time()
        }
        if task_id:
            response_dict["task_id"] = task_id
        return json.dumps(response_dict)
