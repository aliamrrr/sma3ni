"""JetStream pull-consumer loop shared by all workers.

- durable consumer per worker type: replicas share the work (competing consumers)
- explicit ack; long jobs send in_progress() so the ack deadline keeps moving
- transient errors: nak with backoff; permanent errors or last attempt: request
  marked FAILED and handed to the triage desk (a human always gets it)
- idempotency is enforced by processed_events (see events.py)
"""
from __future__ import annotations

import asyncio
import logging
import time

from .. import events, repo
from ..config import Settings, get_settings
from ..errors import PermanentError
from ..logs import setup_logging, stop_event

log = logging.getLogger("sma3ni.worker")


class BaseWorker:
    consumer: str = ""
    event_type: str = ""
    ack_wait_s: float = 60
    max_attempts: int = 5
    backoff_s: tuple[float, ...] = (5, 30, 120, 600)
    pool_size: int = 3

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pool = None

    # -- to implement -------------------------------------------------------
    def load(self) -> None:
        """Blocking setup (model loading). Runs in a thread before consuming."""

    async def handle(self, event: events.Event) -> None:
        raise NotImplementedError

    # -- machinery ----------------------------------------------------------
    async def fail(self, event: events.Event, reason: str) -> None:
        async with self.pool.connection() as conn, conn.transaction():
            prev = await repo.set_status(conn, event.request_id, "FAILED", actor=f"worker:{self.consumer}",
                                         expected=repo.PIPELINE_STATUSES, note=reason[:500])
            if prev is None:
                return  # already moved on (e.g. processed by another delivery)
            await conn.execute(
                "UPDATE requests SET failure_reason = %s, service_code = COALESCE(service_code, 'triage'), "
                "needs_review = true WHERE id = %s",
                (reason[:500], event.request_id),
            )
            await events.emit(conn, events.REQUEST_FAILED, event.request_id,
                              {"stage": self.consumer, "reason": reason[:200]})
        log.warning("request failed: %s", reason[:200],
                    extra={"request_id": event.request_id, "consumer": self.consumer})

    async def _keepalive(self, msg) -> None:
        while True:
            await asyncio.sleep(self.ack_wait_s / 3)
            await msg.in_progress()

    async def _process(self, msg) -> None:
        try:
            event = events.Event.from_bytes(msg.data)
        except Exception:  # noqa: BLE001
            log.error("malformed message, dropping", extra={"consumer": self.consumer})
            await msg.term()
            return

        attempt = msg.metadata.num_delivered
        ctx = {"request_id": event.request_id, "event_id": event.id, "consumer": self.consumer}
        if attempt > self.max_attempts:  # previous attempts crashed the process (OOM...)
            await self.fail(event, f"gave up after {attempt - 1} attempts")
            await msg.ack()
            return

        keepalive = asyncio.create_task(self._keepalive(msg))
        started = time.monotonic()
        try:
            await self.handle(event)
        except PermanentError as exc:
            keepalive.cancel()
            await self.fail(event, str(exc))
            await msg.ack()
        except Exception as exc:  # noqa: BLE001
            keepalive.cancel()
            log.exception("attempt %d failed", attempt, extra=ctx)
            if attempt >= self.max_attempts:
                await self.fail(event, f"{type(exc).__name__}: {exc}")
                await msg.ack()
            else:
                await msg.nak(delay=self.backoff_s[min(attempt - 1, len(self.backoff_s) - 1)])
        else:
            keepalive.cancel()
            await msg.ack()
            log.info("processed", extra={**ctx, "duration_s": round(time.monotonic() - started, 2)})

    async def run(self) -> None:
        from nats.errors import TimeoutError as NatsTimeout
        from nats.js.api import AckPolicy, ConsumerConfig

        setup_logging(self.settings.log_level)
        stop = stop_event()
        log.info("loading %s", self.consumer)
        await asyncio.to_thread(self.load)

        self.pool = await repo.open_pool(self.settings.database_url, self.pool_size, f"sma3ni-{self.consumer}")
        nc = await events.connect_nats(self.settings, f"sma3ni-{self.consumer}")
        js = nc.jetstream()
        await events.ensure_stream(js)
        sub = await js.pull_subscribe(
            events.subject(self.event_type),
            durable=self.consumer,
            stream=events.STREAM,
            config=ConsumerConfig(
                ack_policy=AckPolicy.EXPLICIT,
                ack_wait=self.ack_wait_s,
                max_deliver=self.max_attempts + 1,
                max_ack_pending=1000,
            ),
        )
        log.info("consuming %s", events.subject(self.event_type), extra={"consumer": self.consumer})
        try:
            while not stop.is_set():
                try:
                    msgs = await sub.fetch(1, timeout=5)
                except NatsTimeout:
                    continue
                for msg in msgs:
                    await self._process(msg)
        finally:
            await nc.drain()
            await self.pool.close()


def run_worker(cls: type[BaseWorker]) -> None:
    asyncio.run(cls(get_settings()).run())
