"""HTTP API. Stateless: scale with API_WORKERS or more replicas behind Caddy.

The API never runs models. It stores the audio, writes the request row and a
`request.received` event in one transaction, and answers 202 in milliseconds.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import events, repo
from ..audio_sniff import MEDIA_TYPES, sniff_audio
from ..config import get_settings
from ..crypto import ContactCipher
from ..ids import is_tracking_code, new_tracking_code
from ..logs import setup_logging
from ..storage import AudioNotFound, StorageError, build_store
from .auth import Principal, get_principal, require_scope

log = logging.getLogger("sma3ni.api")

# What the citizen sees (FR / Darija). FAILED is shown as "waiting for an agent":
# failed requests fall back to the triage desk, a human takes over.
CITIZEN_STATUS = {
    "RECEIVED": ("Demande reçue", "توصلنا بالطلب ديالك"),
    "TRANSCRIBING": ("Analyse en cours", "كنحللو الطلب ديالك"),
    "TRANSCRIBED": ("Analyse en cours", "كنحللو الطلب ديالك"),
    "ROUTED": ("Transmise au service concerné", "تصيفط للمصلحة المعنية"),
    "IN_PROGRESS": ("En cours de traitement", "المصلحة كتخدم على الطلب ديالك"),
    "RESOLVED": ("Traitée", "الطلب ديالك تعالج"),
    "REJECTED": ("Clôturée", "الطلب ديالك تسد"),
    "FAILED": ("En attente d'un agent", "غادي يشوفو موظف"),
}


# Timeline shown to the citizen: received -> analysing -> routed -> in_progress -> done
STAGES = {"RECEIVED": "received", "TRANSCRIBING": "analysing", "TRANSCRIBED": "analysing", "ROUTED": "routed",
          "IN_PROGRESS": "in_progress", "RESOLVED": "done", "REJECTED": "done", "FAILED": "routed"}
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    app.state.settings = settings
    app.state.pool = await repo.open_pool(settings.database_url, settings.db_pool_size, "sma3ni-api")
    app.state.storage = build_store(settings)
    app.state.cipher = ContactCipher(settings.contact_enc_key)
    # Dedicated key for client fingerprints, derived so the encryption key itself is never reused.
    app.state.fingerprint_key = hashlib.sha256(
        b"sma3ni-fingerprint|" + (settings.contact_enc_key or "").encode()).digest()
    async with app.state.pool.connection() as conn:
        row = await (await conn.execute(
            "SELECT id FROM api_keys WHERE name = 'system:public-web' ORDER BY created_at LIMIT 1")).fetchone()
    if row is None:
        raise RuntimeError("system:public-web key missing, run migrations")
    app.state.public_key_id = row["id"]
    try:
        yield
    finally:
        await app.state.pool.close()


def create_app() -> FastAPI:
    # Read directly: settings need DATABASE_URL, which is not required to import the module.
    docs = os.environ.get("EXPOSE_DOCS", "false").strip().lower() in {"1", "true", "yes", "on"}
    return FastAPI(
        title="Sma3ni API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )


app = create_app()


# --------------------------------------------------------------------------- web pages
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
async def citizen_page() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/agent", include_in_schema=False)
async def agent_page() -> FileResponse:
    return FileResponse(WEB_DIR / "agent.html")


@app.get("/v1/me")
async def me(principal: Principal = Depends(get_principal)) -> dict:
    return {"name": principal.name, "scopes": principal.scopes, "service_code": principal.service_code}


@app.get("/v1/services")
async def services(request: Request, principal: Principal = Depends(require_scope("agent"))) -> list[dict]:
    async with request.app.state.pool.connection() as conn:
        cur = await conn.execute("SELECT code, name_fr, name_ar FROM services ORDER BY name_fr")
        return await cur.fetchall()


# --------------------------------------------------------------------------- health
@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return {"ok": True}


@app.get("/readyz", include_in_schema=False)
async def readyz(request: Request) -> dict:
    try:
        async with request.app.state.pool.connection(timeout=2) as conn:
            await conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"ok": True}


# --------------------------------------------------------------------------- intake
@app.post("/v1/requests", status_code=202)
async def create_request(
    request: Request,
    response: Response,
    audio: UploadFile = File(...),
    channel: Literal["web", "whatsapp", "call_center", "kiosk", "mobile"] = Form(...),
    contact: str | None = Form(None, max_length=64),
    region: str | None = Form(None, max_length=64),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=128),
    principal: Principal = Depends(require_scope("intake")),
) -> dict:
    """Channel gateways (WhatsApp, call centre, kiosks) authenticate with an intake key."""
    return await _ingest(request, response, audio, channel, contact, region, idempotency_key,
                         key_id=principal.key_id, actor=f"key:{principal.name}")


@app.post("/v1/public/requests", status_code=202)
async def create_public_request(
    request: Request,
    response: Response,
    audio: UploadFile = File(...),
    consent: bool = Form(...),
    contact: str | None = Form(None, max_length=64),
    region: str | None = Form(None, max_length=64),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=128),
) -> dict:
    """The citizen web page. No key; explicit consent and a per-IP quota kept in Postgres
    (so it holds across API workers and replicas)."""
    if not consent:
        raise HTTPException(status_code=422, detail="consent required")
    settings = request.app.state.settings
    fingerprint = _client_fingerprint(request)
    # All web submissions share one system key: scope idempotency keys per client so one
    # citizen can never get another citizen's tracking code by replaying a key.
    if idempotency_key:
        idempotency_key = f"{fingerprint}:{idempotency_key}"[:128]
        existing = await _find_idempotent(request.app.state.pool, request.app.state.public_key_id, idempotency_key)
        if existing:  # a retry must not consume quota
            response.status_code = 200
            return existing
    async with request.app.state.pool.connection() as conn:
        cur = await conn.execute(
            "SELECT count(*) AS n FROM requests "
            "WHERE client_fingerprint = %s AND created_at > now() - interval '1 hour'",
            (fingerprint,),
        )
        if (await cur.fetchone())["n"] >= settings.public_hourly_limit:
            raise HTTPException(status_code=429, detail="too many requests, try again later",
                                headers={"Retry-After": "900"})
    return await _ingest(request, response, audio, "web", contact, region, idempotency_key,
                         key_id=request.app.state.public_key_id, actor="web", fingerprint=fingerprint)


def _client_fingerprint(request: Request) -> str:
    # Keyed hash: rate limiting without storing raw IP addresses.
    ip = request.client.host if request.client else "unknown"
    return hmac.new(request.app.state.fingerprint_key, ip.encode(), hashlib.sha256).hexdigest()[:32]


async def _ingest(request: Request, response: Response, audio: UploadFile, channel: str,
                  contact: str | None, region: str | None, idempotency_key: str | None, *,
                  key_id: UUID, actor: str, fingerprint: str | None = None) -> dict:
    settings = request.app.state.settings
    pool = request.app.state.pool

    if idempotency_key:
        existing = await _find_idempotent(pool, key_id, idempotency_key)
        if existing:
            response.status_code = 200
            return existing

    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await audio.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"audio larger than {settings.max_upload_mb} MB")
    if len(data) < 256:
        raise HTTPException(status_code=422, detail="audio too small")
    fmt = sniff_audio(data[:64])
    if fmt is None:
        raise HTTPException(status_code=415, detail="unsupported audio format")

    request_id = uuid.uuid4()
    tracking_code = new_tracking_code()
    now = datetime.now(UTC)
    audio_key = f"{now:%Y/%m/%d}/{request_id}.{fmt}"
    contact_enc = request.app.state.cipher.encrypt(contact.strip()) if contact and contact.strip() else None

    # Blob first, row second: a crash in between leaves an orphan file (harmless),
    # never a row pointing to missing audio.
    try:
        await asyncio.to_thread(request.app.state.storage.put, audio_key, data, MEDIA_TYPES[fmt])
    except Exception as exc:  # noqa: BLE001 - any backend failure is a 503 for the client
        log.exception("audio storage failed", extra={"request_id": str(request_id)})
        raise HTTPException(status_code=503, detail="storage unavailable, retry later",
                            headers={"Retry-After": "30"}) from exc

    try:
        async with pool.connection() as conn, conn.transaction():
            await conn.execute(
                """
                INSERT INTO requests (id, tracking_code, api_key_id, idempotency_key, channel, status, region,
                                      citizen_contact_enc, audio_key, audio_format, audio_bytes, audio_sha256,
                                      client_fingerprint)
                VALUES (%s, %s, %s, %s, %s, 'RECEIVED', %s, %s, %s, %s, %s, %s, %s)
                """,
                (request_id, tracking_code, key_id, idempotency_key, channel, region, contact_enc,
                 audio_key, fmt, len(data), hashlib.sha256(data).hexdigest(), fingerprint),
            )
            await conn.execute(
                "INSERT INTO request_history (request_id, from_status, to_status, actor) "
                "VALUES (%s, NULL, 'RECEIVED', %s)",
                (request_id, actor),
            )
            await events.emit(conn, events.REQUEST_RECEIVED, request_id, {"channel": channel, "format": fmt})
    except psycopg.errors.UniqueViolation:
        await asyncio.to_thread(request.app.state.storage.delete, audio_key)
        existing = await _find_idempotent(pool, key_id, idempotency_key) if idempotency_key else None
        if existing:
            response.status_code = 200
            return existing
        raise HTTPException(status_code=409, detail="conflict, retry") from None

    log.info("request received", extra={"request_id": str(request_id)})
    return {"id": str(request_id), "tracking_code": tracking_code, "status": "RECEIVED",
            "track_url": f"/v1/track/{tracking_code}"}


async def _find_idempotent(pool, key_id: UUID, idem_key: str) -> dict | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, tracking_code, status FROM requests WHERE api_key_id = %s AND idempotency_key = %s",
            (key_id, idem_key),
        )
        row = await cur.fetchone()
    if not row:
        return None
    return {"id": str(row["id"]), "tracking_code": row["tracking_code"], "status": row["status"],
            "track_url": f"/v1/track/{row['tracking_code']}"}


# --------------------------------------------------------------------------- citizen tracking (public)
@app.get("/v1/track/{tracking_code}")
async def track(tracking_code: str, request: Request) -> dict:
    if not is_tracking_code(tracking_code):
        raise HTTPException(status_code=404, detail="not found")
    async with request.app.state.pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT r.status, r.created_at, r.updated_at, s.name_fr, s.name_ar
            FROM requests r LEFT JOIN services s ON s.code = r.service_code
            WHERE r.tracking_code = %s
            """,
            (tracking_code,),
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    label_fr, label_ar = CITIZEN_STATUS[row["status"]]
    # No transcript, no contact, no internal ids: the code alone must not leak personal data.
    return {
        "tracking_code": tracking_code,
        "stage": STAGES[row["status"]],
        "status": label_fr,
        "status_ar": label_ar,
        "service": row["name_fr"] if row["status"] not in repo.PIPELINE_STATUSES else None,
        "service_ar": row["name_ar"] if row["status"] not in repo.PIPELINE_STATUSES else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# --------------------------------------------------------------------------- agents
_LIST_COLUMNS = """r.id, r.tracking_code, r.status, r.channel, r.region, r.category, r.service_code,
                   r.priority, r.needs_review, r.review_reasons, r.lang_family, r.audio_seconds,
                   left(r.transcript, 240) AS transcript_excerpt, r.created_at, r.updated_at"""


@app.get("/v1/requests")
async def list_requests(
    request: Request,
    status: str | None = Query(None, pattern="^[A-Z_]{4,20}$"),
    service: str | None = Query(None, max_length=64),
    needs_review: bool | None = None,
    before: datetime | None = Query(None, description="cursor: created_at of the last item"),
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(require_scope("agent")),
) -> dict:
    if principal.service_code and not principal.is_admin:
        service = principal.service_code
    clauses, params = [], []
    if status:
        clauses.append("r.status = %s"); params.append(status)
    if service:
        clauses.append("r.service_code = %s"); params.append(service)
    if needs_review is not None:
        clauses.append("r.needs_review = %s"); params.append(needs_review)
    if before:
        clauses.append("r.created_at < %s"); params.append(before)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    async with request.app.state.pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_LIST_COLUMNS} FROM requests r {where} "  # noqa: S608 - clauses are constants
            "ORDER BY r.created_at DESC, r.id DESC LIMIT %s",
            params,
        )
        items = await cur.fetchall()
    next_cursor = items[-1]["created_at"] if len(items) == limit else None
    return {"items": items, "next_before": next_cursor}


