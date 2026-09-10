"""Schema-level checks: pgvector wired, vector column usable, HNSW index present."""
from __future__ import annotations

from sqlalchemy import text

from app.config import settings


def test_vector_extension_installed(conn):
    v = conn.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar_one_or_none()
    assert v is not None


def test_doc_chunks_indexes(conn):
    rows = {
        r[0]: r[1]
        for r in conn.execute(
            text(
                "SELECT i.indexname, am.amname "
                "FROM pg_indexes i "
                "JOIN pg_class c ON c.relname = i.indexname "
                "JOIN pg_am am ON am.oid = c.relam "
                "WHERE i.tablename = 'doc_chunks'"
            )
        )
    }
    assert rows.get("ix_doc_chunks_embedding_hnsw") == "hnsw"
    assert rows.get("ix_doc_chunks_tsv") == "gin"


def test_vector_column_roundtrip(conn):
    dim = settings.embedding_dim
    trx = conn.begin_nested()
    try:
        conn.execute(
            text("INSERT INTO documents (id, title, doc_type, source_path) "
                 "VALUES (999999, 't', 'policy', 'x')")
        )
        vec = "[" + ",".join("0.1" for _ in range(dim)) + "]"
        conn.execute(
            text(
                "INSERT INTO doc_chunks (document_id, content, embedding) "
                "VALUES (999999, 'c', :v)"
            ),
            {"v": vec},
        )
        got = conn.execute(
            text("SELECT vector_dims(embedding) FROM doc_chunks WHERE document_id = 999999")
        ).scalar_one()
        assert got == dim
    finally:
        trx.rollback()
