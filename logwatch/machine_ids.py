"""Auslesen/Erzeugen von Maschinen-Kennungen (TeamViewer-ID, Hardware-ID).

Der eigentliche Registry-Zugriff ist hinter einer dünnen, austauschbaren
Schicht (``RegistryReader``) gekapselt, damit die Logik plattformunabhängig
und per Mock testbar ist.

- TeamViewer-ID: aus HKLM\\SOFTWARE\\TeamViewer bzw. der WOW6432Node-Variante,
  Wert ``ClientID`` (dezimal).
- Hardware-ID: stabiler Fingerprint des PCs. Primär ``MachineGuid`` aus
  HKLM\\SOFTWARE\\Microsoft\\Cryptography, kombiniert mit – falls verfügbar –
  der Computer-Hardware-GUID; Ergebnis als SHA-256-Hex-Hash.

Alle Funktionen sind "best effort": schlägt etwas fehl oder läuft der Code
nicht unter Windows, wird ``None`` (bzw. "unbekannt") zurückgegeben, ohne eine
Exception nach außen zu werfen.
"""
from __future__ import annotations

import hashlib
import sys
from typing import Optional, Protocol


UNKNOWN = "unbekannt"


class RegistryReader(Protocol):
    """Minimale Abstraktion über einen Registry-Lesezugriff (mockbar)."""

    def read_value(self, root: str, subkey: str, value_name: str) -> Optional[str]:
        """Liefert den Wert als String oder None, wenn nicht vorhanden/lesbar."""
        ...


class WindowsRegistryReader:
    """Echter Registry-Zugriff via ``winreg`` (nur unter Windows)."""

    # Zuordnung von Root-Namen zu winreg-Konstanten (lazy, da winreg nur auf Windows existiert)
    def _root_const(self, root: str):
        import winreg  # type: ignore
        mapping = {
            "HKLM": winreg.HKEY_LOCAL_MACHINE,
            "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
            "HKCU": winreg.HKEY_CURRENT_USER,
            "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        }
        return mapping[root]

    def read_value(self, root: str, subkey: str, value_name: str) -> Optional[str]:
        try:
            import winreg  # type: ignore
        except ImportError:
            return None
        # 64-Bit- und 32-Bit-Sicht der Registry berücksichtigen.
        for access in (0, getattr(__import__("winreg"), "KEY_WOW64_64KEY", 0),
                       getattr(__import__("winreg"), "KEY_WOW64_32KEY", 0)):
            try:
                hkey = self._root_const(root)
                with winreg.OpenKey(hkey, subkey, 0, winreg.KEY_READ | access) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                    if value is None:
                        continue
                    return str(value)
            except (FileNotFoundError, OSError, KeyError):
                continue
        return None


def _default_reader() -> Optional[RegistryReader]:
    if sys.platform.startswith("win"):
        return WindowsRegistryReader()
    return None


# ---------------------------------------------------------------------------
# TeamViewer-ID
# ---------------------------------------------------------------------------
_TEAMVIEWER_SUBKEYS = (
    r"SOFTWARE\TeamViewer",
    r"SOFTWARE\WOW6432Node\TeamViewer",
)


def get_teamviewer_id(reader: Optional[RegistryReader] = None) -> Optional[str]:
    """Liest die TeamViewer-ClientID (dezimal) aus der Registry.

    Gibt die ID als String zurück oder None, wenn sie nicht ermittelbar ist.
    """
    if reader is None:
        reader = _default_reader()
    if reader is None:
        return None
    for subkey in _TEAMVIEWER_SUBKEYS:
        raw = reader.read_value("HKLM", subkey, "ClientID")
        if raw is None:
            continue
        normalized = _normalize_clientid(raw)
        if normalized:
            return normalized
    return None


def _normalize_clientid(raw: str) -> Optional[str]:
    """Normalisiert den ClientID-Wert zu einer dezimalen Zeichenkette.

    winreg kann REG_DWORD als int liefern; Mocks liefern evtl. Strings oder
    Hex-Darstellungen ("0x1234"). Alles wird auf Dezimal gebracht.
    """
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.lower().startswith("0x"):
            return str(int(s, 16))
        return str(int(s))  # rein dezimal
    except ValueError:
        # Unerwartetes Format -> unbrauchbar
        return None


def get_teamviewer_id_or_unknown(reader: Optional[RegistryReader] = None) -> str:
    return get_teamviewer_id(reader) or UNKNOWN


# ---------------------------------------------------------------------------
# Hardware-ID (stabiler Fingerprint)
# ---------------------------------------------------------------------------
def _collect_hardware_raw(reader: RegistryReader) -> list[str]:
    """Sammelt rohe, über Neustarts stabile Hardware-Merkmale."""
    parts: list[str] = []
    machine_guid = reader.read_value("HKLM", r"SOFTWARE\Microsoft\Cryptography", "MachineGuid")
    if machine_guid:
        parts.append(f"MachineGuid={machine_guid.strip()}")
    # Optionale zusätzliche Quelle (SMBIOS/Mainboard), falls vorhanden.
    hw_guid = reader.read_value(
        "HKLM", r"SYSTEM\HardwareConfig", "LastConfig"
    )
    if hw_guid:
        parts.append(f"HwConfig={hw_guid.strip()}")
    return parts


def compute_hardware_id(reader: Optional[RegistryReader] = None) -> Optional[str]:
    """Berechnet einen stabilen Hardware-Fingerprint als SHA-256-Hex.

    Deterministisch für dieselben Rohwerte, unterschiedlich auf anderer Hardware.
    Gibt None zurück, wenn keine Rohwerte ermittelbar sind.
    """
    if reader is None:
        reader = _default_reader()
    if reader is None:
        return None
    parts = _collect_hardware_raw(reader)
    if not parts:
        return None
    material = "|".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def compute_hardware_id_or_unknown(reader: Optional[RegistryReader] = None) -> str:
    return compute_hardware_id(reader) or UNKNOWN
