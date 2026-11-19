"""Konfigurationsverwaltung für LogWatch.

Lädt/speichert die Konfiguration als JSON. Unter Windows wird standardmäßig
%APPDATA%\\LogWatch\\config.json verwendet. Dieses Modul ist plattformunabhängig
und damit ohne GUI testbar.
"""
from __future__ import annotations

import copy
import json
import os

from . import crypto
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


APP_NAME = "LogWatch"

# ---------------------------------------------------------------------------
# Standard-Stichwörter für den Modus "Alle Fehler" (case-insensitive).
# ---------------------------------------------------------------------------
DEFAULT_KEYWORDS: List[str] = ["ERROR", "FEHLER", "Exception", "FATAL"]


def get_config_dir() -> str:
    """Liefert das Konfigurationsverzeichnis.

    Unter Windows: %APPDATA%\\LogWatch
    Sonst (z.B. Tests unter Linux): ~/.config/LogWatch
    Kann über die Umgebungsvariable LOGWATCH_CONFIG_DIR überschrieben werden.
    """
    override = os.environ.get("LOGWATCH_CONFIG_DIR")
    if override:
        return override

    appdata = os.environ.get("APPDATA")
    if appdata:  # Windows
        return os.path.join(appdata, APP_NAME)
    # Fallback für Nicht-Windows-Systeme
    base = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    return os.path.join(base, APP_NAME)


def get_config_path() -> str:
    # Verschlüsselte Konfigurationsdatei (kein Klartext, keine .ini).
    return os.path.join(get_config_dir(), "config.dat")


def get_app_log_path() -> str:
    """Pfad der App-eigenen Logdatei (zur Nachverfolgung von Versandfehlern)."""
    return os.path.join(get_config_dir(), "logwatch_app.log")


@dataclass
class Recipient:
    """Ein E-Mail-Empfänger mit Zusatzangaben."""
    email: str = ""
    company: str = ""   # Firma
    machine: str = ""   # Maschine
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Recipient":
        return cls(
            email=str(d.get("email", "")),
            company=str(d.get("company", "")),
            machine=str(d.get("machine", "")),
            active=bool(d.get("active", True)),
        )


@dataclass
class SMTPSettings:
    host: str = "smtp.example.com"          # Platzhalter – vom Nutzer ausfüllen
    port: int = 587
    username: str = "benutzer@example.com"  # Platzhalter
    password: str = ""                      # wird nie im Klartext in der UI angezeigt
    use_tls: bool = True                    # STARTTLS (Port 587)
    use_ssl: bool = False                   # SSL/TLS (Port 465)
    from_address: str = "benutzer@example.com"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SMTPSettings":
        return cls(
            host=str(d.get("host", "smtp.example.com")),
            port=int(d.get("port", 587)),
            username=str(d.get("username", "")),
            password=str(d.get("password", "")),
            use_tls=bool(d.get("use_tls", True)),
            use_ssl=bool(d.get("use_ssl", False)),
            from_address=str(d.get("from_address", "")),
        )


@dataclass
class DashboardSettings:
    """Einstellungen für den optionalen Upload an das zentrale Web-Dashboard."""
    enabled: bool = False          # Upload an/aus
    base_url: str = ""             # z.B. https://logwatch-xyz.abacusai.cloud
    upload_token: str = ""         # Shared-Secret / Upload-Token (Header)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DashboardSettings":
        d = d or {}
        return cls(
            enabled=bool(d.get("enabled", False)),
            base_url=str(d.get("base_url", "")),
            upload_token=str(d.get("upload_token", "")),
        )


