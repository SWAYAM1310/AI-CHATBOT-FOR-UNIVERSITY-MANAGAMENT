"""FastAPI entrypoint. For now: CORS + a DB-backed health check.

Run:  uvicorn app.main:app --reload   (from backend/, with the venv active)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth as auth_api
from app.api import chat as chat_api
from app.api import me as me_api
from app.config import settings
from app.db.session import engine

app = FastAPI(title="UniAssist API", version="0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_api.router)
app.include_router(me_api.router)
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
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {settings.llm_api_key}"})
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
