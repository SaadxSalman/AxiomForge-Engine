# -*- coding: utf-8 -*-
"""Dynamic Strategy Simulation Sandbox — autonomous faction agents.

Implements the turn-based strategy loop described in the AxiomForge design:

* every faction is an **autonomous agent** that first performs hybrid RAG
  retrieval over its own strategic objectives, historical grievances and
  resource constraints, and *then* commits a geopolitical move;
* the LangGraph is **cyclic** (ReAct pattern): ``plan → decide → resolve →
  (decide | finalize)`` — one cycle per turn until ``max_turns`` is reached;
* every decision, resolution and status change is broadcast to the WebSocket
  hub so the dashboard visualises the reasoning pathways live.

The move-selection heuristics are deliberately deterministic-with-jitter so a
simulation is reproducible in tests yet varied across runs.
"""
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
    """Mutable world state threaded through the cyclic LangGraph."""

    run_id: str = ""
    turn: int = 0
    max_turns: int = 20
    factions: dict[str, dict[str, Any]] = {}
    relations: dict[str, dict[str, str]] = {}
    moves: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    world_state: dict[str, Any] = {}
    step: int = 0
    done: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# Canon faction registry (fallback when a run specifies only names)
# ---------------------------------------------------------------------------

CANON_FACTIONS: dict[str, dict[str, Any]] = {
    "iron_covenant": {
        "name": "Iron Covenant",
        "color": "#a855f7",
        "objective": "Consolidate the steel trade and garrison the Ashen Peaks passes",
        "grievances": ["The Free Marches smuggle weapons past its blockade"],
        "resources": {"gold": 80, "manpower": 65, "influence": 70},
    },
    "verdant_compact": {
        "name": "Verdant Compact",
        "color": "#10b981",
        "objective": "Protect the ancient groves while brokering peace between rivals",
        "grievances": ["Ashen Dominion loggers crossed the root-border"],
        "resources": {"gold": 55, "manpower": 45, "influence": 85},
    },
    "ashen_dominion": {
        "name": "Ashen Dominion",
        "color": "#ef4444",
        "objective": "Expand the ash-forges and dominate the southern trade sea",
        "grievances": ["The Iron Covenant annexed the ember mines"],
        "resources": {"gold": 90, "manpower": 75, "influence": 40},
    },
    "free_marches": {
        "name": "Free Marches",
        "color": "#f59e0b",
        "objective": "Keep every toll road open and every crown indebted",
        "grievances": ["Iron Covenant tariffs strangle caravan profits"],
        "resources": {"gold": 60, "manpower": 50, "influence": 60},
    },
    "northern_empire": {
        "name": "Northern Empire",
        "color": "#3b82f6",
        "objective": "Secure the northern trade corridors and suppress piracy",
        "grievances": ["Southern kingdoms tax the strait"],
        "resources": {"gold": 80, "manpower": 60, "influence": 70},
    },
    "southern_union": {
        "name": "Southern Union",
        "color": "#06b6d4",
        "objective": "Control the lucrative southern sea trade and flood markets with luxury goods",
        "grievances": ["Northern Empire privateers raid its grain convoys"],
        "resources": {"gold": 70, "manpower": 55, "influence": 65},
    },
}


def _slugify(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name.strip().lower()).strip("_")


# ---------------------------------------------------------------------------
# State normalisation & helpers
# ---------------------------------------------------------------------------

_RNG = random.Random()

_DEFAULT_FACTION_ORDER = ["iron_covenant", "verdant_compact", "ashen_dominion", "free_marches"]

_PALETTE = ["#a78bfa", "#34d399", "#f87171", "#fbbf24", "#60a5fa", "#22d3ee"]


def _deep_copy(faction: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(faction))


def _canonical_faction(slug_or_name: str) -> dict[str, Any]:
    """Return a canon faction registry entry (or a synthesised one)."""
    key = _slugify(slug_or_name)
    if key in CANON_FACTIONS:
        return _deep_copy(CANON_FACTIONS[key])
    for slug, faction in CANON_FACTIONS.items():
        if _slugify(faction["name"]) == key:
            return _deep_copy(faction)
    display = slug_or_name.replace("_", " ").title()
    return {
        "name": display,
        "color": _PALETTE[sum(ord(c) for c in key) % len(_PALETTE)],
        "objective": f"Survive and expand the influence of {display}.",
        "grievances": [],
        "resources": {"gold": 60, "manpower": 55, "influence": 55},
    }


