# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from typing import Any
from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from app.services.economy_service import EconomyBalancerService

logger = logging.getLogger(__name__)


class EconomyState(BaseModel):
    period: str = ""
    zone: str = ""
    player_progression_index: float = 0.0
    drop_rate_index: float = 0.0
    crafting_loop_velocity: float = 0.0
    recommendations: list[dict[str, Any]] = []
    error: str = ""
    done: bool = False


def economy_analyze_step(state: EconomyState) -> EconomyState:
    svc = EconomyBalancerService()
    try:
        snapshot = svc.analyze({"player_progression_index": state.player_progression_index, "drop_rate_index": state.drop_rate_index, "crafting_loop_velocity": state.crafting_loop_velocity, "zone": state.zone})
        state.recommendations = snapshot.recommended_adjustments
    except Exception as e:  # noqa: BLE001
        logger.exception("Economy analysis failed")
        state.error = str(e)
    state.done = True
    return state


def build_economy_balancer_graph() -> Any:
    workflow = StateGraph(EconomyState)
    workflow.add_node("analyze", economy_analyze_step)
    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", END)
    return workflow.compile()


economy_balancer_agent = build_economy_balancer_graph()
