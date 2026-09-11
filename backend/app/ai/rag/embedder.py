"""Embeddings via the Jina API (plan.md §8 "Embedder" — API, not a local model).

    python -m app.ai.rag.embedder --selftest     # one real call, prints dim + tokens

Two things are encoded here so no call site can get them wrong:

* **Asymmetry.** Indexed content goes up with `task=retrieval.passage`, search
  input with `task=retrieval.query`. Swapping them silently degrades retrieval,
  so the two are separate methods and there is no generic `embed()`.
* **Late chunking.** `embed_documents(chunks, late_chunking=True)` sends the
  chunks of ONE document in ONE request, in order; the API runs the whole
  document through the transformer and pools per chunk, so each vector carries
  document context. The caller guarantees the chunks belong together and fit
  the model's context — a policy (3–4 pages) or one curriculum course record.

Query vectors are cached by text hash: the same question costs one call.

`FakeEmbedder` is the offline stand-in for tests and CI: deterministic hashed
bag-of-words vectors, so texts sharing terms are close and retrieval tests can
assert on ranking without a network.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Protocol

import httpx

from app.ai.budget import backoff_delay
from app.config import settings

BATCH = 32  # inputs per request when not late-chunking
MAX_RETRIES = 4
RETRYABLE = {429, 500, 502, 503, 504}
QUERY_CACHE = 512


class EmbeddingError(RuntimeError):
    pass


class EmbeddingNotConfigured(EmbeddingError):
    pass


class Embedder(Protocol):
    model: str
    dim: int

    def embed_documents(self, texts: list[str], *, late_chunking: bool = False) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def api_model_name(name: str) -> str:
    """`jinaai/jina-embeddings-v5-omni-small` (HF id) -> `jina-embeddings-v5-omni-small` (API id)."""
    return name.split("/", 1)[1] if name.startswith("jinaai/") else name


class JinaEmbedder:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = settings.embedding_model,
        base_url: str = settings.jina_base_url,
        dim: int = settings.embedding_dim,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        if not api_key:
            raise EmbeddingNotConfigured("JINA_API_KEY is not set")
        self.model = api_model_name(model)
        self.dim = dim
        self._client = client or httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        self._sleep = sleeper
        self._max_retries = max_retries
        self._query_cache: OrderedDict[str, list[float]] = OrderedDict()
        self.tokens_used = 0
        self.calls = 0

    # --- public ------------------------------------------------------------------
    def embed_documents(self, texts: list[str], *, late_chunking: bool = False) -> list[list[float]]:
        if not texts:
            return []
        if late_chunking:
            return self._post(texts, task="retrieval.passage", late_chunking=True)
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            out.extend(self._post(texts[i : i + BATCH], task="retrieval.passage", late_chunking=False))
        return out

    def embed_query(self, text: str) -> list[float]:
        key = hashlib.sha1(text.strip().lower().encode()).hexdigest()
        hit = self._query_cache.get(key)
        if hit is not None:
            self._query_cache.move_to_end(key)
            return hit
        (vec,) = self._post([text], task="retrieval.query", late_chunking=False)
        self._query_cache[key] = vec
        if len(self._query_cache) > QUERY_CACHE:
            self._query_cache.popitem(last=False)
        return vec

    # --- wire --------------------------------------------------------------------
    def _post(self, inputs: list[str], *, task: str, late_chunking: bool) -> list[list[float]]:
        body: dict[str, Any] = {"model": self.model, "task": task, "input": inputs}
        if late_chunking:
            body["late_chunking"] = True
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.post("/embeddings", json=body)
            except httpx.HTTPError as exc:
                if attempt == self._max_retries:
                    raise EmbeddingError(f"jina request failed: {exc}") from exc
                self._sleep(backoff_delay(attempt))
                continue
            if resp.status_code in RETRYABLE and attempt < self._max_retries:
                retry_after = resp.headers.get("retry-after")
                self._sleep(float(retry_after) if retry_after else backoff_delay(attempt))
                continue
            if resp.status_code != 200:
                raise EmbeddingError(f"jina {resp.status_code}: {resp.text[:300]}")
            return self._parse(resp.json(), len(inputs))
        raise EmbeddingError("jina: retries exhausted")  # pragma: no cover - loop always returns/raises

    def _parse(self, payload: dict[str, Any], expected: int) -> list[list[float]]:
        data = sorted(payload.get("data", []), key=lambda d: d.get("index", 0))
        vectors = [d["embedding"] for d in data]
        if len(vectors) != expected:
            raise EmbeddingError(f"jina returned {len(vectors)} vectors for {expected} inputs")
        if any(len(v) != self.dim for v in vectors):
            raise EmbeddingError(f"jina returned a vector of the wrong dimension (expected {self.dim})")
        self.calls += 1
        self.tokens_used += int(payload.get("usage", {}).get("total_tokens", 0))
        return vectors


class FakeEmbedder:
    """Deterministic, offline. Hashed bag-of-words: shared terms -> nearby vectors."""

    _token = re.compile(r"[a-z0-9]+")

    def __init__(self, dim: int = settings.embedding_dim) -> None:
        self.model = "fake"
        self.dim = dim
        self.calls = 0

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in self._token.findall(text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)  # noqa: S324 - not security
            v[h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str], *, late_chunking: bool = False) -> list[list[float]]:
        self.calls += 1
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return self._vec(text)


_default: Embedder | None = None


def get_embedder() -> Embedder:
    """Process-wide Jina client. Raises EmbeddingNotConfigured without a key."""
    global _default
    if _default is None:
        _default = JinaEmbedder(api_key=settings.jina_api_key)
    return _default


def selftest() -> int:
    print(f"embedding model : {api_model_name(settings.embedding_model)}")
    print(f"configured dim  : {settings.embedding_dim}")
    try:
        emb = get_embedder()
        vec = emb.embed_query("minimum attendance to sit the end-semester exam")
    except EmbeddingNotConfigured as exc:
        print(f"skip: {exc}")
        return 0
    except EmbeddingError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"vector dim      : {len(vec)}  (tokens billed: {getattr(emb, 'tokens_used', '?')})")
    print("ok")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(selftest())
    ap.print_help()


if __name__ == "__main__":
    main()
