"""AI layer — conversations, messages, RAG document store, audit log.

No synthetic CSV backs these: conversations/messages/audit_log are written at
runtime, documents/doc_chunks by the Phase-3 RAG ingest. Shape from plan.md §2.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR

from app.config import settings
from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant | tool | system
    content = Column(Text, nullable=True)
    tool_calls = Column(JSONB, nullable=True)
    citations = Column(JSONB, nullable=True)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    doc_type = Column(String, nullable=False)  # policy | curriculum | tabular | notice
    category = Column(String, nullable=True)
    audience_roles = Column(ARRAY(String), nullable=True)
    version = Column(String, nullable=True)
    effective_date = Column(Date, nullable=True)
    source_path = Column(String, nullable=False)


class DocChunk(Base):
    __tablename__ = "doc_chunks"
    __table_args__ = (
        Index(
            "ix_doc_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_doc_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    parent_chunk_id = Column(Integer, ForeignKey("doc_chunks.id"), nullable=True)
    section = Column(String, nullable=True)
    page = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    tsv = Column(TSVECTOR, nullable=True)
    embedding = Column(Vector(settings.embedding_dim), nullable=True)
    embedding_model = Column(String, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    role = Column(String, nullable=True)
    tool_name = Column(String, nullable=False)
    args = Column(JSONB, nullable=True)
    decision = Column(String, nullable=False)  # allowed | denied | arg_stripped
    rows_returned = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
