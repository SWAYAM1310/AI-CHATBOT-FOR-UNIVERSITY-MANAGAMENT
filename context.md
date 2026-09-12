# UniAssist — build context (resume here)

Snapshot for picking the work back up. Last updated **2026-09-12, end of the
live smoke test (5c)**. Phases 0–5a complete and committed (`89c5ecc`); the 5c
fixes below are **uncommitted** unless a later commit says otherwise. Groq key
set; the live path is verified for all three roles, the confirm flow and
curriculum/calendar questions (§11). Next: **5b eval harness**.

---

## 1. What this project is

**UniAssist** — a role-aware AI university management assistant. The *same* chatbot
behaves differently for **students / faculty / admins** because identity,
permissions, and data scoping are enforced **server-side**, never prompted.

Three things that make it more than a wrapper (the demo/report story):
1. **Personalized grounding** — "the rule is 75%" → "you're at 68%, 7 points short",
   with a citation to the actual regulation.
2. **Provable RBAC** — a forbidden tool is never even offered to the model.
3. **Confirmed actions** — DB writes go through a two-phase confirm step.

Authoritative design docs in the repo:
- [`plan.md`](plan.md) — full 6-phase architecture & build plan.
- [`DATA_MODEL_EXPLANATION.md`](DATA_MODEL_EXPLANATION.md) — the 24-table dataset,
  table by table, and the relational pathways.
- [`SCHEMA_MAP.md`](SCHEMA_MAP.md) — where the built ORM deliberately diverges from
  `plan.md §2` (the CSVs won; `plan.md §2` is stale on names).

**Stack (locked in):** Python 3.11 · FastAPI · SQLAlchemy 2.0 · Alembic ·
PostgreSQL 16 + pgvector · React + Vite + TS · Groq free tier (OpenAI-compatible,
`openai/gpt-oss-120b` + `-20b`) · local `jina-embeddings-v5-omni-small` (1024-dim)
on an RTX 3050.

**GitHub:** https://github.com/SWAYAM1310/AI-CHATBOT-FOR-UNIVERSITY-MANAGAMENT
(repo name has a typo — "MANAGAMENT"; user aware, left as-is). Push with plain
`git push` (credential cached).

---

## 2. Environment facts

- OS: Windows 11, PowerShell + Git Bash. Repo at `E:\ALL PROJECTS\University Assistant`.
- Toolchain already installed: Python 3.11.9 (`py -3.11`), Node 25.6.1, Docker 29.1.3.
- **A native PostgreSQL service already owns host port 5432.** The project's
  Postgres container is therefore mapped to **host port 5433** — do not change back.
- Run backend commands from `backend/` using the venv interpreter:
  `./.venv/Scripts/python.exe -m ...`
- **Groq key is set** (2026-09-12) in `backend/.env` as `LLM_API_KEY` (that file
  overrides the repo-root `.env`, whose `LLM_API_KEY` stays empty). `python -m
  app.main --check-models` passes for `openai/gpt-oss-120b` + `-20b`. Note:
  Groq's edge returns **403 to urllib's default User-Agent** — the gate now
  sends `User-Agent: uniassist/0.1`; the OpenAI-SDK provider was never affected.
- **Run the app**: `docker compose up -d` (DB, host port 5433) · `cd backend &&
  ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000` · `cd frontend
  && npm run dev` → http://localhost:5173 (Vite proxies `/api`). Demo accounts
  on the sign-in page, password `uniassist`.

---

## 3. What's done (commits on `main`)

| Commit | Phase | Contents |
|---|---|---|
| `a5beafc` | — | Initial commit: planning docs, synthetic-data generator, sample dataset, source PDFs |
| `fb00321` | 0 | Scaffold: `docker-compose.yml`, `backend/` skeleton, `frontend/` Vite stub |
| `76fb601` | 1a | 30-table schema, initial migration, CSV loader, 40 tests |
| `3a24ee9` | 1b | JWT auth, AuthContext, 3-layer RBAC + audit log, starter tools, 56 tests |
| `db77b18` | 2.1 | student SELF read tools + shared tools |
| `d517520` | 2.2 | OpenAI-compatible LLM provider (Groq default) |
| `b816420` | 2.3–4 | three-call orchestrator + token budget / 429 backoff |
| `9c54a8e` | 2.5 | `POST /api/chat` with persisted conversations |
| `80558dc` | 2.6 | offline CI + no-key guard test |
| `c3ec74d` | 2.7a | faculty OWN_COURSES tools |
| `24f1566` | 2.7b | admin UNIVERSITY tools incl. bounded `run_analytics` |
| `ba8befd` | 2.7c | 8 action tools + two-phase confirm + `POST /api/chat/confirm` |
| `96ea994` | 3.0 | 7 synthetic policy docs (md + pdf) + `docs/manifest.yaml` |
| `e117c91` | 3.1 | manifest loader, PDF parsers, ingest skeleton, full-text policy search |
| `5ad9f5e` | 3.2 | Jina API embedder, vectors in ingest, 285 tests |
| `150d524` | 3.3 | clause-aware policy chunker, 305 tests |
| `90af19f` | 3.4 | hybrid retriever (RRF) + numbered citations + router `rag_query`, 319 tests |
| `6ea7bcd` | 3.5a | curriculum parser + parent/child chunker + per-course late chunking, 339 tests |
| `b5e70b9` | 3.5b | syllabus tables + relational extract + curriculum tools + citable tool passages, 355 tests |
| `c00183f` | 3.6 | calendar + notices corpus, tabular extract → academic_calendar, notice chunker, 373 tests |
| `c8c6259` | 4 | gap-check: all 40 planned tools present; `run_analytics` gains `failure_rate`, 378 tests |
| `87bdbcf` | 5a.1 | frontend part 1: API client, login, chat with footnote citations + confirm card |
| `f276164` | 5a.2 | frontend part 2: conversation rail + role-specific suggested prompts + UX audit |
| `7f4fc10` | 5a.3 | typed data cards (backend `app/ai/cards.py` + API `trace`) and their renderers, 380 tests |
| `ebd590d` | 5a.4 | dev tool-trace panel, 429 auto-retry, frontend README (pushed; origin was 11 commits behind) |
| `b86d93c` | 5c.0 | model gate User-Agent fix; cite-marker variants (`【cite:id】`, `[cite:id]`) resolved |
| `f5c716b` | 5c.1 | `POLICY_CONTEXT`: personal-record tools always pull their regulation |
| `7cc5438`, `380eba5` | 5c.2 | faculty course tools accept no course (all taught); provider errors logged |
| `89c5ecc` | 5c.3 | provider retries once with a no-tools note on Groq `tool_use_failed`, 383 tests |
| *(uncommitted)* | 5c.4 | acronym course lookup + citable syllabus, salvage Groq `failed_generation` (phantom tool calls, broken JSON mode), syllabus routing rule, own-dept-first curriculum search, 388 tests |

### Phase 0 — scaffold
- `docker-compose.yml`: `pgvector/pgvector:pg16`, host port **5433**, healthcheck,
  named volume `uniassist_pgdata`.
- `backend/app/`: `config.py` (pydantic-settings, reads repo-root `.env`),
  `db/{base,session}.py` (engine, `SessionLocal`, `Base`), `main.py`
  (FastAPI app, CORS, `GET /health` = DB ping).
- `.env.example` → copy to `.env`. `.env` is git-ignored; `.env.example` tracked.
- `frontend/`: unmodified Vite React-TS template; `npm install` + `npm run build` pass.

### Phase 1a — database foundation
- **Models** in `backend/app/models/` (30 tables), grouped:
  `identity.py` (users, students, faculty, admins, departments) ·
  `academic.py` (subjects, curriculum, classrooms, teaching_assignments,
  course_offerings, enrollments, timetable_slots) ·
  `assessment.py` (attendance_sessions, attendance_records, assessments, marks,
  submissions, results_semester, exam_schedule) ·
  `administration.py` (fees, scholarships, leave_requests, document_requests,
  announcements, academic_calendar) ·
  `ai.py` (conversations, messages, documents, doc_chunks, audit_log).
  - 24 data tables mirror the real `data/synthetic/sample/*.csv` **headers**
    (denormalised mirror columns kept as-is). 5 AI-layer tables from `plan.md §2`.
  - `doc_chunks.embedding` = `Vector(settings.embedding_dim)` (1024, from config,
    not hard-coded). `parent_chunk_id` self-FK. `tsv` = `TSVECTOR`.
  - Circular `departments.hod_faculty_id ↔ faculty.dept_id` → both FKs `use_alter`.
- **Migration** `backend/alembic/versions/5480cd62d6a6_initial_schema.py`:
  autogenerated then hand-edited to add `CREATE EXTENSION IF NOT EXISTS vector`
  at the top of `upgrade()`, `DROP EXTENSION` at the end of `downgrade()`, and
  `import pgvector` / `from app.config import settings`. Reversible (verified
  `downgrade base` → `upgrade head`). Indexes: HNSW on `doc_chunks.embedding`
  (`vector_cosine_ops`, m=16 ef_construction=64), GIN on `doc_chunks.tsv`,
  composite on `attendance_records(student_id, session_id)` and
  `enrollments(offering_id, student_id)`.
- **Loader** `backend/app/seed/load_csv.py`:
  `python -m app.seed.load_csv --dataset sample|full --reset` (default `sample`).
  FK-dependency `LOAD_ORDER`; type coercion (bools, ISO dates via
  `date.fromisoformat` which tolerates 2-digit-year DOBs like `0018-03-15`,
  `HH:MM` times, `...THH:MM:SS` datetimes, blank → NULL, money/gpa → Numeric);
  `departments` loaded with `hod_faculty_id` NULL then patched after `faculty`;
  identity sequences bumped past `MAX(id)`.
