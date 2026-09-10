"""FastAPI entrypoint. For now: CORS + a DB-backed health check.

Run:  uvicorn app.main:app --reload   (from backend/, with the venv active)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

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


@app.get("/health")
def health() -> dict[str, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "up"}
    except Exception as exc:  # noqa: BLE001 - surface any connection failure
        return {"status": "degraded", "db": "down", "detail": str(exc)}
