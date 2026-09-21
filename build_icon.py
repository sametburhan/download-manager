"""
PNG ikonunu .ico formatına çevirir (PyInstaller .ico gerektirir).
"""
import os
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PNG_PATH = os.path.join(BASE_DIR, "extension", "icons", "icon128.png")
ICO_PATH = os.path.join(BASE_DIR, "app_icon.ico")

img = Image.open(PNG_PATH)
img.save(ICO_PATH, format="ICO", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
print(f"ICO olusturuldu: {ICO_PATH}")
