from logwatch import machine_ids
from logwatch.machine_ids import (
    get_teamviewer_id, compute_hardware_id, UNKNOWN,
    get_teamviewer_id_or_unknown, compute_hardware_id_or_unknown,
)


class FakeReader:
    """Mockbarer Registry-Leser: (root, subkey, value) -> Wert."""
    def __init__(self, values):
        self.values = values

    def read_value(self, root, subkey, value_name):
        return self.values.get((root, subkey, value_name))


# -------------------------------- TeamViewer-ID -----------------------------
def test_teamviewer_id_decimal():
    r = FakeReader({("HKLM", r"SOFTWARE\TeamViewer", "ClientID"): "123456789"})
    assert get_teamviewer_id(r) == "123456789"


def test_teamviewer_id_from_wow6432():
    r = FakeReader({("HKLM", r"SOFTWARE\WOW6432Node\TeamViewer", "ClientID"): 987654321})
    assert get_teamviewer_id(r) == "987654321"


def test_teamviewer_id_hex_normalized():
    r = FakeReader({("HKLM", r"SOFTWARE\TeamViewer", "ClientID"): "0x75BCD15"})
    assert get_teamviewer_id(r) == "123456789"


def test_teamviewer_id_missing_returns_none():
    r = FakeReader({})
    assert get_teamviewer_id(r) is None
    assert get_teamviewer_id_or_unknown(r) == UNKNOWN


def test_teamviewer_id_invalid_value():
    r = FakeReader({("HKLM", r"SOFTWARE\TeamViewer", "ClientID"): "abc"})
    assert get_teamviewer_id(r) is None


def test_teamviewer_id_no_reader_non_windows(monkeypatch):
    # Kein Reader + nicht Windows -> None
    monkeypatch.setattr(machine_ids.sys, "platform", "linux")
    assert get_teamviewer_id() is None


# -------------------------------- Hardware-ID -------------------------------
def test_hardware_id_deterministic():
    vals = {("HKLM", r"SOFTWARE\Microsoft\Cryptography", "MachineGuid"): "GUID-AAA"}
    r1 = FakeReader(vals)
    r2 = FakeReader(dict(vals))
    h1 = compute_hardware_id(r1)
    h2 = compute_hardware_id(r2)
    assert h1 == h2
    assert h1 is not None
    assert len(h1) == 64  # SHA-256 hex


def test_hardware_id_differs_on_other_hardware():
    a = compute_hardware_id(FakeReader({("HKLM", r"SOFTWARE\Microsoft\Cryptography", "MachineGuid"): "GUID-AAA"}))
    b = compute_hardware_id(FakeReader({("HKLM", r"SOFTWARE\Microsoft\Cryptography", "MachineGuid"): "GUID-BBB"}))
    assert a != b


def test_hardware_id_combines_sources():
    only_guid = compute_hardware_id(FakeReader({
        ("HKLM", r"SOFTWARE\Microsoft\Cryptography", "MachineGuid"): "GUID-AAA",
    }))
    both = compute_hardware_id(FakeReader({
        ("HKLM", r"SOFTWARE\Microsoft\Cryptography", "MachineGuid"): "GUID-AAA",
        ("HKLM", r"SYSTEM\HardwareConfig", "LastConfig"): "{HW-1}",
    }))
    assert only_guid != both  # zusätzliche Quelle ändert den Hash


def test_hardware_id_missing_returns_none():
    assert compute_hardware_id(FakeReader({})) is None
    assert compute_hardware_id_or_unknown(FakeReader({})) == UNKNOWN
