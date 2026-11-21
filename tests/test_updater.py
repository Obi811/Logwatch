"""Unit-Tests für die plattformunabhängige Update-Logik (logwatch/updater.py).

Kein echter Netzwerkzugriff: Der HTTP-Transport wird über ``get_func`` injiziert.
Die Windows-spezifische Install-Logik wird nicht ausgeführt (nur der Skript-Bau
wird getestet; die eigentliche Installation ist auf Nicht-Windows gekapselt).
"""
from __future__ import annotations

import sys

import pytest

from logwatch import updater
from logwatch.updater import (
    UpdateError,
    build_headers,
    build_update_script,
    check_for_update,
    compare_versions,
    fetch_latest_release,
    is_newer,
    normalize_version,
    read_local_version,
    select_asset,
)


# ---------------------------------------------------------------------------
# Hilfsklasse: Fake-HTTP-Response + injizierbarer get_func
# ---------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status_code: int, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}

    def json(self):
        return self._json


def make_get_func(status_code: int, json_data=None, capture: dict | None = None):
    """Liefert einen get_func, der eine FakeResponse zurückgibt und optional die
    übergebenen Header in ``capture`` ablegt."""
    def _get(url, headers, timeout):
        if capture is not None:
            capture["url"] = url
            capture["headers"] = headers
            capture["timeout"] = timeout
        return FakeResponse(status_code, json_data)
    return _get


SAMPLE_RELEASE = {
    "tag_name": "v0.3.0",
    "name": "LogWatch 0.3.0",
    "body": "Neue Funktionen und Fehlerbehebungen.",
    "assets": [
        {
            "name": "LogWatch.exe",
            "browser_download_url": "https://example.com/LogWatch.exe",
            "url": "https://api.github.com/repos/Obi811/Logwatch/releases/assets/1",
        },
        {
            "name": "checksums.txt",
            "browser_download_url": "https://example.com/checksums.txt",
            "url": "https://api.github.com/repos/Obi811/Logwatch/releases/assets/2",
        },
    ],
}


# ---------------------------------------------------------------------------
# Versionsvergleich
# ---------------------------------------------------------------------------
def test_normalize_version_strips_v_prefix():
    assert normalize_version("v1.2.3") == "1.2.3"
    assert normalize_version("V0.2.0") == "0.2.0"
    assert normalize_version("  1.0.0  ") == "1.0.0"


def test_compare_versions_equal():
    assert compare_versions("1.2.3", "1.2.3") == 0
    assert compare_versions("v1.2.3", "1.2.3") == 0


def test_compare_versions_newer_and_older():
    assert compare_versions("0.3.0", "0.2.0") == 1
    assert compare_versions("0.2.0", "0.3.0") == -1
    assert compare_versions("1.0.0", "0.9.9") == 1


def test_compare_versions_missing_segments():
    # "1.2" -> (1,2,0)
    assert compare_versions("1.2", "1.2.0") == 0
    assert compare_versions("1", "1.0.1") == -1


def test_is_newer():
    assert is_newer("v0.3.0", "0.2.0") is True
    assert is_newer("0.2.0", "0.2.0") is False
    assert is_newer("0.1.0", "0.2.0") is False


def test_compare_versions_tolerant_of_suffix():
    # Vorabversionen werden tolerant behandelt (nur numerischer Kopf zählt).
    assert compare_versions("1.2.0-beta", "1.2.0") == 0


# ---------------------------------------------------------------------------
# Lokale Version lesen
# ---------------------------------------------------------------------------
def test_read_local_version_returns_string():
    v = read_local_version()
    assert isinstance(v, str)
    assert v  # nicht leer (Repo enthält eine VERSION-Datei)


def test_read_local_version_default_on_missing(monkeypatch):
    monkeypatch.setattr(updater, "_version_file_candidates", lambda: ["/nicht/vorhanden/VERSION"])
    assert read_local_version(default="9.9.9") == "9.9.9"


# ---------------------------------------------------------------------------
# Asset-Auswahl
# ---------------------------------------------------------------------------
def test_select_asset_finds_exe():
    asset = select_asset(SAMPLE_RELEASE)
    assert asset is not None
    assert asset["name"] == "LogWatch.exe"


