# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from typing import Any
from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from app.models.models import ChunkKind, Scope
from app.services.rag_service import HybridRetrievalService
from app.config import settings

logger = logging.getLogger(__name__)


class LoreKeeperState(BaseModel):
    query: str = ""
    source_text: str = ""
    chunks: list[dict[str, Any]] = []
    context: list[dict[str, Any]] = []
    draft_lore: str = ""
    canon_check_passed: bool = False
    error: str = ""
    step: int = 0


def _parse_document(text: str, source_id: str) -> list[dict[str, Any]]:
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[dict[str, Any]] = []
    idx = 0
    current_kind: str = "lore"
    for para in parts:
        lowered = para.lower()
        if any(h in lowered for h in ["rules of the world", "mechanics", "systems"]):
            current_kind = "rule"
        elif any(h in lowered for h in ["geography", "map", "region", "continents"]):
            current_kind = "geography"
        elif any(h in lowered for h in ["faction", "kingdom", "guild", "nation"]):
            current_kind = "faction"
        elif any(h in lowered for h in ["economy", "currency", "trade"]):
            current_kind = "economy"
        else:
            current_kind = "lore"
        if len(para) > 60:
            chunks.append({"text": para, "kind": current_kind, "scope": "world", "source_id": source_id, "chunk_index": idx})
            idx += 1
    return chunks


def lore_plan_step(state: LoreKeeperState) -> LoreKeeperState:
    state.step = 1
    return state


def lore_retrieve_step(state: LoreKeeperState) -> LoreKeeperState:
    state.step = 2
    rag = HybridRetrievalService()
    try:
        kind_str = state.query.lower()
        kind: ChunkKind | None = None
        scope: Scope | None = None
        if "rule" in kind_str or "mechanic" in kind_str:
            kind = ChunkKind.RULE
        elif "geography" in kind_str or "map" in kind_str or "region" in kind_str:
            kind = ChunkKind.GEOGRAPHY
            scope = Scope.REGION
        elif "faction" in kind_str or "kingdom" in kind_str or "guild" in kind_str:
            kind = ChunkKind.FACTION
            scope = Scope.FACTION
        elif "economy" in kind_str or "trade" in kind_str or "currency" in kind_str:
            kind = ChunkKind.ECONOMY
            scope = Scope.SYSTEM
        results = rag.query(state.query, kind=kind, scope=scope, top_k=8)
        state.context = results
    except Exception as e:  # noqa: BLE001
        logger.exception("Lore retrieval failed")
        state.error = str(e)
    return state


def lore_draft_step(state: LoreKeeperState) -> LoreKeeperState:
    state.step = 3
    snippet = "\n".join("- [unknown] " + (c.get("text", "")[:250]) for c in state.context[:5])
    prompt = ("You are the Autonomous Lore Keeper. Draft a small lore expansion consistent with the following canon context:\n\n" + snippet + "\n\nUser request: " + state.query + "\n\nOutput only the lore text, no preamble.")
    state.draft_lore = "Lore expansion placeholder for: " + state.query
    return state


def lore_validate_step(state: LoreKeeperState) -> LoreKeeperState:
    state.step = 4
    state.canon_check_passed = True
    return state


def build_lore_keeper_graph() -> Any:
    workflow = StateGraph(LoreKeeperState)
    workflow.add_node("plan", lore_plan_step)
    workflow.add_node("retrieve", lore_retrieve_step)
    workflow.add_node("draft", lore_draft_step)
    workflow.add_node("validate", lore_validate_step)
    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "retrieve")
    workflow.add_edge("retrieve", "draft")
    workflow.add_edge("draft", "validate")
    workflow.add_edge("validate", END)
    return workflow.compile()


lore_keeper_agent = build_lore_keeper_graph()
