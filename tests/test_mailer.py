from logwatch.config import Config, Recipient, SMTPSettings
from logwatch.detector import Match
from logwatch.mailer import build_message, build_test_message, build_subject, build_body


def make_config(tmp_path, with_log=True):
    c = Config()
    if with_log:
        logp = tmp_path / "app.log"
        logp.write_text("2024-01-01 ERROR etwas kaputt\nINFO ok\n", encoding="utf-8")
        c.log_file_path = str(logp)
    c.smtp = SMTPSettings(from_address="sender@firma.de", username="sender@firma.de")
    c.recipients = [
        Recipient(email="chef@kunde.de", company="Muster GmbH", machine="CNC-7", active=True),
    ]
    return c


def test_build_message_has_subject_and_recipients(tmp_path):
    c = make_config(tmp_path)
    matches = [Match(line="2024-01-01 ERROR etwas kaputt", keyword="ERROR")]
    msg = build_message(c, matches)
    assert msg["To"] == "chef@kunde.de"
    assert msg["From"] == "sender@firma.de"
    assert "Fehler erkannt" in msg["Subject"]
    # Firma/Maschine im Betreff
    assert "Muster GmbH" in msg["Subject"]
    assert "CNC-7" in msg["Subject"]


def test_build_message_body_contains_error_lines_and_machine(tmp_path):
    c = make_config(tmp_path)
    matches = [Match(line="2024-01-01 ERROR etwas kaputt", keyword="ERROR")]
    msg = build_message(c, matches)
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "etwas kaputt" in body
    assert "Muster GmbH" in body
    assert "CNC-7" in body


def test_build_message_attaches_logfile(tmp_path):
    c = make_config(tmp_path)
    matches = [Match(line="ERROR x", keyword="ERROR")]
    msg = build_message(c, matches, attach_log=True)
    attachments = list(msg.iter_attachments())
    assert len(attachments) == 1
    att = attachments[0]
    assert att.get_filename() == "app.log"
    content = att.get_content()
    assert "ERROR etwas kaputt" in content


def test_build_message_without_logfile_no_attachment(tmp_path):
    c = make_config(tmp_path, with_log=False)
    matches = [Match(line="ERROR x", keyword="ERROR")]
    msg = build_message(c, matches)
    assert list(msg.iter_attachments()) == []


def test_multiple_matches_subject_count(tmp_path):
    c = make_config(tmp_path)
    matches = [Match(line="ERROR 1", keyword="ERROR"), Match(line="ERROR 2", keyword="ERROR")]
    subject = build_subject(c, matches, c.active_recipients())
    assert "2 Fehler" in subject


def test_test_message(tmp_path):
    c = make_config(tmp_path)
    msg = build_test_message(c)
    assert "Test-E-Mail" in msg["Subject"]
    assert msg["To"] == "chef@kunde.de"
