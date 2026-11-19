"""Hintergrund-Worker für die Überwachung (QThread).

Kapselt die Monitor-Schleife in einem eigenen Thread, damit die UI nicht
blockiert (z.B. während des SMTP-Versands). Kommuniziert per Qt-Signalen.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .config import Config
from .mailer import build_message, send_message
from .monitor import Monitor


class MonitorWorker(QThread):
    log_message = Signal(str)        # Status-/Logtext für die UI
    status_changed = Signal(bool)    # True = läuft, False = gestoppt

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._running = False
        self._check_now = False

        def send(cfg: Config, matches):
            msg = build_message(cfg, matches)
            send_message(cfg.smtp, msg)

        self.monitor = Monitor(config, send_func=send, log_func=self._emit)

    def _emit(self, msg: str) -> None:
        self.log_message.emit(msg)

    def request_check_now(self) -> None:
        self._check_now = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        self.status_changed.emit(True)
        try:
            self.monitor.start()
        except Exception as exc:  # noqa: BLE001
            self._emit(f"Fehler beim Start der Überwachung: {exc}")

        interval = max(1, int(self.config.check_interval_seconds))
        elapsed = 0.0
        step = 0.5
        while self._running:
            if self._check_now or elapsed >= interval:
                self._check_now = False
                elapsed = 0.0
                try:
                    self.monitor.check_once()
                except Exception as exc:  # noqa: BLE001
                    self._emit(f"Unerwarteter Fehler im Prüfzyklus: {exc}")
            self.msleep(int(step * 1000))
            elapsed += step
        self.status_changed.emit(False)
        self._emit("Überwachung gestoppt.")
