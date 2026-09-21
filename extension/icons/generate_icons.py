"""
Eklenti İkonları Üretici (generate_icons.py)

PyQt6 QPainter kullanarak 16x16, 48x48 ve 128x128 boyutlarında modern,
yuvarlatılmış ve gradyanlı eklenti ikonları üretir.
"""

import os
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPainter, QColor, QLinearGradient, QBrush, QPen, QPolygonF
from PyQt6.QtCore import Qt, QPointF


def create_icon(size: int, output_path: str):
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))  # Şeffaf arka plan

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Yuvarlatılmış köşeli kare arka plan
    rect_margin = size * 0.05
    rect_size = size * 0.9
    radius = size * 0.22

    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#0078d4"))
    gradient.setColorAt(1.0, QColor("#00c6ff"))

    from PyQt6.QtCore import QRectF

    painter.setBrush(QBrush(gradient))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(rect_margin, rect_margin, rect_size, rect_size), radius, radius)

    # İndirme Oku (Download Arrow)
    painter.setBrush(QBrush(QColor("#ffffff")))
    painter.setPen(Qt.PenStyle.NoPen)

    # Ok gövdesi
    stem_w = size * 0.2
    stem_h = size * 0.35
    stem_x = (size - stem_w) / 2
    stem_y = size * 0.22
    painter.drawRoundedRect(QRectF(stem_x, stem_y, stem_w, stem_h), 2.0, 2.0)

    # Ok ucu (Üçgen)
    triangle = QPolygonF([
        QPointF(size * 0.25, size * 0.52),
        QPointF(size * 0.75, size * 0.52),
        QPointF(size * 0.5, size * 0.76)
    ])
    painter.drawPolygon(triangle)

    # Alt çizgi taban
    base_w = size * 0.6
    base_h = size * 0.08
    base_x = (size - base_w) / 2
    base_y = size * 0.82
    painter.drawRoundedRect(QRectF(base_x, base_y, base_w, base_h), 2.0, 2.0)

    painter.end()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    image.save(output_path, "PNG")
    print(f"İkon oluşturuldu: {output_path} ({size}x{size})")


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    icons_dir = os.path.dirname(os.path.abspath(__file__))

    create_icon(16, os.path.join(icons_dir, "icon16.png"))
    create_icon(48, os.path.join(icons_dir, "icon48.png"))
    create_icon(128, os.path.join(icons_dir, "icon128.png"))


if __name__ == "__main__":
    main()