- **Gate stubs**: `python -m app.ai.rag.embedder --selftest` (prints dim 1024;
  real Jina load is Phase 3); `python -m app.main --check-models` (hits Groq
  `/models`, skips if no key).
- **Sample dataset fix**: `scripts/generate_synthetic_data.py`
  `SAMPLE_STUDENT_COUNTS["CP"]` bumped 16 → 22 so the planted demo rolls
  `25BCP017` (the ~68%-attendance signature demo) and `25BCP021` exist in the
  subset. `data/synthetic/sample/` regenerated; its README's planted-cases
  section is now accurate (`24BCP009` is a 2024-batch roll, correctly noted
  as sample-absent — 3 of the 4 pending-leave demo rolls are present).

### Phase 1b — auth & RBAC
- `backend/app/auth/`:
  - `security.py` — `verify_password` / `hash_password` for the dataset's
    `pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>` format. **Every synthetic
    user's password is `uniassist`.**
  - `tokens.py` — PyJWT `create_access_token` / `decode_access_token`. Token
    payload carries only `sub`, `subject_ref`, `role`, `iat`, `exp`.
  - `context.py` — `Role` enum; `AuthContext` frozen dataclass (`user_id`, `role`,
    `subject_ref`, `term`, `student_id|faculty_id|admin_id`, `dept_id`, `is_hod`);
    `build_auth_context(payload, db)` re-derives everything from the DB and rejects
    identity mismatches.
  - `deps.py` — `get_db`, `get_auth_context` (Bearer → 401 on bad/expired),
    `require_roles(*roles)`.
- `backend/app/ai/tools/registry.py` — the RBAC core:
  - `Scope` enum (`SELF`, `OWN_COURSES`, `OWN_DEPARTMENT`, `UNIVERSITY`).
  - `@tool(name, description, allowed_roles, scope)` registers a `ToolSpec` in
    module-level `REGISTRY`. Tool fns take `(*, ctx, db, **kwargs)`.
  - `REGISTRY.visible_to(role)` / `index_for(role)` = **Layer 1**.
  - `REGISTRY.invoke(name, ctx, db, args)`:
    - **Layer 2** — role not in `allowed_roles` → `audit('denied')` + raise `ToolDenied`.
    - **Layer 3** — for non-admins, pop any `IDENTITY_ARGS`
      (`student_id, faculty_id, admin_id, user_id, roll_no, employee_id,
      subject_ref`); if any were present the decision is `arg_stripped`. Admins
      may pass them (cross-user).
    - Runs the tool, writes an `audit_log` row **in its own `SessionLocal()`
      transaction** (survives request rollback), returns the result.
- `backend/app/ai/tools/builtin.py` — starter real tools:
  `get_my_profile` (student/faculty, SELF), `get_my_attendance` (student, SELF),
  `list_course_students` (faculty/admin, OWN_COURSES),
  `list_students_below_attendance` (faculty/admin, OWN_COURSES). Faculty-scoped
  helpers filter `course_offerings.faculty_id == ctx.faculty_id`.
- `backend/app/api/`: `auth.py` = `POST /api/auth/login` (`{email, password}` →
  `{access_token, role, subject_ref}`); `me.py` = `GET /api/me` (context + profile
  via the tool) and `GET /api/me/tools` (Layer-1 index). Routers wired in `main.py`.
- Config added: `jwt_secret` (dev default is 39 chars to satisfy the HMAC
  key-length check), `jwt_algorithm`, `jwt_expire_minutes`, `current_term`
  (`2026-27-ODD`, matches `scripts/academic_data.py`).

---

## 4. How to run (from a cold machine)

```bash
# 0. Docker Desktop must be running.
cd "E:/ALL PROJECTS/University Assistant"
cp .env.example .env

docker compose up -d                      # Postgres on host :5433, wait ~10s for healthy

cd backend
py -3.11 -m venv .venv                     # first time only
./.venv/Scripts/python.exe -m pip install -r requirements.txt

./.venv/Scripts/python.exe -m alembic upgrade head
./.venv/Scripts/python.exe -m app.seed.load_csv --dataset sample --reset
./.venv/Scripts/python.exe -m pytest                       # expect 56 passed
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload  # :8000/health, /docs
```

Auth smoke test (any user, password `uniassist`):

```bash
curl -s localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"25bcp001@sot.pdpu.ac.in","password":"uniassist"}'
curl -s localhost:8000/api/me       -H "Authorization: Bearer <token>"
curl -s localhost:8000/api/me/tools -H "Authorization: Bearer <token>"
```

Frontend (stub, not wired to the API yet): `cd frontend && npm install && npm run dev`.

---

## 5. Current state / gotchas

- DB container is up and loaded with the **sample** dataset. `alembic current`
  should be `5480cd62d6a6`.
- `pytest` **auto-loads the sample and truncates `audit_log`** at session start
  (`tests/conftest.py::_loaded_db`), so running tests resets DB data. `make_ctx()`
  in `conftest.py` builds an `AuthContext` straight from the DB for RBAC tests.
- Sample data facts used by tests: `24CS201T` (DBMS) offering is taught by
  **faculty id 2**; faculty id 1 teaches `24CS202T` (Digital Logic), not DBMS.
- Known cosmetic warnings (ignored): FastAPI `TestClient` httpx/starlette
  deprecation; nothing actionable.
- `data/synthetic/*.csv` (full ~2M-row set) is git-ignored and reproducible:
  `./backend/.venv/Scripts/python.exe scripts/generate_synthetic_data.py` (no flag
  = full; `--sample` = subset). Seed 42, deterministic.
- **Secrets:** `backend/.env` holds `JINA_API_KEY` (git-ignored; settings read
  it on top of the root `.env`). `LLM_API_KEY` (Groq) is still empty — the
  live LLM path has never been run; everything is tested with scripted
  providers. Jina IS live: `python -m app.ai.rag.embedder --selftest`.
- **RAG store state:** `documents` / `doc_chunks` hold the 7 policies as
  page-level chunks with real v5 vectors (`python -m app.ai.rag.ingest
  --doc-type policy`). These tables are not touched by the CSV loader's
  `--reset`; `tests/test_rag_ingest.py` truncates and re-ingests them, and
  `test_rag_embedder.py` overwrites the attendance doc's vectors with the
  fake — so **after running the suite, re-run the ingest with `--force`**
  before a live demo.
- Run the suite: `cd backend && .venv/Scripts/python.exe -m pytest tests -q
  -p no:warnings` → 285 passed (~18 s). `python` on PATH is the Windows Store
  interpreter without the deps — always use the venv one.
- Editing files from a script on Windows: always pass `encoding="utf-8"` and
  `newline="
"`; the default cp1252 codec corrupted a `§` once.

---

## 6. Planted demo edge cases (in the sample)

- **~68% attendance**: student `25BCP017` in `24CS201T` (DBMS), current term — the signature demo.
- **~35% Internal-1 fail rate**: `24CS202T` (Digital Logic and Design), current term.
- **missing Assignment 2**: ~18% of the `24CS201T` cohort (`submissions.status='missing'`).
- **unpaid fees + pending scholarship**: student `25BCP012`.
- **pending leave requests** (for `decide_leave_request`): `25BCP003`, `25BCP021`,
  `25BIT004` (`24BCP009` is 2024-batch, not in the sample).

All five are asserted by `backend/tests/test_load.py`.

---

## 7. Phase 2 — the orchestrator (complete)

Per `plan.md §3`, §4, §6.

### Step 1 — DONE: student + shared read tools
- `backend/app/ai/tools/student_tools.py` — the 9 student `SELF`-scope read
  tools: `get_my_courses`, `get_my_timetable(day?)`, `get_my_marks(assessment_type?)`,
  `get_my_results(semester?)`, `get_my_exam_schedule`, `get_my_assignments(status?)`,
  `get_my_fees`, `get_my_scholarships`, `get_my_leave_requests`. All read identity
  from `ctx.student_id` only.
