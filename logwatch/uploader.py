"""Upload von Fehlerberichten an das zentrale Web-Dashboard.

Zusätzlich zum E-Mail-Versand kann bei einem erkannten Fehler ein Fehlerbericht
an die Dashboard-API gesendet werden (Maschinen-ID, Hardware-ID, TeamViewer-ID,
Firma/Kunde, Hostname, auslösende Fehlerzeilen, Zeitstempel + Logdatei).

Robustheit: Netzwerkfehler (Timeout, offline, HTTP-Fehler) werden abgefangen und
nur protokolliert – die App stürzt nicht ab und der E-Mail-Versand bleibt davon
unberührt.

Der eigentliche HTTP-Transport ist über ``post_func`` injizierbar, damit der
Upload ohne echtes Netzwerk testbar ist.

== Upload-API-Vertrag (muss mit dem Dashboard übereinstimmen) ==
  POST {base_url}/api/v1/reports
  Header:  X-Upload-Token: <upload_token>
  Body:    multipart/form-data
             - feld "payload"  : JSON (siehe build_report)
             - datei "logfile" : die Logdatei (optional, falls vorhanden)
  Antwort: 2xx = Erfolg
"""
from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Optional, Sequence

from .config import Config
from .detector import Match

# API-Pfad – an EINER Stelle definiert, damit Client & Dashboard konsistent sind.
API_REPORTS_PATH = "/api/v1/reports"
UPLOAD_TOKEN_HEADER = "X-Upload-Token"

# Signatur des Transports: (url, headers, payload_json, log_path) -> (status_code, text)
PostFunc = Callable[[str, dict, str, Optional[str]], "UploadResult"]


@dataclass
class UploadResult:
    ok: bool
    status_code: Optional[int] = None
    message: str = ""


def build_report(config: Config, matches: Sequence[Match],
                 teamviewer_id: Optional[str] = None,
                 hardware_id: Optional[str] = None,
                 hostname: Optional[str] = None,
                 timestamp: Optional[str] = None) -> dict:
    """Baut die Metadaten des Fehlerberichts (JSON-serialisierbar)."""
    if hostname is None:
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = "unbekannt"
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    error_lines = [m.line for m in matches]
    return {
        "machine_id": config.machine_id or "",
        "company": config.company or "",
        "hardware_id": hardware_id or "",
        "teamviewer_id": teamviewer_id or "",
        "hostname": hostname or "",
        "timestamp": timestamp,
        "error_count": len(error_lines),
        "error_lines": error_lines,
        "log_filename": os.path.basename(config.log_file_path) if config.log_file_path else "",
    }


def _requests_post(url: str, headers: dict, payload_json: str,
                   log_path: Optional[str], timeout: int = 20) -> UploadResult:
    """Standard-Transport über die requests-Bibliothek."""
    import requests  # lokal importiert, damit Tests ohne requests mocken können

    files = {}
    opened = None
    try:
        data = {"payload": payload_json}
        if log_path and os.path.isfile(log_path):
            opened = open(log_path, "rb")
            files["logfile"] = (os.path.basename(log_path), opened, "text/plain")
        resp = requests.post(url, headers=headers, data=data, files=files or None, timeout=timeout)
        ok = 200 <= resp.status_code < 300
        return UploadResult(ok=ok, status_code=resp.status_code,
                            message=("OK" if ok else f"HTTP {resp.status_code}: {resp.text[:200]}"))
    finally:
        if opened is not None:
            try:
                opened.close()
            except Exception:
                pass


def upload_report(config: Config, report: dict,
                  log_path: Optional[str] = None,
                  post_func: Optional[PostFunc] = None,
                  log_func: Optional[Callable[[str], None]] = None) -> UploadResult:
    """Sendet den Fehlerbericht an das Dashboard. Immer "best effort".

    Gibt ein ``UploadResult`` zurück; wirft KEINE Exception nach außen.
    """
    log = log_func or (lambda m: None)
    ds = config.dashboard

    if not ds.enabled:
        return UploadResult(ok=False, message="Dashboard-Upload ist deaktiviert.")
    if not ds.base_url.strip():
        log("Dashboard-Upload übersprungen: keine Dashboard-URL konfiguriert.")
        return UploadResult(ok=False, message="Keine Dashboard-URL konfiguriert.")

    url = ds.base_url.rstrip("/") + API_REPORTS_PATH
    headers = {UPLOAD_TOKEN_HEADER: ds.upload_token or ""}
    payload_json = json.dumps(report, ensure_ascii=False)

    transport = post_func or _requests_post
    try:
        result = transport(url, headers, payload_json, log_path)
        if result.ok:
            log(f"Fehlerbericht an Dashboard gesendet ({url}).")
        else:
            log(f"Dashboard-Upload fehlgeschlagen: {result.message}")
        return result
    except Exception as exc:  # noqa: BLE001 - jeder Netzwerkfehler wird abgefangen
        msg = f"Dashboard-Upload fehlgeschlagen (Netzwerk/Unbekannt): {exc}"
        log(msg)
        return UploadResult(ok=False, message=msg)
