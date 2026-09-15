# -*- coding: utf-8 -*-
"""Lore management endpoints: ingest, hybrid search, and lore-expansion planning."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.models import ChunkKind, Scope
from app.services.rag_service import HybridRetrievalService
from app.worker import ingest_document as ingest_task
from app.agents.lore_keeper import LoreKeeperState, lore_keeper_agent, _parse_document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lore", tags=["lore"])


class IngestDocumentRequest(BaseModel):
    """Raw game design document to index into the knowledge base."""

    source_id: str = Field(..., description="Stable identifier for the source document")
    text: str = Field(..., description="Full document text")


class QueryRequest(BaseModel):
    """Parameters for a hybrid knowledge-base search."""

    query_text: str
    kind: str | None = None
    scope: str | None = None
    top_k: int = Field(default=8, ge=1, le=50)


class PlanLoreRequest(BaseModel):
    """A lore-expansion planning request."""

    query: str
    source_text: str = ""


@router.post("/ingest", response_model=dict[str, Any], summary="Ingest a game design document")
def ingest_document(
        body: IngestDocumentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Parse, chunk, and index a design document; also enqueues a Celery re-ingest."""
    chunks = _parse_document(body.text, body.source_id)
    rag = HybridRetrievalService()
    results: list[dict[str, Any]] = []
    for chunk in chunks:
        try:
            kind = ChunkKind(chunk.get("kind", "lore"))
        except ValueError:
            kind = ChunkKind.LORE
        try:
            scope = Scope(chunk.get("scope", "world"))
        except ValueError:
            scope = Scope.WORLD
        results.append(
            rag.ingest_chunk(
                source_id=chunk["source_id"],
                chunk_index=chunk["chunk_index"],
                text=chunk["text"],
                kind=kind,
                scope=scope,
                tags=chunk.get("tags", []),
                db=db,
            )
        )
    background_tasks.add_task(ingest_task, source_id=body.source_id, text=body.text)
    return {"source_id": body.source_id, "chunks_indexed": len(results), "results": results}


@router.post("/query", response_model=list[dict[str, Any]], summary="Hybrid search the knowledge base")
def query_lore(body: QueryRequest, db: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Dense-vector + graph retrieval across Weaviate and pgvector."""
    rag = HybridRetrievalService()
    kind_enum: ChunkKind | None = None
    scope_enum: Scope | None = None
    if body.kind:
        try:
            kind_enum = ChunkKind(body.kind.lower())
        except ValueError:
            pass
    if body.scope:
        try:
            scope_enum = Scope(body.scope.lower())
        except ValueError:
            pass
    return rag.query(body.query_text, kind=kind_enum, scope=scope_enum, top_k=body.top_k, db=db)


@router.post("/plan", response_model=dict[str, Any], summary="Plan lore expansion")
def plan_lore(body: PlanLoreRequest) -> dict[str, Any]:
    """Run the Autonomous Lore Keeper agent over a query (synchronous)."""
    state = LoreKeeperState(query=body.query, source_text=body.source_text)
    try:
        final = lore_keeper_agent.invoke(state.model_dump())
    except Exception as e:  # noqa: BLE001
        logger.exception("plan_lore inline failed")
        return {
            "query": body.query,
            "draft_lore": "",
            "canon_check_passed": False,
            "error": str(e),
            "context_count": 0,
        }
    return {
        "query": body.query,
        "draft_lore": final.get("draft_lore", ""),
        "canon_check_passed": final.get("canon_check_passed", False),
        "context_count": len(final.get("context", [])),
        "error": final.get("error", ""),
    }
