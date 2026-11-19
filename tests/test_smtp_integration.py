"""End-to-End-Test des SMTP-Versands gegen einen lokalen Dummy-Server.

Wird übersprungen, wenn aiosmtpd nicht installiert ist (reine Dev-Abhängigkeit).
"""
import os
import time

import pytest

aiosmtpd = pytest.importorskip("aiosmtpd")
from aiosmtpd.controller import Controller  # noqa: E402

from logwatch.config import Config, Recipient, SMTPSettings  # noqa: E402
from logwatch.detector import Match  # noqa: E402
from logwatch.mailer import build_message, send_message  # noqa: E402


class _Collector:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        self.messages.append(envelope.content)
        return "250 OK"


def test_send_message_end_to_end(tmp_path):
    logp = tmp_path / "app.log"
    logp.write_text("2024 ERROR etwas kaputt\nINFO ok\n", encoding="utf-8")

    handler = _Collector()
    ctrl = Controller(handler, hostname="127.0.0.1", port=8029)
    ctrl.start()
    try:
        c = Config()
        c.log_file_path = str(logp)
        c.smtp = SMTPSettings(host="127.0.0.1", port=8029, username="", password="",
                              use_tls=False, use_ssl=False, from_address="a@test.de")
        c.recipients = [Recipient(email="chef@kunde.de", company="Muster GmbH",
                                  machine="CNC-7", active=True)]
        msg = build_message(c, [Match(line="2024 ERROR etwas kaputt", keyword="ERROR")])
        send_message(c.smtp, msg)
        time.sleep(0.3)

        assert handler.messages, "Keine E-Mail empfangen"
        raw = handler.messages[0].decode("utf-8", "replace")
        assert "Muster GmbH" in raw
        assert "CNC-7" in raw
        assert "etwas kaputt" in raw
        assert "Content-Disposition: attachment" in raw
        assert os.path.basename(str(logp)) in raw
    finally:
        ctrl.stop()
