"""Verschlüsselung der Konfiguration.

Die Konfiguration wird NICHT im Klartext gespeichert. Stattdessen wird sie mit
``cryptography.Fernet`` (AES-128-CBC + HMAC) verschlüsselt.

Schlüsselableitung:
- Mit Master-Passwort: PBKDF2-HMAC-SHA256 über das Passwort + zufälligem Salt.
  Dann ist die Datei nur mit diesem Passwort entschlüsselbar (empfohlen).
- Ohne Master-Passwort: Es wird ein in der App eingebetteter Schlüssel verwendet.
  Das schützt gegen beiläufiges Mitlesen, ist aber schwächer (der Schlüssel steckt
  in der Anwendung). Für echten Schutz ein Master-Passwort setzen.

Dateiformat (binär):
    MAGIC(6) | VERSION(1) | MODE(1) | SALT(16) | TOKEN(rest)
    MODE 0 = eingebetteter Schlüssel, MODE 1 = Master-Passwort (PBKDF2)

Plattformunabhängig und ohne GUI testbar.
"""
from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"LWCFG\x00"
VERSION = 1
MODE_EMBEDDED = 0
MODE_PASSWORD = 1
SALT_LEN = 16
PBKDF2_ITERATIONS = 390_000

# Eingebetteter Basis-Schlüssel (nur Obfuskation, falls kein Master-Passwort gesetzt ist).
# Bewusst KEIN echtes Geheimnis – dient nur dazu, dass die Datei nicht im Klartext ist.
_EMBEDDED_SECRET = b"LogWatch-default-app-secret-v1-change-via-master-password"


class DecryptionError(Exception):
    pass


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=PBKDF2_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def _embedded_key(salt: bytes) -> bytes:
    # Auch der eingebettete Schlüssel wird mit Salt abgeleitet, damit die Tokens variieren.
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=PBKDF2_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(_EMBEDDED_SECRET))


def encrypt_bytes(plaintext: bytes, password: Optional[str] = None) -> bytes:
    salt = os.urandom(SALT_LEN)
    if password:
        mode = MODE_PASSWORD
        key = _derive_key(password, salt)
    else:
        mode = MODE_EMBEDDED
        key = _embedded_key(salt)
    token = Fernet(key).encrypt(plaintext)
    return MAGIC + bytes([VERSION, mode]) + salt + token


def decrypt_bytes(blob: bytes, password: Optional[str] = None) -> bytes:
    header_len = len(MAGIC) + 2 + SALT_LEN
    if len(blob) < header_len or blob[: len(MAGIC)] != MAGIC:
        raise DecryptionError("Unbekanntes oder beschädigtes Dateiformat.")
    mode = blob[len(MAGIC) + 1]
    salt = blob[len(MAGIC) + 2: len(MAGIC) + 2 + SALT_LEN]
    token = blob[header_len:]
    if mode == MODE_PASSWORD:
        if not password:
            raise DecryptionError("Diese Datei ist mit einem Master-Passwort geschützt.")
        key = _derive_key(password, salt)
    else:
        key = _embedded_key(salt)
    try:
        return Fernet(key).decrypt(token)
    except InvalidToken as exc:
        raise DecryptionError("Entschlüsselung fehlgeschlagen (falsches Passwort oder beschädigte Datei).") from exc


def is_password_protected(blob: bytes) -> bool:
    header_len = len(MAGIC) + 2 + SALT_LEN
    if len(blob) < header_len or blob[: len(MAGIC)] != MAGIC:
        return False
    return blob[len(MAGIC) + 1] == MODE_PASSWORD
