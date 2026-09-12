# Retrieval experiments

Embedding model: `jina-embeddings-v5-omni-small`; k in {1,3,5}; recall = share of queries with a correct chunk in the top k.

## 1. Late vs naive chunking (policy corpus: 226 chunks, 32 queries)

The Jina API ignores `late_chunking` for `jina-embeddings-v5-omni-small`: the stored vectors and an independent re-embedding differ by at most 2.2e-03. The late-vs-naive comparison is therefore made on `jina-embeddings-v3`, which applies it.

| variant | branch | R@1 | R@3 | R@5 | MRR |
|---|---|---|---|---|---|
| jina-embeddings-v5-omni-small stored (flag ignored) | dense | 96.9 | 100.0 | 100.0 | 0.984 |
| jina-embeddings-v5-omni-small stored (flag ignored) | hybrid | 90.6 | 100.0 | 100.0 | 0.948 |
| jina-embeddings-v5-omni-small independent | dense | 96.9 | 100.0 | 100.0 | 0.984 |
| jina-embeddings-v5-omni-small independent | hybrid | 90.6 | 100.0 | 100.0 | 0.948 |
| jina-embeddings-v3 late (per document) | dense | 56.2 | 87.5 | 90.6 | 0.724 |
| jina-embeddings-v3 late (per document) | hybrid | 87.5 | 90.6 | 96.9 | 0.907 |
| jina-embeddings-v3 independent | dense | 96.9 | 96.9 | 100.0 | 0.975 |
| jina-embeddings-v3 independent | hybrid | 96.9 | 96.9 | 100.0 | 0.977 |

## 2. Flat vs parent-child chunking (CP syllabus: 548 chunks, 460 children, 16 queries)

"Labelled" = the child chunk starts with its course label (production); "flat" = the unit body alone, as a chunker that does not know the document structure would produce it. "Right course" counts a hit on the parent record or any unit of the target course (what parent hydration would recover).

| variant | branch | R@1 | R@3 | R@5 | MRR | right course @1 | @3 |
|---|---|---|---|---|---|---|---|
| jina-embeddings-v5-omni-small labelled (stored) | dense | 93.8 | 93.8 | 100.0 | 0.950 | 100.0 | 100.0 |
| jina-embeddings-v5-omni-small labelled (stored) | hybrid | 87.5 | 93.8 | 93.8 | 0.911 |  |  |
| jina-embeddings-v5-omni-small flat: unit body only | dense | 68.8 | 87.5 | 87.5 | 0.794 | 87.5 | 100.0 |
| jina-embeddings-v5-omni-small flat: unit body only | hybrid | 68.8 | 93.8 | 93.8 | 0.802 |  |  |
| jina-embeddings-v3 labelled + late per parent | dense | 62.5 | 87.5 | 100.0 | 0.760 | 75.0 | 100.0 |
| jina-embeddings-v3 labelled + late per parent | hybrid | 75.0 | 93.8 | 93.8 | 0.839 |  |  |
| jina-embeddings-v3 labelled, independent | dense | 93.8 | 100.0 | 100.0 | 0.969 | 93.8 | 100.0 |
| jina-embeddings-v3 labelled, independent | hybrid | 81.2 | 93.8 | 93.8 | 0.871 |  |  |
| jina-embeddings-v3 flat: unit body only | dense | 43.8 | 75.0 | 87.5 | 0.614 | 81.2 | 100.0 |
| jina-embeddings-v3 flat: unit body only | hybrid | 56.2 | 93.8 | 93.8 | 0.743 |  |  |

## 3. Matryoshka dimension sweep (dense only, stored vectors truncated + re-normalised)

**policy** (226 chunks, 32 queries)

| dims | R@1 | R@3 | R@5 | MRR | index size | brute-force ms/query |
|---|---|---|---|---|---|---|
| 1024 | 96.9 | 100.0 | 100.0 | 0.984 | 904 KiB | 0.032 |
| 512 | 96.9 | 100.0 | 100.0 | 0.979 | 452 KiB | 0.037 |
| 256 | 90.6 | 100.0 | 100.0 | 0.948 | 226 KiB | 0.027 |
| 128 | 90.6 | 96.9 | 100.0 | 0.940 | 113 KiB | 0.023 |

**curriculum (CP)** (548 chunks, 16 queries)

| dims | R@1 | R@3 | R@5 | MRR | index size | brute-force ms/query |
|---|---|---|---|---|---|---|
| 1024 | 93.8 | 93.8 | 100.0 | 0.950 | 2192 KiB | 0.858 |
| 512 | 93.8 | 93.8 | 100.0 | 0.950 | 1096 KiB | 0.061 |
| 256 | 93.8 | 93.8 | 100.0 | 0.950 | 548 KiB | 0.051 |
| 128 | 87.5 | 93.8 | 100.0 | 0.922 | 274 KiB | 0.048 |

## Reading the numbers

- Recall is over the gold set in `retrieval_set.yaml`; the queries are phrased the way the router's `rag_query` rewrite phrases them (regulation language), so this measures the retriever, not the LLM.
- "hybrid" fuses the in-memory dense ranking with the production full-text branch by RRF (k=60), exactly as `retriever.retrieve` does; it is the number the assistant actually sees.
- The brute-force latency column is a numpy dot product over a few hundred vectors - microseconds, noise-level, and not the production path (pgvector HNSW at 1024 dims). Index size is the honest cost axis.
- Truncating the stored vectors assumes the model is Matryoshka-trained (Jina v3+ are); the API's `dimensions` parameter would produce the same vectors server-side.
