"""Windows-Autostart (pro Benutzer, kein Admin nötig).

Verwendet den Registry-Run-Key
``HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``.
Robust gegen fehlende Rechte: schlägt der Registry-Zugriff fehl, wird ein
Fehler zurückgemeldet, ohne die App zu beenden.

Unter Nicht-Windows-Systemen sind die Funktionen No-Ops (für Tests).
"""
from __future__ import annotations

import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_VALUE_NAME = "LogWatch"


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def get_executable_command() -> str:
    """Liefert den Befehl, der beim Login gestartet werden soll.

    - Als gefrorene .exe (PyInstaller): der Pfad zur .exe selbst.
    - Als Python-Skript: python.exe + Skriptpfad.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # Script-Modus: pythonw bevorzugen, damit kein Konsolenfenster erscheint.
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        pyw = exe[:-10] + "pythonw.exe"
        import os
        if os.path.isfile(pyw):
            exe = pyw
    script = sys.argv[0]
    return f'"{exe}" "{script}"'


def is_enabled() -> bool:
    if not _is_windows():
        return False
    try:
        import winreg  # type: ignore
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable(command: str | None = None) -> None:
    """Trägt den Autostart-Eintrag ein. Wirft bei Fehler eine Exception."""
    if not _is_windows():
        return
    import winreg  # type: ignore
    if command is None:
        command = get_executable_command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, APP_VALUE_NAME, 0, winreg.REG_SZ, command)


def disable() -> None:
    """Entfernt den Autostart-Eintrag (falls vorhanden)."""
    if not _is_windows():
        return
    import winreg  # type: ignore
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_VALUE_NAME)
    except FileNotFoundError:
        pass


def apply(enabled: bool) -> bool:
    """Setzt den gewünschten Zustand. Gibt True bei Erfolg zurück."""
    try:
        if enabled:
            enable()
        else:
            disable()
        return True
    except OSError:
        return False
