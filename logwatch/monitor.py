"""Überwachungs-Orchestrierung: Log lesen -> Fehler erkennen -> Mail (throttled).

Die Klasse ``Monitor`` kapselt die Kernlogik ohne GUI/Threads, damit sie
testbar ist. Ein Aufruf von ``check_once`` führt genau einen Prüfzyklus aus.
Das Throttling/Anti-Spam basiert auf einer übergebbaren Zeitquelle (``time_func``),
sodass es deterministisch getestet werden kann.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional
import time as _time

from .config import Config
from .detector import Match, detect
from .log_reader import LogReader


@dataclass
class CheckOutcome:
    new_lines: int = 0
    matches: List[Match] = field(default_factory=list)
    rotated: bool = False
    mail_sent: bool = False
    mail_skipped_cooldown: bool = False
    pending_count: int = 0
    error: Optional[str] = None


# Signatur des Sende-Callbacks: (config, matches) -> None (wirft bei Fehler)
SendFunc = Callable[[Config, List[Match]], None]
LogFunc = Callable[[str], None]


class Monitor:
    def __init__(self, config: Config, send_func: SendFunc,
                 log_func: Optional[LogFunc] = None,
                 time_func: Callable[[], float] = _time.time,
                 reader: Optional[LogReader] = None):
        self.config = config
        self.send_func = send_func
        self.log_func = log_func or (lambda msg: None)
        self.time_func = time_func
        self.reader = reader or LogReader(config.log_file_path)
        # Zeitpunkt der letzten erfolgreich gesendeten Mail (für Cooldown)
        self.last_sent_at: float = 0.0
        # Gesammelte Treffer, die während des Cooldowns aufgelaufen sind
        self.pending: List[Match] = []

    def start(self, from_beginning: bool = False) -> None:
        """Bereitet die Überwachung vor. Standardmäßig wird ab dem aktuellen
        Dateiende gelesen, damit alte Zeilen nicht erneut gemeldet werden."""
        self.reader.path = self.config.log_file_path
        if from_beginning:
            self.reader.reset()
        else:
            self.reader.prime_to_end()
        self.log_func("Überwachung gestartet.")

    def _cooldown_active(self, now: float) -> bool:
        if self.last_sent_at <= 0:
            return False
        return (now - self.last_sent_at) < self.config.cooldown_seconds

    def check_once(self) -> CheckOutcome:
        """Führt einen Prüfzyklus aus."""
        outcome = CheckOutcome()
        result = self.reader.read_new_lines()
        outcome.rotated = result.rotated
        outcome.new_lines = len(result.lines)
        if result.rotated:
            self.log_func("Logrotation/Trunkierung erkannt – lese ab Dateianfang.")

        matches = detect(
            result.lines,
            self.config.error_mode,
            self.config.all_keywords,
            self.config.specific_keywords,
        )
        outcome.matches = matches

        if matches:
            self.pending.extend(matches)
            self.log_func(f"{len(matches)} Fehlerzeile(n) erkannt.")

        now = self.time_func()

        if not self.pending:
            return outcome

        if self._cooldown_active(now):
            outcome.mail_skipped_cooldown = True
            outcome.pending_count = len(self.pending)
            self.log_func(
                f"Cooldown aktiv – {len(self.pending)} Fehler gesammelt, "
                f"warte bis zum nächsten Versandfenster."
            )
            return outcome

        # Versand (ggf. mit gesammelten Treffern)
        to_send = list(self.pending)
        recipients = self.config.active_recipients()
        if not recipients:
            outcome.error = "Keine aktiven Empfänger konfiguriert."
            self.log_func(outcome.error)
            return outcome

        try:
            self.send_func(self.config, to_send)
            self.last_sent_at = now
            self.pending.clear()
            outcome.mail_sent = True
            self.log_func(f"E-Mail mit {len(to_send)} Fehlerzeile(n) versendet.")
        except Exception as exc:  # noqa: BLE001 - alle Fehler loggen
            outcome.error = f"Versandfehler: {exc}"
            self.log_func(outcome.error)

        outcome.pending_count = len(self.pending)
        return outcome
