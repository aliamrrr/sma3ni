"""Apply db/migrations/*.sql in order, once each. Safe to run from several containers (advisory lock)."""
from __future__ import annotations

import logging
from pathlib import Path

import psycopg

from .config import get_settings
from .logs import setup_logging

log = logging.getLogger("sma3ni.migrate")
MIGRATIONS = Path(__file__).resolve().parent.parent / "db" / "migrations"
LOCK_ID = 7_272_740


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                     "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
            log.info("applied %s", path.name)
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
    log.info("database up to date")


if __name__ == "__main__":
    main()
