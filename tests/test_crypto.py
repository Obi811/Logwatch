import pytest
from logwatch import crypto


def test_roundtrip_embedded():
    data = b"geheime konfiguration"
    blob = crypto.encrypt_bytes(data)
    assert blob[:6] == crypto.MAGIC
    assert crypto.is_password_protected(blob) is False
    assert crypto.decrypt_bytes(blob) == data


def test_roundtrip_password():
    data = b"geheime konfiguration"
    blob = crypto.encrypt_bytes(data, password="pw")
    assert crypto.is_password_protected(blob) is True
    assert crypto.decrypt_bytes(blob, "pw") == data


def test_wrong_password_fails():
    blob = crypto.encrypt_bytes(b"x", password="pw")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_bytes(blob, "falsch")


def test_missing_password_fails():
    blob = crypto.encrypt_bytes(b"x", password="pw")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_bytes(blob)


def test_corrupt_blob_fails():
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_bytes(b"not a valid blob")


def test_ciphertext_differs_each_time():
    a = crypto.encrypt_bytes(b"same")
    b = crypto.encrypt_bytes(b"same")
    assert a != b  # unterschiedliches Salt/Token
