"""Inkrementelles Lesen einer Logdatei.

Merkt sich die zuletzt gelesene Byte-Position (Offset) und liefert bei jedem
Aufruf nur die neu hinzugekommenen Zeilen. Erkennt Logrotation/Trunkierung:
Wird die Datei kleiner als der gemerkte Offset (oder durch eine neue Datei
ersetzt), wird von vorne gelesen.

Plattformunabhängig und ohne GUI testbar.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List


@dataclass
class ReadResult:
    lines: List[str]
    rotated: bool  # True, wenn Rotation/Trunkierung erkannt wurde


class LogReader:
    """Verfolgt den Lesefortschritt einer Logdatei anhand Offset + Inode/Größe.

    Die Position wird im Speicher gehalten. Sie kann über ``state``/``load_state``
    serialisiert werden, falls sie persistiert werden soll.
    """

    def __init__(self, path: str, encoding: str = "utf-8"):
        self.path = path
        self.encoding = encoding
        self.offset: int = 0
        self._signature: tuple | None = None  # (inode, dev) zur Rotationserkennung
        self._head: bytes | None = None       # Fingerprint des Dateianfangs (robust gg. Inode-Recycling)

    _HEAD_LEN = 256

    # -- Signatur zur Erkennung eines Dateiwechsels -------------------------
    @staticmethod
    def _file_signature(path: str) -> tuple | None:
        try:
            st = os.stat(path)
        except (OSError, FileNotFoundError):
            return None
        # st_ino ist unter Windows seit Python 3.x ebenfalls befüllt.
        return (st.st_ino, st.st_dev)

    def _read_head(self) -> bytes | None:
        try:
            with open(self.path, "rb") as f:
                return f.read(self._HEAD_LEN)
        except (OSError, FileNotFoundError):
            return None

    def reset(self) -> None:
        self.offset = 0
        self._signature = None
        self._head = None

    def prime_to_end(self) -> None:
        """Setzt den Offset ans aktuelle Dateiende, ohne zu lesen.

        Nützlich beim Start der Überwachung, damit alte Logzeilen nicht erneut
        als Fehler gemeldet werden.
        """
        try:
            self.offset = os.path.getsize(self.path)
            self._signature = self._file_signature(self.path)
            self._head = self._read_head()
        except (OSError, FileNotFoundError):
            self.offset = 0
            self._signature = None
            self._head = None

    def read_new_lines(self) -> ReadResult:
        """Liest neu hinzugekommene Zeilen seit dem letzten Aufruf."""
        if not self.path or not os.path.isfile(self.path):
            return ReadResult(lines=[], rotated=False)

        rotated = False
        current_sig = self._file_signature(self.path)
        current_head = self._read_head()
        try:
            size = os.path.getsize(self.path)
        except (OSError, FileNotFoundError):
            return ReadResult(lines=[], rotated=False)

        # Rotation/Trunkierung erkennen (mehrere Indizien, robust kombiniert):
        # - Datei kleiner als Offset         -> trunkiert oder ersetzt
        # - Signatur (Inode/Device) geändert -> Datei ersetzt
        # - Dateianfang geändert             -> neue Datei, auch bei Inode-Recycling
        if size < self.offset:
            rotated = True
        elif self._signature is not None and current_sig != self._signature:
            rotated = True
        elif (self._head is not None and self.offset > 0
              and current_head is not None and not current_head.startswith(self._head)
              and not self._head.startswith(current_head)):
            # Der zuvor gesehene Anfang ist nicht mehr Präfix des aktuellen Anfangs
            # (und umgekehrt) -> die Datei wurde ersetzt/neu beschrieben.
            rotated = True

        if rotated:
            self.offset = 0

        self._signature = current_sig
        self._head = current_head

        if size == self.offset:
            return ReadResult(lines=[], rotated=rotated)

        lines: List[str] = []
        with open(self.path, "r", encoding=self.encoding, errors="replace", newline="") as f:
            f.seek(self.offset)
            data = f.read()
            self.offset = f.tell()

        if data:
            # Nur vollständige Zeilen (mit Zeilenende) verarbeiten; eine evtl.
            # unvollständige letzte Zeile beim nächsten Durchgang nachholen.
            if not data.endswith(("\n", "\r")):
                last_nl = max(data.rfind("\n"), data.rfind("\r"))
                if last_nl >= 0:
                    # Offset um den unvollständigen Rest zurücksetzen.
                    remainder = data[last_nl + 1:]
                    self.offset -= len(remainder.encode(self.encoding))
                    data = data[: last_nl + 1]
                else:
                    # Komplette Zeile noch unvollständig -> nichts verarbeiten,
                    # Offset zurücksetzen.
                    self.offset -= len(data.encode(self.encoding))
                    data = ""

            if data:
                lines = data.splitlines()

        return ReadResult(lines=lines, rotated=rotated)

    # -- Serialisierung (optional) -----------------------------------------
    def state(self) -> dict:
        return {"path": self.path, "offset": self.offset, "signature": self._signature}

    def load_state(self, state: dict) -> None:
        if not state:
            return
        self.offset = int(state.get("offset", 0))
        sig = state.get("signature")
        self._signature = tuple(sig) if sig else None
