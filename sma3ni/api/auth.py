"""Bearer API keys with scopes.

intake : channel gateways (WhatsApp Business gateway, web form backend, call centre)
agent  : public-service agents; optionally restricted to one service
admin  : operations
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)
KEY_PREFIX = "sk_sma3ni_"


def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(raw: str) -> bytes:
    # Keys carry 256 bits of entropy, so a fast hash is fine (no brute-force risk).
    return hashlib.sha256(raw.encode("utf-8")).digest()


@dataclass(frozen=True)
class Principal:
    key_id: UUID
    name: str
    scopes: tuple[str, ...]
    service_code: str | None

    @property
    def is_admin(self) -> bool:
        return "admin" in self.scopes

    def can_see_service(self, service_code: str | None) -> bool:
        return self.is_admin or self.service_code is None or self.service_code == service_code


_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="invalid or missing API key",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_principal(request: Request,
                        creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    if creds is None or not creds.credentials.startswith(KEY_PREFIX) or len(creds.credentials) > 128:
        raise _UNAUTHORIZED
    async with request.app.state.pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, name, scopes, service_code, last_used_at FROM api_keys "
            "WHERE key_hash = %s AND revoked_at IS NULL",
            (hash_key(creds.credentials),),
        )
        row = await cur.fetchone()
        if row is None:
            raise _UNAUTHORIZED
        last = row["last_used_at"]
        if last is None or last < datetime.now(UTC) - timedelta(minutes=5):
            await conn.execute("UPDATE api_keys SET last_used_at = now() WHERE id = %s", (row["id"],))
    return Principal(row["id"], row["name"], tuple(row["scopes"]), row["service_code"])


def require_scope(scope: str):
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if scope not in principal.scopes and not principal.is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"scope '{scope}' required")
        return principal

    return dependency
