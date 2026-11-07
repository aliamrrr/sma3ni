"""Small SQL helpers shared by the API and the workers (psycopg 3, dict rows)."""
from __future__ import annotations

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

PIPELINE_STATUSES = ("RECEIVED", "TRANSCRIBING", "TRANSCRIBED")
OPEN_STATUSES = ("ROUTED", "IN_PROGRESS")
AGENT_TRANSITIONS = {
    "ROUTED": {"IN_PROGRESS", "RESOLVED", "REJECTED"},
    "IN_PROGRESS": {"RESOLVED", "REJECTED"},
    "FAILED": {"IN_PROGRESS", "RESOLVED", "REJECTED"},
}


async def open_pool(dsn: str, max_size: int, name: str) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(
        dsn,
        min_size=1,
        max_size=max_size,
        kwargs={"row_factory": dict_row, "application_name": name},
        open=False,
    )
    await pool.open(wait=True, timeout=60)
    return pool


async def set_status(conn: AsyncConnection, request_id, to_status: str, *, actor: str,
                     expected: tuple[str, ...] | set[str], note: str | None = None) -> str | None:
    """Atomic compare-and-set on status + history row. Returns previous status, or None if not applied."""
    cur = await conn.execute(
        """
        WITH prev AS (SELECT id, status FROM requests WHERE id = %(id)s FOR UPDATE)
        UPDATE requests r SET status = %(to)s, updated_at = now()
        FROM prev
        WHERE r.id = prev.id AND prev.status = ANY(%(expected)s)
        RETURNING prev.status AS from_status
        """,
        {"id": request_id, "to": to_status, "expected": list(expected)},
    )
    row = await cur.fetchone()
    if row is None:
        return None
    await conn.execute(
        "INSERT INTO request_history (request_id, from_status, to_status, actor, note) VALUES (%s, %s, %s, %s, %s)",
        (request_id, row["from_status"], to_status, actor, note),
    )
    return row["from_status"]


async def is_processed(conn: AsyncConnection, consumer: str, event_id: str) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM processed_events WHERE consumer = %s AND event_id = %s", (consumer, event_id)
    )
    return await cur.fetchone() is not None


async def mark_processed(conn: AsyncConnection, consumer: str, event_id: str) -> bool:
    """False if another delivery already applied this event (caller must roll back)."""
    cur = await conn.execute(
        "INSERT INTO processed_events (consumer, event_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING 1",
        (consumer, event_id),
    )
    return await cur.fetchone() is not None


async def audit(conn: AsyncConnection, api_key_id, action: str, request_id=None) -> None:
    await conn.execute(
        "INSERT INTO audit_log (api_key_id, action, request_id) VALUES (%s, %s, %s)",
        (api_key_id, action, request_id),
    )
