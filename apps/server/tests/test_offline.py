# -*- coding: utf-8 -*-
"""Offline test-suite for AxiomForge-Engine.

Everything runs WITHOUT Postgres/Neo4j/Weaviate/Redis — the retrieval
circuit-breakers degrade gracefully and the LangGraph agents execute
deterministically.  Run with::

    cd apps/server && python -m pytest tests -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Ensure no "real" LLM key leaks from the environment during tests.
os.environ.setdefault("LLM_API_KEY", "")


# ---------------------------------------------------------------------------
# FastAPI app + routes
# ---------------------------------------------------------------------------


def test_app_routes_registered() -> None:
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    for expected in (
        "/health",
        "/ready",
        "/lore/ingest",
        "/lore/query",
        "/lore/plan",
        "/simulation/runs",
        "/simulation/runs/{run_id}",
        "/simulation/runs/{run_id}/moves",
        "/simulation/runs/{run_id}/events",
        "/simulation/runs/{run_id}/start",
        "/economy/analyze",
        "/economy/notes",
        "/ws/{run_id}",
    ):
        assert expected in paths, f"missing route {expected}"


# ---------------------------------------------------------------------------
# Hybrid retrieval service (offline fallback chain)
# ---------------------------------------------------------------------------


def test_deterministic_hash_embeddings_are_stable() -> None:
    from app.services.rag_service import _hash_embed

    a = _hash_embed("The Iron Covenant garrisons the Ashen Peaks passes")
    b = _hash_embed("The Iron Covenant garrisons the Ashen Peaks passes")
    c = _hash_embed("Verdant Compact protects the ancient groves")
    assert a == b, "same text must yield the identical vector"
    assert a != c, "different text should differ"
    assert len(a) == 1536
    norm = sum(v * v for v in a) ** 0.5
    assert abs(norm - 1.0) < 1e-6, "vector must be L2-normalized"


def test_related_texts_score_higher_than_unrelated() -> None:
    from app.services.rag_service import _hash_embed

    def cos(x: list[float], y: list[float]) -> float:
        return sum(a * b for a, b in zip(x, y))

    base = _hash_embed("iron covenant steel trade garrison war ashen peaks")
    near = _hash_embed("iron covenant steel trade garrison war ashen peaks and ore mines")
    far = _hash_embed("verdant compact groves peace brokering ancient root border")
    assert cos(base, near) > cos(base, far), "vocabulary overlap must dominate cosine"


def test_hybrid_query_degrades_gracefully_offline() -> None:
    from app.services.rag_service import HybridRetrievalService

    rag = HybridRetrievalService()
    results = rag.query("any query at all", top_k=5)
    assert isinstance(results, list)
    assert len(results) <= 5


# ---------------------------------------------------------------------------
# LangGraph agents — Lore Keeper
# ---------------------------------------------------------------------------


def test_lore_keeper_agent_runs_and_validates() -> None:
    from app.agents.lore_keeper import LoreKeeperState, lore_keeper_agent

    final = lore_keeper_agent.invoke(
        LoreKeeperState(query="Describe the Ashen Peaks region and its trade rules").model_dump(),
        config={"recursion_limit": 12},
    )
    assert final.get("draft_lore"), "agent must produce a draft"
    assert isinstance(final.get("canon_check_passed"), bool)
    assert final.get("step", 0) >= 4


def test_lore_document_parser_chunks_paragraphs() -> None:
    from app.agents.lore_keeper import _parse_document

    doc = (
        "Rules of the World\n\n"
        "All spellcasting consumes essence from the caster's well, and every well "
        "slowly refills at the first light of dawn.\n\n"
        "Geography\n\n"
        "The Ashen Peaks form a volcanic barrier between the northern kingdoms and "
        "the southern trade sea, passable only through two fortified passes.\n\n"
        "Factions\n\n"
        "The Iron Covenant controls the steel trade across the mountains and garrisons "
        "the northern pass against smugglers and rival banners alike.\n\n"
    )
    chunks = _parse_document(doc, source_id="world_bible_v1")
    assert len(chunks) == 3
    kinds = [c["kind"] for c in chunks]
    assert kinds == ["rule", "geography", "faction"]
    assert [c["chunk_index"] for c in chunks] == [0, 1, 2]
    assert all(c["source_id"] == "world_bible_v1" for c in chunks)
    assert all(c["tags"] for c in chunks), "chunks should carry extracted keyword tags"


# ---------------------------------------------------------------------------
# LangGraph agents — Strategy Simulator
# ---------------------------------------------------------------------------


def test_strategy_simulator_completes_all_turns() -> None:
    from app.agents.strategy_simulator import (
        SimulationState,
        normalize_factions,
        strategy_simulator_agent,
    )

    factions = normalize_factions(["Iron Covenant", "Verdant Compact", "Free Marches"])
    assert set(factions) == {"iron_covenant", "verdant_compact", "free_marches"}
    assert all("resources" in f for f in factions.values())

    final = strategy_simulator_agent.invoke(
        SimulationState(run_id="t", max_turns=3, factions=factions).model_dump(),
        config={"recursion_limit": 50},
    )
    assert final.get("done") is True
    moves = final.get("moves", [])
    assert len(moves) == 9, "3 factions x 3 turns = 9 moves"
    assert {m["turn"] for m in moves} == {1, 2, 3}
    assert all(
        m["move_type"] in {"declare_war", "propose_trade", "covert_op", "mobilize", "diplomatic_plea"}
        for m in moves
    )
    assert final.get("world_state", {}).get("turn") == 3
    rels = final.get("relations", {})
    assert set(rels) == set(factions)


def test_strategy_moves_change_world_state() -> None:
    from app.agents.strategy_simulator import (
        SimulationState,
        normalize_factions,
        strategy_simulator_agent,
    )

    factions = normalize_factions(["Ashen Dominion", "Northern Empire"])
    baseline = {s: dict(f.get("resources", {})) for s, f in factions.items()}
    final = strategy_simulator_agent.invoke(
        SimulationState(run_id="t2", max_turns=6, factions=factions).model_dump(),
        config={"recursion_limit": 80},
    )
    ws = final.get("world_state", {})
    assert ws.get("turn") == 6
    resources_changed = any(
        factions[s].get("resources", {}).get("gold", 0) != b.get("gold", 0)
        or factions[s].get("resources", {}).get("manpower", 0) != b.get("manpower", 0)
        for s, b in baseline.items()
    )
    assert resources_changed or final.get("events"), "resolutions must affect resources or emit events"


# ---------------------------------------------------------------------------
# LangGraph agents — Economy Balancer
# ---------------------------------------------------------------------------


def test_economy_balancer_flags_all_breaches() -> None:
    from app.agents.economy_balancer import EconomyState, economy_balancer_agent

    final = economy_balancer_agent.invoke(
        EconomyState(
            player_progression_index=1.9, drop_rate_index=1.4, crafting_loop_velocity=0.5
        ).model_dump(),
        config={"recursion_limit": 8},
    )
    recs = {r["aspect"]: r for r in final.get("recommendations", [])}
    assert "progression" in recs and recs["progression"]["direction"] == "decrease"
    assert "drop_rate" in recs and recs["drop_rate"]["direction"] == "decrease"
    assert "crafting_velocity" in recs and recs["crafting_velocity"]["direction"] == "recalibrate"


def test_economy_balancer_happy_path_is_no_change() -> None:
    from app.agents.economy_balancer import EconomyState, economy_balancer_agent

    final = economy_balancer_agent.invoke(
        EconomyState(
            player_progression_index=1.0, drop_rate_index=1.0, crafting_loop_velocity=1.0
        ).model_dump(),
        config={"recursion_limit": 8},
    )
    assert final["recommendations"][0]["direction"] == "no_change"


# ---------------------------------------------------------------------------
# WebSocket streaming hub (pure functions, no server)
# ---------------------------------------------------------------------------


def test_run_agent_to_stream_emits_steps_and_final_state() -> None:
    from app.agents.economy_balancer import EconomyState, economy_balancer_agent
    from app.websocket import run_agent_to_stream

    sink: list = []
    final = run_agent_to_stream(
        "ws-test-run",
        economy_balancer_agent,
        EconomyState(player_progression_index=2.0, drop_rate_index=1.0, crafting_loop_velocity=1.0).model_dump(),
        phase_keys=("recommendations",),
        label="economy",
        sink=sink,
    )
    assert final.get("recommendations"), "final state must contain recommendations"
    actions = [s.action for s in sink]
    assert actions[0] == "init" and actions[-1] == "complete"
    assert "recommendations" in actions
    assert all(s.step > 0 for s in sink)
    assert [s.step for s in sink] == sorted(s.step for s in sink), "steps must be ordered"


def test_replay_buffer_records_broadcasts() -> None:
    from app.models.schemas import AgentStepOut
    from app.websocket import broadcast_step, recent_steps

    broadcast_step(
        "replay-run-test",
        AgentStepOut(agent_id="x", step=1, thought="t", action="probe", done=False),
    )
    steps = recent_steps("replay-run-test")
    assert steps, "broadcast must be recorded in the replay buffer"
    assert steps[-1]["action"] == "probe"


# ---------------------------------------------------------------------------
# Worker tasks (eager mode, no broker)
# ---------------------------------------------------------------------------


def test_worker_tasks_exist_and_are_registered() -> None:
    import app.worker as worker

    for name in ("ingest_document", "run_simulation", "plan_lore", "balance_economy"):
        assert hasattr(worker, name), f"worker missing public task {name}"
        registered = f"axiomforge.{name}"
        assert registered in worker.celery_app.tasks, (
            f"celery registry missing {registered}"
        )


# ---------------------------------------------------------------------------
# Live API handlers (TestClient — exercises lifespan + request handlers)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_health_endpoint(client) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "redis" in body["services"]


def test_lore_plan_endpoint(client) -> None:
    res = client.post(
        "/lore/plan",
        json={
            "query": "Expand the Ashen Peaks region with a hidden faction stronghold",
            "source_text": "The Ashen Peaks watch the trade roads. " * 6,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["draft_lore"]
    assert isinstance(body["canon_check_passed"], bool)


def test_lore_query_endpoint(client) -> None:
    res = client.post("/lore/query", json={"query_text": "iron covenant trade", "top_k": 3})
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_economy_analyze_endpoint(client) -> None:
    res = client.post(
        "/economy/analyze",
        json={
            "player_progression_index": 1.7,
            "drop_rate_index": 1.3,
            "crafting_loop_velocity": 0.4,
            "zone": "emberwood",
        },
    )
    assert res.status_code == 200
    body = res.json()
    aspects = {r["aspect"] for r in body["recommended_adjustments"]}
    assert {"progression", "drop_rate", "crafting_velocity"} <= aspects


def test_economy_notes_endpoint(client) -> None:
    res = client.post(
        "/economy/notes",
        json={
            "source_id": "balance_notes_v2",
            "text": "Drop rates above 1.2x baseline historically softened player retention.",
        },
    )
    assert res.status_code == 200
    assert res.json()["source_id"] == "balance_notes_v2"


def test_simulation_run_degrades_gracefully(client) -> None:
    """POST /simulation/runs must never crash the process: it either persists
    and dispatches (200) or reports the storage outage cleanly (503)."""
    res = client.post(
        "/simulation/runs",
        json={"name": "solo", "turns": 2, "factions": ["Iron Covenant"]},
    )
    assert res.status_code in {200, 503}, res.text
    if res.status_code == 503:
        assert "unavailable" in res.json()["detail"].lower()


def test_root_and_ready(client) -> None:
    assert client.get("/ready").json()["status"] == "ready"
    assert client.get("/").json()["status"] == "ok"


