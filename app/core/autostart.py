"""
Download Manager - Windows Autostart on Boot Module (autostart.py)

Manages launching the application automatically in the background (system tray)
on Windows logon via HKCU\Software\Microsoft\Windows\CurrentVersion\Run registry key.
"""

import os
import sys
import winreg

APP_REG_NAME = "DownloadManagerPro"


def get_startup_command(minimized: bool = True) -> str:
    """
    Generates the complete command line to execute on Windows startup.
    Uses pythonw.exe to prevent launching a console terminal window.
    """
    python_dir = os.path.dirname(sys.executable)
    pythonw_path = os.path.join(python_dir, "pythonw.exe")

    # If pythonw.exe does not exist, fallback to sys.executable
    if not os.path.exists(pythonw_path):
        pythonw_path = sys.executable

    # Absolute path to main run.py entry point
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    run_py = os.path.join(root_dir, "run.py")

    cmd = f'"{pythonw_path}" "{run_py}"'
    if minimized:
        cmd += " --tray"

    return cmd


def is_autostart_enabled() -> bool:
    """Checks whether the application is registered in Windows startup registry."""
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
    Adds or removes the application from Windows startup.
    :param enabled: True to register startup, False to remove.
    :param run_minimized: Start silently minimized to the system tray.
    :return: True if successful, False otherwise.
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
