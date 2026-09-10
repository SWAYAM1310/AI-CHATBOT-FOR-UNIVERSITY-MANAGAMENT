# UniAssist — Role-Aware AI University Management Assistant

A conversational assistant that behaves differently for **students**, **faculty**, and
**admins** — identity, permissions, and data scoping are enforced server-side, not
prompted. Combines a typed-tool database layer (no text-to-SQL), RAG with citations over
university regulations, and two-phase confirmed write actions.

See [`plan.md`](plan.md) for the full architecture and build plan, and
[`DATA_MODEL_EXPLANATION.md`](DATA_MODEL_EXPLANATION.md) for the 24-table dataset.

## Status

Phase 0 — scaffold. Backend skeleton (FastAPI + SQLAlchemy 2.0 + Alembic), Postgres 16
+ pgvector via Docker, and a Vite/React/TS frontend stub. **No schema or data yet** —
that is the next part (authoritative models + CSV loader for `data/synthetic/sample/`).

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

alembic upgrade head                     # no migrations yet — added next part
uvicorn app.main:app --reload            # http://localhost:8000/health
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