- `backend/app/ai/tools/shared_tools.py` — 3 shared tools, all roles:
  `search_university_policies(query)` (keyword `ILIKE` over `doc_chunks`; returns
  `[]` until the Phase-3 RAG ingest populates it — shape is final),
  `get_academic_calendar(event_type?)` (current term + term-less events),
  `get_my_announcements()` (audience-role match + university/department/course
  scope filtering via the caller's dept_code / enrolled or taught course codes).
- Wired into `backend/app/ai/tools/__init__.py` alongside `builtin`.
- `backend/tests/test_student_tools.py` — 12 new tests (Layer-1 visibility for
  both groups, Layer-3 identity-arg stripping, functional smoke per tool using
  student id **17** = roll `25BCP017`, which has 9 current-term enrollments).
  Full suite now **68 passed** (was 56).
- Committed as `db77b18`.

### Step 2 — DONE: the LLM provider layer
- `backend/app/ai/providers/base.py` — the provider-agnostic contract:
  `Msg` (TypedDict), `ToolCall`, `Usage` (addable, feeds `messages.tokens_in/out`),
  `LLMResponse` (text, tool_calls, usage, model, finish_reason, reasoning),
  the `LLMProvider` Protocol, the error types (`ProviderError`,
  `ProviderNotConfigured`, `ProviderRateLimited` w/ `retry_after`), and
  `parse_json_object()` — a fence/prose-tolerant parser for Calls A and B that
  returns `{}` rather than raising.
- `backend/app/ai/providers/openai_compat.py` — `OpenAICompatProvider`:
  - `chat(system, messages, model, tools?, reasoning_effort='low', temperature,
    max_tokens?, json_object?)`. `max_tokens` → `max_completion_tokens`;
    `tools` → also sets `tool_choice='auto'`; `json_object` → `response_format`.
  - **`max_retries=0` on the SDK client on purpose** — backoff w/ jitter belongs
    to `app/ai/budget.py` (step 4), which feeds the UI's "queued" state.
  - Error mapping: `RateLimitError` → `ProviderRateLimited` (parses the
    `retry-after` header); everything else under `openai.APIError` →
    `ProviderError`. A `BadRequestError` that names `reasoning_effort` retries
    once without that param, so a local Ollama/vLLM fallback still works.
  - Accepts an injected `client=` (tests use a fake; no key, no network).
- `backend/app/ai/providers/__init__.py` — `get_provider()`, `lru_cache`d so one
  HTTP client is reused. **Must be called per turn, never at import time**: it
  raises `ProviderNotConfigured` with no key, and the app has to boot without one.
- `requirements.txt` += `openai>=1.60` (installed 3.13.0 in the venv; it pulls
  `httpx2`, which also silenced the old TestClient deprecation warning).
- `backend/tests/test_providers.py` — 21 tests: request shaping, response/usage
  parsing, malformed tool-args degradation, error mapping, the reasoning_effort
  retry, missing-key refusal, and `parse_json_object`. Suite now **89 passed**.
- Still no Groq key in `.env`, so the live path is unexercised by design.

### Step 3 — DONE: the orchestrator
- `backend/app/ai/tools/schema.py` — closes the gap step 3 had to close first:
  `function_schema(spec)` builds the OpenAI function schema by introspecting the
  tool fn's own signature (`get_type_hints`, `str|None` → `string`, default
  present → optional), skipping `ctx`/`db`/`**_` **and every `IDENTITY_ARGS`
  name**, so the model is never shown a `student_id` field to fill in — Layer 3
  remains the enforcing check. Also `schemas_for(names, role)` (silently drops
  unknown/off-limits names — Call A is an LLM) and `required_params(spec)`.
- `backend/app/ai/compact.py` — `compact(result)` → Markdown table, `ROW_CAP=40`,
  and it states how many rows were hidden (a truncated table the model believes
  is complete is worse than none). `(no rows)` vs `(no data)` are distinct.
- `backend/app/ai/prompts/system.py` — `route_system` / `plan_system` /
  `synthesize_system` + `synthesize_user`. Carries plan.md §3's four rules
  (role, personalization, grounding, refusal). Rendered router prompt for a
  student ≈ 2.6k chars ≈ 650 tok, matching §4's ~600 tok budget line.
- `backend/app/ai/orchestrator.py` — `run_turn(question, ctx, db, history, provider)`
  → `TurnResult(text, citations, cards, tool_runs, usage, intent, path)`.
  A route (`json_object=True`) → fast path or B plan (tools=candidate schemas)
  → execute via `REGISTRY.invoke` → C synthesize (`reasoning_effort='medium'`,
  **no tools**). `path` is one of `full|fast|smalltalk|confirm`.
  - Candidate names from Call A are filtered against the registry *and* the
    role before use; a tool failure becomes a result row, never a 500.
  - `_confirmation_card()` is the two-phase-confirm hook (a tool returning
    `needs_confirmation` stops the turn and returns a preview card) — no action
    tools exist yet, so it is inert today.
  - `_retrieve()` runs `search_university_policies` through the registry so
    retrieval is audited too; top-3; `[]` until the Phase-3 ingest.
  - `_resolve_citations()` keeps only passages the answer actually cited.
  - **Provider errors propagate on purpose** — retry/backoff is step 4's job.
  - History trimmed to the last 3 user+assistant pairs.
- `search_university_policies`'s description lost its "(Placeholder…)" tail: a
  tool description is model-facing, so the caveat moved to the docstring.
- `backend/tests/test_orchestrator.py` — 22 tests with a scripted provider
  (offline, real DB): schema builder incl. "no identity arg in any schema",
  compaction incl. the row cap, full/fast/smalltalk paths, Call C gets no tools,
  Call B sees only the candidates, role-filtered router index, hallucinated
  names dropped, **Layer 2 still denies a planner-requested faculty tool**,
  **Layer 3 strips a planner-supplied `student_id`**, malformed route reply
  degrades, citation resolution, history trimming. Suite now **111 passed**.

### Step 4 — DONE: token budget, limiter, 429 backoff
- `backend/app/ai/budget.py`:
  - `TokenBucket(rate_per_min, capacity, clock, sleeper)` — thread-safe leaky
    bucket (FastAPI runs sync endpoints in a threadpool, so concurrent turns
    really do share it). `take()` returns seconds waited; `charge()` may drive
    the level negative on purpose (an under-estimate is paid by the next
    caller); `refund()` returns an over-estimate. Clock/sleeper are injected so
    tests fake time.
  - `estimate_tokens(system, messages, tools, max_tokens)` — chars/4 + per-message
    overhead + an **output allowance**, since TPM counts output too.
  - `backoff_delay(attempt, retry_after)` — **equal jitter** (half fixed, half
    random): full jitter can retry instantly and re-trip the limit, no jitter
    makes concurrent callers retry in lockstep. Honours `retry-after` when the
    server sent one. `with_backoff(call)` retries **only** `ProviderRateLimited`.
  - `BudgetedProvider(inner)` — a drop-in `LLMProvider`: estimate → take from
    the TPM and RPM buckets → call with backoff → reconcile estimate vs the
    billed usage → meter it. `Meter` tracks calls/usage/waited_seconds/rate_limited
    (the per-turn numbers for the report; also logged at INFO per call).
  - `queued_notifier(fn)` — a **ContextVar** context manager, because the
    provider is process-wide but the UI needing the "queued" state is one
    caller's. A waiting turn calls it instead of failing; a notifier that raises
    is swallowed. Waits under 0.5s are not reported.
  - `get_budgeted_provider()` — process-wide, lazily built (so the app still
    boots with no key). **The orchestrator now defaults to this**, so the 429
    path is live for every turn.
- `app/config.py` + `.env.example` += `LLM_TPM=6000`, `LLM_RPM=25`,
  `LLM_MAX_RETRIES=4`, `LLM_BACKOFF_BASE=1.0`, `LLM_BACKOFF_CAP=30.0`
  (below Groq's published ceiling — its limits are per *organisation*).
- `backend/tests/test_budget.py` — 23 tests on a fake clock that only moves when
  something sleeps, so a 30s backoff test runs in microseconds: bucket
  refill/clamp/overdraw/refund, estimation, jitter bounds and the cap, retry
  then succeed, give up and re-raise, non-429 errors not retried, pass-through,
  metering, estimate reconciliation both ways, queue-don't-fail, notifier
  scoping and a notifier that explodes. Plus one orchestrator test running a
  whole turn through `BudgetedProvider`. Suite now **135 passed**.

### Step 5 — DONE: `POST /api/chat`
- `backend/app/api/chat.py`, mounted in `main.py`:
  - `POST /api/chat {message, conversation_id?}` → `run_turn` → `{conversation_id,
    message_id, text, citations[], cards[], path, intent, usage{tokens_in,tokens_out},
    queued_seconds}`. First message creates the `conversations` row (title = first
    60 chars); every turn persists a `user` row and an `assistant` row with
    `tokens_in/out`, `tool_calls` (the executed runs, incl. any confirm `preview`)
    and `citations`.
  - **All-or-nothing per turn**: a provider failure persists nothing, so a
    client retry does not leave orphan user rows in the transcript.
  - **Stateless server**: history is rebuilt from `messages` (user/assistant
    text only — tool tables are not replayed) and trimmed by the orchestrator.
  - Provider errors → HTTP: exhausted 429 → **503 + `Retry-After`** (provider
    hint, else 30s); no key → 503; other `ProviderError` → 502. Waits absorbed
    by `BudgetedProvider` are collected via `queued_notifier` and returned as
    `queued_seconds` (+ `X-Queued-Seconds` header).
  - `get_provider()` is a FastAPI dependency so tests override it with the
    scripted provider — no live key in CI.
  - Someone else's `conversation_id` is a **404**, not 403 (existence not leaked).
  - Also `GET /api/chat` (my conversations) and `GET /api/chat/{id}` (transcript,
    confirm cards rebuilt from stored runs) — small, needed to resume a chat.
  - Message length capped at 2000 chars; blank messages are 422.
- `backend/tests/test_chat_api.py` — 11 tests: create + persist both rows with
  summed usage, owner comes from the JWT, second message replays stored history
  into Call A, title truncation, list/get/continue are owner-scoped, unknown id
  404 before touching the model, student→faculty tool via chat still blocked,
  exhausted 429 = 503 + Retry-After + nothing persisted, no-key 503 / other 502,
  queued wait reported, auth + validation. Suite now **146 passed**.

### Step 6 — DONE: offline CI
- `.github/workflows/backend-tests.yml` — pgvector Postgres service →
  `alembic upgrade head` → `pytest`, with `LLM_API_KEY` **deliberately empty**.
  A green run is the proof the suite (routing, RBAC, budget) is offline.
- `backend/tests/test_offline.py` — one guard: with no key the process-wide
  budgeted provider refuses at construction (`ProviderNotConfigured`) and caches
  nothing half-built. Note `get_provider` is `lru_cache`d — tests that touch it
  must `cache_clear()`.
- The rest of step 6's brief (mock the provider; routing picks the right tool;
  RBAC still blocks; budget respected) was already covered by
  `test_orchestrator.py` / `test_budget.py` / `test_chat_api.py`.
