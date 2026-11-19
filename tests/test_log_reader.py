import os
from logwatch.log_reader import LogReader


def write(path, text, mode="w"):
    with open(path, mode, encoding="utf-8", newline="") as f:
        f.write(text)


def test_incremental_reading(tmp_path):
    p = str(tmp_path / "app.log")
    write(p, "zeile 1\nzeile 2\n")
    r = LogReader(p)
    res = r.read_new_lines()
    assert res.lines == ["zeile 1", "zeile 2"]
    assert res.rotated is False

    # Keine neuen Zeilen
    res = r.read_new_lines()
    assert res.lines == []

    # Anhängen
    write(p, "zeile 3\n", mode="a")
    res = r.read_new_lines()
    assert res.lines == ["zeile 3"]


def test_prime_to_end_skips_existing(tmp_path):
    p = str(tmp_path / "app.log")
    write(p, "alt 1\nalt 2\n")
    r = LogReader(p)
    r.prime_to_end()
    res = r.read_new_lines()
    assert res.lines == []
    write(p, "neu 1\n", mode="a")
    res = r.read_new_lines()
    assert res.lines == ["neu 1"]


def test_partial_last_line_held_until_complete(tmp_path):
    p = str(tmp_path / "app.log")
    write(p, "vollstaendig\nunvoll")
    r = LogReader(p)
    res = r.read_new_lines()
    assert res.lines == ["vollstaendig"]
    # Rest der Zeile wird angehängt
    write(p, "staendig2\n", mode="a")
    res = r.read_new_lines()
    assert res.lines == ["unvollstaendig2"]


def test_truncation_detected(tmp_path):
    p = str(tmp_path / "app.log")
    write(p, "a\nb\nc\n")
    r = LogReader(p)
    r.read_new_lines()
    # Trunkieren (gleiche Datei, kleiner)
    write(p, "x\n")
    res = r.read_new_lines()
    assert res.rotated is True
    assert res.lines == ["x"]


def test_rotation_by_replacement(tmp_path):
    p = str(tmp_path / "app.log")
    write(p, "line old 1\nline old 2\n")
    r = LogReader(p)
    r.read_new_lines()
    # Rotation simulieren: Datei löschen und neu anlegen (neue Inode)
    os.remove(p)
    write(p, "fresh 1\n")
    res = r.read_new_lines()
    assert res.rotated is True
    assert res.lines == ["fresh 1"]


def test_missing_file_returns_empty(tmp_path):
    r = LogReader(str(tmp_path / "does_not_exist.log"))
    res = r.read_new_lines()
    assert res.lines == []
    assert res.rotated is False
