"""docs/manifest.yaml — the declared corpus (plan.md §8).

Document type is *declared*, never detected: ten lines of YAML per file
eliminate a whole class of "why did the policy chunker run on the syllabus"
bugs. Everything the ingest needs to know about a file is here, and a manifest
that names a missing file or an unknown type is rejected before any parsing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from app.auth.context import Role
from app.config import REPO_ROOT

DEFAULT_MANIFEST = REPO_ROOT / "docs" / "manifest.yaml"
DOC_TYPES = ("policy", "curriculum", "tabular", "notice")
ROLES = tuple(r.value for r in Role)


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class ManifestEntry:
    path: Path  # absolute
    title: str
    doc_type: str
    audience_roles: tuple[str, ...]
    category: str | None = None
    dept_code: str | None = None
    effective_date: date | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def source_path(self) -> str:
        """Repo-relative, forward slashes — the stable key in `documents.source_path`."""
        return self.path.relative_to(REPO_ROOT).as_posix()


def load_manifest(path: Path = DEFAULT_MANIFEST, *, root: Path = REPO_ROOT) -> list[ManifestEntry]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {path}") from exc
    docs = (raw or {}).get("documents")
    if not isinstance(docs, list) or not docs:
        raise ManifestError("manifest has no `documents` list")

    entries: list[ManifestEntry] = []
    seen: set[str] = set()
    for i, item in enumerate(docs):
        if not isinstance(item, dict):
            raise ManifestError(f"documents[{i}] is not a mapping")
        entry = _entry(item, i, root)
        if entry.source_path in seen:
            raise ManifestError(f"documents[{i}]: duplicate path {entry.source_path}")
        seen.add(entry.source_path)
        entries.append(entry)
    return entries


_KNOWN = {"path", "title", "doc_type", "audience_roles", "category", "dept_code", "effective_date"}


def _entry(item: dict[str, Any], i: int, root: Path) -> ManifestEntry:
    for key in ("path", "title", "doc_type", "audience_roles"):
        if not item.get(key):
            raise ManifestError(f"documents[{i}]: missing `{key}`")
    if item["doc_type"] not in DOC_TYPES:
        raise ManifestError(f"documents[{i}]: doc_type {item['doc_type']!r} not in {DOC_TYPES}")
    roles = item["audience_roles"]
    if not isinstance(roles, list) or any(r not in ROLES for r in roles):
        raise ManifestError(f"documents[{i}]: audience_roles must be a subset of {ROLES}")
    path = (root / item["path"]).resolve()
    if not path.is_file():
        raise ManifestError(f"documents[{i}]: file not found: {item['path']}")
    eff = item.get("effective_date")
    if eff is not None and not isinstance(eff, date):
        raise ManifestError(f"documents[{i}]: effective_date must be a date, got {eff!r}")
    return ManifestEntry(
        path=path,
        title=str(item["title"]),
        doc_type=item["doc_type"],
        audience_roles=tuple(roles),
        category=item.get("category"),
        dept_code=item.get("dept_code"),
        effective_date=eff,
        extra={k: v for k, v in item.items() if k not in _KNOWN},
    )
