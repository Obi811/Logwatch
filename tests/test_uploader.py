import json

from logwatch.config import Config, DashboardSettings
from logwatch.detector import Match
from logwatch.uploader import (
    build_report, upload_report, UploadResult,
    API_REPORTS_PATH, UPLOAD_TOKEN_HEADER,
)


def make_config(tmp_path, enabled=True, url="https://dash.example.com", token="geheim"):
    c = Config()
    c.machine_id = "M-001"
    c.company = "Muster GmbH"
    logp = tmp_path / "app.log"
    logp.write_text("ERROR etwas kaputt\n", encoding="utf-8")
    c.log_file_path = str(logp)
    c.dashboard = DashboardSettings(enabled=enabled, base_url=url, upload_token=token)
    return c


def test_build_report_fields(tmp_path):
    c = make_config(tmp_path)
    matches = [Match(line="2024 ERROR etwas kaputt", keyword="ERROR")]
    rep = build_report(c, matches, teamviewer_id="123", hardware_id="hwabc",
                       hostname="PC1", timestamp="2026-01-01T00:00:00+00:00")
    assert rep["machine_id"] == "M-001"
    assert rep["company"] == "Muster GmbH"
    assert rep["teamviewer_id"] == "123"
    assert rep["hardware_id"] == "hwabc"
    assert rep["hostname"] == "PC1"
    assert rep["error_count"] == 1
    assert rep["error_lines"] == ["2024 ERROR etwas kaputt"]
    assert rep["log_filename"] == "app.log"


def test_upload_calls_transport_with_contract(tmp_path):
    c = make_config(tmp_path)
    captured = {}

    def fake_post(url, headers, payload_json, log_path):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json.loads(payload_json)
        captured["log_path"] = log_path
        return UploadResult(ok=True, status_code=201, message="OK")

    rep = build_report(c, [Match(line="ERROR x", keyword="ERROR")])
    res = upload_report(c, rep, log_path=c.log_file_path, post_func=fake_post)
    assert res.ok is True
    assert captured["url"] == "https://dash.example.com" + API_REPORTS_PATH
    assert captured["headers"][UPLOAD_TOKEN_HEADER] == "geheim"
    assert captured["payload"]["machine_id"] == "M-001"
    assert captured["log_path"] == c.log_file_path


def test_upload_disabled(tmp_path):
    c = make_config(tmp_path, enabled=False)
    called = {"n": 0}

    def fake_post(*a, **k):
        called["n"] += 1
        return UploadResult(ok=True)

    res = upload_report(c, build_report(c, []), post_func=fake_post)
    assert res.ok is False
    assert called["n"] == 0  # Transport wurde nicht aufgerufen


def test_upload_no_url(tmp_path):
    c = make_config(tmp_path, url="")
    res = upload_report(c, build_report(c, []), post_func=lambda *a, **k: UploadResult(ok=True))
    assert res.ok is False


def test_upload_network_error_is_caught(tmp_path):
    c = make_config(tmp_path)
    logs = []

    def boom(*a, **k):
        raise ConnectionError("offline")

    res = upload_report(c, build_report(c, []), post_func=boom, log_func=logs.append)
    assert res.ok is False
    assert "fehlgeschlagen" in res.message.lower()
    assert any("fehlgeschlagen" in m.lower() for m in logs)


def test_upload_http_error_reported(tmp_path):
    c = make_config(tmp_path)

    def fail(url, headers, payload_json, log_path):
        return UploadResult(ok=False, status_code=401, message="HTTP 401: Unauthorized")

    res = upload_report(c, build_report(c, []), post_func=fail)
    assert res.ok is False
    assert res.status_code == 401
