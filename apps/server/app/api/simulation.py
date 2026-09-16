# -*- coding: utf-8 -*-
"""Dynamic-strategy simulation endpoints (turn-based faction sandbox)."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.models import SimulationEventModel, SimulationMoveModel, SimulationRunModel, SimulationStatus
from app.models.schemas import SimulationConfig, SimulationEventOut, SimulationMoveOut, SimulationRunOut
from app.worker import run_simulation as run_simulation_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.post("/runs", response_model=SimulationRunOut, summary="Create a new simulation run")
def create_run(
        cfg: SimulationConfig,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
) -> SimulationRunOut:
    """Create a simulation run and enqueue the autonomous-strategy Celery task."""
    run = SimulationRunModel(
        name=cfg.name,
        status=SimulationStatus.PENDING,
        config_json=cfg.model_dump_json(),
        turn_count=0,
    )
    try:
        db.add(run)
        db.commit()
        db.refresh(run)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable — cannot persist simulation run: {e}",
        ) from e
    background_tasks.add_task(run_simulation_task, run_id=str(run.id), turns=cfg.turns, factions=cfg.factions)
    return SimulationRunOut.model_validate(run)


@router.get("/runs/{run_id}", response_model=SimulationRunOut, summary="Get simulation run status")
def get_run(run_id: int, db: Session = Depends(get_session)) -> SimulationRunOut:
    try:
        run = db.query(SimulationRunModel).filter(SimulationRunModel.id == run_id).first()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}") from e
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return SimulationRunOut.model_validate(run)


@router.get("/runs/{run_id}/moves", response_model=list[SimulationMoveOut], summary="List moves for a run")
def list_moves(run_id: int, db: Session = Depends(get_session)) -> list[SimulationMoveOut]:
    try:
        moves = (
            db.query(SimulationMoveModel)
            .filter(SimulationMoveModel.run_id == run_id)
            .order_by(SimulationMoveModel.turn)
            .all()
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}") from e
    return [SimulationMoveOut.model_validate(m) for m in moves]


@router.get("/runs/{run_id}/events", response_model=list[SimulationEventOut], summary="List events for a run")
def list_events(run_id: int, db: Session = Depends(get_session)) -> list[SimulationEventOut]:
    try:
        events = (
            db.query(SimulationEventModel)
            .filter(SimulationEventModel.run_id == run_id)
            .order_by(SimulationEventModel.turn)
            .all()
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}") from e
    return [SimulationEventOut.model_validate(e) for e in events]


@router.post("/runs/{run_id}/start", response_model=dict[str, Any], summary="Start a pending simulation")
def start_run(
        run_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    run = db.query(SimulationRunModel).filter(SimulationRunModel.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    cfg = json.loads(run.config_json or "{}")
    factions = cfg.get("factions", [])
    background_tasks.add_task(
        run_simulation_task,
        run_id=str(run.id),
        turns=cfg.get("turns", 20),
        factions=factions,
    )
    return {"run_id": run_id, "status": "started"}
