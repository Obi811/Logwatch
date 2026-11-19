from logwatch.config import DEFAULT_KEYWORDS
from logwatch.detector import detect, line_matches, Match


def test_line_matches_case_insensitive():
    assert line_matches("Da war ein error aufgetreten", ["ERROR"]) == "ERROR"
    assert line_matches("alles gut", ["ERROR"]) is None


def test_mode_all_default_keywords():
    lines = [
        "INFO startup ok",
        "2024-01-01 ERROR database down",
        "ein FEHLER ist passiert",
        "java.lang.Exception blah",
        "FATAL kernel panic",
        "nur info",
    ]
    matches = detect(lines, "all", DEFAULT_KEYWORDS, [])
    assert len(matches) == 4
    keywords = {m.keyword for m in matches}
    assert keywords == {"ERROR", "FEHLER", "Exception", "FATAL"}


def test_mode_all_skips_blank_lines():
    lines = ["", "   ", "ERROR x"]
    matches = detect(lines, "all", DEFAULT_KEYWORDS, [])
    assert len(matches) == 1


def test_mode_specific_only_matches_given():
    lines = [
        "2024-01-01 ERROR database down",   # würde in 'all' matchen, hier nicht
        "Timeout bei Maschine 7 aufgetreten",
        "alles gut",
    ]
    specific = ["Timeout bei Maschine 7"]
    matches = detect(lines, "specific", DEFAULT_KEYWORDS, specific)
    assert len(matches) == 1
    assert matches[0].keyword == "Timeout bei Maschine 7"


def test_mode_specific_full_line_pattern():
    """Nutzer trägt eine komplette Logzeile (ohne wechselnden Zeitstempel) ein."""
    pattern = "FATAL: Verbindung zur Steuerung verloren"
    lines = [
        "2024-05-01 08:00:00 FATAL: Verbindung zur Steuerung verloren",
        "2024-05-01 09:30:00 FATAL: Verbindung zur Steuerung verloren",
        "2024-05-01 10:00:00 INFO: alles ok",
    ]
    matches = detect(lines, "specific", DEFAULT_KEYWORDS, [pattern])
    assert len(matches) == 2


def test_mode_specific_empty_matches_nothing():
    lines = ["ERROR x", "FATAL y"]
    matches = detect(lines, "specific", DEFAULT_KEYWORDS, [])
    assert matches == []


def test_whitespace_keywords_ignored():
    lines = ["ERROR x"]
    matches = detect(lines, "specific", DEFAULT_KEYWORDS, ["   ", ""])
    assert matches == []
