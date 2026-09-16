# -*- coding: utf-8 -*-
"""Celery task-queue layer with an eager thread fallback.

Long-running agent work (document ingestion, strategy simulations, lore
planning, economy analyses) is dispatched here from the API layer:

* when a Redis broker is reachable the work is queued as a real **Celery**
  task and executed by a worker process
  (``celery -A app.worker worker --loglevel=info``);
* when ``AXIOM_CELERY_TASK_ALWAYS_EAGER`` is set — or the broker is down — the
  work runs *inline* on a daemon thread so zero-dependency local development
  keeps working.

The public callables (``ingest_document``, ``run_simulation``, ``plan_lore``,
``balance_economy``) are safe to pass straight into FastAPI's
``BackgroundTasks`` — they never raise and never block the event loop.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from celery import Celery

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "axiomforge",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=settings.celery_task_time_limit,
    broker_connection_retry_on_startup=False,
    broker_connection_max_retries=1,
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
    result_expires=3600,
    worker_concurrency=settings.celery_worker_concurrency,
)


# ---------------------------------------------------------------------------
# Dispatch plumbing
# ---------------------------------------------------------------------------

def _run_inline(fn: Any, kwargs: dict[str, Any]) -> None:
    """Execute ``fn(**kwargs)`` on a daemon thread, swallowing errors."""

    def _target() -> None:
        try:
            fn(**kwargs)
        except Exception:  # noqa: BLE001
            logger.exception("Inline execution of %s failed", getattr(fn, "__name__", fn))

    threading.Thread(
        target=_target,
        name=f"axiom-eager-{getattr(fn, '__name__', 'task')}",
        daemon=True,
    ).start()


def dispatch(fn: Any, task: Any, **kwargs: Any) -> None:
    """Queue ``task(**kwargs)`` on Celery, or run it inline when unavailable."""
    if settings.celery_always_eager:
        _run_inline(fn, kwargs)
        return
    try:
        task.delay(**kwargs)
    except Exception as e:  # noqa: BLE001
        logger.warning("Celery dispatch for %s failed (%s); running inline", task.name, e)
        _run_inline(fn, kwargs)


# ---------------------------------------------------------------------------
# Document ingestion
# ---------------------------------------------------------------------------

def _ingest_document_impl(*, source_id: str, text: str) -> dict[str, Any]:
    """Parse, chunk and index a design document into all backing stores."""
    from app.agents.lore_keeper import _parse_document
    from app.models.models import ChunkKind, Scope
    from app.services.rag_service import HybridRetrievalService

    chunks = _parse_document(text, source_id)
    rag = HybridRetrievalService()
    indexed: list[dict[str, Any]] = []
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        for chunk in chunks:
            try:
                kind = ChunkKind(chunk.get("kind", "lore"))
            except ValueError:
                kind = ChunkKind.LORE
            try:
                scope = Scope(chunk.get("scope", "world"))
            except ValueError:
                scope = Scope.WORLD
            indexed.append(
                rag.ingest_chunk(
                    source_id=chunk["source_id"],
                    chunk_index=int(chunk["chunk_index"]),
                    text=chunk["text"],
                    kind=kind,
                    scope=scope,
                    tags=chunk.get("tags", []),
                    db=db,
                )
            )
    finally:
        db.close()
    logger.info("Ingested %s chunks for source %s", len(indexed), source_id)
    return {"source_id": source_id, "chunks_indexed": len(indexed)}


@celery_app.task(name="axiomforge.ingest_document")
def _ingest_document_task(source_id: str, text: str) -> dict[str, Any]:
    return _ingest_document_impl(source_id=source_id, text=text)


def ingest_document(*, source_id: str, text: str) -> None:
    """Public entry point — see :func:`dispatch`."""
    dispatch(_ingest_document_impl, _ingest_document_task, source_id=source_id, text=text)


# ---------------------------------------------------------------------------
# Strategy simulation
# ---------------------------------------------------------------------------

_MOVE_COLUMNS = (
    "turn",
    "faction_id",
    "actor_type",
    "move_type",
    "payload_json",
    "rag_context",
    "confidence",
)
_EVENT_COLUMNS = ("turn", "faction_id", "event_type", "description")


def _run_simulation_impl(*, run_id: str, turns: int = 20, factions: Any = None) -> dict[str, Any]:
    """Execute the cyclic strategy LangGraph and persist moves + events."""
    import json as _json

    from sqlalchemy.exc import SQLAlchemyError

    from app.agents.strategy_simulator import (
        SimulationState,
        normalize_factions,
        strategy_simulator_agent,
    )
    from app.database import SessionLocal
    from app.models.models import (
        SimulationEventModel,
        SimulationMoveModel,
        SimulationRunModel,
        SimulationStatus,
    )
    from app.utils import state_to_dict
    from app.websocket import broadcast_run_status

    run_key = str(run_id)
    db = SessionLocal()
    try:
        run = db.query(SimulationRunModel).filter(SimulationRunModel.id == int(run_key)).first()
        if run is None:
            raise ValueError(f"Simulation run {run_key} not found")

        run.status = SimulationStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        db.commit()
        broadcast_run_status(run_key, "running", 0, f"Simulation '{run.name}' started")

        state = SimulationState(
            run_id=run_key,
            max_turns=max(1, min(int(turns), 200)),
            factions=normalize_factions(factions),
        )
        final = state_to_dict(
            strategy_simulator_agent.invoke(
                state.model_dump(),
                config={"recursion_limit": max(50, turns * 10)},
            )
        )

        for m in final.get("moves", []):
            db.add(SimulationMoveModel(run_id=run.id, **{k: m.get(k) for k in _MOVE_COLUMNS}))
        for e in final.get("events", []):
            db.add(SimulationEventModel(run_id=run.id, **{k: e.get(k) for k in _EVENT_COLUMNS}))
        run.turn_count = int(final.get("turn", 0))
        run.status = SimulationStatus.COMPLETED
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

        summary = {
            "turns": run.turn_count,
            "moves": len(final.get("moves", [])),
            "events": len(final.get("events", [])),
        }
        broadcast_run_status(run_key, "completed", run.turn_count, _json.dumps(summary))
        return {"run_id": run_key, "status": "completed", **summary}
    except Exception as e:  # noqa: BLE001
        try:
            db.rollback()
            failed = (
                db.query(SimulationRunModel)
                .filter(SimulationRunModel.id == int(run_key))
                .first()
            )
            if failed is not None:
                failed.status = SimulationStatus.FAILED
                failed.error = str(e)[:2000]
                failed.completed_at = datetime.now(timezone.utc)
                db.commit()
        except SQLAlchemyError:  # pragma: no cover - defensive
            logger.exception("Could not persist FAILED status for run %s", run_key)
        broadcast_run_status(run_key, "failed", 0, str(e)[:500])
        raise
    finally:
        db.close()


@celery_app.task(name="axiomforge.run_simulation")
def _run_simulation_task(run_id: str, turns: int = 20, factions: Any = None) -> dict[str, Any]:
    return _run_simulation_impl(run_id=run_id, turns=turns, factions=factions)


def run_simulation(*, run_id: str, turns: int = 20, factions: Any = None) -> None:
    """Public entry point — see :func:`dispatch`."""
    dispatch(_run_simulation_impl, _run_simulation_task, run_id=run_id, turns=turns, factions=factions)


# ---------------------------------------------------------------------------
# Lore planning
# ---------------------------------------------------------------------------

def _plan_lore_impl(*, query: str, source_text: str = "") -> dict[str, Any]:
    """Run the Autonomous Lore Keeper graph and return its final state."""
    from app.agents.lore_keeper import LoreKeeperState, lore_keeper_agent
    from app.utils import state_to_dict

    state = LoreKeeperState(query=query, source_text=source_text)
    final = state_to_dict(
        lore_keeper_agent.invoke(state.model_dump(), config={"recursion_limit": 12})
    )
    return {
        "query": query,
        "draft_lore": final.get("draft_lore", ""),
        "canon_check_passed": bool(final.get("canon_check_passed", False)),
        "context_count": len(final.get("context", [])),
        "sources": final.get("sources", []),
        "error": final.get("error", ""),
    }


@celery_app.task(name="axiomforge.plan_lore")
def _plan_lore_task(query: str, source_text: str = "") -> dict[str, Any]:
    return _plan_lore_impl(query=query, source_text=source_text)


def plan_lore(*, query: str, source_text: str = "") -> None:
    """Public entry point — see :func:`dispatch`."""
    dispatch(_plan_lore_impl, _plan_lore_task, query=query, source_text=source_text)


# ---------------------------------------------------------------------------
# Economy balancing
# ---------------------------------------------------------------------------

def _balance_economy_impl(*, metrics: dict[str, Any]) -> dict[str, Any]:
    """Run the economy balancer graph over a metrics snapshot."""
    from app.agents.economy_balancer import EconomyState, economy_balancer_agent
    from app.utils import state_to_dict

    payload = {
        key: metrics.get(key, 0.0)
        for key in (
            "period",
            "zone",
            "player_progression_index",
            "drop_rate_index",
            "crafting_loop_velocity",
        )
    }
    state = EconomyState(**payload)
    final = state_to_dict(
        economy_balancer_agent.invoke(state.model_dump(), config={"recursion_limit": 8})
    )
    return {
        "recommendations": final.get("recommendations", []),
        "error": final.get("error", ""),
    }


@celery_app.task(name="axiomforge.balance_economy")
def _balance_economy_task(metrics: dict[str, Any]) -> dict[str, Any]:
    return _balance_economy_impl(metrics=metrics)


def balance_economy(*, metrics: dict[str, Any]) -> None:
    """Public entry point — see :func:`dispatch`."""
    dispatch(_balance_economy_impl, _balance_economy_task, metrics=metrics)


__all__ = [
    "celery_app",
    "dispatch",
    "ingest_document",
    "run_simulation",
    "plan_lore",
    "balance_economy",
]

