"""FastAPI entrypoint. For now: CORS + a DB-backed health check.

Run:  uvicorn app.main:app --reload   (from backend/, with the venv active)
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import admin as admin_api
from app.api import auth as auth_api
from app.api import chat as chat_api
from app.api import faculty as faculty_api
from app.api import me as me_api
from app.api import profile as profile_api
from app.api import student as student_api
from app.config import settings
from app.db.session import engine
from app.jobs import upkeep

log = logging.getLogger("uvicorn.error")


async def _upkeep_loop() -> None:
    """Settle the records now, then again every interval, so a day closes soon after midnight."""
    while True:
        try:
            log.info("upkeep: %s", upkeep.describe(await run_in_threadpool(upkeep.run_now)))
        except Exception:  # noqa: BLE001 - a bad run must not stop the next one
            log.exception("upkeep failed")
        await asyncio.sleep(settings.upkeep_interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_upkeep_loop()) if settings.upkeep_enabled else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="UniAssist API", version="0.0.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_api.router)
app.include_router(me_api.router)
app.include_router(profile_api.router)
app.include_router(faculty_api.router)
app.include_router(student_api.router)
app.include_router(admin_api.router)
app.include_router(chat_api.router)


@app.get("/health")
def health() -> dict[str, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "up"}
    except Exception as exc:  # noqa: BLE001 - surface any connection failure
        return {"status": "degraded", "db": "down", "detail": str(exc)}


def check_models() -> int:
    """Phase-0 gate: assert every configured LLM model id exists on the provider.

    Hard-fails with the live list. Skips (exit 0) when no API key is set, since a
    key is only required from Phase 2.
    """
    import json
    import urllib.request

    if not settings.llm_api_key:
        print("LLM_API_KEY not set - skipping model check (required from Phase 2)")
        return 0

    url = settings.llm_base_url.rstrip("/") + "/models"
    # Groq's edge answers 403 to urllib's default "Python-urllib" agent; any real one passes
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {settings.llm_api_key}", "User-Agent": "uniassist/0.1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            available = {m["id"] for m in json.load(resp).get("data", [])}
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: could not reach {url}: {exc}")
        return 1

    wanted = {settings.llm_model_router, settings.llm_model_main}
    missing = wanted - available
    if missing:
        print(f"FAIL: configured models missing from provider: {sorted(missing)}")
        print(f"available: {sorted(available)}")
        return 1
    print(f"ok - all configured models present: {sorted(wanted)}")
    return 0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="UniAssist backend CLI")
    ap.add_argument("--check-models", action="store_true", help="Phase-0 model gate")
    args = ap.parse_args()
    if args.check_models:
        raise SystemExit(check_models())
    ap.print_help()
