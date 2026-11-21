"""Update-Funktion für den LogWatch-Client.

Prüft über die GitHub-API, ob ein neueres Release verfügbar ist, lädt die neue
``LogWatch.exe`` herunter und stößt unter Windows einen Austausch der laufenden
EXE an.

Design-Prinzipien
-----------------
* **Plattformunabhängige Logik** (Versionslesen, -vergleich, Release-Abfrage,
  Asset-Auswahl) ist von der **Windows-spezifischen** Install-Logik getrennt und
  damit ohne echtes Windows/Netzwerk testbar.
* Der HTTP-Transport ist über ``get_func`` injizierbar (wie in ``uploader.py``),
  damit Tests ohne echten Netzwerkzugriff laufen.
* Funktioniert mit ÖFFENTLICHEN **und** PRIVATEN Repos: ist ein Personal Access
  Token (PAT) hinterlegt, wird es als ``Authorization: Bearer <token>`` gesendet.
* **Sicherheit:** Das Token wird NIEMALS geloggt oder in Fehlermeldungen
  ausgegeben.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Konstanten (an EINER Stelle, damit sie leicht anpassbar sind)
# ---------------------------------------------------------------------------
GITHUB_OWNER = "Obi811"
GITHUB_REPO = "Logwatch"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
GITHUB_API_VERSION = "2022-11-28"
ASSET_NAME = "LogWatch.exe"
HTTP_TIMEOUT = 10  # Sekunden

# Signatur des injizierbaren GET-Transports: (url, headers, timeout) -> Response-artig
GetFunc = Callable[[str, dict, int], "object"]


class UpdateError(Exception):
    """Fehler bei der Update-Prüfung/Installation (deutsche Meldung)."""


# ---------------------------------------------------------------------------
# Ergebnis-Datenstrukturen
# ---------------------------------------------------------------------------
@dataclass
class ReleaseInfo:
    """Die für ein Update relevanten Infos eines GitHub-Releases."""
    version: str                 # normalisiert, z.B. "0.3.0"
    tag: str                     # Original-Tag, z.B. "v0.3.0"
    name: str                    # Release-Titel
    notes: str                   # Release-Beschreibung (Markdown)
    assets: List[dict] = field(default_factory=list)


@dataclass
class UpdateCheckResult:
    """Ergebnis einer Update-Prüfung (robust, enthält ggf. Fehlertext)."""
    ok: bool                              # True, wenn die Prüfung technisch erfolgreich war
    local_version: str = ""
    remote_version: str = ""
    update_available: bool = False
    release_notes: str = ""
    release_name: str = ""
    asset_available: bool = False         # LogWatch.exe im Release vorhanden?
    error: str = ""                       # deutschsprachiger Fehlertext (ohne Token!)
    release: Optional[ReleaseInfo] = None


# ---------------------------------------------------------------------------
# Lokale Version lesen (auch im PyInstaller-Build)
# ---------------------------------------------------------------------------
def _version_file_candidates() -> List[str]:
    """Mögliche Speicherorte der VERSION-Datei – in sinnvoller Reihenfolge."""
    candidates: List[str] = []

    # 1) PyInstaller-Onefile entpackt Daten nach sys._MEIPASS.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "VERSION"))

    # 2) Neben der laufenden .exe (PyInstaller-Build).
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "VERSION"))

    # 3) Projektwurzel relativ zu dieser Datei (Entwicklung/Script-Betrieb):
    #    logwatch/updater.py -> Projektwurzel ist eine Ebene höher.
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(os.path.dirname(pkg_dir), "VERSION"))
    # 4) Auch direkt im Paketverzeichnis (falls so gebündelt).
    candidates.append(os.path.join(pkg_dir, "VERSION"))

    return candidates


def read_local_version(default: str = "0.0.0") -> str:
    """Liest die lokale Version aus der VERSION-Datei (robust).

    Gibt bei Nichtauffindbarkeit ``default`` zurück, damit die App nie wegen einer
    fehlenden VERSION-Datei abbricht.
    """
    for path in _version_file_candidates():
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                if text:
                    return text
        except OSError:
            continue
    return default


# ---------------------------------------------------------------------------
# Versionsvergleich (semantisch, tolerant gegenüber führendem "v")
# ---------------------------------------------------------------------------
def normalize_version(value: str) -> str:
    """Entfernt führendes 'v'/'V' und umgebende Leerzeichen."""
    v = (value or "").strip()
    if v[:1] in ("v", "V"):
        v = v[1:]
    return v.strip()


def _version_tuple(value: str) -> Tuple[int, ...]:
    """Wandelt 'X.Y.Z' in ein Vergleichs-Tupel (int, int, int) um.

    Nicht-numerische Zusätze (z.B. '1.2.0-beta') werden tolerant behandelt:
    Nur der numerische Kopf eines Segments zählt; fehlende Segmente werden mit 0
    aufgefüllt (bis zu 3 Stellen).
    """
    v = normalize_version(value)
    parts = v.split(".") if v else []
    nums: List[int] = []
    for part in parts:
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break  # z.B. '0-beta' -> 0
        nums.append(int(digits) if digits else 0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def compare_versions(a: str, b: str) -> int:
    """Vergleicht zwei Versionen. Rückgabe: -1 (a<b), 0 (a==b), 1 (a>b)."""
    ta, tb = _version_tuple(a), _version_tuple(b)
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


def is_newer(remote: str, local: str) -> bool:
    """True, wenn die Remote-Version NEUER ist als die lokale Version."""
    return compare_versions(remote, local) > 0


# ---------------------------------------------------------------------------
# HTTP: Header bauen + Release abfragen
# ---------------------------------------------------------------------------
def build_headers(token: Optional[str] = None,
                  accept: str = "application/vnd.github+json") -> dict:
    """Baut die GitHub-API-Header. Mit Token wird 'Authorization: Bearer ...'
    gesetzt (funktioniert für öffentliche UND private Repos)."""
    headers = {
        "Accept": accept,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "LogWatch-Updater",
    }
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


def _requests_get(url: str, headers: dict, timeout: int):
    """Standard-GET über die requests-Bibliothek (lokal importiert → mockbar)."""
    import requests
    return requests.get(url, headers=headers, timeout=timeout)


def fetch_latest_release(token: Optional[str] = None,
                         get_func: Optional[GetFunc] = None,
                         timeout: int = HTTP_TIMEOUT) -> ReleaseInfo:
    """Fragt das neueste Release über die GitHub-API ab.

    Wirft bei Problemen ``UpdateError`` mit verständlicher deutscher Meldung.
    Das Token taucht in keiner Fehlermeldung auf.
    """
    headers = build_headers(token)
    transport = get_func or _requests_get

    try:
        resp = transport(GITHUB_API_LATEST, headers, timeout)
    except Exception as exc:  # noqa: BLE001 - jeder Netzwerkfehler wird hier gefangen
        raise UpdateError(
            "Keine Verbindung zu GitHub möglich. Bitte Internetverbindung prüfen."
        ) from exc

    status = getattr(resp, "status_code", None)
    if status == 200:
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise UpdateError("Unerwartete Antwort von GitHub (kein gültiges JSON).") from exc
        return _parse_release(data)

    if status in (401, 403):
        raise UpdateError(
            "Zugriff verweigert oder Anfrage-Limit erreicht (HTTP {code}). "
            "Für private Repos bitte ein gültiges GitHub-Token hinterlegen; "
            "andernfalls später erneut versuchen.".format(code=status)
        )
    if status == 404:
        raise UpdateError("Kein Release gefunden (HTTP 404).")
    raise UpdateError(f"GitHub-Anfrage fehlgeschlagen (HTTP {status}).")


def _parse_release(data: dict) -> ReleaseInfo:
    """Baut aus dem Release-JSON ein ``ReleaseInfo``-Objekt."""
    if not isinstance(data, dict):
        raise UpdateError("Unerwartetes Release-Format von GitHub.")
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    if not tag:
        raise UpdateError("Release ohne Versions-Tag erhalten.")
    return ReleaseInfo(
        version=normalize_version(tag),
        tag=tag,
        name=str(data.get("name") or tag),
        notes=str(data.get("body") or ""),
        assets=list(data.get("assets") or []),
    )


# ---------------------------------------------------------------------------
# Asset-Auswahl + Download-URL
# ---------------------------------------------------------------------------
def select_asset(release: "ReleaseInfo | dict", asset_name: str = ASSET_NAME) -> Optional[dict]:
    """Sucht das Asset mit passendem Namen (z.B. 'LogWatch.exe') im Release.

    Akzeptiert sowohl ein ``ReleaseInfo`` als auch rohes Release-JSON (dict).
    Gibt das Asset-dict oder ``None`` zurück.
    """
    if isinstance(release, ReleaseInfo):
        assets = release.assets
    elif isinstance(release, dict):
        assets = release.get("assets") or []
    else:
        assets = []
    target = asset_name.strip().lower()
    for asset in assets:
        name = str(asset.get("name", "")).strip().lower()
        if name == target:
            return asset
    return None


def asset_download_url(asset: dict, token: Optional[str] = None) -> Tuple[str, dict]:
    """Liefert (URL, Header) für den Download eines Assets.

    * Mit Token wird der **Asset-API-Endpoint** (Feld 'url') mit
      ``Accept: application/octet-stream`` verwendet – funktioniert für private
      UND öffentliche Repos.
    * Ohne Token wird die öffentliche ``browser_download_url`` genutzt.
    """
    if token and token.strip():
        api_url = str(asset.get("url", "")).strip()
        if api_url:
            headers = build_headers(token, accept="application/octet-stream")
            return api_url, headers
    browser_url = str(asset.get("browser_download_url", "")).strip()
    if not browser_url:
        # Fallback: API-URL ohne Token (öffentliches Repo)
        api_url = str(asset.get("url", "")).strip()
        if api_url:
            return api_url, build_headers(None, accept="application/octet-stream")
        raise UpdateError("Keine gültige Download-URL im Release-Asset gefunden.")
    return browser_url, build_headers(None, accept="application/octet-stream")


# ---------------------------------------------------------------------------
# High-Level-Prüfung (robust, für UI geeignet)
# ---------------------------------------------------------------------------
def check_for_update(local_version: Optional[str] = None,
                     token: Optional[str] = None,
                     get_func: Optional[GetFunc] = None) -> UpdateCheckResult:
    """Komplette Update-Prüfung. Wirft KEINE Exception, sondern liefert ein
    ``UpdateCheckResult`` (mit ``ok=False`` + ``error`` bei Problemen)."""
    local = (local_version or read_local_version()).strip()
    try:
        release = fetch_latest_release(token=token, get_func=get_func)
    except UpdateError as exc:
        return UpdateCheckResult(ok=False, local_version=local, error=str(exc))

    asset = select_asset(release)
    newer = is_newer(release.version, local)
    return UpdateCheckResult(
        ok=True,
        local_version=local,
        remote_version=release.version,
        update_available=newer,
        release_notes=release.notes,
        release_name=release.name,
        asset_available=asset is not None,
        release=release,
    )


# ---------------------------------------------------------------------------
# Download der neuen EXE (Streaming, optionaler Fortschritt)
# ---------------------------------------------------------------------------
def download_asset(asset: dict, dest_path: str,
                   token: Optional[str] = None,
                   progress_callback: Optional[Callable[[int, int], None]] = None,
                   timeout: int = 60) -> str:
    """Lädt das Asset nach ``dest_path`` (Streaming).

    ``progress_callback(gelesen, gesamt)`` wird – falls angegeben – fortlaufend
    aufgerufen (``gesamt`` kann 0 sein, wenn die Größe unbekannt ist).
    Gibt den Zielpfad zurück. Wirft ``UpdateError`` bei Problemen.
    """
    url, headers = asset_download_url(asset, token=token)
    try:
        import requests
        with requests.get(url, headers=headers, timeout=timeout, stream=True,
                          allow_redirects=True) as resp:
            if resp.status_code != 200:
                raise UpdateError(f"Download fehlgeschlagen (HTTP {resp.status_code}).")
            total = int(resp.headers.get("Content-Length") or 0)
            read = 0
            os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
            with open(dest_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    read += len(chunk)
                    if progress_callback:
                        try:
                            progress_callback(read, total)
                        except Exception:  # noqa: BLE001 - Fortschritt darf nie crashen
                            pass
    except UpdateError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise UpdateError("Download der neuen Version fehlgeschlagen.") from exc
    return dest_path


def download_update(release: "ReleaseInfo | dict", dest_path: Optional[str] = None,
                    token: Optional[str] = None,
                    progress_callback: Optional[Callable[[int, int], None]] = None) -> str:
    """Bequemer Download: sucht das 'LogWatch.exe'-Asset und lädt es herunter."""
    asset = select_asset(release)
    if asset is None:
        raise UpdateError(f"Im Release ist kein Asset '{ASSET_NAME}' vorhanden.")
    if dest_path is None:
        dest_path = os.path.join(tempfile.gettempdir(), f"LogWatch_update_{os.getpid()}.exe")
    return download_asset(asset, dest_path, token=token, progress_callback=progress_callback)


# ---------------------------------------------------------------------------
# Windows-spezifische Installation (Austausch der laufenden EXE)
# ---------------------------------------------------------------------------
def is_windows() -> bool:
    return sys.platform.startswith("win")


def current_exe_path() -> Optional[str]:
    """Pfad der laufenden LogWatch.exe (nur sinnvoll im PyInstaller-Build)."""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return None


# Inhalt der temporären .bat, die den Austausch nach Prozessende durchführt.
# Deutsche Kommentare; defensiv (wartet auf Prozessende, mehrere Versuche).
_UPDATE_BAT_TEMPLATE = r"""@echo off
rem === LogWatch Auto-Update ===
rem Ersetzt die laufende EXE, nachdem der alte Prozess beendet wurde, und startet neu.
setlocal enableextensions
set "PID={pid}"
set "NEW={new}"
set "TARGET={target}"