def test_select_asset_case_insensitive():
    release = {"assets": [{"name": "logwatch.EXE", "url": "x"}]}
    asset = select_asset(release, asset_name="LogWatch.exe")
    assert asset is not None


def test_select_asset_missing_returns_none():
    release = {"assets": [{"name": "something_else.zip"}]}
    assert select_asset(release) is None


# ---------------------------------------------------------------------------
# Header / Authorization
# ---------------------------------------------------------------------------
def test_build_headers_without_token():
    headers = build_headers(None)
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == updater.GITHUB_API_VERSION
    assert "Authorization" not in headers


def test_build_headers_with_token():
    headers = build_headers("secret-token-123")
    assert headers["Authorization"] == "Bearer secret-token-123"


def test_build_headers_empty_token_omits_authorization():
    headers = build_headers("   ")
    assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# fetch_latest_release / check_for_update mit injiziertem Transport
# ---------------------------------------------------------------------------
def test_fetch_latest_release_sends_auth_header_when_token():
    capture: dict = {}
    get_func = make_get_func(200, SAMPLE_RELEASE, capture=capture)
    release = fetch_latest_release(token="my-pat", get_func=get_func)
    assert release.version == "0.3.0"
    assert release.tag == "v0.3.0"
    assert capture["headers"]["Authorization"] == "Bearer my-pat"
    assert capture["headers"]["Accept"] == "application/vnd.github+json"


def test_fetch_latest_release_no_auth_header_without_token():
    capture: dict = {}
    get_func = make_get_func(200, SAMPLE_RELEASE, capture=capture)
    fetch_latest_release(token=None, get_func=get_func)
    assert "Authorization" not in capture["headers"]


def test_fetch_latest_release_404_raises():
    get_func = make_get_func(404, {})
    with pytest.raises(UpdateError):
        fetch_latest_release(get_func=get_func)


def test_fetch_latest_release_401_raises_without_token_leak():
    get_func = make_get_func(401, {})
    with pytest.raises(UpdateError) as excinfo:
        fetch_latest_release(token="super-secret", get_func=get_func)
    # Das Token darf NIEMALS in der Fehlermeldung auftauchen.
    assert "super-secret" not in str(excinfo.value)


def test_fetch_latest_release_network_error_no_token_leak():
    def boom(url, headers, timeout):
        raise ConnectionError("boom")

    with pytest.raises(UpdateError) as excinfo:
        fetch_latest_release(token="super-secret", get_func=boom)
    assert "super-secret" not in str(excinfo.value)


def test_check_for_update_available():
    get_func = make_get_func(200, SAMPLE_RELEASE)
    result = check_for_update(local_version="0.2.0", token=None, get_func=get_func)
    assert result.ok is True
    assert result.update_available is True
    assert result.remote_version == "0.3.0"
    assert result.asset_available is True
    assert result.release_name == "LogWatch 0.3.0"


def test_check_for_update_up_to_date():
    get_func = make_get_func(200, SAMPLE_RELEASE)
    result = check_for_update(local_version="0.3.0", token=None, get_func=get_func)
    assert result.ok is True
    assert result.update_available is False


def test_check_for_update_error_is_captured():
    get_func = make_get_func(404, {})
    result = check_for_update(local_version="0.2.0", get_func=get_func)
    assert result.ok is False
    assert result.error  # deutschsprachige Fehlermeldung vorhanden


# ---------------------------------------------------------------------------
# Windows-Install: nur der Skript-Bau wird getestet (plattformunabhängig)
# ---------------------------------------------------------------------------
def test_build_update_script_contains_paths_and_pid():
    script = build_update_script(r"C:\tmp\new.exe", r"C:\app\LogWatch.exe", 4242)
    assert "4242" in script
    assert r"C:\tmp\new.exe" in script
    assert r"C:\app\LogWatch.exe" in script


@pytest.mark.skipif(sys.platform.startswith("win"), reason="nur auf Nicht-Windows prüfbar")
def test_install_and_restart_refuses_on_non_windows():
    with pytest.raises(UpdateError):
        updater.install_and_restart("/tmp/new.exe", "/tmp/target.exe", pid=1)
