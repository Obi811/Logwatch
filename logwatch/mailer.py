"""E-Mail-Bau und SMTP-Versand für LogWatch.

Der Message-Aufbau (``build_message``) ist plattformunabhängig und ohne Netzwerk
testbar. Der eigentliche Versand (``send_message``) erfolgt per SMTP.
"""
from __future__ import annotations

import os
import smtplib
import socket
from email.message import EmailMessage
from email.utils import formatdate
from typing import List, Sequence

from .config import Config, Recipient, SMTPSettings
from .detector import Match


def _machine_info(recipients: Sequence[Recipient]) -> str:
    """Baut eine kurze "Firma/Maschine"-Zusammenfassung für Betreff/Text."""
    parts = []
    for r in recipients:
        label = " / ".join([x for x in (r.company.strip(), r.machine.strip()) if x])
        if label:
            parts.append(label)
    # Duplikate entfernen, Reihenfolge erhalten
    seen = set()
    uniq = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return ", ".join(uniq)


def build_subject(config: Config, matches: Sequence[Match], recipients: Sequence[Recipient],
                  teamviewer_id: str | None = None) -> str:
    info = _machine_info(recipients)
    count = len(matches)
    base = "[LogWatch] Fehler erkannt"
    if count > 1:
        base = f"[LogWatch] {count} Fehler erkannt"
    # Maschinen-ID zuerst, dann Firma/Maschine der Empfänger
    tags = []
    if config.machine_id:
        tags.append(config.machine_id)
    if info:
        tags.append(info)
    if teamviewer_id:
        tags.append(f"TV {teamviewer_id}")
    if tags:
        return f"{base} – {' / '.join(tags)}"
    return base


def build_body(config: Config, matches: Sequence[Match], recipients: Sequence[Recipient],
               hostname: str | None = None, teamviewer_id: str | None = None) -> str:
    if hostname is None:
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = "unbekannt"

    lines: List[str] = []
    lines.append("LogWatch hat Fehler in der überwachten Logdatei erkannt.")
    lines.append("")
    lines.append(f"Überwachte Logdatei : {config.log_file_path or '(nicht gesetzt)'}")
    lines.append(f"Rechner (Hostname)  : {hostname}")
    if config.machine_id:
        lines.append(f"Maschinen-ID        : {config.machine_id}")
    if config.company:
        lines.append(f"Firma/Kunde         : {config.company}")
    if teamviewer_id:
        lines.append(f"TeamViewer-ID       : {teamviewer_id}")

    # Firma/Maschine aus den Empfängerangaben
    companies = sorted({r.company.strip() for r in recipients if r.company.strip()})
    machines = sorted({r.machine.strip() for r in recipients if r.machine.strip()})
    if companies:
        lines.append(f"Firma               : {', '.join(companies)}")
    if machines:
        lines.append(f"Maschine            : {', '.join(machines)}")

    lines.append("")
    lines.append(f"Anzahl erkannter Fehlerzeilen: {len(matches)}")
    lines.append("-" * 60)
    # Bis zu 50 Zeilen im Text ausgeben, Rest ist im Anhang enthalten.
    max_inline = 50
    for m in matches[:max_inline]:
        lines.append(f"[{m.keyword}] {m.line}")
    if len(matches) > max_inline:
        lines.append(f"... und {len(matches) - max_inline} weitere (siehe Anhang).")
    lines.append("-" * 60)
    lines.append("")
    lines.append("Die vollständige Logdatei ist als Anhang beigefügt (sofern vorhanden).")
    lines.append("")
    lines.append("— Diese Nachricht wurde automatisch von LogWatch erstellt.")
    return "\n".join(lines)


def build_message(config: Config, matches: Sequence[Match],
                  recipients: Sequence[Recipient] | None = None,
                  attach_log: bool = True,
                  hostname: str | None = None,
                  teamviewer_id: str | None = None) -> EmailMessage:
    """Baut die EmailMessage inkl. Betreff, Text und Logdatei-Anhang.

    Kein Netzwerkzugriff – ideal für Unit-Tests.
    """
    if recipients is None:
        recipients = config.active_recipients()

    msg = EmailMessage()
    msg["Subject"] = build_subject(config, matches, recipients, teamviewer_id=teamviewer_id)
    msg["From"] = config.smtp.from_address or config.smtp.username
    msg["To"] = ", ".join(r.email.strip() for r in recipients if r.email.strip())
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(build_body(config, matches, recipients, hostname=hostname,
                               teamviewer_id=teamviewer_id))

    if attach_log and config.log_file_path and os.path.isfile(config.log_file_path):
        try:
            with open(config.log_file_path, "rb") as f:
                data = f.read()
            filename = os.path.basename(config.log_file_path) or "logfile.log"
            msg.add_attachment(data, maintype="text", subtype="plain", filename=filename)
        except OSError:
            # Anhang optional – Versand soll nicht scheitern, wenn Datei gesperrt ist.
            pass

    return msg


def build_test_message(config: Config, recipients: Sequence[Recipient] | None = None) -> EmailMessage:
    """Test-E-Mail zum Prüfen der SMTP-Einstellungen."""
    if recipients is None:
        recipients = config.active_recipients()
    msg = EmailMessage()
    info = _machine_info(recipients)
    msg["Subject"] = "[LogWatch] Test-E-Mail" + (f" – {info}" if info else "")
    msg["From"] = config.smtp.from_address or config.smtp.username
    msg["To"] = ", ".join(r.email.strip() for r in recipients if r.email.strip())
    msg["Date"] = formatdate(localtime=True)
    body = [
        "Dies ist eine Test-E-Mail von LogWatch.",
        "",
        "Wenn Sie diese Nachricht erhalten, sind Ihre SMTP-Einstellungen korrekt.",
        "",
        "— LogWatch",
    ]
    msg.set_content("\n".join(body))
    return msg


def send_message(smtp: SMTPSettings, msg: EmailMessage, timeout: int = 30) -> None:
    """Versendet eine EmailMessage per SMTP.

    Wählt SSL oder STARTTLS anhand der Einstellungen. Wirft bei Fehlern eine
    Exception (vom Aufrufer zu behandeln/zu loggen).
    """
    if not smtp.host:
        raise ValueError("SMTP-Host ist nicht konfiguriert.")

    if smtp.use_ssl:
        server = smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=timeout)
    else:
        server = smtplib.SMTP(smtp.host, smtp.port, timeout=timeout)
    try:
        server.ehlo()
        if smtp.use_tls and not smtp.use_ssl:
            server.starttls()
            server.ehlo()
        if smtp.username:
            server.login(smtp.username, smtp.password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass
