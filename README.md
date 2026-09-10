# UniAssist — Role-Aware AI University Management Assistant

A conversational assistant that behaves differently for **students**, **faculty**, and
**admins** — identity, permissions, and data scoping are enforced server-side, not
prompted. Combines a typed-tool database layer (no text-to-SQL), RAG with citations over
university regulations, and two-phase confirmed write actions.

See [`plan.md`](plan.md) for the full architecture and build plan, and
[`DATA_MODEL_EXPLANATION.md`](DATA_MODEL_EXPLANATION.md) for the 24-table dataset.

## Status

Phase 1b — auth & RBAC done.

- **Phase 1a:** 30-table schema (SQLAlchemy 2.0 models from the actual
  `data/synthetic/sample/*.csv` headers — see [SCHEMA_MAP.md](SCHEMA_MAP.md)),
  initial Alembic migration (`CREATE EXTENSION vector`, HNSW + GIN + composite
  indexes), CSV → Postgres loader.
- **Phase 1b:** `POST /api/auth/login` (email + `uniassist`) → JWT; `AuthContext`
  built server-side from `users.subject_ref`; the three RBAC layers (tool
  exposure / execution guard / identity-arg stripping) in
  [app/ai/tools/registry.py](backend/app/ai/tools/registry.py) with `audit_log`
  writes; a starter set of RBAC-guarded tools; `GET /api/me`, `GET /api/me/tools`.

`pytest` — 56 tests (load/schema + auth + the RBAC suite, which must stay green).

Next: Phase 2 — tool registry fan-out, Groq provider, the three-call orchestrator.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11 · FastAPI · SQLAlchemy 2.0 · Alembic |
| DB + vectors | PostgreSQL 16 + pgvector (`docker compose up`) |
| Frontend | React + Vite + TypeScript |
| LLM | Groq free tier, OpenAI-compatible (from Phase 2) |
| Embeddings | `jinaai/jina-embeddings-v5-omni-small`, 1024-dim, local (from Phase 3) |

## Quickstart

```bash
cp .env.example .env                     # adjust if needed

docker compose up -d                     # Postgres 16 + pgvector on :5432

cd backend
python -m venv .venv
.venv\Scripts\activate                   # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt

alembic upgrade head                     # creates the 30-table schema
python -m app.seed.load_csv --dataset sample --reset   # load data/synthetic/sample/
pytest                                   # 40 tests
uvicorn app.main:app --reload            # http://localhost:8000/health
```

Phase-0 dependency gates:

```bash
python -m app.ai.rag.embedder --selftest   # prints configured dim (1024)
python -m app.main --check-models           # validates Groq model ids (skips w/o key)
```

Try the auth flow (every synthetic user's password is `uniassist`):

```bash
curl -s localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"25bcp001@sot.pdpu.ac.in","password":"uniassist"}'
curl -s localhost:8000/api/me       -H "Authorization: Bearer <token>"
curl -s localhost:8000/api/me/tools -H "Authorization: Bearer <token>"   # RBAC layer 1
```

```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173
```

## Repo layout

```
docker-compose.yml       postgres:16 + pgvector
.env.example
backend/
  requirements.txt
  alembic/               migrations (env.py wired to app.config + app.db.base)
  app/
    main.py              FastAPI app, CORS, GET /health
    config.py            pydantic-settings
    db/                  engine, session, DeclarativeBase
    models/              ORM models — next part
    seed/                CSV -> Postgres loader — next part
frontend/                Vite + React + TS
data/                    synthetic dataset + source syllabus PDFs
scripts/                 synthetic data generator
```
