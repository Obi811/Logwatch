"""Fehlererkennung in Logzeilen.

Zwei Modi:
- "all"      -> generische Fehler-Stichwörter (ERROR/FEHLER/Exception/FATAL, konfigurierbar)
- "specific" -> nur vom Nutzer angegebene Stichwörter/Muster

Alle Vergleiche sind case-insensitive. Stichwörter werden als einfache
Teilstring-Treffer behandelt (robust und für Nutzer leicht verständlich).
Plattformunabhängig und ohne GUI testbar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence


@dataclass
class Match:
    """Ein Treffer: die Logzeile und das auslösende Stichwort."""
    line: str
    keyword: str


def _clean_keywords(keywords: Iterable[str]) -> List[str]:
    """Leere/whitespace-Stichwörter entfernen und trimmen."""
    result = []
    for kw in keywords:
        kw = (kw or "").strip()
        if kw:
            result.append(kw)
    return result


def line_matches(line: str, keywords: Sequence[str]) -> str | None:
    """Gibt das erste passende Stichwort zurück oder None.

    Case-insensitive Teilstring-Suche.
    """
    line_lower = line.lower()
    for kw in keywords:
        if kw and kw.lower() in line_lower:
            return kw
    return None


def detect(lines: Iterable[str], mode: str, all_keywords: Sequence[str],
           specific_keywords: Sequence[str]) -> List[Match]:
    """Untersucht Zeilen und liefert alle Treffer.

    mode: "all" oder "specific".
    """
    if mode == "specific":
        keywords = _clean_keywords(specific_keywords)
    else:
        keywords = _clean_keywords(all_keywords)

    matches: List[Match] = []
    if not keywords:
        # Im Modus "specific" ohne Stichwörter wird bewusst nichts erkannt.
        return matches

    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        kw = line_matches(line, keywords)
        if kw is not None:
            matches.append(Match(line=line, keyword=kw))
    return matches
