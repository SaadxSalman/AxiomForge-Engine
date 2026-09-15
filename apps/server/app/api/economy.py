# -*- coding: utf-8 -*-
"""Dynamic economy-balance analysis endpoints."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.schemas import EconomyMetricSnapshot
from app.services.economy_service import EconomyBalancerService
from app.services.rag_service import HybridRetrievalService
from app.worker import balance_economy as balance_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/economy", tags=["economy"])


class AnalyzeEconomyRequest(BaseModel):
    """Player-progression economy metrics to evaluate."""

    period: str | None = None
    zone: str | None = None
    player_progression_index: float = Field(default=0.0, ge=0.0)
    drop_rate_index: float = Field(default=0.0, ge=0.0)
    crafting_loop_velocity: float = Field(default=0.0, ge=0.0)


class IngestBalanceNoteRequest(BaseModel):
    """A historical balance-design note to index."""

    source_id: str = Field(default="economy_notes", description="Source identifier")
    text: str


@router.post("/analyze", response_model=EconomyMetricSnapshot, summary="Analyze economy metrics")
def analyze_economy(
        body: AnalyzeEconomyRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
) -> EconomyMetricSnapshot:
    """Analyze live economy metrics and produce adjustment recommendations."""
    svc = EconomyBalancerService()
    snapshot = svc.analyze(body.model_dump(), db=db)
    background_tasks.add_task(balance_task, metrics=body.model_dump())
    return snapshot


@router.post("/notes", response_model=dict[str, Any], summary="Index a historical balance note")
def ingest_balance_note(
    body: IngestBalanceNoteRequest,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Index a historical balance note for vector/ graph retrieval."""
    rag = HybridRetrievalService()
    return rag.ingest_chunk(
        source_id=body.source_id,
        chunk_index=0,
        text=body.text,
        kind=None,
        scope=None,
        tags=["economy", "balance"],
        db=db,
    )
