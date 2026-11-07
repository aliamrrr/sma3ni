"""Application-level encryption of citizen contact details (phone numbers).

A DB dump or backup leak does not expose contacts without CONTACT_ENC_KEY.
Rotation: MultiFernet accepts "new_key,old_key"; encrypt with the first, decrypt with any.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class ContactCipher:
    def __init__(self, keys: str | None) -> None:
        if not keys:
            raise RuntimeError("CONTACT_ENC_KEY is required")
        self._fernet = MultiFernet([Fernet(k.strip()) for k in keys.split(",") if k.strip()])

    def encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode("utf-8"))

    def decrypt(self, token: bytes | None) -> str | None:
        if not token:
            return None
        try:
            return self._fernet.decrypt(bytes(token)).decode("utf-8")
        except InvalidToken:
            return None
