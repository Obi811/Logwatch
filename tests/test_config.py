import os
import json

from logwatch.config import (
    Config, Recipient, SMTPSettings, DEFAULT_KEYWORDS,
    load_config, save_config, export_config, import_config,
)


def test_defaults():
    c = Config()
    assert c.check_interval_seconds == 30
    assert c.error_mode == "all"
    assert c.all_keywords == DEFAULT_KEYWORDS
    assert c.cooldown_seconds == 300
    assert c.MAX_RECIPIENTS == 5
    assert c.autostart is False


def test_roundtrip(tmp_path):
    c = Config()
    c.log_file_path = r"C:\logs\app.log"
    c.check_interval_seconds = 15
    c.error_mode = "specific"
    c.specific_keywords = ["2024-01-01 FATAL Datenbank weg", "Timeout bei Maschine X"]
    c.smtp = SMTPSettings(host="smtp.test", port=465, username="u", password="geheim",
                          use_tls=False, use_ssl=True, from_address="a@test")
    c.recipients = [
        Recipient(email="a@x.de", company="Firma A", machine="M1", active=True),
        Recipient(email="b@x.de", company="Firma B", machine="M2", active=False),
    ]
    c.cooldown_seconds = 120
    c.autostart = True

    path = str(tmp_path / "config.json")
    save_config(c, path)
    assert os.path.isfile(path)

    loaded = load_config(path)
    assert loaded.log_file_path == c.log_file_path
    assert loaded.check_interval_seconds == 15
    assert loaded.error_mode == "specific"
    assert loaded.specific_keywords == c.specific_keywords
    assert loaded.smtp.use_ssl is True
    assert loaded.smtp.password == "geheim"
    assert len(loaded.recipients) == 2
    assert loaded.recipients[1].active is False
    assert loaded.cooldown_seconds == 120
    assert loaded.autostart is True


def test_load_missing_returns_defaults(tmp_path):
    loaded = load_config(str(tmp_path / "nope.json"))
    assert loaded.error_mode == "all"


def test_saved_file_is_not_plaintext(tmp_path):
    """Die gespeicherte Datei darf das Passwort NICHT im Klartext enthalten."""
    c = Config()
    c.smtp.password = "supergeheim123"
    path = str(tmp_path / "config.dat")
    save_config(c, path)
    raw = open(path, "rb").read()
    assert b"supergeheim123" not in raw
    assert b"smtp" not in raw  # auch Feldnamen sind verschlüsselt


def test_master_password_required(tmp_path):
    import pytest
    from logwatch import crypto
    c = Config()
    c.smtp.password = "x"
    path = str(tmp_path / "config.dat")
    save_config(c, path, master_password="Meister!")
    # Ohne Passwort scheitert das Laden
    with pytest.raises(crypto.DecryptionError):
        load_config(path)
    # Mit falschem Passwort scheitert es ebenfalls
    with pytest.raises(crypto.DecryptionError):
        load_config(path, master_password="falsch")
    # Mit richtigem Passwort klappt es
    loaded = load_config(path, master_password="Meister!")
    assert loaded.smtp.password == "x"


def test_export_import_portable(tmp_path):
    """Eine einmal erstellte Config muss sich auf mehreren PCs einspielen lassen."""
    c = Config()
    c.error_mode = "specific"
    c.specific_keywords = ["Komplette Fehlerzeile aus dem Log", "Noch eine Zeile"]
    export_path = str(tmp_path / "logwatch_profil.dat")
    export_config(c, export_path)

    imported = import_config(export_path)
    assert imported.error_mode == "specific"
    assert imported.specific_keywords == c.specific_keywords


def test_new_fields_roundtrip(tmp_path):
    from logwatch.config import DashboardSettings
    c = Config()
    c.machine_id = "M-42"
    c.company = "Kunde AG"
    c.dashboard = DashboardSettings(enabled=True, base_url="https://d.example.com", upload_token="tok")
    path = str(tmp_path / "config.dat")
    save_config(c, path)
    loaded = load_config(path)
    assert loaded.machine_id == "M-42"
    assert loaded.company == "Kunde AG"
    assert loaded.dashboard.enabled is True
    assert loaded.dashboard.base_url == "https://d.example.com"
    assert loaded.dashboard.upload_token == "tok"


def test_backward_compatible_old_config_without_new_fields():
    """Eine alte Config (ohne machine_id/company/dashboard) muss weiter laden."""
    old = {
        "log_file_path": r"C:\logs\app.log",
        "check_interval_seconds": 20,
        "error_mode": "all",
        "all_keywords": ["ERROR"],
        "specific_keywords": [],
        "smtp": {"host": "h"},
        "recipients": [],
        "cooldown_seconds": 300,
        "autostart": False,
    }
    c = Config.from_dict(old)
    assert c.machine_id == ""
    assert c.company == ""
    assert c.dashboard.enabled is False
    assert c.dashboard.base_url == ""


def test_export_import_includes_new_fields(tmp_path):
    from logwatch.config import DashboardSettings
    c = Config()
    c.machine_id = "M-7"
    c.dashboard = DashboardSettings(enabled=True, base_url="https://x", upload_token="s")
    p = str(tmp_path / "profil.dat")
    export_config(c, p)
    imported = import_config(p)
    assert imported.machine_id == "M-7"
    assert imported.dashboard.upload_token == "s"


def test_active_recipients_filters():
    c = Config()
    c.recipients = [
        Recipient(email="a@x.de", active=True),
        Recipient(email="", active=True),       # keine Adresse
        Recipient(email="b@x.de", active=False),  # inaktiv
    ]
    active = c.active_recipients()
    assert len(active) == 1
    assert active[0].email == "a@x.de"
