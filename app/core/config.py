"""
Download Manager - Network and Application Configuration (config.py)

User network parameters (timeouts, connection segments, speed limits, proxies, etc.)
are serialized and managed in JSON format via this module.
"""

import os
import json
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class NetworkSettings:
    """Network and download parameter configuration."""
    connection_timeout: int = 30               # Connection timeout in seconds
    segments_per_download: int = 8             # Concurrent chunk segments per download
    max_retries: int = 10                      # Maximum retry attempts
    speed_limit_enabled: bool = False          # Whether speed limiter is enabled
    speed_limit_kbs: int = 2600                # Speed limit in KB/s (0 = unlimited)
    proxy_mode: str = "system"                 # "system", "none", "manual"
    proxy_type: str = "HTTP"                   # "HTTP", "HTTPS", "SOCKS4", "SOCKS5"
    proxy_host: str = ""                       # Proxy server hostname/IP
    proxy_port: int = 0                        # Proxy port
    proxy_user: str = ""                       # Proxy username
    proxy_pass: str = ""                       # Proxy password


def get_config_dir() -> str:
    """Returns the directory where configurations are stored, creating it if necessary."""
    config_dir = os.path.join(os.path.expanduser("~"), ".download_manager")
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def get_config_file_path() -> str:
    """Returns the full path to settings.json."""
    return os.path.join(get_config_dir(), "settings.json")


def get_tasks_file_path() -> str:
    """Returns the full path to tasks.json."""
    custom_path = os.environ.get("DOWNLOAD_MANAGER_TASKS_FILE")
    if custom_path:
        return custom_path
    return os.path.join(get_config_dir(), "tasks.json")


def get_temp_dir() -> str:
    """Returns the directory for temporary chunk (.part) and metadata files, creating it if needed."""
    temp_dir = os.path.join(get_config_dir(), "temp")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def load_network_settings() -> NetworkSettings:
    """Loads settings from settings.json; returns default settings if file is absent or corrupted."""
    file_path = get_config_file_path()
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return NetworkSettings(
                    connection_timeout=int(data.get("connection_timeout", 30)),
                    segments_per_download=int(data.get("segments_per_download", 8)),
                    max_retries=int(data.get("max_retries", 10)),
                    speed_limit_enabled=bool(data.get("speed_limit_enabled", False)),
                    speed_limit_kbs=int(data.get("speed_limit_kbs", 2600)),
                    proxy_mode=str(data.get("proxy_mode", "system")),
                    proxy_type=str(data.get("proxy_type", "HTTP")).upper(),
                    proxy_host=str(data.get("proxy_host", "")),
                    proxy_port=int(data.get("proxy_port", 0)),
                    proxy_user=str(data.get("proxy_user", "")),
                    proxy_pass=str(data.get("proxy_pass", ""))
                )
        except Exception as e:
            print(f"Failed to load settings: {e}")

    return NetworkSettings()


def save_network_settings(settings: NetworkSettings) -> bool:
    """Saves settings to settings.json file."""
    file_path = get_config_file_path()
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Failed to save settings: {e}")
        return False
