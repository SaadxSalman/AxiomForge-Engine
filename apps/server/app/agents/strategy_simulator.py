# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
import random
from typing import Any
from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from app.models.models import MoveType
from app.services.rag_service import HybridRetrievalService

logger = logging.getLogger(__name__)


class SimulationState(BaseModel):
    run_id: str = ""
    turn: int = 1
    max_turns: int = 20
    factions: dict[str, dict[str, Any]] = {}
    moves: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    world_state: dict[str, Any] = {}
    error: str = ""
    done: bool = False


def _default_factions() -> dict[str, dict[str, Any]]:
    return {
        "northern_empire": {"name": "Northern Empire", "objective": "Secure the northern trade corridors and suppress piracy", "grievances": ["Southern kingdoms tax the strait"], "resources": {"gold": 80, "manpower": 60, "influence": 70}},
        "southern_union": {"name": "Southern Union", "objective": "Control the lucrative southern sea trade and fund expeditions", "grievances": ["Northern blockades threaten supply lines"], "resources": {"gold": 90, "manpower": 50, "influence": 60}},
        "highland_confederacy": {"name": "Highland Confederacy", "objective": "Maintain independence and profit from mediation", "grievances": ["Both neighbors demand tolls"], "resources": {"gold": 40, "manpower": 90, "influence": 50}},
    }


def sim_plan_step(state: SimulationState) -> SimulationState:
    return state


def sim_retrieve_for_faction(state: SimulationState, faction_id: str) -> dict[str, Any]:
    rag = HybridRetrievalService()
    faction = state.factions.get(faction_id, {})
    query = "Strategic objectives and historical grievances for " + faction.get("name", "")
    try:
        context = rag.query(query, kind=None, scope=None, top_k=4)
    except Exception as e:  # noqa: BLE001
        logger.debug("RAG query for faction %s failed: %s", faction_id, e)
        context = []
    return {"faction_id": faction_id, "context": context, "resources": faction.get("resources", {})}


def _choose_move(faction_id: str, faction: dict[str, Any], rag_info: dict[str, Any], world: dict[str, Any]) -> dict[str, Any]:
    resources = faction.get("resources", {})
    grievances = faction.get("grievances", [])
    if resources.get("gold", 50) < 25:
        return {"move_type": MoveType.PROPOSE_TRADE.value, "payload": {"target": random.choice(["northern_empire", "southern_union", "highland_confederacy"]), "terms": "resource exchange"}, "confidence": "high"}
    if resources.get("influence", 0) > 60 and grievances:
        return {"move_type": MoveType.COVERT_OP.value, "payload": {"target": random.choice(grievances), "method": "sabotage"}, "confidence": "medium"}
    if resources.get("manpower", 0) > 50:
        return {"move_type": MoveType.MOBILIZE.value, "payload": {"target": "border_region", "strength": resources["manpower"]}, "confidence": "medium"}
    return {"move_type": MoveType.DIPLOMATIC_PLEA.value, "payload": {"target": "neighbors", "message": faction.get("objective", "")}, "confidence": "low"}


def sim_decide_step(state: SimulationState) -> SimulationState:
    state.turn += 1
    for faction_id, faction in state.factions.items():
        rag_info = sim_retrieve_for_faction(state, faction_id)
        move = _choose_move(faction_id, faction, rag_info, state.world_state)
        state.moves.append({"turn": state.turn, "faction_id": faction_id, "actor_type": "agent", "move_type": move["move_type"], "payload_json": json.dumps(move.get("payload", {})), "rag_context": json.dumps(rag_info.get("context", [])[:2]), "confidence": move.get("confidence", "medium")})
        event = {"turn": state.turn, "faction_id": faction_id, "event_type": move["move_type"], "description": faction.get("name", "") + " initiated " + move["move_type"] + "."}
        if event:
            state.events.append(event)
    return state


def sim_finalize_step(state: SimulationState) -> SimulationState:
    state.done = state.turn >= state.max_turns
    return state


def build_strategy_simulator_graph() -> Any:
    workflow = StateGraph(SimulationState)
    workflow.add_node("plan", sim_plan_step)
    workflow.add_node("decide", sim_decide_step)
    workflow.add_node("finalize", sim_finalize_step)
    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "decide")
    workflow.add_edge("decide", "finalize")
    workflow.add_edge("finalize", END)
    return workflow.compile()


strategy_simulator_agent = build_strategy_simulator_graph()
