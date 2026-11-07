"""ASR worker: request.received -> transcript -> request.transcribed.

One transcription at a time per container. On a GPU instance (ASR_DEVICE=cuda)
one worker per GPU; on CPU, scale with `docker compose up -d --scale asr-worker=N`
(N x ~10 GB RAM) and set ASR_THREADS = cores / N.
"""
from __future__ import annotations

import asyncio

from .. import events, repo
from ..engines.asr import build_asr_engine
from ..errors import PermanentError
from ..storage import AudioNotFound, build_store
from .base import BaseWorker, run_worker


class AsrWorker(BaseWorker):
    consumer = "asr"
    event_type = events.REQUEST_RECEIVED
    ack_wait_s = 90
    max_attempts = 4

    def load(self) -> None:
        self.engine = build_asr_engine(self.settings)
        self.store = build_store(self.settings)

    async def handle(self, event: events.Event) -> None:
        rid = event.request_id
        async with self.pool.connection() as conn, conn.transaction():
            if await repo.is_processed(conn, self.consumer, event.id):
                return
            cur = await conn.execute("SELECT audio_key FROM requests WHERE id = %s", (rid,))
            row = await cur.fetchone()
            if row is None:
                return  # unknown request: nothing to do
            prev = await repo.set_status(conn, rid, "TRANSCRIBING", actor="worker:asr",
                                         expected=("RECEIVED", "TRANSCRIBING"))
            if prev is None:
                return  # already transcribed or handled by a human
            await conn.execute("UPDATE requests SET attempts = attempts + 1 WHERE id = %s", (rid,))

        # Heavy part runs outside any DB transaction (minutes on CPU).
        try:
            data = await asyncio.to_thread(self.store.get, row["audio_key"])
        except AudioNotFound:
            raise PermanentError("audio missing from storage") from None
        result = await asyncio.to_thread(self.engine.transcribe, data)

        async with self.pool.connection() as conn, conn.transaction():
            if not await repo.mark_processed(conn, self.consumer, event.id):
                return
            await conn.execute(
                "UPDATE requests SET transcript = %s, audio_seconds = %s, asr_model = %s WHERE id = %s",
                (result.text, result.audio_seconds, result.model, rid),
            )
            if await repo.set_status(conn, rid, "TRANSCRIBED", actor="worker:asr", expected=("TRANSCRIBING",)) is None:
                raise RuntimeError("status changed during transcription")  # rolls back, will retry/skip
            await events.emit(conn, events.REQUEST_TRANSCRIBED, rid, {"audio_seconds": result.audio_seconds})


def main() -> None:
    run_worker(AsrWorker)


if __name__ == "__main__":
    main()
