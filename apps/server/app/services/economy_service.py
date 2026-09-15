# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import Any
from sqlalchemy.orm import Session
from app.models.models import LoreChunkModel
from app.models.schemas import EconomyMetricSnapshot
from app.services.rag_service import HybridRetrievalService

logger = logging.getLogger(__name__)


class EconomyBalancerService:
    def __init__(self, rag: HybridRetrievalService | None = None) -> None:
        self.rag = rag or HybridRetrievalService()

    def analyze(self, metrics: dict[str, Any], db: Session | None = None) -> EconomyMetricSnapshot:
        progression = float(metrics.get("player_progression_index", 0.0))
        drop_rate = float(metrics.get("drop_rate_index", 0.0))
        crafting_velocity = float(metrics.get("crafting_loop_velocity", 0.0))
        period = datetime.utcnow().isoformat()
        adjustments: list[dict[str, Any]] = []
        if progression > 1.2:
            history = self.rag.query("player progression too fast balancing notes", kind=None, scope=None, top_k=3, db=db)
            context = " ".join(h.get("text", "") for h in history)[:2000]
            adjustments.append({"aspect": "progression", "direction": "decrease", "suggested_delta": -0.15, "rationale": "Progression index above healthy threshold; consult historical balance notes.", "rag_context": context})
        if drop_rate > 1.15:
            history = self.rag.query("drop rate too high balancing notes", kind=None, scope=None, top_k=3, db=db)
            context = " ".join(h.get("text", "") for h in history)[:2000]
            adjustments.append({"aspect": "drop_rate", "direction": "decrease", "suggested_delta": -0.12, "rationale": "Drop rate index elevated; historical balance notes may indicate soft caps.", "rag_context": context})
        if crafting_velocity > 1.2 or crafting_velocity < 0.8:
            history = self.rag.query("crafting loop balance notes", kind=None, scope=None, top_k=3, db=db)
            context = " ".join(h.get("text", "") for h in history)[:2000]
            adjustments.append({"aspect": "crafting_velocity", "direction": "recalibrate", "suggested_delta": 0.0, "rationale": "Crafting loop velocity out of expected band; review input/output ratios.", "rag_context": context})
        if not adjustments:
            adjustments.append({"aspect": "overall", "direction": "no_change", "suggested_delta": 0.0, "rationale": "Metrics within expected tolerance; no immediate adjustment recommended.", "rag_context": ""})
        return EconomyMetricSnapshot(period=period, zone=metrics.get("zone"), player_progression_index=progression, drop_rate_index=drop_rate, crafting_loop_velocity=crafting_velocity, recommended_adjustments=adjustments)

    def ingest_balance_note(self, text: str, source_id: str = "economy_notes", db: Session | None = None) -> dict[str, Any]:
        return self.rag.ingest_chunk(source_id=source_id, chunk_index=0, text=text, kind=None, scope=None, tags=["economy", "balance"], db=db)
