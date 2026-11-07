"""Event envelope, outbox writes and NATS JetStream setup.

Flow: state change + outbox row in ONE Postgres transaction -> relay publishes
to JetStream with Nats-Msg-Id = event id (broker-side dedupe) -> consumers
record (consumer, event_id) in processed_events in the same transaction as
their own writes (consumer-side dedupe). Net effect: exactly-once processing
on top of at-least-once delivery.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

STREAM = "SMA3NI"
SUBJECT_PREFIX = "sma3ni"

REQUEST_RECEIVED = "request.received"
REQUEST_TRANSCRIBED = "request.transcribed"
REQUEST_ROUTED = "request.routed"
REQUEST_FAILED = "request.failed"
REQUEST_STATUS_CHANGED = "request.status_changed"


def subject(event_type: str) -> str:
    return f"{SUBJECT_PREFIX}.{event_type}"


@dataclass(frozen=True)
class Event:
    type: str
    request_id: str
    data: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_bytes(cls, raw: bytes) -> Event:
        body = json.loads(raw)
        return cls(
            type=body["type"],
            request_id=str(body["request_id"]),
            data=body.get("data") or {},
            id=str(body["id"]),
            occurred_at=body["occurred_at"],
            version=int(body.get("version", 1)),
        )


async def emit(conn, event_type: str, request_id, data: dict[str, Any] | None = None) -> Event:
    """Insert an event in the outbox. Must run inside the caller's transaction."""
    from psycopg.types.json import Jsonb

    event = Event(type=event_type, request_id=str(request_id), data=data or {})
    await conn.execute(
        "INSERT INTO outbox (event_id, subject, payload) VALUES (%s, %s, %s)",
        (event.id, subject(event_type), Jsonb(event.to_dict())),
    )
    return event


async def connect_nats(settings, name: str):
    import nats

    return await nats.connect(
        settings.nats_url,
        user=settings.nats_user,
        password=settings.nats_password,
        name=name,
        max_reconnect_attempts=-1,
        reconnect_time_wait=2,
    )


async def ensure_stream(js) -> None:
    from nats.js.api import RetentionPolicy, StorageType, StreamConfig
    from nats.js.errors import BadRequestError, NotFoundError

    config = StreamConfig(
        name=STREAM,
        subjects=[f"{SUBJECT_PREFIX}.>"],
        storage=StorageType.FILE,
        retention=RetentionPolicy.LIMITS,  # several consumer groups can replay the same events
        max_age=7 * 24 * 3600,
        duplicate_window=120,
        num_replicas=1,  # 3 when running a NATS cluster
    )
    try:
        await js.stream_info(STREAM)
        await js.update_stream(config)
    except NotFoundError:
        try:
            await js.add_stream(config)
        except BadRequestError:
            pass  # created concurrently by another service
