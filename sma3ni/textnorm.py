"""Normalisation for Darija / MSA transcripts with French code-switching.

Pure stdlib, so it runs in every image and in unit tests.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# Letters NFKD does not fold for us.
_CHAR_MAP = str.maketrans({
    "ة": "ه",   # ta marbuta
    "ى": "ي",   # alef maqsura
    "ٱ": "ا",   # alef wasla
    "ڭ": "ك",   # Moroccan gaf (g)
    "گ": "ك",
    "ڤ": "ف",   # v
    "پ": "ب",   # p
    "ـ": "",    # tatweel
    "’": " ",
    "'": " ",
})
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_UNDERSCORE = re.compile(r"[_]+")

# Proclitics glued to Arabic words: w-, b-, f-, l-, k- plus the article.
_PREFIXES = ("وال", "بال", "فال", "كال", "لل", "ال", "و", "ب", "ف", "ل")
_MIN_STEM = 3  # never strip down to 2 letters ("الما" must not become "ما" = negation)


def normalize(text: str) -> str:
    """Lowercase, strip diacritics/hamza seats/tatweel, unify letter variants, drop punctuation."""
    decomposed = unicodedata.normalize("NFKD", text)
    # Drops Arabic harakat and the hamza mark (أ -> ا, ؤ -> و, ئ -> ي) and Latin accents (é -> e).
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    stripped = stripped.translate(_CHAR_MAP).lower()
    stripped = _NON_WORD.sub(" ", stripped)
    stripped = _UNDERSCORE.sub(" ", stripped)
    return " ".join(stripped.split())


def tokens(text: str) -> list[str]:
    return normalize(text).split()


def _is_arabic(token: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in token)


@lru_cache(maxsize=65536)
def variants(token: str) -> frozenset[str]:
    """Surface forms a token may match: itself plus clitic-stripped stems."""
    forms = {token}
    if _is_arabic(token):
        for prefix in _PREFIXES:
            if token.startswith(prefix) and len(token) - len(prefix) >= _MIN_STEM:
                forms.add(token[len(prefix):])
    elif len(token) > 4 and token.endswith("s"):
        forms.add(token[:-1])  # factures -> facture
    return frozenset(forms)
