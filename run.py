"""
Download Manager - Root Launcher (run.py)

To run from the root directory with a single command:
    python run.py
"""

import sys
import os

# Ensure project root directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from app.main import main

if __name__ == "__main__":
    main()
