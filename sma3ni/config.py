"""Settings read from the environment. Every secret also accepts NAME_FILE (Docker secrets)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _secret(name: str, default: str | None = None) -> str | None:
    path = os.environ.get(f"{name}_FILE")
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    db_pool_size: int
    nats_url: str
    nats_user: str | None
    nats_password: str | None

    storage_backend: str  # "local" | "s3"
    storage_dir: str
    s3_bucket: str | None
    s3_prefix: str
    s3_region: str | None
    s3_endpoint_url: str | None  # S3-compatible stores (MinIO...) only; empty on AWS
    s3_sse: str  # "aws:kms" | "AES256" | "" (no header, rely on bucket default)
    s3_kms_key_id: str | None

    contact_enc_key: str | None
    max_upload_mb: int
    max_audio_seconds: int
    audio_retention_days: int
    expose_docs: bool
    public_hourly_limit: int

    asr_engine: str  # "voxtral" | "fake"
    asr_model_id: str
    asr_revision: str | None
    asr_dtype: str
    asr_device: str  # "cpu" or "cuda" (AWS GPU instance)
    asr_threads: int
    fake_transcript: str

    lid_engine: str  # "lidstral" | "fake"
    lid_model_id: str
    lid_revision: str | None
    lid_min_confidence: float

    hf_token: str | None
    janitor_interval_s: int
    log_level: str


@lru_cache
def get_settings() -> Settings:
    db_url = _secret("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is required")
    return Settings(
        database_url=db_url,
        db_pool_size=_int("DB_POOL_SIZE", 10),
        nats_url=os.environ.get("NATS_URL", "nats://nats:4222"),
        nats_user=os.environ.get("NATS_USER") or None,
        nats_password=_secret("NATS_PASSWORD") or None,
        storage_backend=os.environ.get("STORAGE_BACKEND", "local").strip().lower(),
        storage_dir=os.environ.get("STORAGE_DIR", "/data/audio"),
        s3_bucket=os.environ.get("S3_BUCKET") or None,
        s3_prefix=os.environ.get("S3_PREFIX", "audio"),
        s3_region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or None,
        s3_endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
        s3_sse=os.environ.get("S3_SSE", "aws:kms"),
        s3_kms_key_id=os.environ.get("S3_KMS_KEY_ID") or None,
        contact_enc_key=_secret("CONTACT_ENC_KEY") or None,
        max_upload_mb=_int("MAX_UPLOAD_MB", 10),
        max_audio_seconds=_int("MAX_AUDIO_SECONDS", 180),
        audio_retention_days=_int("AUDIO_RETENTION_DAYS", 7),
        expose_docs=_bool("EXPOSE_DOCS", False),
        public_hourly_limit=_int("PUBLIC_HOURLY_LIMIT", 5),
        asr_engine=os.environ.get("ASR_ENGINE", "voxtral"),
        asr_model_id=os.environ.get("ASR_MODEL_ID", "Morocco-MTNRA-Labs/Voxtral-Mini-4B-Realtime-Arabic"),
        asr_revision=os.environ.get("ASR_REVISION") or None,
        asr_dtype=os.environ.get("ASR_DTYPE", "bfloat16"),
        asr_device=os.environ.get("ASR_DEVICE", "cpu"),
        asr_threads=_int("ASR_THREADS", os.cpu_count() or 4),
        fake_transcript=os.environ.get(
            "FAKE_TRANSCRIPT",
            "السلام عليكم بغيت نخرج عقد الازدياد ديال ولدي والمقاطعة قالو ليا رجع غدا",
        ),
        lid_engine=os.environ.get("LID_ENGINE", "lidstral"),
        lid_model_id=os.environ.get("LID_MODEL_ID", "Morocco-MTNRA-Labs/LIDstral-Arabic"),
        lid_revision=os.environ.get("LID_REVISION") or None,
        lid_min_confidence=_float("LID_MIN_CONFIDENCE", 0.5),
        hf_token=_secret("HF_TOKEN") or None,
        janitor_interval_s=_int("JANITOR_INTERVAL_S", 300),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
