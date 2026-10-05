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


def get_search_icon(size: int = 14, color: str = "#94a3b8") -> QIcon:
    """Arama kutuları için modern büyüteç ikonu üretir."""
    try:
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtCore import QByteArray
        from PyQt6.QtGui import QPainter

        svg_str = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="11" cy="11" r="7"/>
  <line x1="21" y1="21" x2="16.65" y2="16.65"/>
</svg>'''

        renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)
    except Exception:
        try:
            from PyQt6.QtGui import QPainter, QPen, QColor
            from PyQt6.QtCore import QPoint
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(color), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            r = int(size * 0.35)
            cx = int(size * 0.42)
            cy = int(size * 0.42)
            painter.drawEllipse(QPoint(cx, cy), r, r)
            painter.drawLine(cx + int(r * 0.7), cy + int(r * 0.7), int(size * 0.85), int(size * 0.85))
            painter.end()
            return QIcon(pixmap)
        except Exception:
            return QIcon()
