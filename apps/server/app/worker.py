# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from typing import Any
from celery import Celery
from celery.signals import worker_process_init
from app.config import settings

logger = logging.getLogger(__name__)
celery_app = Celery("axiom")
celery_app.config_from_object({"broker_url": settings.redis_url, "result_backend": settings.redis_url, "task_always_eager": settings.celery_always_eager, "task_time_limit": settings.celery_task_time_limit, "worker_concurrency": settings.celery_worker_concurrency, "task_serializer": "json", "result_serializer": "json", "accept_content": ["json"], "enable_utc": True})
if settings.celery_flower_enabled:
    celery_app.autodiscover_tasks(lambda: ["app.worker"])


@worker_process_init.connect
def _configure_logging(*args: Any, **kwargs: Any) -> None:  # noqa: ANN401, ARG001
    logging.basicConfig(level=settings.log_level.upper())


@celery_app.task(bind=True, name="app.worker.ingest_document", max_retries=3)
def ingest_document(self, source_id: str, text: str) -> dict[str, Any]:
    try:
        from app.agents.lore_keeper import _parse_document
        from app.models.models import ChunkKind, Scope
        from app.models.schemas import ChunkCreate
        from app.services.rag_service import HybridRetrievalService
        from app.database import SessionLocal
        chunks = _parse_document(text, source_id)
        rag = HybridRetrievalService()
        db = SessionLocal()
        results: list[dict[str, Any]] = []
        try:
            for chunk in chunks:
                kind_str = chunk.get("kind", "lore")
                try:
                    kind = ChunkKind(kind_str)
                except ValueError:
                    kind = ChunkKind.LORE
                scope_str = chunk.get("scope", "world")
                try:
                    scope = Scope(scope_str)
                except ValueError:
                    scope = Scope.WORLD
                create = ChunkCreate(source_id=chunk["source_id"], chunk_index=chunk["chunk_index"], text=chunk["text"], kind=kind, scope=scope, tags=chunk.get("tags", []))
                res = rag.ingest_chunk(source_id=create.source_id, chunk_index=create.chunk_index, text=create.text, kind=kind, scope=scope, tags=create.tags, db=db)
                results.append(res)
        finally:
            db.close()
        return {"source_id": source_id, "chunks_indexed": len(results), "results": results}
    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest_document failed")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.worker.run_simulation", max_retries=1)
def run_simulation(self, run_id: str, turns: int, factions: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        from app.agents.strategy_simulator import SimulationState, strategy_simulator_agent, _default_factions
        from app.database import SessionLocal
        from app.models.models import SimulationRunModel, SimulationMoveModel, SimulationEventModel, SimulationStatus
        import datetime as dt
        state = SimulationState(run_id=run_id, max_turns=turns, factions=factions or _default_factions())
        final = strategy_simulator_agent.invoke(state.model_dump())
        db = SessionLocal()
        try:
            run = db.query(SimulationRunModel).filter(SimulationRunModel.id == int(run_id)).first()
            if run is None:
                run = SimulationRunModel(id=int(run_id), name=f"Sim {run_id}", status=SimulationStatus.RUNNING)
                db.add(run)
            run.status = SimulationStatus.COMPLETED
            run.turn_count = final.turn
            run.completed_at = dt.datetime.utcnow()
            db.flush()
            for move in final.moves:
                db.add(SimulationMoveModel(run_id=run.id, **move))
            for event in final.events:
                db.add(SimulationEventModel(run_id=run.id, **event))
            db.commit()
        finally:
            db.close()
        return {"run_id": run_id, "turn": final.turn, "moves": final.moves, "events": final.events}
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_simulation failed")
        raise self.retry(exc=exc, countdown=2)


@celery_app.task(bind=True, name="app.worker.plan_lore", max_retries=1)
def plan_lore(self, query: str, source_text: str = "") -> dict[str, Any]:
    try:
        from app.agents.lore_keeper import LoreKeeperState, lore_keeper_agent
        state = LoreKeeperState(query=query, source_text=source_text)
        final = lore_keeper_agent.invoke(state.model_dump())
        return {"query": query, "draft_lore": final.get("draft_lore", ""), "canon_check_passed": final.get("canon_check_passed", False), "context_count": len(final.get("context", [])), "error": final.get("error", "")}
    except Exception as exc:  # noqa: BLE001
        logger.exception("plan_lore failed")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.worker.balance_economy", max_retries=1)
def balance_economy(self, metrics: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.agents.economy_balancer import EconomyState, economy_balancer_agent
        state = EconomyState(**metrics)
        final = economy_balancer_agent.invoke(state.model_dump())
        return {"period": state.period, "zone": state.zone, "player_progression_index": state.player_progression_index, "drop_rate_index": state.drop_rate_index, "crafting_loop_velocity": state.crafting_loop_velocity, "recommendations": final.get("recommendations", []), "error": final.get("error", "")}
    except Exception as exc:  # noqa: BLE001
        logger.exception("balance_economy failed")
        raise self.retry(exc=exc)
