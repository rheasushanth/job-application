"""Embedding provider.

Two backends behind one interface:

1. `sentence-transformers` (all-MiniLM-L6-v2) — true semantic embeddings, used
   when the package is installed.
2. A hashing-vectoriser + TF-IDF fallback that needs no model download and no
   network. Lexically driven, so weaker than (1), but it still produces a real
   cosine similarity rather than a constant, and it keeps the whole pipeline
   runnable offline.

`active_backend()` is surfaced on /health so the UI can state which is in use
instead of implying model-grade semantics when running on the fallback.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
from typing import Sequence

import numpy as np

from app.core.config import settings

_LOCK = threading.Lock()
_st_model = None
_st_failed = False

FALLBACK_DIM = 384
FALLBACK_NAME = "hashed-tfidf-384"

_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")

# Very common English tokens get down-weighted; a full IDF table would need a
# fitted corpus, and this keeps the fallback stateless and reproducible.
_COMMON = {
    "the", "and", "a", "an", "to", "of", "in", "for", "with", "on", "is", "are",
    "be", "as", "at", "by", "or", "from", "this", "that", "will", "you", "we",
    "our", "your", "it", "have", "has", "can", "all", "work", "team", "role",
    "job", "company", "experience", "years", "new", "about", "us", "more",
    "who", "what", "their", "they", "them", "other", "including", "across",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1]


def _load_sentence_transformer():
    global _st_model, _st_failed
    if _st_model is not None or _st_failed:
        return _st_model
    if not settings.use_sentence_transformers:
        _st_failed = True
        return None
    with _LOCK:
        if _st_model is not None or _st_failed:
            return _st_model
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            _st_model = SentenceTransformer(settings.embedding_model)
        except Exception:
            # Not installed, or no network to fetch weights — use the fallback.
            _st_failed = True
            _st_model = None
        return _st_model


def active_backend() -> str:
    model = _load_sentence_transformer()
    return settings.embedding_model if model is not None else FALLBACK_NAME


def _fallback_embed(text: str) -> list[float]:
    """Hash tokens (and bigrams) into a fixed vector with sublinear TF weights."""
    vec = np.zeros(FALLBACK_DIM, dtype=np.float32)
    toks = _tokens(text)
    if not toks:
        return vec.tolist()

    counts: dict[str, int] = {}
    for tok in toks:
        counts[tok] = counts.get(tok, 0) + 1
    for a, b in zip(toks, toks[1:]):
        bg = f"{a}_{b}"
        counts[bg] = counts.get(bg, 0) + 1

    for term, count in counts.items():
        base = term.split("_")[0]
        if base in _COMMON and "_" not in term:
            weight = 0.15
        else:
            weight = 1.0
        # Bigrams carry a little less weight than unigrams.
        if "_" in term:
            weight *= 0.6
        tf = 1.0 + math.log(count)
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "little") % FALLBACK_DIM
        sign = 1.0 if digest[4] & 1 else -1.0
        vec[idx] += sign * tf * weight

    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec.tolist()


def embed_texts(texts: Sequence[str]) -> tuple[list[list[float]], str]:
    """Embed a batch. Returns (vectors, model_name)."""
    cleaned = [(t or "").strip() for t in texts]
    model = _load_sentence_transformer()
    if model is not None:
        try:
            arr = model.encode(
                cleaned, normalize_embeddings=True, batch_size=32, show_progress_bar=False
            )
            return [list(map(float, row)) for row in np.asarray(arr)], settings.embedding_model
        except Exception:
            pass
    return [_fallback_embed(t) for t in cleaned], FALLBACK_NAME


def embed_text(text: str) -> tuple[list[float], str]:
    vectors, name = embed_texts([text])
    return vectors[0], name


def cosine_similarity(a: Sequence[float] | None, b: Sequence[float] | None) -> float:
    if not a or not b:
        return 0.0
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    if va.shape != vb.shape:
        return 0.0
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0.0:
        return 0.0
    return float(np.clip(np.dot(va, vb) / denom, -1.0, 1.0))


# Raw cosines cluster in a narrow band, so they are rescaled to 0..1 before
# being weighted. The band is backend-specific and was *measured* on
# candidate-profile vs job-description pairs, not assumed — the two backends
# occupy very different ranges, and using one band for both either saturates
# every job at 1.0 or clamps every job to 0.0, in both cases destroying the
# semantic component's ability to discriminate.
#
# Measured on representative profile/JD pairs (see docs/ARCHITECTURE.md §3):
#
#                        strong match   adjacent role   unrelated
#   MiniLM-L6-v2         0.46 - 0.76    0.39 - 0.44     0.11 - 0.30
#   hashed TF-IDF        0.24 - 0.31    ~0.15           -0.04 - 0.01
#
# Each band runs from just above the unrelated ceiling to just above the
# strongest observed match, so a real match lands mid-range rather than pinned
# at an endpoint. Re-measure if the embedding model changes.
_BANDS: dict[str, tuple[float, float]] = {
    "sentence_transformers": (0.25, 0.78),
    FALLBACK_NAME: (0.03, 0.34),
}


def similarity_band() -> tuple[float, float]:
    if active_backend() == FALLBACK_NAME:
        return _BANDS[FALLBACK_NAME]
    return _BANDS["sentence_transformers"]


def rescale_similarity(cos: float, band: tuple[float, float] | None = None) -> float:
    floor, ceiling = band or similarity_band()
    if cos <= floor:
        return 0.0
    if cos >= ceiling:
        return 1.0
    return round((cos - floor) / (ceiling - floor), 4)