def normalize_factions(factions: Any) -> dict[str, dict[str, Any]]:
    """Normalise every accepted faction shape into ``{slug: faction_dict}``.

    Accepted inputs:

    * ``None`` / empty — defaults to the four canon factions;
    * ``["Iron Covenant", ...]`` — bare names (matched against the canon
      registry, unknown names synthesised);
    * ``[{"name": ..., "objective": ..., "resources": {...}}, ...]`` — full
      faction dicts (missing fields fall back to canon/defaults);
    * ``{"iron_covenant": {...}, ...}`` — mapping keyed by slug.
    """
    if factions is None or factions == [] or factions == {}:
        raw: list[Any] = list(_DEFAULT_FACTION_ORDER)
    elif isinstance(factions, dict):
        raw = []
        for key, val in factions.items():
            if isinstance(val, dict):
                merged = dict(val)
                merged.setdefault("name", str(key))
                raw.append(merged)
            else:
                raw.append(str(key))
    elif isinstance(factions, (list, tuple)):
        raw = list(factions)
    else:
        raw = [str(factions)]

    roster: dict[str, dict[str, Any]] = {}
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("id") or "unnamed_faction")
            slug = _slugify(str(item.get("id") or name))
            base = _canonical_faction(slug)
            for k, v in item.items():
                if v is not None:
                    base[k] = v
            base["name"] = name
            roster[slug] = base
        else:
            slug = _slugify(str(item))
            roster.setdefault(slug, _canonical_faction(str(item)))
        if len(roster) >= 6:
            break

    # A sandbox needs at least two rivals to be interesting.
    if len(roster) < 2:
        for slug in _DEFAULT_FACTION_ORDER:
            roster.setdefault(slug, _deep_copy(CANON_FACTIONS[slug]))
            if len(roster) >= 2:
                break
    return roster


