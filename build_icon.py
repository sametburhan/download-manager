"""
PNG ikonunu .ico formatina cevirir (PyInstaller .ico gerektirir).
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PNG_PATH = os.path.join(BASE_DIR, "extension", "icons", "icon128.png")
ICO_PATH = os.path.join(BASE_DIR, "app_icon.ico")

try:
    from PIL import Image
    if os.path.exists(PNG_PATH):
        img = Image.open(PNG_PATH)
        img.save(ICO_PATH, format="ICO", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
        print(f"[OK] ICO created with PIL: {ICO_PATH}")
    elif os.path.exists(ICO_PATH):
        print(f"[OK] Existing app_icon.ico preserved: {ICO_PATH}")
except ImportError:
    if os.path.exists(ICO_PATH):
        print(f"[OK] PIL not installed, but existing app_icon.ico found: {ICO_PATH}")
    else:
        try:
            from PyQt6.QtGui import QImage
            img = QImage(PNG_PATH)
            img.save(ICO_PATH, "ICO")
            print(f"[OK] ICO created with PyQt6: {ICO_PATH}")
        except Exception as e:
            print(f"[WARNING] Could not generate ICO: {e}")
