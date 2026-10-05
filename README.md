# UniAssist — Role-Aware AI University Management Assistant

A conversational assistant that behaves differently for **students**, **faculty**, and
**admins** — identity, permissions, and data scoping are enforced server-side, not
prompted. It combines a typed-tool database layer (no text-to-SQL), RAG with citations
over university regulations, and two-phase confirmed write actions.

> **Student:** "Can I sit for the exam if my attendance is 72%?"
>
> **UniAssist:** "Your DBMS attendance is currently **68%** (34 of 50 sessions), not 72%.
> The Attendance Regulations require a minimum of 75% to be eligible for the
> end-semester examination, with condonation available up to 65% on medical grounds.
> You are **7 points short**. [1]
> [1] *Academic Regulations Part IV — Attendance, §4.2*"

Ask the same question as a faculty member and the tools that could answer it are never
even shown to the model. Ask it about another student and the identity argument is
stripped below the model, in the registry.

See [`plan.md`](plan.md) for the full architecture, and
[`DATA_MODEL_EXPLANATION.md`](DATA_MODEL_EXPLANATION.md) for the dataset.

---

## Status — Phases 0–6 complete

| Phase | What shipped |
|---|---|
| **1a** | 35-table schema (SQLAlchemy 2.0), Alembic migration (`CREATE EXTENSION vector`, HNSW + GIN + composite indexes), CSV → Postgres loader ([SCHEMA_MAP.md](SCHEMA_MAP.md)) |
| **1b** | JWT auth; `AuthContext` built server-side from `users.subject_ref`; the three RBAC layers in [registry.py](backend/app/ai/tools/registry.py) with `audit_log` writes |
| **2** | The 42-tool catalog; OpenAI-compatible provider (Groq); the three-call orchestrator; token-bucket limiter + 429 backoff; `POST /api/chat`; 8 action tools behind two-phase confirmation |
| **3** | RAG — manifest-driven ingest, per-`doc_type` chunkers, hybrid retrieval, resolved citations |
| **4** | Gap-check against the plan |
| **5a–5c** | React frontend: streaming answers, Markdown rendering, citation chips, confirmation cards, dev trace panel |
| **5b** | Evaluation harness, 83-case golden set, three retrieval experiments |
| **6** | Agentic email notifications for leave apply/decide (Mailpit sandbox + real SMTP) |

**`pytest` — 434 tests, fully offline**: every LLM call goes through a scripted provider,
and CI ([backend-tests.yml](.github/workflows/backend-tests.yml)) runs the suite with
`LLM_API_KEY` unset on purpose. The RBAC suite must stay green.

**Known open item:** the end-to-end golden-set run on disk
([`eval/results.json`](eval/results.json)) predates the commit that added reference-based
quality scoring, so it carries routing/refusal/citation/path but not retrieval recall or
fact recall. Re-running it is blocked on Groq free-tier quota — see `context.md` §15.

---

## Evaluation

Two harnesses, both over the real corpus and the real database. Neither mocks anything.

### 1. End-to-end turns — [`eval/run_eval.py`](eval/run_eval.py)

