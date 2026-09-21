"""
Download Manager - Ağ ve Uygulama Ayarları Yapılandırması (config.py)

Kullanıcının ağ ayarları (zaman aşımı, parça sayısı, hız limiti, proxy vb.)
bu modül aracılığıyla JSON formatında saklanır ve yönetilir.
"""

import os
import json
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class NetworkSettings:
    """Ağ ve indirme parametreleri."""
    connection_timeout: int = 30               # Saniye cinsinden bağlantı zaman aşımı
    segments_per_download: int = 8             # İndirme başına eşzamanlı parça (segment) sayısı
    max_retries: int = 10                      # Maksimum yeniden deneme sınırı
    speed_limit_enabled: bool = False          # Hız limiti aktif mi?
    speed_limit_kbs: int = 2600                # KB/sn cinsinden hız sınırı (0 = sınırsız)
    proxy_mode: str = "system"                 # "system", "none", "manual"
    proxy_host: str = ""                       # Proxy sunucu adresi
    proxy_port: int = 0                        # Proxy portu
    proxy_user: str = ""                       # Proxy kullanıcı adı
    proxy_pass: str = ""                       # Proxy parolası


def get_config_dir() -> str:
    """Ayarların kaydedileceği dizini döndürür ve yoksa oluşturur."""
    config_dir = os.path.join(os.path.expanduser("~"), ".download_manager")
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def get_config_file_path() -> str:
    """settings.json dosyasının tam yolunu döndürür."""
    return os.path.join(get_config_dir(), "settings.json")


def get_tasks_file_path() -> str:
    """tasks.json dosyasının tam yolunu döndürür."""
    return os.path.join(get_config_dir(), "tasks.json")


def load_network_settings() -> NetworkSettings:
    """settings.json dosyasından ayarları yükler, dosya yoksa varsayılanı döndürür."""
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
                    proxy_host=str(data.get("proxy_host", "")),
                    proxy_port=int(data.get("proxy_port", 0)),
                    proxy_user=str(data.get("proxy_user", "")),
                    proxy_pass=str(data.get("proxy_pass", ""))
                )
        except Exception as e:
            print(f"Ayar yükleme hatası: {e}")

    return NetworkSettings()


def save_network_settings(settings: NetworkSettings) -> bool:
    """Ayarları settings.json dosyasına kaydeder."""
    file_path = get_config_file_path()
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Ayar kaydetme hatası: {e}")
        return False
