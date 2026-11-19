from logwatch.config import Config, Recipient
from logwatch.monitor import Monitor


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def make_config(tmp_path):
    c = Config()
    logp = tmp_path / "app.log"
    logp.write_text("", encoding="utf-8")
    c.log_file_path = str(logp)
    c.cooldown_seconds = 300
    c.recipients = [Recipient(email="a@x.de", company="F", machine="M", active=True)]
    return c, str(logp)


def append(path, text):
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(text)


def test_sends_on_error(tmp_path):
    c, logp = make_config(tmp_path)
    sent = []
    clock = FakeClock()
    m = Monitor(c, send_func=lambda cfg, matches: sent.append(matches), time_func=clock)
    m.start()  # prime to end (leer)
    append(logp, "INFO ok\nERROR kaputt\n")
    out = m.check_once()
    assert out.mail_sent is True
    assert len(sent) == 1
    assert len(sent[0]) == 1


def test_no_error_no_mail(tmp_path):
    c, logp = make_config(tmp_path)
    sent = []
    m = Monitor(c, send_func=lambda cfg, matches: sent.append(matches), time_func=FakeClock())
    m.start()
    append(logp, "INFO alles gut\n")
    out = m.check_once()
    assert out.mail_sent is False
    assert sent == []


def test_cooldown_collects_and_sends_later(tmp_path):
    c, logp = make_config(tmp_path)
    sent = []
    clock = FakeClock(1000.0)
    m = Monitor(c, send_func=lambda cfg, matches: sent.append(list(matches)), time_func=clock)
    m.start()

    # Erster Fehler -> Mail sofort
    append(logp, "ERROR eins\n")
    out1 = m.check_once()
    assert out1.mail_sent is True
    assert len(sent) == 1

    # Innerhalb des Cooldowns weitere Fehler -> keine Mail, aber gesammelt
    clock.t = 1100.0  # +100s < 300s
    append(logp, "ERROR zwei\nERROR drei\n")
    out2 = m.check_once()
    assert out2.mail_sent is False
    assert out2.mail_skipped_cooldown is True
    assert out2.pending_count == 2
    assert len(sent) == 1

    # Nach Ablauf des Cooldowns -> gesammelte Fehler gehen raus
    clock.t = 1400.0  # +400s > 300s seit letztem Versand
    out3 = m.check_once()
    assert out3.mail_sent is True
    assert len(sent) == 2
    assert len(sent[1]) == 2  # zwei gesammelte


def test_no_recipients_reports_error(tmp_path):
    c, logp = make_config(tmp_path)
    c.recipients = []
    m = Monitor(c, send_func=lambda cfg, matches: None, time_func=FakeClock())
    m.start()
    append(logp, "ERROR x\n")
    out = m.check_once()
    assert out.mail_sent is False
    assert out.error is not None


def test_send_failure_keeps_pending(tmp_path):
    c, logp = make_config(tmp_path)

    def failing(cfg, matches):
        raise RuntimeError("SMTP down")

    m = Monitor(c, send_func=failing, time_func=FakeClock())
    m.start()
    append(logp, "ERROR x\n")
    out = m.check_once()
    assert out.mail_sent is False
    assert "SMTP down" in out.error
    assert len(m.pending) == 1  # bleibt für nächsten Versuch erhalten


def test_specific_mode_full_line(tmp_path):
    c, logp = make_config(tmp_path)
    c.error_mode = "specific"
    c.specific_keywords = ["FATAL: Verbindung zur Steuerung verloren"]
    sent = []
    m = Monitor(c, send_func=lambda cfg, matches: sent.append(matches), time_func=FakeClock())
    m.start()
    append(logp, "2024 INFO ok\n2024 FATAL: Verbindung zur Steuerung verloren\n")
    out = m.check_once()
    assert out.mail_sent is True
    assert len(sent[0]) == 1


def test_rotation_handled(tmp_path):
    c, logp = make_config(tmp_path)
    sent = []
    clock = FakeClock()
    m = Monitor(c, send_func=lambda cfg, matches: sent.append(matches), time_func=clock)
    m.start()
    append(logp, "ERROR a\n")
    m.check_once()
    # Realistische Rotation: alte Datei wird ersetzt (neue Inode), wie bei
    # logrotate mit 'create'.
    import os
    os.remove(logp)
    with open(logp, "w", encoding="utf-8", newline="") as f:
        f.write("ERROR nach rotation\n")
    clock.t += 1000
    out = m.check_once()
    assert out.rotated is True
    assert out.mail_sent is True