- README updated (was still saying 56 tests). Suite now **147 passed**.

### Step 7a — DONE: faculty OWN_COURSES tools
- `backend/app/ai/tools/faculty_tools.py` (registered in `tools/__init__.py`):
  `get_my_teaching_courses` (named so because `get_my_courses` is the student
  tool and the registry forbids duplicate names; the index is role-filtered so
  each role sees exactly one), `get_my_teaching_schedule(day?)`,
  `get_course_attendance_summary(course_code)` → dict or **None**,
  `list_missing_submissions(course_code, assessment?)` (missing + late),
  `get_course_marks_summary(course_code, assessment_type?)`,
  `identify_at_risk_students(course_code)` — attendance <75 / marks <40% of
  max / missing submissions, with a `reasons` string, worst first.
- All course tools gate through `builtin._faculty_offerings` (own
  `faculty_id` from AuthContext) → a course you don't teach yields `[]`/None,
  never an error. Course tools are `{FACULTY, ADMIN}`; the two "my" tools are
  faculty-only.
- **Bug fixed on the way**: `get_my_assignments` filtered
  `Assessment.type == "Assignment"` but the data has `Assignment-1/-2`, so it
  always returned `[]` and its test passed vacuously (`all()` on empty). Now
  `LIKE 'Assignment%'`; test asserts non-empty.
- `backend/tests/test_faculty_tools.py` — 18 tests: exposure per role, every
  faculty tool denied + audited for a student, every course tool empty for a
  non-teacher, **`faculty_id` arg stripped can't borrow a colleague's course**,
  summary ↔ below-threshold consistency, at-risk ↔ attendance agreement,
  filters, ordering. Suite now **165 passed**.

### Step 7b — DONE: admin UNIVERSITY tools
- `backend/app/ai/tools/admin_tools.py` (registered in `tools/__init__.py`),
  all `{ADMIN}` / `Scope.UNIVERSITY`: `get_enrollment_stats(dept?, semester?)`,
  `get_department_overview`, `get_course_performance(course?, dept?)`,
  `list_students(dept?, semester?, division?, min_cgpa?, max_cgpa?, hosteller?)`
  (capped at 100), `get_university_attendance_report(dept?, semester?,
  threshold=75)`, `get_faculty_workload(dept?)` (weekly hours from slot
  durations), `find_available_classrooms(date, start_time, end_time, room_type?)`
  (weekly timetable overlap; Sunday → `[]`; bad input → `{"error"}` row),
  `get_fee_collection_summary(dept?, term?)`, `run_analytics(metric, group_by,
  dept?, semester?)`.
- **`run_analytics` is bounded by construction**: `METRICS` (student_count,
  average_cgpa, average_attendance, average_marks_percent, fee_collection_rate,
  backlog_count) and `GROUP_BY` (department, semester, batch, division) are
  fixed maps to SQL expressions; anything else returns an `error` row listing
  what is allowed — no free-form SQL, no injection surface.
- Tools return `{"error": ...}` dicts for bad input rather than raising, so
  Call C can explain instead of the orchestrator logging "(tool failed)".
- `dept`/`course` args are upper-cased (the router often emits "cp").
- `backend/tests/test_admin_tools.py` — 39 tests: admin-only exposure, denied
  for student/faculty, aggregates reconciled against raw counts and against
  the faculty view of the same course, filters/caps/thresholds, classroom
  overlap + Sunday + bad input, fee arithmetic, **every metric × group_by
  combination runs**, enum refusal incl. an injection-shaped string.
  Suite now **204 passed**.

### Step 7c — DONE (uncommitted): action tools + two-phase confirm
- **Registry** (`tools/registry.py`): `ToolSpec.action` flag; `invoke(...,
  confirmed=False)` is a keyword of *invoke*, not a tool arg — a model-emitted
  `"confirmed": true` is popped and ignored, and `confirmed=True` is injected
  only into action tools (else `ValueError`). Phase-2 audit decision is
  `"confirmed"`. `schema.py` never emits `confirmed`.
- **`tools/confirm.py`**: `sign(user_id, tool, args)` → `<b64 payload>.<hmac>`
  over `(u, t, canonical args, exp, nonce)`; key = HMAC(jwt_secret,
  "uniassist-confirm-v1"); TTL `settings.confirm_token_ttl_seconds` (300).
  `verify(token, user_id, now?)` → `(tool, args)` or `TokenInvalid` /
  `TokenExpired` / `TokenUsed`; `consume(token)` retires the nonce (in-process
  set — a restart re-opens at most one TTL of replay, and every tool
  re-validates anyway). `pending(ctx, tool, args, preview)` is what a tool
  returns instead of writing.
