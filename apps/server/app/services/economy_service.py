# -*- coding: utf-8 -*-
"""Real-time economy analytics service.

The :class:`EconomyBalancerService` analyses live economy metrics against
configured "healthy" thresholds and uses the hybrid RAG retriever to attach
historical balance-design context to each recommendation.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import LoreChunkModel
from app.models.schemas import EconomyMetricSnapshot
from app.services.rag_service import HybridRetrievalService

logger = logging.getLogger(__name__)


# Thresholds outside which the balancer issues an adjustment recommendation.
PROGRESSION_SOFT_CAP = 1.2
DROP_RATE_SOFT_CAP = 1.15
CRAFTING_VELOCITY_MIN = 0.8
CRAFTING_VELOCITY_MAX = 1.2


class EconomyBalancerService:
    """Monitors player-progression metrics and recommends balance tweaks."""

    def __init__(self, rag: HybridRetrievalService | None = None) -> None:
        self.rag = rag or HybridRetrievalService()

    def analyze(self, metrics: dict[str, Any], db: Session | None = None) -> EconomyMetricSnapshot:
        progression = float(metrics.get("player_progression_index", 0.0))
        drop_rate = float(metrics.get("drop_rate_index", 0.0))
        crafting_velocity = float(metrics.get("crafting_loop_velocity", 0.0))
        period = datetime.now(timezone.utc).isoformat()
        adjustments: list[dict[str, Any]] = []

        if progression > PROGRESSION_SOFT_CAP:
            history = self.rag.query(
                "player progression too fast balancing notes", kind=None, scope=None, top_k=3, db=db
            )
            context = " ".join(h.get("text", "") for h in history)[:2000]
            adjustments.append(
                {
                    "aspect": "progression",
                    "direction": "decrease",
                    "suggested_delta": -0.15,
                    "rationale": "Progression index above healthy threshold; consult historical balance notes.",
                    "rag_context": context,
                }
            )
        if drop_rate > DROP_RATE_SOFT_CAP:
            history = self.rag.query(
                "drop rate too high balancing notes", kind=None, scope=None, top_k=3, db=db
            )
            context = " ".join(h.get("text", "") for h in history)[:2000]
            adjustments.append(
                {
                    "aspect": "drop_rate",
                    "direction": "decrease",
                    "suggested_delta": -0.12,
                    "rationale": "Drop rate index elevated; historical balance notes may indicate soft caps.",
                    "rag_context": context,
                }
            )
        if crafting_velocity > CRAFTING_VELOCITY_MAX or crafting_velocity < CRAFTING_VELOCITY_MIN:
            history = self.rag.query("crafting loop balance notes", kind=None, scope=None, top_k=3, db=db)
            context = " ".join(h.get("text", "") for h in history)[:2000]
            adjustments.append(
                {
                    "aspect": "crafting_velocity",
                    "direction": "recalibrate",
                    "suggested_delta": 0.0,
                    "rationale": "Crafting loop velocity out of expected band; review input/output ratios.",
                    "rag_context": context,
                }
            )
        if not adjustments:
            adjustments.append(
                {
                    "aspect": "overall",
                    "direction": "no_change",
                    "suggested_delta": 0.0,
                    "rationale": "Metrics within expected tolerance; no immediate adjustment recommended.",
                    "rag_context": "",
                }
            )

        return EconomyMetricSnapshot(
            period=period,
            zone=metrics.get("zone"),
            player_progression_index=progression,
            drop_rate_index=drop_rate,
            crafting_loop_velocity=crafting_velocity,
            recommended_adjustments=adjustments,
        )

    def ingest_balance_note(
        self, text: str, source_id: str = "economy_notes", db: Session | None = None
    ) -> dict[str, Any]:
        return self.rag.ingest_chunk(
            source_id=source_id,
            chunk_index=0,
            text=text,
            kind=None,
            scope=None,
            tags=["economy", "balance"],
            db=db,
        )
