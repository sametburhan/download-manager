"""
Download Manager - İkon ve Logo Yöneticisi (icon_utils.py)

extension/icons dizinindeki resmi logo ve ikonları masaüstü uygulamasına,
pencere başlıklarına, Windows görev çubuğuna ve sistem tepsisine bağlar.
"""

import os
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import Qt


def get_app_icon_path(size: int = 128) -> str:
    """Uygulama logosunun dosya yolunu döndürür."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    icon_filename = f"icon{size}.png"
    target_path = os.path.join(base_dir, "extension", "icons", icon_filename)
    if os.path.exists(target_path):
        return target_path

    # Alternatif boyutları dene
    for s in (128, 48, 16):
        alt_path = os.path.join(base_dir, "extension", "icons", f"icon{s}.png")
        if os.path.exists(alt_path):
            return alt_path
    return ""


def get_app_icon() -> QIcon:
    """Tüm pencereler ve Windows görev çubuğu için çok çözünürlüklü QIcon üretir."""
    icon = QIcon()
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    for s in (16, 48, 128):
        p = os.path.join(base_dir, "extension", "icons", f"icon{s}.png")
        if os.path.exists(p):
            icon.addFile(p)
    return icon


def get_app_pixmap(size: int = 32) -> QPixmap:
    """Pencere içi logo görselleştirmesi için ölçeklenmiş QPixmap döndürür."""
    path = get_app_icon_path(128)
    if path and os.path.exists(path):
        pix = QPixmap(path)
        return pix.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
    return QPixmap()