rem 1) Warten, bis der alte Prozess (PID) beendet ist (max. ~30 Sekunden).
set /a tries=0
:waitloop
tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul
if not errorlevel 1 (
    set /a tries+=1
    if %tries% geq 30 goto afterwait
    timeout /t 1 /nobreak >nul
    goto waitloop
)
:afterwait

rem 2) Alte Datei durch die neue ersetzen (mehrere Versuche, falls kurz gesperrt).
set /a rep=0
:replace
copy /y "%NEW%" "%TARGET%" >nul
if errorlevel 1 (
    set /a rep+=1
    if %rep% geq 15 goto startnew
    timeout /t 1 /nobreak >nul
    goto replace
)

:startnew
rem 3) Neue Version starten.
start "" "%TARGET%"

rem 4) Aufräumen: heruntergeladene Datei und dieses Skript entfernen.
del "%NEW%" >nul 2>&1
(goto) 2>nul & del "%~f0"
"""


def build_update_script(new_exe_path: str, target_exe_path: str, pid: int) -> str:
    """Erzeugt den Inhalt der Update-.bat (plattformunabhängig testbar)."""
    return _UPDATE_BAT_TEMPLATE.format(
        pid=int(pid), new=new_exe_path, target=target_exe_path)


def install_and_restart(new_exe_path: str,
                        target_exe_path: Optional[str] = None,
                        pid: Optional[int] = None) -> None:
    """Startet den Austausch der laufenden EXE (NUR Windows).

    Schreibt eine temporäre .bat, die wartet bis dieser Prozess beendet ist, die
    alte EXE durch die neue ersetzt und die neue startet. Danach muss die App
    beendet werden (das übernimmt der Aufrufer in der UI).
    """
    if not is_windows():
        raise UpdateError("Die automatische Installation ist nur unter Windows verfügbar.")
    if not new_exe_path or not os.path.isfile(new_exe_path):
        raise UpdateError("Die heruntergeladene Datei wurde nicht gefunden.")

    target = target_exe_path or current_exe_path()
    if not target:
        raise UpdateError(
            "Das Ziel (laufende LogWatch.exe) konnte nicht bestimmt werden. "
            "Die automatische Installation funktioniert nur im gebauten EXE-Betrieb."
        )
    the_pid = int(pid if pid is not None else os.getpid())

    script = build_update_script(new_exe_path, os.path.abspath(target), the_pid)
    bat_path = os.path.join(tempfile.gettempdir(), f"logwatch_update_{the_pid}.bat")
    try:
        with open(bat_path, "w", encoding="utf-8") as fh:
            fh.write(script)
        os.chmod(bat_path, os.stat(bat_path).st_mode | stat.S_IEXEC)
    except OSError as exc:
        raise UpdateError("Das Update-Skript konnte nicht geschrieben werden.") from exc

    # Detached starten, damit es den App-Prozess überlebt.
    creationflags = 0
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    if is_windows():
        creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    try:
        subprocess.Popen(["cmd", "/c", bat_path], close_fds=True, creationflags=creationflags)
    except Exception as exc:  # noqa: BLE001
        raise UpdateError("Der Update-Vorgang konnte nicht gestartet werden.") from exc
