"""Embedding wrapper.

Phase-0 stub: the real jina-embeddings-v5 load (CUDA torch, trust_remote_code)
lands in Phase 3. For now `--selftest` just confirms the configured dimension so
the Phase-0 gate has something to run.

    python -m app.ai.rag.embedder --selftest
"""
from __future__ import annotations

import argparse

from app.config import settings

EXPECTED_DIM = 1024


def selftest() -> int:
    dim = settings.embedding_dim
    model = settings.embedding_model
    print(f"embedding model : {model}")
    print(f"configured dim  : {dim}")
    if dim != EXPECTED_DIM:
        print(f"FAIL: expected {EXPECTED_DIM}, got {dim}")
        return 1
    print("ok (stub - real model loads in Phase 3)")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(selftest())
    ap.print_help()


if __name__ == "__main__":
    main()