def _ensure_relations(factions: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Initialise the symmetric relation matrix (everything neutral)."""
    return {a: {b: "neutral" for b in factions if b != a} for a in factions}


def _broadcast(
    state: SimulationState,
    *,
    thought: str,
    action: str,
    observation: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit an ``AgentStepOut`` to the WebSocket hub (never raises)."""
    try:
        from app.models.schemas import AgentStepOut
        from app.websocket import broadcast_step

        state.step += 1
        broadcast_step(
            state.run_id or "simulation",
            AgentStepOut(
                agent_id=state.run_id or "simulation",
                step=state.step,
                thought=thought,
                action=action,
                observation=observation or None,
                done=False,
                metadata=metadata or {},
            ),
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("Simulation broadcast skipped: %s", e)


def _retrieve_canon(query: str, top_k: int = 2) -> str:
    """Hybrid-RAG recall of a faction's objectives / grievances / constraints."""
    try:
        rag = HybridRetrievalService()
        hits = rag.query(query, kind=None, scope=None, top_k=top_k)
        return " | ".join(h.get("text", "")[:180] for h in hits if h.get("text"))
    except Exception as e:  # noqa: BLE001
        logger.debug("Faction RAG recall unavailable: %s", e)
        return ""


# ---------------------------------------------------------------------------
# Graph nodes — plan → decide → resolve (cyclic) → finalize
# ---------------------------------------------------------------------------

def sim_plan_step(state: SimulationState) -> SimulationState:
    """Node 1 — initialise relations + world state, announce the roster."""
    if not state.relations:
        state.relations = _ensure_relations(state.factions)
    state.world_state = {"turn": 0, "active_wars": 0, "trade_pacts": 0, "last_move": None}
    roster = [f.get("name", slug) for slug, f in state.factions.items()]
    _broadcast(
        state,
        thought=f"Planning horizon: {state.max_turns} turns. Roster: {', '.join(roster)}.",
        action="plan",
        observation=json.dumps({"factions": roster}),
        metadata={"max_turns": state.max_turns},
    )
    return state


def _select_move(
    state: SimulationState, slug: str, faction: dict[str, Any]
) -> dict[str, Any]:
    """Deterministic-with-jitter geopolitical move selection (ReAct *action*)."""
    res = faction.get("resources", {}) or {}
    gold = int(res.get("gold", 0))
    manpower = int(res.get("manpower", 0))
    influence = int(res.get("influence", 0))
    neighbours = [b for b in state.factions if b != slug]
    wars = [b for b, st in state.relations.get(slug, {}).items() if st == "war"]
    neutral = [b for b in neighbours if state.relations.get(slug, {}).get(b) == "neutral"]
    grievances = len(faction.get("grievances", []) or [])

    if wars and manpower >= 35:
        target = wars[0]
        return {
            "move_type": MoveType.DECLARE_WAR.value,
            "payload": {"target": target, "front": "ashen_passes", "strength": manpower},
            "confidence": "high",
            "rationale": f"Already at war with {state.factions.get(target, {}).get('name', target)}; pressing the offensive.",
        }
    if grievances and influence >= 60 and _RNG.random() < 0.55 and neighbours:
        target = neutral[0] if neutral else neighbours[0]
        return {
            "move_type": MoveType.COVERT_OP.value,
            "payload": {"target": target, "operation": "sabotage_supply_lines"},
            "confidence": "medium",
            "rationale": "High influence and unresolved grievances enable deniable action.",
        }
    if neutral and (gold >= 60 or influence >= 65) and _RNG.random() < 0.6:
        target = neutral[0]
        return {
            "move_type": MoveType.PROPOSE_TRADE.value,
            "payload": {
                "target": target,
                "offer": {"gold": max(5, gold // 8), "good": "steel"},
                "request": "open_borders",
            },
            "confidence": "medium",
            "rationale": "Surplus resources make a mutually beneficial pact likely.",
        }
    if manpower >= 50 and _RNG.random() < 0.5:
        return {
            "move_type": MoveType.MOBILIZE.value,
            "payload": {"target": "border_region", "strength": manpower},
            "confidence": "medium",
            "rationale": "Large reserves allow a show of force without open war.",
        }
    return {
        "move_type": MoveType.DIPLOMATIC_PLEA.value,
        "payload": {"target": "all", "message": faction.get("objective", "peace")},
        "confidence": "low",
        "rationale": "Limited resources leave only diplomacy on the table.",
    }


def sim_decide_step(state: SimulationState) -> SimulationState:
    """Node 2 — one RAG-grounded decision per faction for the next turn."""
    turn = state.turn + 1
    state.turn = turn  # persist the turn so the resolve/router nodes see it
    for slug, faction in state.factions.items():
        canon = _retrieve_canon(
            f"{faction.get('name', slug)} strategic objectives grievances resources "
            f"{faction.get('objective', '')}"
        )
        choice = _select_move(state, slug, faction)
        state.moves.append(
            {
                "turn": turn,
                "faction_id": slug,
                "actor_type": "faction_agent",
                "move_type": choice["move_type"],
                "payload_json": json.dumps(choice["payload"]),
                "rag_context": canon[:900],
                "confidence": choice["confidence"],
                "rationale": choice["rationale"],
            }
        )
        _broadcast(
            state,
            thought=(
                f"{faction.get('name', slug)} → {choice['move_type']} "
                f"({choice['confidence']}). {choice['rationale']}"
            ),
            action="decide",
            observation=json.dumps(choice["payload"]),
            metadata={
                "turn": turn,
                "faction": slug,
                "faction_name": faction.get("name", slug),
                "color": faction.get("color"),
                "move_type": choice["move_type"],
            },
        )
    return state




# ---------------------------------------------------------------------------
# resolve / finalize nodes + cyclic graph assembly
# ---------------------------------------------------------------------------

def sim_resolve_step(state: SimulationState) -> SimulationState:
    """Apply the committed moves for this turn to relations/resources/world."""
    turn_moves = [m for m in state.moves if m.get("turn") == state.turn]
    for mv in turn_moves:
        fid = mv.get("faction_id", "")
        try:
            payload = json.loads(mv.get("payload_json") or "{}")
        except Exception:  # noqa: BLE001
            payload = {}
        faction = state.factions.get(fid, {})
        res = faction.setdefault("resources", {})
        target = str(payload.get("target", ""))
        target_slug = _slugify(target) if target and target != "all neighbors" else ""
        mt = mv.get("move_type")

        if mt == MoveType.DECLARE_WAR.value:
            if target_slug and target_slug in state.factions:
                state.relations.setdefault(fid, {})[target_slug] = "war"
                state.relations.setdefault(target_slug, {})[fid] = "war"
            res["manpower"] = int(res.get("manpower", 0)) - 5
            state.events.append(
                {"turn": state.turn, "faction_id": fid, "event_type": "war_declared",
                 "description": f"{faction.get('name', fid)} declared war on {target or 'a rival'}."}
            )
        elif mt == MoveType.PROPOSE_TRADE.value:
            if target_slug and target_slug in state.factions:
                state.relations.setdefault(fid, {})[target_slug] = "trade"
                state.relations.setdefault(target_slug, {})[fid] = "trade"
            res["gold"] = int(res.get("gold", 0)) + 6
            state.events.append(
                {"turn": state.turn, "faction_id": fid, "event_type": "trade_pact",
                 "description": f"{faction.get('name', fid)} proposed a trade pact with {target or 'neighbours'}."}
            )
        elif mt == MoveType.COVERT_OP.value:
            res["influence"] = int(res.get("influence", 0)) + 4
            res["gold"] = int(res.get("gold", 0)) - 4
            state.events.append(
                {"turn": state.turn, "faction_id": fid, "event_type": "covert_op",
                 "description": f"{faction.get('name', fid)} ran a covert operation against {target or 'a rival'}."}
            )
        elif mt == MoveType.MOBILIZE.value:
            res["manpower"] = int(res.get("manpower", 0)) + 4
            state.events.append(
                {"turn": state.turn, "faction_id": fid, "event_type": "mobilization",
                 "description": f"{faction.get('name', fid)} mobilized forces at {target or 'the border'}."}
            )
        else:  # diplomatic_plea
            res["influence"] = int(res.get("influence", 0)) + 3
            state.events.append(
                {"turn": state.turn, "faction_id": fid, "event_type": "diplomacy",
                 "description": f"{faction.get('name', fid)} issued a diplomatic plea."}
            )

    state.world_state = {
        "turn": state.turn,
        "active_wars": sorted(
            {f"{a}--{b}" for a, rels in state.relations.items() for b, v in rels.items() if v == "war" and a < b}
        ),
        "trade_pacts": sorted(
            {f"{a}--{b}" for a, rels in state.relations.items() for b, v in rels.items() if v == "trade" and a < b}
        ),
        "last_move": turn_moves[-1]["faction_id"] if turn_moves else None,
    }
    _broadcast(
        state,
        thought=f"Resolved turn {state.turn} — {len(turn_moves)} moves applied.",
        action="resolve",
        observation=json.dumps(state.world_state),
        metadata={"turn": state.turn, "world_state": state.world_state},
    )
    return state


def _route_after_resolve(state: SimulationState) -> str:
    return "finalize" if state.turn >= state.max_turns else "decide"


def sim_finalize_step(state: SimulationState) -> SimulationState:
    state.done = True
    wars = sum(1 for rs in state.relations.values() for v in rs.values() if v == "war") // 2
    pacts = sum(1 for rs in state.relations.values() for v in rs.values() if v == "trade") // 2
    summary = {
        "turns": state.turn,
        "moves": len(state.moves),
        "events": len(state.events),
        "wars": wars,
        "trade_pacts": pacts,
    }
    state.world_state.update(summary)
    _broadcast(
        state,
        thought=f"Finalized — {summary['moves']} moves across {summary['turns']} turns.",
        action="finalize",
        observation=json.dumps(summary),
        metadata=summary,
    )
    return state


def build_strategy_simulator_graph() -> Any:
    workflow = StateGraph(SimulationState)
    workflow.add_node("plan", sim_plan_step)
    workflow.add_node("decide", sim_decide_step)
    workflow.add_node("resolve", sim_resolve_step)
    workflow.add_node("finalize", sim_finalize_step)
    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "decide")
    workflow.add_edge("decide", "resolve")
    workflow.add_conditional_edges(
        "resolve",
        _route_after_resolve,
        {"decide": "decide", "finalize": "finalize"},
    )
    workflow.add_edge("finalize", END)
    return workflow.compile()


strategy_simulator_agent = build_strategy_simulator_graph()

