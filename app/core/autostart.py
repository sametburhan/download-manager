"""
Download Manager - Windows Başlangıcında Otomatik Başlatma Modülü (autostart.py)

Windows Kayıt Defteri (Registry) 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'
anahtarı üzerinden uygulamanın bilgisayar açıldığında arka planda (sistem tepsisinde)
otomatik olarak başlatılmasını yönetir.
"""

import os
import sys
import winreg

APP_REG_NAME = "DownloadManagerPro"


def get_startup_command(minimized: bool = True) -> str:
    """
    Windows açılışında çalıştırılacak tam komut satırını üretir.
    pythonw.exe kullanılarak konsol siyah ekranının açılması engellenir.
    """
    python_dir = os.path.dirname(sys.executable)
    pythonw_path = os.path.join(python_dir, "pythonw.exe")

    # Eğer pythonw.exe yoksa normal python.exe kullan
    if not os.path.exists(pythonw_path):
        pythonw_path = sys.executable

    # Proje ana run.py dosyasının yolu
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    run_py = os.path.join(root_dir, "run.py")

    cmd = f'"{pythonw_path}" "{run_py}"'
    if minimized:
        cmd += " --tray"

    return cmd


def is_autostart_enabled() -> bool:
    """Uygulamanın Windows başlangıcına ekli olup olmadığını kontrol eder."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
        )
        try:
            val, _ = winreg.QueryValueEx(key, APP_REG_NAME)
            return bool(val)
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def set_autostart(enabled: bool, run_minimized: bool = True) -> bool:
    """
    Uygulamayı Windows başlangıcına ekler veya kaldırır.
    :param enabled: True ise açılışa ekle, False ise kaldır.
    :param run_minimized: Açılışta doğrudan sistem tepsisinde sessiz başla.
    :return: Başarılı ise True
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        if enabled:
            cmd = get_startup_command(minimized=run_minimized)
            winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_REG_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as exc:
        print(f"Failed to save autostart setting: {exc}")
        return False