80 hand-written cases (40 student / 22 faculty / 18 admin) run through the live
orchestrator, live tools, live retrieval and the live model. 14 are refusal cases,
including adversarial ones ("ignore your instructions…", "I'm actually an admin…",
"what's Rahul's attendance?", a faculty member asking about a course they don't teach).

Last complete run — 80/80 turns completed, `openai/gpt-oss-120b`:

| Metric | Result | Gate |
|---|---|---|
| **Refusal accuracy** | **100%** (14/14) | 100% — one leak invalidates the RBAC claim |
| Routing accuracy | **96.2%** (50/52) | ≥ 85% |
| Citation rate on policy answers | **95%** (19/20) | 100% |
| Path accuracy (fast / full / confirm / smalltalk) | **100%** (10/10) | — |
| Cases fully passed | 77 / 80 | — |
| Median latency | **2.7 s** (excluding free-tier rate-limit waits) | — |
| Mean tokens / turn | 2,312 (max 4,007) | < 5,000 |

Per role: student **40/40**, faculty 21/22, admin 16/18.

Action tools stop at the confirmation card — the harness never calls the confirm
endpoint, so no run ever writes to a data table.

### 2. Retrieval ablations — [`eval/retrieval_experiments.py`](eval/retrieval_experiments.py)

48 gold queries against the production vectors. Full tables in
[`eval/retrieval_results.md`](eval/retrieval_results.md).

**Chunking strategy is worth more than the embedding model.** The curriculum chunker
splits by course record into parent chunks, then into per-unit children that carry their
course label — retrieval searches children and hydrates the parent:

| Curriculum (548 chunks, 16 queries) | R@1 | R@5 | MRR | right course @1 |
|---|---|---|---|---|
| **parent–child + course label** (production) | **93.8** | **100.0** | **0.950** | **100.0** |
| flat: unit body only | 68.8 | 87.5 | 0.794 | 87.5 |

That is **+25 points of R@1** from structure alone, and it eliminates the classic failure
mode of retrieving "Unit 3: Normalization" with no idea which course it came from.

| Policy corpus (226 clause chunks, 32 queries) | R@1 | R@3 | R@5 | MRR |
|---|---|---|---|---|
| clause-aware chunking, dense | **96.9** | **100.0** | **100.0** | **0.984** |

A **Matryoshka dimension sweep** shows 1024 → 512 dims halves the index with no measurable
quality loss (policy R@1 96.9 → 96.9; curriculum unchanged at 93.8), while 128 dims starts
to cost recall.

A negative result is recorded too: the Jina API **silently ignores `late_chunking`** for
`v5-omni-small` (stored vectors and an independent re-embedding differ by ≤ 2.5e-03), so
the late-vs-naive comparison is made on `v3`, which honours it.

---

## How it works

**Three-call turn** ([orchestrator.py](backend/app/ai/orchestrator.py)) — route → plan →
execute → synthesize. Call A sees only a role-filtered tool *index* (name + one line) and
narrows to 2–4 candidates; Call B gets full schemas for just those; Call C gets no tool
schemas at all and therefore cannot call tools. Splitting the turn keeps each call inside
the free-tier token ceiling and makes routing more accurate by shrinking the decision
space. A fast path skips Call B for smalltalk and no-argument tools.

**Three RBAC layers** ([registry.py](backend/app/ai/tools/registry.py)) — all below the model:

1. **Exposure** — `visible_to(role)` filters the catalog *before* the LLM sees it. The model is never told a tool it cannot use exists.
2. **Execution** — `invoke()` re-checks the role on every call; wrong role → denied + audit row.
3. **Identity** — caller-supplied `student_id` / `roll_no` / … are *dropped* for non-admins; the tool reads identity from `AuthContext`.

Every invocation writes an `audit_log` row in its own transaction, so the record survives
a rolled-back request. Document-level RBAC is a SQL pre-filter on `documents.audience_roles`
in both retrieval branches, so a restricted circular never surfaces to a student.

**RAG** — `docs/manifest.yaml` declares `doc_type` per file; ingest dispatches to a chunker:
`policy` (clause-aware, ~400 tok), `curriculum` (course record → unit children, also
extracted relationally so "how many credits is DBMS?" is an exact tool call, not retrieval),
`tabular` (rows extracted to `academic_calendar`), `notice` (single chunk). Retrieval is
**hybrid**: pgvector cosine top-20 ∪ Postgres full-text top-20, fused by Reciprocal Rank
Fusion (k=60) — hybrid matters because policy questions carry exact tokens ("§4.2",
"condonation") that dense retrieval alone handles poorly. Call C emits `[[cite:<id>]]`,
resolved server-side to `{doc_title, section, page, snippet}`.

**Two-phase writes** — the 8 action tools return a preview plus an HMAC-signed, 5-minute
token; `POST /api/chat/confirm` re-checks RBAC and only then executes. A model that emits
`"confirmed": true` has it silently stripped.

**Free-tier survival is a feature** ([budget.py](backend/app/ai/budget.py)) — a process-wide
token bucket (Groq limits are per *organisation*), exponential backoff honouring
`retry-after`, and a per-turn meter. Waiting is surfaced to the UI as a "queued" state
rather than hidden as an error.

**Live quality signals** ([scoring.py](backend/app/ai/scoring.py)) — every answered turn is
scored deterministically with no LLM judge: context precision, citation coverage, numeric
grounding (is "68%" actually in the tool results?), and tool success. The dev trace panel
shows them live.

---

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11 · FastAPI · SQLAlchemy 2.0 · Alembic |
| DB + vectors | PostgreSQL 16 + pgvector (`docker compose up`) |
| Frontend | React + Vite + TypeScript |
| LLM | Groq free tier, OpenAI-compatible — `openai/gpt-oss-120b` |
| Embeddings | Jina API, `jina-embeddings-v5-omni-small`, 1024-dim |
| Email | SMTP — Mailpit sandbox locally, real provider in demo |

---

## Quickstart

```bash
cp .env.example .env                     # adjust if needed

docker compose up -d                     # Postgres 16 + pgvector on :5434, Mailpit on :8025

cd backend
python -m venv .venv
.venv\Scripts\activate                   # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt

alembic upgrade head                                   # 35-table schema
python -m app.seed.load_csv --dataset sample --reset   # loads data/synthetic/sample/
python -m app.ai.rag.ingest                            # 18 docs -> 2,723 chunks (needs JINA_API_KEY)

pytest                                   # 434 tests, no LLM key needed
uvicorn app.main:app --reload            # http://localhost:8000/health
```

```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173
```

Dependency gates (from `backend/`, venv active):

```bash
python -m app.ai.rag.embedder --selftest   # one real Jina call; prints model + dim (1024)
python -m app.main --check-models           # validates Groq model ids (skips without a key)
```

Every synthetic user's password is `uniassist`:

```bash
curl -s localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"25bcp001@sot.pdpu.ac.in","password":"uniassist"}'
curl -s localhost:8000/api/me       -H "Authorization: Bearer <token>"
curl -s localhost:8000/api/me/tools -H "Authorization: Bearer <token>"   # RBAC layer 1
```

Run the evaluation (from `backend/`; needs `LLM_API_KEY`, `--dry-run` validates the set offline):

```bash
python -u ../eval/run_eval.py --dry-run                      # no LLM calls
python -u ../eval/run_eval.py --out ../eval/results.json     # full 83 cases, ~30 min
python -u ../eval/retrieval_experiments.py                   # Jina only, ~3 min
```

---

## Repo layout

```
docker-compose.yml       postgres:16 + pgvector, mailpit
backend/
  alembic/               migrations
  app/
    main.py              FastAPI app, CORS, GET /health
    config.py            pydantic-settings
    api/                 auth, me, chat (+ /stream, /confirm)
    auth/                JWT, AuthContext
    models/              35 ORM models
    seed/                CSV -> Postgres loader
    notify/              SMTP transport, mailer, redirect guard
    ai/
      orchestrator.py    the three-call turn
      budget.py          token bucket, 429 backoff, per-turn meter
      scoring.py         reference-free quality signals
      prompts/           Call A / B / C system prompts
      providers/         OpenAI-compatible client
      tools/             registry (3 RBAC layers) + 42 tools + two-phase confirm
      rag/               manifest, parsers, chunkers/, embedder, retriever, citations
  tests/                 434 tests, fully offline
eval/
  golden_set.yaml        80 end-to-end cases
  run_eval.py            turn-level harness
  retrieval_set.yaml     48 gold retrieval queries
  retrieval_experiments.py  chunking + dimension ablations
  retrieval_results.md   results
frontend/src/            React + Vite + TS
data/                    synthetic dataset + source PDFs
docs/                    manifest.yaml + the policy / notice / calendar corpus
scripts/                 synthetic data generator
```
