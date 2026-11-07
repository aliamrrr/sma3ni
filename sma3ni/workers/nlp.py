"""NLP worker: request.transcribed -> dialect (LIDstral) + routing -> request.routed. Fast (ms)."""
from __future__ import annotations

import asyncio
import time

from .. import events, repo
from ..engines.lid import LidResult, build_lid_engine
from ..routing import Rule, route
from .base import BaseWorker, run_worker

RULES_TTL_S = 60


class NlpWorker(BaseWorker):
    consumer = "nlp"
    event_type = events.REQUEST_TRANSCRIBED
    ack_wait_s = 30
    max_attempts = 5

    def load(self) -> None:
        self.lid = build_lid_engine(self.settings)
        self._rules: list[Rule] = []
        self._rules_at = 0.0

    async def rules(self, conn) -> list[Rule]:
        if time.monotonic() - self._rules_at > RULES_TTL_S:
            cur = await conn.execute(
                "SELECT id, category, service_code, keywords, priority FROM routing_rules WHERE enabled ORDER BY id")
            self._rules = [Rule.build(r["category"], r["service_code"], r["keywords"], r["priority"], r["id"])
                           for r in await cur.fetchall()]
            self._rules_at = time.monotonic()
        return self._rules

    async def handle(self, event: events.Event) -> None:
        rid = event.request_id
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT status, transcript FROM requests WHERE id = %s", (rid,))
            row = await cur.fetchone()
            if row is None or row["status"] != "TRANSCRIBED":
                return
            rules = await self.rules(conn)

        transcript = row["transcript"] or ""
        if transcript.strip():
            lid = await asyncio.to_thread(self.lid.identify, transcript)
        else:
            lid = LidResult("unknown", 0.0)
        decision = route(transcript, rules, lid.label, lid.confidence, self.settings.lid_min_confidence)

        async with self.pool.connection() as conn, conn.transaction():
            if not await repo.mark_processed(conn, self.consumer, event.id):
                return
            prev = await repo.set_status(conn, rid, "ROUTED", actor="worker:nlp", expected=("TRANSCRIBED",),
                                         note=f"{decision.category} -> {decision.service_code}")
            if prev is None:
                return
            await conn.execute(
                """
                UPDATE requests SET lang_label = %s, lang_confidence = %s, lang_family = %s, category = %s,
                       service_code = %s, priority = %s, needs_review = %s, review_reasons = %s
                WHERE id = %s
                """,
                (lid.label, lid.confidence, decision.lang_family, decision.category, decision.service_code,
                 decision.priority, decision.needs_review, list(decision.review_reasons), rid),
            )
            await events.emit(conn, events.REQUEST_ROUTED, rid, {
                "service_code": decision.service_code,
                "category": decision.category,
                "priority": decision.priority,
                "needs_review": decision.needs_review,
                "lang_family": decision.lang_family,
            })


def main() -> None:
    run_worker(NlpWorker)


if __name__ == "__main__":
    main()
