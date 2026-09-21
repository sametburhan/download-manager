"""
Download Manager - Ana Başlatıcı (Root Launcher)

Kök dizinden tek komutla çalıştırmak için:
    python run.py
"""

import sys
import os

# Proje kök dizinini garantiye al
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import main

if __name__ == "__main__":
    main()
