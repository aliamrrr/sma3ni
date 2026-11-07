-- Sma3ni core schema. Applied once by `python -m sma3ni.migrate` (advisory-locked).

CREATE TABLE services (
    code        text PRIMARY KEY,
    name_fr     text NOT NULL,
    name_ar     text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- API keys are stored as SHA-256 hashes only; the raw key is shown once at creation.
CREATE TABLE api_keys (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text NOT NULL,
    key_hash      bytea NOT NULL UNIQUE,
    scopes        text[] NOT NULL CHECK (scopes <@ ARRAY['intake', 'agent', 'admin']::text[] AND cardinality(scopes) > 0),
    service_code  text REFERENCES services(code),   -- agent keys can be restricted to one service
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_used_at  timestamptz,
    revoked_at    timestamptz
);

-- Keyword routing, editable at runtime (the nlp-worker reloads it every minute).
CREATE TABLE routing_rules (
    id            serial PRIMARY KEY,
    category      text NOT NULL UNIQUE,
    service_code  text NOT NULL REFERENCES services(code),
    keywords      text[] NOT NULL,
    priority      smallint NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 3),  -- 1 = urgent
    enabled       boolean NOT NULL DEFAULT true,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE requests (
    id                   uuid PRIMARY KEY,
    tracking_code        text NOT NULL UNIQUE,
    api_key_id           uuid NOT NULL REFERENCES api_keys(id),
    idempotency_key      text,
    channel              text NOT NULL CHECK (channel IN ('web', 'whatsapp', 'call_center', 'kiosk', 'mobile')),
    status               text NOT NULL CHECK (status IN (
                             'RECEIVED', 'TRANSCRIBING', 'TRANSCRIBED', 'ROUTED',
                             'IN_PROGRESS', 'RESOLVED', 'REJECTED', 'FAILED')),
    region               text,
    citizen_contact_enc  bytea,             -- Fernet-encrypted at application level (Loi 09-08)
    audio_key            text,
    audio_format         text,
    audio_bytes          integer,
    audio_sha256         text,
    audio_seconds        real,
    audio_purged_at      timestamptz,
    transcript           text,
    asr_model            text,
    lang_label           text,
    lang_confidence      real,
    lang_family          text,
    category             text,
    service_code         text REFERENCES services(code),
    priority             smallint,
    needs_review         boolean NOT NULL DEFAULT false,
    review_reasons       text[],
    attempts             integer NOT NULL DEFAULT 0,
    failure_reason       text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (api_key_id, idempotency_key)
);
CREATE INDEX requests_queue_idx     ON requests (service_code, status, priority, created_at DESC);
CREATE INDEX requests_status_idx    ON requests (status, updated_at);
CREATE INDEX requests_created_idx   ON requests (created_at DESC, id DESC);
CREATE INDEX requests_retention_idx ON requests (created_at)
    WHERE audio_key IS NOT NULL AND audio_purged_at IS NULL;

CREATE TABLE request_history (
    id           bigserial PRIMARY KEY,
    request_id   uuid NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    from_status  text,
    to_status    text NOT NULL,
    actor        text NOT NULL,
    note         text,
    at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX request_history_req_idx ON request_history (request_id, at);

-- Who looked at which citizen data (CNDP accountability).
CREATE TABLE audit_log (
    id          bigserial PRIMARY KEY,
    api_key_id  uuid REFERENCES api_keys(id),
    action      text NOT NULL,
    request_id  uuid,
    at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_req_idx ON audit_log (request_id, at);

-- Transactional outbox: events are written in the same transaction as the state
-- change, then published to NATS JetStream by the relay. No dual-write problem.
CREATE TABLE outbox (
    id            bigserial PRIMARY KEY,
    event_id      uuid NOT NULL UNIQUE,
    subject       text NOT NULL,
    payload       jsonb NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    published_at  timestamptz
);
CREATE INDEX outbox_pending_idx ON outbox (id) WHERE published_at IS NULL;

CREATE FUNCTION outbox_notify() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('outbox', '');
    RETURN NULL;
END
$$;
CREATE TRIGGER outbox_notify AFTER INSERT ON outbox
    FOR EACH STATEMENT EXECUTE FUNCTION outbox_notify();

-- Consumer-side idempotency (inbox): one row per (consumer, event) actually applied.
CREATE TABLE processed_events (
    consumer      text NOT NULL,
    event_id      uuid NOT NULL,
    processed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, event_id)
);