- **`tools/action_tools.py`** — one code path per tool: validate → preview →
  `pending(...)` unless `confirmed`, then write + `{"done": True, "message"}`.
  Validation errors are `{"error": ...}`. Student (SELF): `apply_for_leave(from,
  to, reason)` (future, ≤10 days, no overlap with pending/approved),
  `request_document(doc_type, purpose?)` (fuzzy match to the 7 known types, no
  duplicate open request). Faculty (OWN_COURSES): `mark_attendance(course_code,
  date, absent_roll_nos?, slot_no?, division?, lab_group?)` (everyone present
  except the list; refuses future date / unknown roll / already recorded),
  `enter_marks(course_code, assessment, marks{roll: score})` (upsert, 0..max),
  `post_announcement(course_code, title, body)` (scope=course, audience=student).
  Faculty (OWN_DEPARTMENT): `list_pending_leave_requests` (read; HOD only) and
  `decide_leave_request(leave_request_id, approve|reject)` (HOD of the
  student's dept only). Admin (UNIVERSITY): `publish_notice(title, body,
  audience=all|student|faculty, dept?)`, `manage_user(email,
  activate|deactivate|reset_password)` (not self; reset returns a temp password).
- **`POST /api/chat/confirm {token, conversation_id?}`** in `api/chat.py`:
  verify (400 invalid / 410 expired / 409 used) → `_own_conversation` (404) →
  `REGISTRY.invoke(..., confirmed=True)` (403 on `ToolDenied` — RBAC re-checked
  at execution) → tool `error` → 409 with the reason, token left unconsumed →
  commit → optional assistant `Message` (content = tool message,
  `tool_calls=[{..., "executed": True}]`) → `consume`. **No LLM call.**
- Data facts used by tests: faculty 4 = HOD CP, 5 = HOD IT; leave request #4
  is pending for 25BCP021 (CP); student 17's user email
  `25bcp017@sot.pdpu.ac.in`.
- Tests: `test_action_tools.py` (40) — 8 flagged actions, `confirmed` absent
  from every schema, model-supplied flag dropped, denial with confirmed, token
  round-trip/tamper/user-binding/expiry/single-use, **preview pass writes
  nothing for all 8**, per-tool validation + execution + a replay refused by
  re-validation; `test_confirm_api.py` (8) — chat turn stops on the card
  (2 model calls), card survives transcript reload, confirm executes with no
  model call and files an assistant row, 409 on reuse, 400/410/403/404 paths,
  stale-facts 409. Tests undo their own writes. Suite now **252 passed**.

## 8. Phase 3 — RAG (in progress)

Per `plan.md §8`. Embeddings via the **Jina API** (not a local model — user's
decision); `JINA_API_KEY` in `backend/.env`, needed from step 2 onward.

### Step 0 — DONE: synthetic policy corpus + manifest
- No policy documents existed in the repo (only 6 curriculum PDFs under
  `data/`). Wrote 7 institution-neutral ("the University" / "School of
  Technology") policies in `docs/policies/*.md`, every number taken from
  `scripts/academic_data.py` / the CSVs: attendance (75% floor §4.2,
  condonation ≥65% §5.2, worked 68% example §6, `excused_leave` counts),
  examination (assessment scheme = `ASSESSMENT_TEMPLATE`, 40% pass, grade
  table, form window 12–20 Oct, exams 17–28 Nov, results 18 Dec, revaluation
  15 days), fees (₹1,52,500 / ₹2,14,500 hosteller, due 12 Sep, ₹500/week late,
  overdue = 30 days), scholarships (the 7 schemes + amounts, pending doesn't
  defer fees), leave (≤10 days/request, no overlap, HOD decides — mirrors
  `apply_for_leave`/`decide_leave_request`), student services (8 doc types,
  one open request per type — mirrors `request_document`), code of conduct /
  anti-ragging.
- `scripts/render_policies.py` renders them to `docs/policies/pdf/*.pdf`
  (PyMuPDF `Story`, deterministic page breaks; 3–4 pages each; the 75% clause
  is on p.2). PDF text carries ligatures (`ﬃ`) → ingest must NFKC-normalise.
- `docs/manifest.yaml`: 7 policies + 6 curricula with `doc_type`, `category`,
  `audience_roles`, `effective_date`; paths relative to repo root.
- requirements: pymupdf, pdfplumber, pyyaml, markdown.

### Step 1 — DONE: manifest + parsers + ingest skeleton
- `app/ai/rag/manifest.py` — `load_manifest()` → `ManifestEntry(path, title,
  doc_type, audience_roles, category?, dept_code?, effective_date?)`;
  `ManifestError` on missing file / unknown doc_type / bad role / duplicate.
  `entry.source_path` = repo-relative posix path = the key in
  `documents.source_path`.
- `app/ai/rag/parsers.py` — `parse_pdf()` → pages (1-based) with NFKC +
  whitespace `normalize()`; `extract_tables()` via pdfplumber (lazy import).
- `app/ai/rag/ingest.py` — `ingest(entries, force?, doc_type?)` →
  `IngestReport`; `ingest_one()` upserts the `Document` (`version` = file
  SHA-256 → unchanged files skipped), drops old chunks (unlinking
  `academic_calendar.source_chunk_id` and the parent self-FK first), writes
  `ChunkDraft`s with `tsv = to_tsvector('english', ...)`, **embedding NULL**.
  `CHUNKERS: dict[doc_type, Chunker]` — empty for now, `page_chunks` fallback;
  steps 3/5/6 register into it. One transaction per document. CLI:
  `python -m app.ai.rag.ingest [--doc-type policy] [--force]`.
- `search_university_policies` is now real: `websearch_to_tsquery` +
  `ts_rank_cd`, **filtered by `documents.audience_roles @> role`**, returns
  `page`. Ranking is crude with page-sized chunks (step 3/4 fix it).
- Policies ingested: 7 docs, 25 page-chunks. `tests/test_rag_ingest.py` (19):
  manifest validation, ligature folding, page numbers (§4.2 on p.2), tables,
  idempotence/force/changed-file, per-file failure isolation, parent links,
  audience filter. Old "empty doc store" test retargeted. Suite **271 passed**.
- Note: `documents`/`doc_chunks` are NOT truncated by the CSV loader's
  `--reset`; the ingest test module truncates them itself.

### Step 2 — DONE: Jina API embedder + vectors in ingest
- **Model: `jina-embeddings-v5-omni-small` via `https://api.jina.ai/v1/embeddings`**
  — served by the API, 1024-dim (schema unchanged), supports `task` and
  `late_chunking`. (v3 = 1024, v4 = 2048 also served.) `api_model_name()`
  strips a `jinaai/` HF prefix from `EMBEDDING_MODEL`.
- Config: `jina_api_key`, `jina_base_url`; **settings now read both repo-root
  `.env` and `backend/.env` (the latter overrides)** — the key lives in
  `backend/.env`.
- `app/ai/rag/embedder.py`: `Embedder` Protocol; `JinaEmbedder` —
  `embed_documents(texts, late_chunking=False)` (one request for a whole
  late-chunked document, else batches of 32, `task=retrieval.passage`),
  `embed_query(text)` (`task=retrieval.query`, LRU cache 512 by text hash),
  retries 429/5xx with Retry-After or `budget.backoff_delay`, `EmbeddingError`
  / `EmbeddingNotConfigured`, `.calls` / `.tokens_used` meters.
  `FakeEmbedder` = deterministic hashed bag-of-words (offline tests/CI).
  `get_embedder()` lazy singleton. `--selftest` does one real call.
- `ingest(..., embedder=None|Embedder)`: vectors computed **before** the old
  chunks are dropped; `LATE_CHUNKED = {policy, notice}` → one late-chunked
  call per document; `embedding_model` recorded. CLI embeds by default when a
  key is present, `--no-embed` for text-only.
- Policies re-ingested with real vectors (25 chunks, ~1 call/doc). Dense
  top-1 already picks the right document for every probe question.
- `tests/test_rag_embedder.py` (14, MockTransport): task asymmetry, late
  chunking = one request, batching, cache, retry/backoff bounds, malformed
  responses, order restoration, no-key, fake determinism, ingest writes
  vectors / NULL without embedder / failure keeps previous chunks.

### Step 3 — DONE: clause-aware policy chunker
- `ChunkDraft` / `Chunker` / `CHUNKERS` / `page_chunks` moved to
  `app/ai/rag/chunkers/base.py` (re-exported from `ingest`). Reason: a chunker
  importing `app.ai.rag.ingest` while `python -m app.ai.rag.ingest` runs it as
  `__main__` registered into a *second* copy of the module — the CLI kept
  page-chunking. `ingest` now imports the `chunkers` package, which registers.
- `app/ai/rag/chunkers/policy.py` — `parse_outline()` walks pages line by
  line keeping page provenance (so `page` is exact, no text search):
  `N. Title` = section, `N.M` / `N.M.K` = clause **only when it is the next
  number in sequence** — table cells (`10`, `5 %`) and wrapped lines
  (`5, except…`, `3.6.`) stay continuation text. Text before section 1 →
  "Preamble" chunk (doc ref, effective date).
- `policy_chunks()` → **one chunk per top-level clause**, sub-clauses folded
  in, section heading prepended to `content`
  (`"4. Minimum attendance…
4.2 A student must…"`), `section` =
  `"§4.2 Minimum attendance for examination eligibility"`. Clauses over
  `TARGET_TOKENS`=400 (chars/4) split at sub-clause then sentence boundaries,
  labelled `§5.3 (2/3)`. **Deliberate deviation from the "~400 tokens" plan:**
  chunks are one clause each (median ~65 tokens, max ~300) so a citation
  names exactly one clause; packing clauses would blur `section` to a range.
- Verified: every section/clause/sub-clause in all 7 PDFs equals the
  markdown source (test does this). Force re-ingest: **7 docs, 226 chunks,
  7 late-chunked Jina calls (~15k tokens)**. Dense top-1 for "what attendance
  do I need to sit the end-semester exam" = Part IV §4.2 p.2; bare "minimum
  attendance" has §4.2 in dense top-3. Full-text (`websearch_to_tsquery`)
  returns nothing on longer NL queries because it ANDs terms — step 4's RRF
  fusion handles that; the tool was left as is.
- Tests: `tests/test_rag_policy_chunker.py` (18) — outline parsing on
  synthetic pages (sequence guard, sub-clause scoping, heading order,
  lead-ins), chunk assembly (heading + sub-clauses, part labels, page = clause
  start, unnumbered fallback), corpus-vs-markdown parity per PDF, the 75%
  rule = one chunk §4.2 p.2. Ingest/embedder tests retargeted from 4 page
  chunks to `ATTENDANCE_CHUNKS = 40`; fake-vector NN assertion loosened to
  "≥2 of top-3 are §5.x" (hashed bag-of-words collides on the short
  preamble). Suite **305 passed**.

### Step 4 — DONE: hybrid retriever + citations
- `app/ai/rag/retriever.py` — `retrieve(db, query, role=, k=5, candidates=20,
  doc_types=None, embedder=None) -> list[Hit]`. Dense = pgvector
  `cosine_distance` top-20 on the Jina query vector; sparse = full-text
  `websearch_to_tsquery` (AND) top-20, **topped up with an OR `to_tsquery`
  over the same terms when it under-fills** (long NL questions were returning
  nothing). `rrf()` fuses ranks (k=60). Audience filter
  (`documents.audience_roles @> role`) and `doc_types` are in *both* SQL
  branches. `_hydrate` outer-joins the parent chunk → `Hit.parent_content`
  (for curriculum; None for policies). No Jina key / API error →
  `EmbeddingError` caught, warns once, sparse-only. `Hit.as_passage()` =
  `{chunk_id, document, section, page, excerpt (full clause, ≤1500 chars),
  parent?}`.
- `app/ai/rag/citations.py` — `resolve(text, passages) -> (text, citations)`:
  `[[cite:<id>]]` → ` [n]` numbered by first appearance, repeats reuse n,
  ids not offered are stripped. Citation = `{n, chunk_id, document, section,
  page, snippet(300)}`. Replaces the orchestrator's `_resolve_citations`;
  `TurnResult.text` is now the cleaned text (markers gone).
- `search_university_policies` now calls `retrieve(..., doc_types=("policy",
  "notice"))` and returns whole clauses (was a 300-char cut of a page).
- Orchestrator: `RAG_TOP_K` 3 → **5** (clause chunks are ~65 tokens). Router
  (Call A) JSON gained **`rag_query`** — the question rewritten as regulation
  language ("am I short on attendance?" → "minimum attendance percentage
  required for end-semester examination eligibility"); `_retrieve` uses it,
  falling back to the raw question. Reason: with the raw vague question §4.2
  ranked 5–8; with the rewrite it is rank 1 on both branches.
- Verified with real vectors (no Groq key, so Call A/C were scripted): a
  full `run_turn` for student 17 "am I short on attendance?" puts
  `get_my_attendance` (DBMS 67.7%) and passages §4.2 (75%), §2.5, §4.3,
  §4.5, §6.1 (worked 68% example) in front of Call C. Probe table (dense
  rank / sparse rank): "what attendance do I need to sit the end-semester
  exam" → §4.2 p.2 = 1/1; "condonation on medical grounds" → §5.3 = 1/1;
  "late fee per week" → Fee §4.1; "results declared" → Exam §8.x.
- **Test-DB hygiene fix**: `tests/conftest.py` `_preserve_doc_store` (session,
  autouse) snapshots `documents` + `doc_chunks` (+ calendar links) before the
  session and restores them after — RAG tests truncate and re-ingest with
  no/fake vectors, which used to leave the dev DB without real vectors until
  the next `--force` ingest. Verified: 226 Jina-vector chunks survive `pytest`.
- Tests: `tests/test_rag_retriever.py` (14) — RRF math, both ranks on hits,
  each branch contributes, OR fallback, no-embedder degrade + single warning,
  empty/stopword/no-match, audience filter both branches, doc_type filter,
  parent hydration, tool returns whole clause; citations numbering/dedupe/
  unknown-dropped/untouched. `test_orchestrator.py`: text rewrite + `n`
  asserted; new `rag_query` used/fallback test. Suite **319 passed**.

### Step 5a — DONE: curriculum parser + parent/child chunker
- **`parsers.parse_pdf` now uses `get_text("text", sort=True)`** (position-
  sorted blocks). Reason: on some syllabus pages PyMuPDF emitted the
  code/title/scheme table *after* the body, so records were cut mid-course.
  Sorted mode also joins table rows into single lines
  (`24MA101T Mathematics – I`, `3 1 0 4 4 25 50 25 -- -- 100`). Policy
  chunking is unaffected (tests unchanged).
- `app/ai/rag/chunkers/curriculum.py` — all 6 PDFs share one university
  template. `parse_courses(parsed) -> (preface_lines, [CourseRecord])`:
  anchor = a `Teaching Scheme` line **followed by at least one section
  heading before the next anchor** (structure tables use "Teaching Scheme" as
  a column header → not records). Header = up to 3 lines above the anchor:
  code token anywhere (`24PH101T`), placeholders (`<Course Code>`,
  `24ICxxxT`, `24ECE***T`) → `code=None`; title wraps glued
  (`_wrapped`: trailing `,(/&-`, unbalanced `)`, lowercase start); code on
  its own line with the title above it handled. Fields: L/T/P/C from the
  first numeric values row; objectives (bullets incl. Symbol-font PUA
  `` stripped, wraps glued); units (`UNIT I: TITLE 08 Hrs.` / hours
  on next line / title on next line; roman or arabic; `LIST OF
  EXPERIMENTS` variants → one "List of experiments" unit); outcomes
  (`CO1 : text`, label split across lines, or a plain `1. 2.` list);
  books (numbered, wraps glued). Page furniture (`Pandit Deendayal…`,
  `B. Tech. … Engineering`, `Semester – VI`, `Academic year:`) dropped.
- `curriculum_chunks()` → preface pages as `section="Programme structure"`
  page chunks; per course **one parent** (label, `L-T-P 3-0-0, 3 credits`,
  objectives, unit-title list) + **children** (`<label> / Unit N: title
  (h hrs)` + body; `/ Course outcomes`; `/ Books`), `parent=` index set.
  `CourseRecord.label` = `"24CS202T Database Management Systems"` (title
  only when the code is a placeholder).
- Coverage (records / no-code / no-units / no-CO / no-books): CP 88/1/4/0/0 ·
  ICT 49/45/5/0/1 · ECE 68/62/5/0/4 · ME 72/0/1/0/0 · CE 52/52/2/1/3 ·
  CH 78/47/3/0/2. **No-code counts are the PDFs' own placeholders**, not
  parse failures; unit-less records are NSS/NCC/Yoga-type courses.
  **The synthetic DB's subject codes differ from the PDFs'** (DB DBMS =
  `24CS201T`, CP PDF DBMS = `24CS202T`) → 5b must join by *name*, not code.
- Ingest: `LATE_CHUNKED_BY_PARENT = {"curriculum"}` → `_embed_by_parent`:
  one late-chunked Jina call per parent + its children; family-less chunks
  (structure pages) in a plain batch. Full curriculum ingest = **6 docs,
  2482 chunks (2021 children), 413 calls, ~305k tokens, ~5.5 min**.
- Retrieval probe (hybrid, `doc_types=("curriculum",)`): "which unit of
  DBMS covers normalization" → Unit 3 children (ICT p23, CP p35, ECE p73)
  with parent hydrated; "ACID properties and concurrency control" → CP
  Unit 4 rank 1/1. Short queries ("unit 3 of DBMS") let the big
  "Programme structure" chunks win sparse rank → **5b's curriculum tool
  should exclude `section = 'Programme structure'`** (the `curriculum` DB
  table answers structure questions exactly).
- `tests/conftest.py` restore now inserts chunks with NULL `parent_chunk_id`
  and links afterwards (self-FK order). Tests:
  `tests/test_rag_curriculum_chunker.py` (20) — one record every field,
  numbered outcomes + experiment lists, 9 header variants, structure-table
  headers stay in preface, record boundaries + pages, furniture dropped,
  parent/child assembly, preface chunks, `_embed` grouping (3 calls), real
  CP PDF: 88 records / full fields, DBMS Unit 3 p35 is a child of the DBMS
  parent. Suite **339 passed**.

### Step 5b — DONE: relational extract + curriculum tools
- **Migration `cc3862737634`** (reversible; `alembic check` still reports the
  pre-existing `use_alter` FK false positive, unrelated): `syllabus_courses`
  (document_id CASCADE, dept_code, `code` as printed / NULL for placeholders,
  `subject_code` FK→subjects nullable, title, `title_key`, L/T/P, credits
  Numeric(3,1), objectives ARRAY, page, source_chunk_id SET NULL),
  `syllabus_units` (number, title, hours, topics, page), `course_outcomes`
  (number, text), `textbooks` (position, citation) — children CASCADE on
  course, each with `source_chunk_id`. Models in `app/models/syllabus.py`.
- `chunkers/base.py`: `EXTRACTORS[doc_type]` — `fn(db, document, parsed,
  entry, rows)` run by `ingest_one` after `_write_chunks` (which now returns
  the rows, index-aligned with drafts) in the same transaction; `_drop_chunks`
  deletes the document's `syllabus_courses` first (children cascade).
- `chunkers/curriculum.py`: `build()` returns `(drafts, records)` with
  `rec.draft` / `unit.draft` / `outcomes_draft` / `books_draft` indices;
  `extract_courses` writes the four tables. **Linking to `subjects` is by
  name first** (`title_key`: lowercase, drop `(For …)` qualifiers,
  punctuation, `lab`→`laboratory`, `– I`/`-1`→`1`, crude singular), several
  same-name subjects → the one in this dept's `curriculum` table wins, and
  the printed code is trusted only if the dataset's subject of that code has
  a similar name (Jaccard ≥ 0.6). Reason: the PDF's `24CS202T` is DBMS, the
  dataset's `24CS202T` is Digital Logic. Result: 352/407 linked; CP DBMS →
  `24CS201T` (what the student's own records show).
- Parser fixes found on the way: furniture `B. Tech. … Engineering,` /
  `Department of … Engineering` / `UG Curriculum (…)` / `Semester 6`; title
  junk `Course Code: XXXX …`, `XXXXXX IC Technology`, `2nd Semester UG_2_T(…)`;
  `24ECE***T` placeholders; **interstitial programme-structure tables**
  (`COURSE STRUCTURE …`, `Category Course` / `… Course Name Theory …`
  header rows) now end the record above (`rec.trailing`) and join the
  "Programme structure" chunks instead of the previous course's books.
  Curriculum corpus is now **2487 chunks**.
- `ingest_one` → `_reusable_vectors`: a forced re-run whose chunk texts are
  identical (same count/content/model, all vectors present) **reuses the
  stored vectors** — an extractor-only change costs 0 Jina calls (~20 s vs
  5.5 min). Any text difference re-embeds the whole document (late chunking
  needs each family embedded together).
- `app/ai/tools/curriculum_tools.py` (all roles, UNIVERSITY scope):
  `get_course_syllabus(course, unit?)` — resolves dataset `subject_code`
  first, then printed code, then `title_key`, then ILIKE; caller's dept
  first; >1 distinct title → `{"matches": [...], "hint"}`; returns course,
  department, subject_code, credits, scheme, `source` ("<doc>, p.N"),
  `chunk_id`, objectives / units (`Unit N: title (h hrs): topics || …`) /
  outcomes / textbooks as pre-joined strings (compact() flattens nested
  values), or just `unit` when asked. `search_curriculum(query)` →
  `retrieve(doc_types=("curriculum",), exclude_sections=("Programme
  structure",))` (new `exclude_sections` param) with `parent`.
- Orchestrator: `PASSAGE_TOOLS = {search_university_policies,
  search_curriculum}` — their hits are kept on `ToolRun.passages`,
  `_merge_passages` adds them to the citable passage list (dedupe by
  chunk_id) and those runs are dropped from the "Tool results" block.
  Prompt: "Document passages", `(course record: <label> | <scheme>)` line
  for hits with a parent, grounding rule extended to syllabus details.
- **conftest**: `_preserve_doc_store` now snapshots/restores the four
  extract tables too, and runs **before** `_loaded_db` (the CSV loader's
  `TRUNCATE subjects CASCADE` was emptying `syllabus_courses` before the
  snapshot). Verified after a full run: 226 + 2487 chunks with vectors, 407
  courses, 352 linked.
- Tests: `tests/test_rag_curriculum_extract.py` (16) — title_key variants,
  link precedence (name → dept → plausible code), extract rows + source
  chunks + counts, DBMS→24CS201T with unit rows citing their chunks,
  re-ingest without duplicates, vector reuse (0 extra fake calls), structure
  table between records, tool by name/code/unit + disambiguation + unknown,
  search_curriculum parent + no structure pages, `_merge_passages`, a
  scripted turn where a planned `search_curriculum` call becomes passages.
  `test_rag_embedder` exploding embedder now uses its own model name (reuse
  would otherwise skip the API). Suite **355 passed**.

### Step 6 — DONE: tabular (calendar) + notices
- **Sources** (synthetic, every date from `academic_calendar.csv` / the
  policies): `docs/calendar/academic_calendar_2026_27.md` (two tables, 25
  events, notes) and `docs/notices/{fee_payment_reminder, internal_test_2_
  schedule, anti_ragging_helpline, faculty_marks_entry_deadline}.md` (the
  last is `audience_roles: [faculty, admin]`). `scripts/render_policies.py`
  now renders all of `docs/{policies,calendar,notices}` → `<dir>/pdf/`.
  Manifest: 18 entries (7 policy, 1 tabular `category: calendar`, 4 notice,
  6 curriculum).
- **`parsers.extract_tables` now uses PyMuPDF `page.find_tables()`**
  (pdfplumber dropped the first row after a page break; requirement removed)
  + `clean_tables()`: drop columns empty in every row (phantom rulings on a
  continued table), merge rows whose first cell is empty (a wrapped cell
  split the row), cell newlines → spaces. The calendar comes out as 25 clean
  6-column rows.
- `chunkers/tabular.py`: `build()` → page chunks for the prose + one chunk
  per table (`section="Table N (<headers>)"`, rows rendered `Event: …;
  Type: …; From: …`), a header-less continuation table inherits the previous
  header when widths agree. `extract_calendar` (only `category == "calendar"`):
  header → column map (event/type/from|start|date/to|end/applies/term),
  `parse_date` (d Month YYYY, d Mon YYYY, ISO, d/m/Y, d-m-Y), **upsert
  `academic_calendar` by (event, start_date)**, sets `source_chunk_id` to the
  table chunk. Result: 25/25 rows linked. Registered as `EXTRACTORS["tabular"]`.
- `chunkers/notice.py`: one chunk, `section` = first line (the heading).
- `search_university_policies` now searches `("policy", "notice", "tabular")`
  — notices and the calendar chunks are the low-priority fallback; RRF keeps
  clauses on top. Audience filter verified: the faculty circular is invisible
  to a student, rank 1 for faculty.
- `get_academic_calendar` returns `{"rows": [...], "passages": [...]}` —
  the calendar-table chunks its rows came from (`excerpt` = first 300 chars).
  Orchestrator `_execute` picks up a dict's `passages` (a *data* tool that
  names its source), keeps the run in "Tool results" (only `PASSAGE_TOOLS`
  runs are moved out), so a dates answer can cite the calendar PDF.
- **conftest restore bugs fixed** (they were silently emptying the extract
  after every `pytest`): the calendar re-link statement used `:cid` for a
  `source_chunk_id` key (aborted the whole restore transaction); the
  `academic_calendar` table is now snapshotted/restored whole (tests delete
  and re-insert rows). Verified after a full run: 2723 chunks, 25/25 calendar
  links, 407 courses.
- Tests: `tests/test_rag_tabular_notice.py` (18) — clean_tables, parse_date,
  PDF tables keep the page-break row, tabular chunks + header inheritance,
  notice chunk, calendar upsert with source chunks, re-ingest corrects a
  changed row and re-inserts a deleted one, non-calendar tabular extracts
  nothing, audience + notice/calendar coverage in policy search, calendar
  tool passages, a scripted turn citing the calendar. `test_rag_ingest`
  manifest count → 18. Suite **373 passed**.

**Phase 3 deliverable check (plan.md §11):** manifest-driven ingest ✔, all
three chunkers (+ notice) ✔, curriculum extraction to DB ✔, hybrid
retrieval + parent hydration ✔, citations ✔, personalized synthesis (Call C
prompt + `rag_query`) ✔, faculty tools ✔ (2.7a). Not yet run live end-to-end
(no Groq key) — every turn above was scripted at Call A/C with real tools
and real vectors.

## 9. Phase 4 — gap-check (DONE 2026-09-12)

plan.md §6 catalog vs `REGISTRY`: **all 40 planned tools registered** (4 shared,
11 student, 8 faculty, 9 admin, 8 actions) plus 3 extras
(`get_my_teaching_courses`, `list_pending_leave_requests`,
`search_curriculum`). Visible per role: student 18, faculty 19, admin 22
(plan said 12–16; still a small Call-A index). §7 two-phase confirm: HMAC-SHA256
token over (user, tool, canonical args, exp, nonce), TTL
`settings.confirm_token_ttl_seconds` = 300, RBAC re-checked at execution, turn
stops before Call C — all in place since 2.7c.

One gap fixed: the Phase-4 demo "department failure-rate analysis" had no
metric. `run_analytics` gained **`failure_rate`** = % of a group's declared
semester results whose `result_status` is not `Pass` (the dataset uses
`ATKT`, not `Fail`). Sample: CH 16.67, EC 16.67, others 0. Test added in
`test_admin_tools.py`. Suite **378 passed**.

## 10. Phase 5a — frontend (in progress)

Design (plan.md §9, chosen 2026-09-12): institutional and quiet. Page
`#F3F5F7`, surface white, ink `#17202B`, slate `#5B6675`, crest green
`#1E6B58` (actions, citation numbers), amber `#9A6B12` (confirm pending),
red `#9B2C2C` (errors). IBM Plex Sans for chrome, **IBM Plex Serif for the
assistant's prose** — answers read like a cited memo: `[n]` markers become
superscripts and the citations render as **numbered footnotes** under the
answer (`Academic Regulations Part IV — §4.2 …, p.2` + a "passage"
disclosure). 68ch reading column, composer pinned at the bottom. No
dependencies beyond React; Google Fonts in `index.html`; Vite proxies
`/api` and `/health` to `:8000`.

### Part 1 — DONE: client, login, chat, confirm
- `src/types.ts` (API shapes + the UI `Turn`), `src/api.ts` (fetch wrapper,
  bearer token, `ApiError{status, retryAfter}`), `src/session.ts`
  (localStorage `uniassist.session`), `src/App.tsx` (session → `/api/me`;
  a rejected token signs out), `src/Login.tsx` (three demo accounts, password
  `uniassist`: `25bcp017@…` student, `milan.vyas@…` faculty/HOD CP,
  `tanvi.joshi@…` admin), `src/Chat.tsx` (turns, send, confirm/cancel,
  `openConversation`/`newConversation` ready for the rail), `src/Message.tsx`
  (Prose: paragraphs / bullet lists / Markdown-pipe tables, `[n]` → `<sup>`,
  footnotes; `Confirm` card: preview `summary` + fields, Confirm/Cancel,
  settled/failed states; unknown cards dumped as JSON), `src/index.css`.
  Errors map: 429 → "rate-limited, try in N s", 503 → no API key, 410 →
  confirmation expired, 409 → server reason. `queued_seconds` shown above the
  answer when non-zero.
- **Verified with Playwright** against the real backend + DB with a canned
  LLM (scratchpad `dev_server.py` overrides `chat_api.get_provider`; no Groq
  key): sign-in → "am I short on attendance?" → table + serif answer +
  footnotes §2.5 p.1 / §4.2 p.2 → "apply for leave …" → confirm card →
  Confirm → "Leave application #37 submitted … pending approval from Dr.
  Milan Vyas." Mobile (400px) fine. `npm run build` clean.
- Known nits: top bar shows "Student 17" — `get_my_profile` has no `name`
  key the UI expected (check its keys and show the person's name); the
  scratchpad demo server is not in the repo (consider
  `backend/scripts/dev_server_demo.py` if useful for the viva).

### Part 2 — DONE: conversation rail + suggested prompts
- `src/Rail.tsx`: `SUGGESTIONS[role]` (5 per role; each hits a different
  path — own records, a cited regulation, the syllabus, an action), the
  `New conversation` button, and the history list (`GET /api/chat`,
  title = first question, short date, active row highlighted).
- `Chat.tsx`: `refreshConversations` on mount and whenever a turn opens a
  new conversation; `openConversation` loads the stored transcript (user +
  assistant rows with citations/cards); a suggestion click sends it. Caller
  line now uses `profile.full_name` → "Isha Kanani (Student)".
- Layout: CSS grid `260px | 1fr` (top / rail+main / rail+composer); under
  800px the rail is a fixed overlay opened by a "Menu" button in the top bar
  and closed by "Close" / any action.
- Verified with Playwright (`scratchpad/ui_rail.py`): suggestion → answer
  with footnotes, history grows and highlights, New → reopen restores 2 turns
  + 2 footnotes, mobile overlay opens/closes; no page errors. Build clean.
  Note: the dev DB's `conversations` carry leftovers from `test_chat_api`
  ("hi", "xxxx…") — they are user 17's; harmless, but the API test suite
  could clean up after itself.

### UX audit pass (ui-ux-pro-max, 2026-09-12) — applied on top of part 2
- Design-system query confirmed the direction (institutional navy/green +
  serif reading voice); its "landing page" pattern/style rows were a
  misroute for a signed-in tool and were ignored.
- Contrast computed for every text pair in use: all ≥ 5.3:1 (amber 4.24 is
  border-only). Fixes applied: body 15→16px; buttons `min-height` 40px, 44px
  under `pointer: coarse` (rail rows, Send, top-bar links); 150 ms hover
  transitions incl. a darker primary; "Working on it" with three pulsing dots
  (animation only under `prefers-reduced-motion: no-preference`,
  `aria-busy`). Verified at 375px: no horizontal overflow, target heights
  40 / 56. Not done: dark mode (single light theme by design for now).

### Part 3 — DONE: typed data cards
- Backend `app/ai/cards.py` — `cards_for(name, result, ok, error)` maps tool
  results to cards by tool name: `attendance` (`get_my_attendance`; rows +
  `threshold: 75`), `marks` (`get_my_marks`), `timetable`
  (`get_my_timetable`, `get_my_teaching_schedule`), `student_table`
  (`list_students`, `list_course_students`, `list_students_below_attendance`,
  `identify_at_risk_students`, `list_missing_submissions`; columns + row
  arrays, capped at 100 with `total`), `denied` (`error == "denied"`).
  `ToolRun.cards` is filled in `_execute`; `TurnResult.cards` = the confirm
  card (turn stops) or the data cards. Stored in `messages.tool_calls[*].cards`
  → `_cards_from_runs` replays them in `GET /api/chat/{id}`.
- API: `ChatOut.trace = {path, intent, tool_runs[{name,args,ok,error}],
  usage}` (for part 4); `MessageOut.tool_runs` for stored turns.
- Frontend `src/Cards.tsx` — `DataCard` dispatch: attendance bars with the
  75% line (short courses red, `role="img"` labels), marks bars grouped by
  course, timetable day grid (labs amber), student table (click-to-sort with
  `aria-sort`, "Download CSV"), denied note (red: "Not available to your
  role… the server refused it before any data was read"), unknown → JSON.
  `Turn.trace` carried from `ChatOut.trace` / stored `tool_runs`.
- Verified with Playwright + the canned backend: attendance (DBMS 67.7% red vs
  the line), timetable, marks for the student; faculty "who is below 75%" →
  sortable table (sort by percent → 63.6 first). Backend suite **380 passed**
  (API tests: attendance card + trace on a turn, cards replayed from the
  transcript, forced `list_students` for a student → `denied` card).

### Part 4 — DONE: tool-trace panel + queued retry
- `src/Trace.tsx`: `<details>` under each answer — summary line
  ("router → tool → answer (planner skipped) · 1 tool call · 1170 tokens"),
  then path, intent, tool runs (`ok` green / `refused by RBAC` red / failed),
  tokens in/out and any rate-limit wait. Shown only when the **Trace**
  checkbox in the top bar is on (`localStorage` `uniassist.trace`); stored
  transcripts carry it too (path "stored" = "from the saved transcript").
- `Chat.tsx` `chatWithOneRetry`: a 429 with `Retry-After ≤ 20 s` shows
  "Queued — the assistant is busy, retrying in N s" on the pending turn,
  waits, resends once, and adds the wait to `queued_seconds`; longer waits
  surface as the error message. `frontend/README.md` replaced with run
  instructions + a source map.
- Verified with Playwright: hidden by default, toggle remembered across
  reload, panel content, trace on a reopened conversation; no page errors.

Phase 5a deliverables vs plan.md §9: chat-first layout ✔, sidebar with
history + role prompts ✔, rich cards (attendance/student_table/timetable/
marks/confirm/citation/denied) ✔ (`syllabus` unit accordion not built —
syllabus answers come as prose + a passage footnote), tool trace ✔,
rate-limit UX ✔. Live end-to-end still unrun (no Groq key; canned provider
in `scratchpad/dev_server.py`).

## 11. Live runs (Groq, from 2026-09-12)

- First live turn, student 17, "am I short on attendance?" → path `fast`,
  `get_my_attendance`, 1936 in / 478 out tokens, attendance card, a correct
  table + "short only in 24CS201T at 67.7%". **Finding:** gpt-oss-120b wrote
  the marker as `【cite:31128】` (full-width brackets) → the resolver missed
  it and the answer had no footnote. `citations._CITE` now also accepts
  `【cite:id】` and `[cite:id]` (test added). Re-check on the next live run
  that footnotes appear.
- Second live finding (via the UI, "Am I short on attendance in any
  course?"): the 20b router returned `needs_rag: false`, so no passage was
  retrieved and the model rightly said the rule "could not be found". Fix:
  **`POLICY_CONTEXT`** in the orchestrator — a map from personal-record tools
  (`get_my_attendance`, `get_my_fees`, `get_my_marks`, `get_my_results`,
  `get_my_scholarships`, `get_my_leave_requests`, faculty attendance tools)
  to a regulation query; when such a tool ran and the router said no RAG,
  that query is retrieved anyway. Live re-run: `[1] §4.2 … p.2`, "67.7 % …
  below the required 75 %". Test added in `test_orchestrator.py`.
- Third live finding (faculty, "Which of my students have missing
  submissions?"): no tool ran — `list_missing_submissions` *required*
  `course_code`, the question named none, the planner emitted no call and
  Call C said "no data"; the follow-up then hit a bare **502 "LLM provider
  error"** with the cause unlogged. Fixes: `_faculty_offerings(course_code=None)`
  → every offering the faculty teaches this term (admin must still name a
  course) and `course_code` optional on all six course-level faculty tools
  (descriptions say so); `list_missing_submissions` rows gain `course`; the
  API now logs provider errors and returns `LLM provider error: <reason>`.
  Live re-run: fast path, `list_missing_submissions {}`, student_table card;
  the follow-up answers 200. The original 502's cause was never captured —
  watch the log (`log.error("LLM provider error …")`) if it recurs.
- **The 502's cause, captured** (faculty "what course do i teach?", "what is
  my name?"): Groq **400 `tool_use_failed` — "Tool choice is none, but model
  called a tool"**. gpt-oss emits a phantom tool call (`router`,
  `mark_attendance`…) in a step with no tools attached (Call A with
  `json_object`, or Call C) and Groq rejects the response; it is random per
  phrasing. Fix in `openai_compat._create`: on that 400, when the payload has
  no `tools`, retry **once** with `NO_TOOLS_NOTE` appended to the system
  prompt ("There are no tools in this step…"), logged as a warning; a second
  failure raises `ProviderError`. Tests in `test_providers.py`. Live re-run:
  all four faculty questions answer (fast path, right tools).
- The dev DB `conversations` for user 17 now also hold live turns.

- **5c.4 (second session, via the API with `scratchpad/smoke.py`)** — four
  more findings, all fixed, suite **388 passed**:
  1. "what's in Unit 3 of DBMS?" → `get_course_syllabus {course: "DBMS"}` →
     `no course matching 'DBMS'`: the resolver had no abbreviation stage.
     `_acronym_score()` in `curriculum_tools.py`: each letter starts a
     significant word or follows the previous letter inside the same word
     (DBMS = Data-Base Management Systems); the tightest reading wins
     (OS = Operating System, not Open Source Technologies) and the caller's
     department is preferred (COA → CP's course, no disambiguation list).
     `get_course_syllabus` now also returns `passages` (the course's / unit's
     source chunk) so the answer footnotes the syllabus PDF; `_execute` strips
     `passages` from the compacted table (it is in the passage block already).
  2. "when are the end-sem exams?" → 502: the 20b router "called"
     `tool.get_my_exam_schedule` **twice** (the no-tools-note retry is
     near-deterministic at temperature 0). The provider now **salvages Groq's
     `failed_generation`**: `_failed_generation(exc)` reads it from the body
     or the message repr, `_salvage_tool_call()` turns `{"name":
     "tool.x", "arguments": …}` into an `LLMResponse` with one `ToolCall`
     (namespace prefix stripped). Orchestrator: an empty-text route with
     tool_calls → those names are the candidates; an empty-text **Call C**
     with tool_calls → run them through the registry (RBAC intact, `denied`
     card if refused) and synthesize once more. Live: the exam question now
     answers on the fast path with the schedule table.
  3. "show me all students with CGPA above 9" (student) → 502
     `json_validate_failed` (the router refused in prose); later
     `output_parse_failed` (`failed_generation: "Need academic calendar."`).
     Both: retry once **without `response_format`** (the prompt asks for JSON
     anyway, `parse_json_object` is prose-tolerant), then use the rejected
     prose as the reply (→ `{}` → Call C applies the refusal rule). Live: the
     student gets "outside your access level"; no 502s in the log since.
  4. "how many credits is DBMS and what are the textbooks?" → the router
     picked `search_university_policies`. Router prompt gained one rule: a
     course's units/credits/scheme/outcomes/textbooks come from
     `get_course_syllabus` / `search_curriculum`, not policy search. Live:
     `get_course_syllabus`, "3 credits [1]" + the three textbooks, footnote
     = CP syllabus p.35. `search_curriculum` now ranks the **caller's own
     department's syllabus first** (every programme has a DBMS) via
     `syllabus_courses.document_id`.
- Live-verified in this session (all 200, correct, no warnings in the log
  after the fixes): admin `run_analytics failure_rate × department` (CH/EC
  16.67), `get_department_overview`; student exam schedule, Unit 3 (cited
  CP p.35 first), credits + textbooks, announcements, smalltalk, out-of-role
  refusal ("mark my attendance" → "outside your access level", smalltalk
  path — no `denied` card because no tool was refused at execution); the
  **two-phase confirm end-to-end** three times: student `apply_for_leave`
  (→ #33, pending, approver Dr. Milan Vyas), HOD `list_pending_leave_requests`
  then `decide_leave_request 33 approve`, admin `publish_notice` (→ #34,
  visible to the student's `get_my_announcements` next turn); a replayed
  confirm token is 409. Groq free-tier 429s appear as `queued_seconds` of
  15–28 s on some turns — the budgeter absorbs them, nothing fails.
- The dev DB now carries leave request #33 (approved) and announcement #34
  from the live run; `pytest` reloads the sample anyway.
- Not run through the browser this session (API only); the UI's confirm card
  was Playwright-verified in 5a against the canned provider, and the API
  contract is unchanged.

### Remaining steps (do one at a time; report and ask before committing)
5b. **Eval harness** (plan.md §10): `eval/golden_set.yaml`, `run_eval.py`
   reporting tool-routing accuracy, refusal accuracy (must be 100%), citation
   rate on policy questions, median latency, mean tokens/turn; then the three
   experiments (late vs naive chunking retrieval@3, hybrid vs dense-only,
   Matryoshka dimension sweep). Needs the Groq key (set). Budget the free
   tier: a turn is 2–3 calls and 429 waits of ~15–30 s were seen at ~10
   turns/min.
6. Report / demo prep (plan.md §11).
