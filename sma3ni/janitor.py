"""Periodic housekeeping:
- delete audio (local volume or S3) older than AUDIO_RETENTION_DAYS (temporary storage, data minimisation)
- fail requests stuck in TRANSCRIBING (worker died mid-job) so triage picks them up
- trim the published outbox and the dedupe table
"""
from __future__ import annotations

import asyncio
import logging

from . import events, repo
from .config import get_settings
from .logs import setup_logging, stop_event
from .storage import AudioStore, StorageError, build_store

log = logging.getLogger("sma3ni.janitor")
STUCK_AFTER_MINUTES = 60


async def purge_audio(pool, store: AudioStore, days: int) -> int:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, audio_key FROM requests WHERE audio_key IS NOT NULL AND audio_purged_at IS NULL "
            "AND created_at < now() - make_interval(days => %s) LIMIT 1000",
            (days,),
        )
        rows = await cur.fetchall()
        purged = 0
        for row in rows:
            try:
                await asyncio.to_thread(store.delete, row["audio_key"])
            except StorageError:
                # Storage down: stop this pass, the next one retries. The S3 lifecycle rule
                # expires the object anyway, so retention holds even if the janitor lags.
                log.warning("audio purge interrupted, storage unavailable", exc_info=True)
                break
            await conn.execute("UPDATE requests SET audio_purged_at = now() WHERE id = %s", (row["id"],))
            await conn.commit()
            purged += 1
    return purged


async def fail_stuck(pool) -> int:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id FROM requests WHERE status = 'TRANSCRIBING' "
            "AND updated_at < now() - make_interval(mins => %s)",
            (STUCK_AFTER_MINUTES,),
        )
        ids = [r["id"] for r in await cur.fetchall()]
        await conn.commit()
    for rid in ids:
        async with pool.connection() as conn, conn.transaction():
            if await repo.set_status(conn, rid, "FAILED", actor="janitor", expected=("TRANSCRIBING",),
                                     note="stuck in transcription"):
                await conn.execute(
                    "UPDATE requests SET failure_reason = 'stuck', service_code = 'triage', needs_review = true "
                    "WHERE id = %s", (rid,))
                await events.emit(conn, events.REQUEST_FAILED, rid, {"stage": "janitor", "reason": "stuck"})
    return len(ids)


async def trim(pool) -> None:
    async with pool.connection() as conn:
        await conn.execute("DELETE FROM outbox WHERE published_at < now() - interval '7 days'")
        await conn.execute("DELETE FROM processed_events WHERE processed_at < now() - interval '30 days'")
        await conn.commit()


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    stop = stop_event()
    store = build_store(settings)
    pool = await repo.open_pool(settings.database_url, 2, "sma3ni-janitor")
    try:
        while not stop.is_set():
            purged = await purge_audio(pool, store, settings.audio_retention_days)
            stuck = await fail_stuck(pool)
            await trim(pool)
            log.info("janitor pass: %d audio purged, %d stuck failed", purged, stuck)
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.janitor_interval_s)
            except TimeoutError:
                pass
    finally:
        await pool.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