async def _load_request(conn, request_id: UUID, principal: Principal) -> dict:
    cur = await conn.execute("SELECT * FROM requests WHERE id = %s", (request_id,))
    row = await cur.fetchone()
    if not row or not principal.can_see_service(row["service_code"]):
        raise HTTPException(status_code=404, detail="not found")  # same answer: no existence oracle
    return row


@app.get("/v1/requests/{request_id}")
async def get_request(request_id: UUID, request: Request,
                      principal: Principal = Depends(require_scope("agent"))) -> dict:
    async with request.app.state.pool.connection() as conn:
        row = await _load_request(conn, request_id, principal)
        cur = await conn.execute(
            "SELECT from_status, to_status, actor, note, at FROM request_history WHERE request_id = %s ORDER BY at",
            (request_id,),
        )
        history = await cur.fetchall()
        await repo.audit(conn, principal.key_id, "request.read", request_id)
    contact = request.app.state.cipher.decrypt(row.pop("citizen_contact_enc"))
    for internal in ("api_key_id", "idempotency_key", "audio_key", "audio_sha256"):
        row.pop(internal, None)
    return {**row, "contact": contact, "history": history}


@app.get("/v1/requests/{request_id}/audio")
async def get_audio(request_id: UUID, request: Request,
                    principal: Principal = Depends(require_scope("agent"))) -> Response:
    async with request.app.state.pool.connection() as conn:
        row = await _load_request(conn, request_id, principal)
        if row["audio_purged_at"] or not row["audio_key"]:
            raise HTTPException(status_code=410, detail="audio purged (retention policy)")
        await repo.audit(conn, principal.key_id, "audio.read", request_id)
    try:
        data = await asyncio.to_thread(request.app.state.storage.get, row["audio_key"])
    except AudioNotFound:
        raise HTTPException(status_code=410, detail="audio purged (retention policy)") from None
    except StorageError as exc:
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    return Response(content=data, media_type=MEDIA_TYPES.get(row["audio_format"], "application/octet-stream"),
                    headers={"Cache-Control": "no-store", "Content-Disposition": "inline"})


