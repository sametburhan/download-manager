"""
Download Manager - WebSocket Protocol & Message Parsing Module

This module validates, securely parses, and transforms raw JSON data received
from the browser extension into standardized data models.
It provides resilience against malformed or malicious packets.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import json
import time


class ActionType:
    """Allowed action types coming from the browser extension."""
    DOWNLOAD_URL = "DOWNLOAD_URL"       # Standard file download request
    MEDIA_DETECTED = "MEDIA_DETECTED"   # Video/audio stream detected on page
    PING = "PING"                       # Heartbeat check


@dataclass
class DownloadRequest:
    """Standard file download request model."""
    url: str
    filename: Optional[str] = None
    referrer: Optional[str] = None
    user_agent: Optional[str] = None
    cookies: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Converts model data to dictionary format."""
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
    """Video / Audio capture request model (for yt-dlp or direct stream)."""
    page_url: str
    media_src: Optional[str] = None
    title: Optional[str] = None
    mime_type: Optional[str] = None
    thumbnail: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Converts model data to dictionary format."""
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
    Helper class analyzing raw JSON strings received from the browser
    extension and converting them into validated objects.
    """

    @staticmethod
    def parse_message(raw_data: str) -> Dict[str, Any]:
        """
        Parses raw JSON string and returns validated object according to action type.

        Return Format:
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
                "error": "Empty or invalid data type provided."
            }

        # 1. Validate JSON syntax
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

        # 2. Parse according to action type
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
            # Heartbeat request
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
        Creates JSON response packet to send back to the browser extension.
        """
        response_dict = {
            "status": status,
            "message": message,
            "timestamp": time.time()
        }
        if task_id:
            response_dict["task_id"] = task_id
        return json.dumps(response_dict)

