# -*- mode: python ; coding: utf-8 -*-
"""
Download Manager - PyInstaller Build Spec
"""

import os

block_cipher = None

# Proje kök dizini
ROOT = os.path.abspath('.')

a = Analysis(
    ['run.py'],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # QSS Tema dosyaları
        (os.path.join(ROOT, 'app', 'ui', 'styles', 'ab_dark_theme.qss'),    os.path.join('app', 'ui', 'styles')),
        (os.path.join(ROOT, 'app', 'ui', 'styles', 'windows11_dark.qss'),   os.path.join('app', 'ui', 'styles')),
        # Uygulama ikonları
        (os.path.join(ROOT, 'extension', 'icons', 'icon128.png'),  os.path.join('extension', 'icons')),
        (os.path.join(ROOT, 'extension', 'icons', 'icon48.png'),   os.path.join('extension', 'icons')),
        (os.path.join(ROOT, 'extension', 'icons', 'icon16.png'),   os.path.join('extension', 'icons')),
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
        'PyQt6.QtNetwork',
        'PyQt6.sip',
        'websockets',
        'websockets.legacy',
        'websockets.legacy.server',
        'httpx',
        'httpx._transports',
        'httpx._transports.default',
        'aiohttp',
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.postprocessor',
        'imageio_ffmpeg',
        'asyncio',
        'concurrent.futures',
        'pkg_resources',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'PIL',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DownloadManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,        # Konsol penceresi gösterme (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
    version='file_version_info.txt' if os.path.exists('file_version_info.txt') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DownloadManager',
)
