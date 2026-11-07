"""Outbox relay: Postgres outbox -> NATS JetStream.

Wakes on LISTEN/NOTIFY (low latency) with a polling fallback. Several replicas
can run safely thanks to FOR UPDATE SKIP LOCKED. If NATS or Postgres goes away
the process crashes and Docker restarts it: nothing is lost, unpublished rows
stay in the outbox.
"""
from __future__ import annotations

import asyncio
import json
import logging

import psycopg
from psycopg.rows import dict_row

from . import events
from .config import get_settings
from .logs import setup_logging, stop_event

log = logging.getLogger("sma3ni.relay")
BATCH = 200
POLL_INTERVAL_S = 1.0


async def publish_batch(conn: psycopg.AsyncConnection, js) -> int:
    async with conn.transaction():
        cur = await conn.execute(
            "SELECT id, event_id, subject, payload FROM outbox WHERE published_at IS NULL "
            "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED",
            (BATCH,),
        )
        rows = await cur.fetchall()
        for row in rows:
            body = json.dumps(row["payload"], ensure_ascii=False).encode("utf-8")
            # Nats-Msg-Id: if we crash after publish but before commit, the re-publish is dropped by JetStream.
            await js.publish(row["subject"], body, headers={"Nats-Msg-Id": str(row["event_id"])}, timeout=5)
        if rows:
            await conn.execute("UPDATE outbox SET published_at = now() WHERE id = ANY(%s)",
                               ([r["id"] for r in rows],))
    return len(rows)


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    stop = stop_event()

    nc = await events.connect_nats(settings, "sma3ni-relay")
    js = nc.jetstream()
    await events.ensure_stream(js)

    conn = await psycopg.AsyncConnection.connect(settings.database_url, row_factory=dict_row,
                                                 application_name="sma3ni-relay")
    listener = await psycopg.AsyncConnection.connect(settings.database_url, autocommit=True,
                                                     application_name="sma3ni-relay-listen")
    await listener.execute("LISTEN outbox")
    log.info("relay started")

    try:
        while not stop.is_set():
            published = await publish_batch(conn, js)
            if published:
                log.info("published %d events", published)
            if published < BATCH:
                # Sleep until a NOTIFY arrives or the poll interval elapses.
                async for _ in listener.notifies(timeout=POLL_INTERVAL_S, stop_after=1):
                    pass
    finally:
        await nc.drain()
        await conn.close()
        await listener.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
