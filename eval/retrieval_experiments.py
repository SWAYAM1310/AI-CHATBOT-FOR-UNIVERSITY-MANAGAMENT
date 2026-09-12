"""The three retrieval experiments of plan.md §10, over the real corpus.

  1. late vs naive chunking     policy corpus (226 clause chunks): each clause embedded
                                with its whole document as context (late chunking)
                                against the same texts embedded independently.
                                FINDING (2026-09-12): the Jina API silently ignores
                                `late_chunking` for jina-embeddings-v5-omni-small -
                                the vectors are bit-identical either way - so the
                                production store is in effect independent embeddings.
                                The experiment therefore runs on jina-embeddings-v3,
                                which honours the flag, and reports v5 alongside.
  2. flat vs parent-child       CP syllabus (~550 chunks): a child chunk that carries
                                its course label (and, on v3, is embedded together
                                with its parent) against the unit body alone - the
                                "Unit 3: Normalization, but of which course?" failure
                                mode §8 is built to avoid.
  3. Matryoshka dimension sweep 1024 / 512 / 256 / 128 dims by truncating the stored
                                vectors and the query vectors (re-normalised), on
                                both corpora: retrieval quality, index size and
                                brute-force query latency.

Nothing is written to the database: alternative vectors live in memory (numpy)
and the sparse branch reads the stored tsvectors as production does. Needs
JINA_API_KEY (the queries and the alternative embeddings are real Jina calls;
~30 requests, ~150k tokens for the full run).

    cd backend
    ./.venv/Scripts/python.exe ../eval/retrieval_experiments.py            # all three
    ./.venv/Scripts/python.exe ../eval/retrieval_experiments.py --only 1 3 # a subset
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent / "backend"))

from sqlalchemy import select  # noqa: E402

from app.ai.rag.embedder import JinaEmbedder, get_embedder  # noqa: E402
from app.config import settings  # noqa: E402
from app.ai.rag.retriever import RRF_K, _sparse_candidates, rrf  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import DocChunk, Document  # noqa: E402

KS = (1, 3, 5)
DIMS = (1024, 512, 256, 128)
LATE_MODEL = "jina-embeddings-v3"  # the served model that actually applies late_chunking (1024-dim too)
CP_TITLE = "B.Tech Computer Engineering Syllabus 2025"
STRUCTURE_SECTION = "Programme structure"


# --- corpus -----------------------------------------------------------------

@dataclass
class Chunk:
    id: int
    document_id: int
    doc: str
    section: str
    content: str
    parent_id: int | None
    vec: np.ndarray  # the stored (production) vector

    @property
    def body(self) -> str:
        """The text without its first line - for curriculum children that is the course label."""
        return self.content.split("\n", 1)[1] if "\n" in self.content else self.content


def load_corpus(db, *, doc_type: str, title: str | None = None) -> list[Chunk]:
    stmt = (
        select(DocChunk, Document.title)
        .join(Document, Document.id == DocChunk.document_id)
        .where(Document.doc_type == doc_type, DocChunk.embedding.is_not(None))
        .order_by(DocChunk.id)
    )
    if title:
        stmt = stmt.where(Document.title == title)
    out = []
    for chunk, doc_title in db.execute(stmt):
        if chunk.section == STRUCTURE_SECTION:
            continue  # excluded by search_curriculum in production too
        out.append(Chunk(chunk.id, chunk.document_id, doc_title, chunk.section or "", chunk.content,
                         chunk.parent_chunk_id, np.asarray(chunk.embedding, dtype=np.float32)))
    return out


def matrix(vecs: list[np.ndarray] | list[list[float]]) -> np.ndarray:
    m = np.asarray(vecs, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


# --- gold set ---------------------------------------------------------------

@dataclass
class Query:
    text: str
    targets: list[tuple[str, str]]  # (doc substring, section prefix)

    def hit(self, c: Chunk) -> bool:
        return any(doc in c.doc and c.section.startswith(sec) for doc, sec in self.targets)


def load_queries(kind: str) -> list[Query]:
    raw = yaml.safe_load((EVAL_DIR / "retrieval_set.yaml").read_text(encoding="utf-8"))[kind]
    out = []
    for q in raw:
        targets = [(t["doc"], t["section"]) for t in q["any"]] if "any" in q else [(q["doc"], q["section"])]
        out.append(Query(q["query"], targets))
    return out


# --- scoring ----------------------------------------------------------------

def dense_ranking(qm: np.ndarray, cm: np.ndarray, n: int = 20) -> list[list[int]]:
    """Per query, corpus row indices ordered by cosine similarity (normalised inputs)."""
    sims = qm @ cm.T
    return [list(np.argsort(-row, kind="stable")[:n]) for row in sims]


def recall(rankings: list[list[int]], queries: list[Query], corpus: list[Chunk]) -> dict[str, float]:
    out: dict[str, float] = {}
    for k in KS:
        out[f"r@{k}"] = sum(any(q.hit(corpus[i]) for i in r[:k]) for q, r in zip(queries, rankings)) / len(queries)
    rr = []
    for q, r in zip(queries, rankings):
        rank = next((i + 1 for i, idx in enumerate(r) if q.hit(corpus[idx])), None)
        rr.append(1 / rank if rank else 0.0)
    out["mrr"] = statistics.fmean(rr)
    return out


def hybrid_ranking(db, dense: list[list[int]], queries: list[Query], corpus: list[Chunk]) -> list[list[int]]:
    """RRF of the in-memory dense ranking with the production sparse branch over the same chunks."""
    by_id = {c.id: i for i, c in enumerate(corpus)}
    ids = list(by_id)
    out = []
    for q, d in zip(queries, dense):
        base = select(DocChunk.id).where(DocChunk.id.in_(ids))
        sparse = [by_id[cid] for cid in _sparse_candidates(db, base, q.text, 20) if cid in by_id]
        scores = rrf([lst for lst in (d, sparse) if lst], k=RRF_K)
        out.append(sorted(scores, key=lambda i: (-scores[i], i))[:20])
    return out


def fmt(m: dict[str, float]) -> str:
    return "  ".join(f"{k} {100 * v:5.1f}" for k, v in m.items())


# --- experiments ------------------------------------------------------------

def embed_texts(embedder: JinaEmbedder, texts: list[str], *, late: bool, groups: list[list[int]] | None = None) -> np.ndarray:
    """Embed independently, or late-chunked per group (a document, or a parent with its children)."""
    if not late:
        return matrix(embedder.embed_documents(texts, late_chunking=False))
    vecs: list[list[float] | None] = [None] * len(texts)
    for members in groups or [list(range(len(texts)))]:
        if len(members) == 1:
            (vecs[members[0]],) = embedder.embed_documents([texts[members[0]]])
            continue
        for i, v in zip(members, embedder.embed_documents([texts[i] for i in members], late_chunking=True)):
            vecs[i] = v
    return matrix(vecs)  # type: ignore[arg-type]


def experiment_1(db, embedder: JinaEmbedder) -> dict[str, Any]:
    print("\n[1] late vs naive chunking - policy corpus")
    corpus = load_corpus(db, doc_type="policy")
    queries = load_queries("policy")
    qm = matrix([embedder.embed_query(q.text) for q in queries])
    print(f"    {len(corpus)} chunks, {len(queries)} queries")

    texts = [c.content for c in corpus]
    by_doc: dict[int, list[int]] = {}
    for i, c in enumerate(corpus):
        by_doc.setdefault(c.document_id, []).append(i)

    t0 = time.perf_counter()
    v5_independent = embed_texts(embedder, texts, late=False)
    stored = matrix([c.vec for c in corpus])
    identical = float(np.abs(stored - v5_independent).max())
    print(f"    {embedder.model}: stored (ingested with late_chunking=true) vs independent, max |diff| = {identical:.2e}")

    late_embedder = JinaEmbedder(model=LATE_MODEL, api_key=settings.jina_api_key)
    late_qm = matrix([late_embedder.embed_query(q.text) for q in queries])
    variants: dict[str, tuple[np.ndarray, np.ndarray]] = {
        f"{embedder.model} stored (flag ignored)": (qm, stored),
        f"{embedder.model} independent": (qm, v5_independent),
        f"{LATE_MODEL} late (per document)": (late_qm, embed_texts(late_embedder, texts, late=True, groups=list(by_doc.values()))),
        f"{LATE_MODEL} independent": (late_qm, embed_texts(late_embedder, texts, late=False)),
    }
    print(f"    alternative embeddings: {time.perf_counter() - t0:.1f}s")

    results: dict[str, Any] = {
        "chunks": len(corpus), "queries": len(queries), "late_model": LATE_MODEL,
        "v5_late_flag_max_abs_diff": identical, "variants": {},
    }
    for name, (q_m, cm) in variants.items():
        dense = dense_ranking(q_m, cm)
        r = {"dense": recall(dense, queries, corpus), "hybrid": recall(hybrid_ranking(db, dense, queries, corpus), queries, corpus)}
        results["variants"][name] = r
        print(f"    {name:44s} dense   {fmt(r['dense'])}")
        print(f"    {'':44s} hybrid  {fmt(r['hybrid'])}")
    return results


def experiment_2(db, embedder: JinaEmbedder) -> dict[str, Any]:
    print("\n[2] flat vs parent-child chunking - CP syllabus")
    corpus = load_corpus(db, doc_type="curriculum", title=CP_TITLE)
    queries = load_queries("curriculum")
    qm = matrix([embedder.embed_query(q.text) for q in queries])
    children = sum(c.parent_id is not None for c in corpus)
    print(f"    {len(corpus)} chunks ({children} children), {len(queries)} queries")

    labelled = [c.content for c in corpus]
    flat = [c.body if c.parent_id is not None else c.content for c in corpus]  # a naive chunker never sees the course
    by_id = {c.id: i for i, c in enumerate(corpus)}
    families: dict[int, list[int]] = {}
    for i, c in enumerate(corpus):
        families.setdefault(by_id.get(c.parent_id, i) if c.parent_id else i, []).append(i)

    t0 = time.perf_counter()
    late_embedder = JinaEmbedder(model=LATE_MODEL, api_key=settings.jina_api_key)
    late_qm = matrix([late_embedder.embed_query(q.text) for q in queries])
    variants: dict[str, tuple[np.ndarray, np.ndarray]] = {
        f"{embedder.model} labelled (stored)": (qm, matrix([c.vec for c in corpus])),
        f"{embedder.model} flat: unit body only": (qm, embed_texts(embedder, flat, late=False)),
        f"{LATE_MODEL} labelled + late per parent": (late_qm, embed_texts(late_embedder, labelled, late=True, groups=list(families.values()))),
        f"{LATE_MODEL} labelled, independent": (late_qm, embed_texts(late_embedder, labelled, late=False)),
        f"{LATE_MODEL} flat: unit body only": (late_qm, embed_texts(late_embedder, flat, late=False)),
    }
    print(f"    alternative embeddings: {time.perf_counter() - t0:.1f}s")

    # secondary measure: did we at least land in the right course (parent or any sibling)?
    parent_of = {c.id: c.parent_id or c.id for c in corpus}
    def family_recall(rankings: list[list[int]]) -> dict[str, float]:
        target_family = []
        for q in queries:
            tgt = next((c for c in corpus if q.hit(c)), None)
            target_family.append(parent_of[tgt.id] if tgt else None)
        return {
            f"course@{k}": sum(any(parent_of[corpus[i].id] == fam for i in r[:k]) for fam, r in zip(target_family, rankings)) / len(queries)
            for k in KS
        }

    results: dict[str, Any] = {"chunks": len(corpus), "children": children, "queries": len(queries),
                               "late_model": LATE_MODEL, "variants": {}}
    for name, (q_m, cm) in variants.items():
        dense = dense_ranking(q_m, cm)
        hybrid = hybrid_ranking(db, dense, queries, corpus)
        r = {"dense": recall(dense, queries, corpus), "hybrid": recall(hybrid, queries, corpus),
             "dense_course": family_recall(dense)}
        results["variants"][name] = r
        print(f"    {name:44s} dense   {fmt(r['dense'])}   |  {fmt(r['dense_course'])}")
        print(f"    {'':44s} hybrid  {fmt(r['hybrid'])}")
    return results


def experiment_3(db, embedder: JinaEmbedder) -> dict[str, Any]:
    print("\n[3] Matryoshka dimension sweep - stored vectors truncated and re-normalised")
    results: dict[str, Any] = {}
    for label, corpus, queries in (
        ("policy", load_corpus(db, doc_type="policy"), load_queries("policy")),
        ("curriculum (CP)", load_corpus(db, doc_type="curriculum", title=CP_TITLE), load_queries("curriculum")),
    ):
        full_q = np.asarray([embedder.embed_query(q.text) for q in queries], dtype=np.float32)
        full_c = np.asarray([c.vec for c in corpus], dtype=np.float32)
        print(f"    {label}: {len(corpus)} chunks, {len(queries)} queries")
        rows = []
        for dim in DIMS:
            qm, cm = matrix(full_q[:, :dim]), matrix(full_c[:, :dim])
            # brute-force latency: mean per query over a few repetitions (pgvector's HNSW is the
            # production index; the trend with dimension is what the sweep is about)
            reps = 20
            t0 = time.perf_counter()
            for _ in range(reps):
                dense_ranking(qm, cm, n=5)
            per_query_ms = (time.perf_counter() - t0) / reps / len(queries) * 1000
            r = recall(dense_ranking(qm, cm), queries, corpus)
            row = {"dim": dim, **r, "index_bytes": int(cm.nbytes), "query_ms": per_query_ms}
            rows.append(row)
            print(f"      {dim:5d} dims  {fmt(r)}   index {cm.nbytes / 1024:7.0f} KiB   {per_query_ms:.3f} ms/query")
        results[label] = {"chunks": len(corpus), "queries": len(queries), "dims": rows}
    return results


# --- main -------------------------------------------------------------------

def write_markdown(results: dict[str, Any], path: Path) -> None:
    lines = ["# Retrieval experiments", "", f"Embedding model: `{results['embedding_model']}`; k in {{1,3,5}}; recall = share of queries with a correct chunk in the top k.", ""]
    if "1_late_vs_naive" in results:
        e = results["1_late_vs_naive"]
        lines += [f"## 1. Late vs naive chunking (policy corpus: {e['chunks']} chunks, {e['queries']} queries)", "",
                  f"The Jina API ignores `late_chunking` for `{results['embedding_model']}`: the stored vectors and an "
                  f"independent re-embedding differ by at most {e['v5_late_flag_max_abs_diff']:.1e}. "
                  f"The late-vs-naive comparison is therefore made on `{e['late_model']}`, which applies it.", "",
                  "| variant | branch | R@1 | R@3 | R@5 | MRR |", "|---|---|---|---|---|---|"]
        for name, r in e["variants"].items():
            for branch in ("dense", "hybrid"):
                m = r[branch]
                lines.append(f"| {name} | {branch} | {100*m['r@1']:.1f} | {100*m['r@3']:.1f} | {100*m['r@5']:.1f} | {m['mrr']:.3f} |")
        lines.append("")
    if "2_flat_vs_parent_child" in results:
        e = results["2_flat_vs_parent_child"]
        lines += [f"## 2. Flat vs parent-child chunking (CP syllabus: {e['chunks']} chunks, {e['children']} children, {e['queries']} queries)", "",
                  '"Labelled" = the child chunk starts with its course label (production); "flat" = the unit body alone, '
                  'as a chunker that does not know the document structure would produce it. "Right course" counts a hit '
                  'on the parent record or any unit of the target course (what parent hydration would recover).', "",
                  "| variant | branch | R@1 | R@3 | R@5 | MRR | right course @1 | @3 |", "|---|---|---|---|---|---|---|---|"]
        for name, r in e["variants"].items():
            for branch in ("dense", "hybrid"):
                m, fam = r[branch], r["dense_course"]
                extra = f"{100*fam['course@1']:.1f} | {100*fam['course@3']:.1f}" if branch == "dense" else " | "
                lines.append(f"| {name} | {branch} | {100*m['r@1']:.1f} | {100*m['r@3']:.1f} | {100*m['r@5']:.1f} | {m['mrr']:.3f} | {extra} |")
        lines.append("")
    if "3_matryoshka" in results:
        lines += ["## 3. Matryoshka dimension sweep (dense only, stored vectors truncated + re-normalised)", ""]
        for label, e in results["3_matryoshka"].items():
            lines += [f"**{label}** ({e['chunks']} chunks, {e['queries']} queries)", "",
                      "| dims | R@1 | R@3 | R@5 | MRR | index size | brute-force ms/query |", "|---|---|---|---|---|---|---|"]
            for r in e["dims"]:
                lines.append(f"| {r['dim']} | {100*r['r@1']:.1f} | {100*r['r@3']:.1f} | {100*r['r@5']:.1f} | {r['mrr']:.3f} | {r['index_bytes']/1024:.0f} KiB | {r['query_ms']:.3f} |")
            lines.append("")
    lines += ["## Reading the numbers", "",
              "- Recall is over the gold set in `retrieval_set.yaml`; the queries are phrased the way the router's "
              "`rag_query` rewrite phrases them (regulation language), so this measures the retriever, not the LLM.",
              "- \"hybrid\" fuses the in-memory dense ranking with the production full-text branch by RRF (k=60), "
              "exactly as `retriever.retrieve` does; it is the number the assistant actually sees.",
              "- The brute-force latency column is a numpy dot product over a few hundred vectors - microseconds, "
              "noise-level, and not the production path (pgvector HNSW at 1024 dims). Index size is the honest cost axis.",
              "- Truncating the stored vectors assumes the model is Matryoshka-trained (Jina v3+ are); the API's "
              "`dimensions` parameter would produce the same vectors server-side.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", type=int, default=[1, 2, 3])
    ap.add_argument("--out", type=Path, default=EVAL_DIR / "retrieval_results.json")
    args = ap.parse_args(argv)

    embedder = get_embedder()
    if not isinstance(embedder, JinaEmbedder):
        print("JINA_API_KEY is not set - the experiments need real embeddings", file=sys.stderr)
        return 2
    results: dict[str, Any] = {"embedding_model": embedder.model}
    started = time.time()
    with SessionLocal() as db:
        if 1 in args.only:
            results["1_late_vs_naive"] = experiment_1(db, embedder)
        if 2 in args.only:
            results["2_flat_vs_parent_child"] = experiment_2(db, embedder)
        if 3 in args.only:
            results["3_matryoshka"] = experiment_3(db, embedder)
        db.rollback()
    results["jina_calls"] = embedder.calls
    results["jina_tokens"] = embedder.tokens_used
    results["wall_clock_s"] = time.time() - started
    print(f"\n{embedder.calls} Jina calls, {embedder.tokens_used} tokens, {results['wall_clock_s']:.0f}s")

    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_markdown(results, args.out.with_suffix(".md"))
    print(f"wrote {args.out} and {args.out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
