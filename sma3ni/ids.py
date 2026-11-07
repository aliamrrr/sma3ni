"""Citizen-facing tracking codes: short, unambiguous, unguessable (31^10 ~ 8e14)."""
from __future__ import annotations

import re
import secrets

_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no 0/O, 1/I
TRACKING_RE = re.compile(r"^SM-[2-9A-HJ-NP-Z]{5}-[2-9A-HJ-NP-Z]{5}$")


def new_tracking_code() -> str:
    chars = "".join(secrets.choice(_ALPHABET) for _ in range(10))
    return f"SM-{chars[:5]}-{chars[5:]}"


def is_tracking_code(value: str) -> bool:
    return bool(TRACKING_RE.match(value))