class RequestUpdate(BaseModel):
    status: Literal["IN_PROGRESS", "RESOLVED", "REJECTED"] | None = None
    service_code: str | None = Field(None, max_length=64)
    note: str | None = Field(None, max_length=2000)


@app.patch("/v1/requests/{request_id}")
async def update_request(request_id: UUID, body: RequestUpdate, request: Request,
                         principal: Principal = Depends(require_scope("agent"))) -> dict:
    if body.status is None and body.service_code is None:
        raise HTTPException(status_code=422, detail="nothing to update")
    actor = f"key:{principal.name}"
    async with request.app.state.pool.connection() as conn, conn.transaction():
        row = await _load_request(conn, request_id, principal)
        if body.service_code and body.service_code != row["service_code"]:
            # Re-assignment: triage desk and unrestricted keys only.
            if principal.service_code not in (None, "triage") and not principal.is_admin:
                raise HTTPException(status_code=403, detail="only triage can reassign")
            if row["status"] in repo.PIPELINE_STATUSES:
                raise HTTPException(status_code=409, detail="request still being analysed")
            cur = await conn.execute("SELECT 1 FROM services WHERE code = %s", (body.service_code,))
            if not await cur.fetchone():
                raise HTTPException(status_code=422, detail="unknown service")
            await conn.execute(
                "UPDATE requests SET service_code = %s, needs_review = false, updated_at = now() WHERE id = %s",
                (body.service_code, request_id),
            )
            await conn.execute(
                "INSERT INTO request_history (request_id, from_status, to_status, actor, note) "
                "VALUES (%s, %s, %s, %s, %s)",
                (request_id, row["status"], row["status"], actor,
                 f"reassigned {row['service_code']} -> {body.service_code}"),
            )
        new_status = row["status"]
        if body.status and body.status != row["status"]:
            allowed = {s for s, targets in repo.AGENT_TRANSITIONS.items() if body.status in targets}
            prev = await repo.set_status(conn, request_id, body.status, actor=actor, expected=allowed, note=body.note)
            if prev is None:
                raise HTTPException(status_code=409, detail=f"cannot go from {row['status']} to {body.status}")
            new_status = body.status
        await events.emit(conn, events.REQUEST_STATUS_CHANGED, request_id,
                          {"status": new_status, "service_code": body.service_code or row["service_code"]})
    return {"id": str(request_id), "status": new_status}


# --------------------------------------------------------------------------- ops
@app.get("/v1/admin/stats")
async def stats(request: Request, principal: Principal = Depends(require_scope("admin"))) -> dict:
    async with request.app.state.pool.connection() as conn:
        by_status = await (await conn.execute(
            "SELECT status, count(*) AS n FROM requests GROUP BY status")).fetchall()
        backlog = await (await conn.execute(
            "SELECT count(*) AS n, min(created_at) AS oldest FROM outbox WHERE published_at IS NULL")).fetchone()
        review = await (await conn.execute(
            "SELECT count(*) AS n FROM requests WHERE needs_review AND status IN ('ROUTED','FAILED')")).fetchone()
        last_24h = await (await conn.execute(
            "SELECT count(*) AS n, avg(audio_seconds) AS avg_audio_s FROM requests "
            "WHERE created_at > now() - interval '24 hours'")).fetchone()
    return {"by_status": {r["status"]: r["n"] for r in by_status}, "outbox_pending": backlog,
            "needs_review": review["n"], "last_24h": last_24h}
