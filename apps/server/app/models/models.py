# -*- coding: utf-8 -*-
"""SQLAlchemy ORM models for AxiomForge-Engine.

Defines the canonical schema for lore-chunk storage (with a ``pgvector``
embedding column), the dynamic-strategy simulation tables and the supporting
PostgreSQL ``ENUM`` types used throughout the RAG/agents pipeline.
"""
from __future__ import annotations

import datetime as dt
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.config import settings


class ChunkKind(str, Enum):
    LORE = "lore"
    RULE = "rule"
    GEOGRAPHY = "geography"
    FACTION = "faction"
    ECONOMY = "economy"


class Scope(str, Enum):
    WORLD = "world"
    REGION = "region"
    FACTION = "faction"
    SYSTEM = "system"


class SimulationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class MoveType(str, Enum):
    DECLARE_WAR = "declare_war"
    PROPOSE_TRADE = "propose_trade"
    COVERT_OP = "covert_op"
    MOBILIZE = "mobilize"
    DIPLOMATIC_PLEA = "diplomatic_plea"


class LoreChunkModel(Base):
    __tablename__ = "lore_chunks"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_id = Column(String(255), nullable=False, index=True)
    chunk_index = Column(BigInteger, nullable=False)
    text = Column(Text, nullable=False)
    kind = Column(SAEnum(ChunkKind, name="chunk_kind", create_type=True), nullable=False)
    scope = Column(SAEnum(Scope, name="chunk_scope", create_type=True), nullable=False)
    tags = Column(Text, nullable=True)
    # The pgvector ``Vector`` type is attached in ``_ensure_pgvector_column`` so
    # that importing this module never hard-fails when pgvector is unavailable.
    embedding = Column(type_=None, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    __table_args__ = (Index("ix_lore_chunks_embedding", "embedding", postgresql_using="hnsw"),)


def _ensure_pgvector_column() -> None:
    """Attach the ``pgvector`` ``Vector`` type to the embedding column.

    ``pgvector``'s SQLAlchemy ``Vector`` type takes a single ``dim`` argument
    (the embedding dimensionality).  It is attached once at import time so the
    rest of the code can rely on the column being a proper vector column.
    """
    try:
        from pgvector.sqlalchemy import Vector as PGVector

        col = LoreChunkModel.__table__.c["embedding"]
        if not getattr(col.type, "dimensions", None):
            col.type = PGVector(settings.pg_vector_dim)
    except Exception as e:  # noqa: BLE001
        # Importing/attaching pgvector is optional — the column stays as a
        # generic nullable column and vector search degrades gracefully.
        import logging

        logging.getLogger(__name__).warning("pgvector column not attached: %s", e)


_ensure_pgvector_column()


class SimulationRunModel(Base):
    __tablename__ = "simulation_runs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    status = Column(
        SAEnum(SimulationStatus, name="sim_status", create_type=True),
        nullable=False,
        default=SimulationStatus.PENDING,
    )
    config_json = Column(Text, nullable=True)
    turn_count = Column(BigInteger, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    moves = relationship("SimulationMoveModel", back_populates="run", cascade="all, delete-orphan")
    events = relationship("SimulationEventModel", back_populates="run", cascade="all, delete-orphan")


class SimulationMoveModel(Base):
    __tablename__ = "simulation_moves"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("simulation_runs.id"), nullable=False, index=True)
    turn = Column(BigInteger, nullable=False)
    faction_id = Column(String(255), nullable=False)
    actor_type = Column(String(64), nullable=False)
    move_type = Column(SAEnum(MoveType, name="move_type", create_type=True), nullable=False)
    payload_json = Column(Text, nullable=True)
    rag_context = Column(Text, nullable=True)
    confidence = Column(String(16), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    run = relationship("SimulationRunModel", back_populates="moves")


class SimulationEventModel(Base):
    __tablename__ = "simulation_events"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("simulation_runs.id"), nullable=False, index=True)
    turn = Column(BigInteger, nullable=False)
    faction_id = Column(String(255), nullable=False)
    event_type = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    run = relationship("SimulationRunModel", back_populates="events")
