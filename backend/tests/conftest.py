"""Shared fixtures. Loads the sample dataset once for the whole test session."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import REPO_ROOT
from app.db.session import engine
from app.seed.load_csv import LOAD_ORDER, load

SAMPLE_DIR = REPO_ROOT / "data" / "synthetic" / "sample"


@pytest.fixture(scope="session", autouse=True)
def _loaded_db() -> None:
    """Ensure a freshly loaded sample DB before any test runs."""
    load("sample", reset=True)


@pytest.fixture(scope="session")
def conn():
    with engine.connect() as c:
        yield c


def csv_row_count(name: str) -> int:
    path = SAMPLE_DIR / f"{name}.csv"
    with path.open(newline="", encoding="utf-8") as fh:
        return sum(1 for _ in csv.reader(fh)) - 1  # minus header
