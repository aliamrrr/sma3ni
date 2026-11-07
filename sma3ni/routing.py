"""Decide which public service handles a transcribed request.

Deterministic keyword routing (auditable, editable in Postgres by non-ML staff)
plus a language gate from LIDstral: low confidence, Amazigh (not covered by the
Arabic ASR) or non-Arabic speech is flagged for human review instead of guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .textnorm import tokens, variants

TRIAGE_SERVICE = "triage"
FALLBACK_CATEGORY = "autre"

# Families checked in order. Codes are matched as whole tokens of the label
# ("ary", "ary_Arab"), names as substrings ("Moroccan Arabic").
# LIDstral-Arabic labels are regions/countries ("Morocco", "Mauritania", "MSA", "Tamazight_Tifinagh"...).
# ISO codes ("ary", "mey") are accepted too. Codes match whole tokens, names match substrings.
_FAMILIES: tuple[tuple[str, frozenset[str], tuple[str, ...]], ...] = (
    ("darija", frozenset({"ary"}), ("morocco", "moroccan", "darija")),
    ("hassaniya", frozenset({"mey"}), ("mauritania", "hassaniya", "hassani")),
    ("amazigh", frozenset({"zgh", "tzm", "shi", "rif", "kab", "ber", "tmh"}),
     ("tamazight", "amazigh", "berber", "tachelhit", "tarifit")),
    ("msa", frozenset({"arb", "msa"}), ("standard", "fusha")),
    ("arabic_other", frozenset({
        "ar", "ara", "arz", "aeb", "arq", "ayl", "apc", "ajp", "acm", "afb", "ars",
        "acx", "ayn", "apd", "shu", "acq", "abv", "ayp", "aao", "pga", "uae",
    }), ("algeria", "tunisia", "libya", "egypt", "sudan", "chad", "iraq", "jordan", "lebanon", "palestine",
         "syria", "saudi", "kuwait", "bahrain", "qatar", "oman", "yemen", "emirates", "arabic")),
)
ASR_SUPPORTED_FAMILIES = frozenset({"darija", "hassaniya", "msa", "arabic_other"})


def lang_family(label: str | None) -> str:
    if not label:
        return "unknown"
    lowered = label.lower()
    parts = set(re.split(r"[^a-z]+", lowered))
    for family, codes, names in _FAMILIES:
        if parts & codes or any(name in lowered for name in names):
            return family
    return "other"


@dataclass(frozen=True)
class Rule:
    category: str
    service_code: str
    keywords: tuple[str, ...]
    priority: int = 3
    rule_id: int = 0
    # (keyword, per-token variant sets); keywords that normalise to nothing are dropped.
    _compiled: tuple[tuple[str, tuple[frozenset[str], ...]], ...] = field(default=(), compare=False, repr=False)

    @classmethod
    def build(cls, category: str, service_code: str, keywords: list[str] | tuple[str, ...],
              priority: int = 3, rule_id: int = 0) -> Rule:
        compiled = []
        for kw in keywords:
            kw_tokens = tokens(kw)
            if kw_tokens:
                compiled.append((kw, tuple(variants(t) for t in kw_tokens)))
        return cls(category, service_code, tuple(keywords), priority, rule_id, tuple(compiled))

    def matches(self, text_variants: list[frozenset[str]]) -> list[str]:
        hits = []
        n = len(text_variants)
        for kw, pattern in self._compiled:
            width = len(pattern)
            for start in range(n - width + 1):
                if all(text_variants[start + j] & pattern[j] for j in range(width)):
                    hits.append(kw)
                    break
        return hits


@dataclass(frozen=True)
class Decision:
    category: str
    service_code: str
    priority: int
    needs_review: bool
    review_reasons: tuple[str, ...]
    lang_family: str
    matched_keywords: tuple[str, ...]


def route(transcript: str, rules: list[Rule], lang_label: str | None,
          lang_confidence: float | None, min_confidence: float) -> Decision:
    reasons: list[str] = []
    family = lang_family(lang_label)

    if not transcript or not transcript.strip():
        reasons.append("empty_transcript")
    if lang_confidence is None or lang_confidence < min_confidence:
        reasons.append("low_language_confidence")
    if family not in ASR_SUPPORTED_FAMILIES:
        reasons.append(f"language_not_supported_by_asr:{family}")

    text_variants = [variants(t) for t in tokens(transcript or "")]
    scored: list[tuple[int, int, int, Rule, list[str]]] = []
    for rule in rules:
        hits = rule.matches(text_variants)
        if hits:
            # Most keywords first, then most urgent, then oldest rule.
            scored.append((-len(hits), rule.priority, rule.rule_id, rule, hits))

    if not scored:
        reasons.append("no_rule_matched")
        return Decision(FALLBACK_CATEGORY, TRIAGE_SERVICE, 3, True, tuple(reasons), family, ())

    scored.sort(key=lambda s: s[:3])
    best = scored[0][3]
    priority = min(s[1] for s in scored)  # any urgent keyword escalates the request
    if len(scored) > 1 and scored[0][0] == scored[1][0] and scored[0][1] == scored[1][1]:
        reasons.append("ambiguous_category")
    matched = tuple(kw for s in scored for kw in s[4])
    return Decision(best.category, best.service_code, priority, bool(reasons), tuple(reasons), family, matched)