@dataclass
class Config:
    # Überwachung
    log_file_path: str = ""
    check_interval_seconds: int = 30

    # Maschinen-Identität (vom Betreiber "auf dem Papier" vergeben)
    machine_id: str = ""          # eindeutige Maschinen-ID
    company: str = ""             # Firma/Kunde auf Maschinen-Ebene

    # Zentrales Dashboard (optionaler Upload)
    dashboard: "DashboardSettings" = field(default_factory=lambda: DashboardSettings())

    # Fehlererkennung
    # Modus: "all" (alle Fehler, generische Stichwörter) oder "specific" (nur bestimmte)
    error_mode: str = "all"
    all_keywords: List[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    specific_keywords: List[str] = field(default_factory=list)

    # E-Mail
    smtp: SMTPSettings = field(default_factory=SMTPSettings)
    recipients: List[Recipient] = field(default_factory=list)

    # Anti-Spam / Throttling
    # Nach einer gesendeten Mail wird für cooldown_seconds keine weitere gesendet;
    # in dieser Zeit auftretende Fehler werden gesammelt und mit der nächsten Mail
    # (nach Ablauf des Cooldowns) mitgeschickt.
    cooldown_seconds: int = 300

    # Autostart mit Windows (pro Benutzer)
    autostart: bool = False

    # Max. Empfängeranzahl
    MAX_RECIPIENTS: int = 5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_file_path": self.log_file_path,
            "check_interval_seconds": self.check_interval_seconds,
            "machine_id": self.machine_id,
            "company": self.company,
            "dashboard": self.dashboard.to_dict(),
            "error_mode": self.error_mode,
            "all_keywords": list(self.all_keywords),
            "specific_keywords": list(self.specific_keywords),
            "smtp": self.smtp.to_dict(),
            "recipients": [r.to_dict() for r in self.recipients],
            "cooldown_seconds": self.cooldown_seconds,
            "autostart": self.autostart,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Config":
        c = cls()
        c.log_file_path = str(d.get("log_file_path", ""))
        c.check_interval_seconds = int(d.get("check_interval_seconds", 30))
        # Neue Felder (abwärtskompatibel: alte Config ohne diese Felder lädt weiter)
        c.machine_id = str(d.get("machine_id", ""))
        c.company = str(d.get("company", ""))
        c.dashboard = DashboardSettings.from_dict(d.get("dashboard", {}))
        c.error_mode = str(d.get("error_mode", "all"))
        if c.error_mode not in ("all", "specific"):
            c.error_mode = "all"
        c.all_keywords = [str(x) for x in d.get("all_keywords", list(DEFAULT_KEYWORDS))]
        if not c.all_keywords:
            c.all_keywords = list(DEFAULT_KEYWORDS)
        c.specific_keywords = [str(x) for x in d.get("specific_keywords", [])]
        c.smtp = SMTPSettings.from_dict(d.get("smtp", {}))
        c.recipients = [Recipient.from_dict(r) for r in d.get("recipients", [])]
        c.cooldown_seconds = int(d.get("cooldown_seconds", 300))
        c.autostart = bool(d.get("autostart", False))
        return c

    def active_recipients(self) -> List[Recipient]:
        return [r for r in self.recipients if r.active and r.email.strip()]

    def copy(self) -> "Config":
        return Config.from_dict(copy.deepcopy(self.to_dict()))


def load_config(path: str | None = None, master_password: str | None = None) -> Config:
    """Lädt die (verschlüsselte) Konfiguration.

    Existiert keine Datei, wird eine Default-Config zurückgegeben (und NICHT
    automatisch geschrieben). Ist die Datei mit einem Master-Passwort geschützt
    und keines angegeben, wird eine ``crypto.DecryptionError`` ausgelöst.
    """
    if path is None:
        path = get_config_path()
    if not os.path.isfile(path):
        return Config()
    with open(path, "rb") as f:
        blob = f.read()
    try:
        plaintext = crypto.decrypt_bytes(blob, master_password)
    except crypto.DecryptionError:
        # Wenn passwortgeschützt -> weiterreichen, damit UI nachfragen kann.
        if crypto.is_password_protected(blob) and not master_password:
            raise
        # Beschädigte Datei -> weiterreichen, nicht stillschweigend Defaults nehmen.
        raise
    data = json.loads(plaintext.decode("utf-8"))
    return Config.from_dict(data)


def export_config(config: Config, path: str, master_password: str | None = None) -> str:
    """Exportiert die komplette Konfiguration als portable, VERSCHLÜSSELTE Datei.

    Damit lässt sich eine einmal erstellte Konfiguration (inkl. der Liste der
    bestimmten Fehlerzeilen) auf mehreren PCs einspielen. Die Datei ist
    verschlüsselt; mit Master-Passwort nur mit diesem entschlüsselbar.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    plaintext = json.dumps(config.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
    blob = crypto.encrypt_bytes(plaintext, master_password)
    with open(path, "wb") as f:
        f.write(blob)
    return path


def import_config(path: str, master_password: str | None = None) -> Config:
    """Importiert eine zuvor exportierte (verschlüsselte) Konfigurationsdatei."""
    with open(path, "rb") as f:
        blob = f.read()
    plaintext = crypto.decrypt_bytes(blob, master_password)
    data = json.loads(plaintext.decode("utf-8"))
    return Config.from_dict(data)


def save_config(config: Config, path: str | None = None, master_password: str | None = None) -> str:
    """Speichert die Konfiguration VERSCHLÜSSELT (kein Klartext). Legt das
    Zielverzeichnis bei Bedarf an. Gibt den Pfad zurück."""
    if path is None:
        path = get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plaintext = json.dumps(config.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
    blob = crypto.encrypt_bytes(plaintext, master_password)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, path)  # atomar
    return path


def config_file_is_password_protected(path: str | None = None) -> bool:
    if path is None:
        path = get_config_path()
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "rb") as f:
            return crypto.is_password_protected(f.read())
    except OSError:
        return False
