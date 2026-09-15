# -*- coding: utf-8 -*-
from __future__ import annotations
import datetime as dt
from typing import Any
from pydantic import BaseModel
from app.models.models import ChunkKind, MoveType, SimulationStatus, Scope


class ChunkBase(BaseModel):
    source_id: str
    chunk_index: int
    text: str
    kind: ChunkKind
    scope: Scope
    tags: list[str] = []


class ChunkCreate(ChunkBase):
    pass


class ChunkOut(ChunkBase):
    id: int
    created_at: dt.datetime
    model_config = {"from_attributes": True}


class SimulationConfig(BaseModel):
    name: str = "Sandbox Run"
    turns: int = 20
    factions: list[dict[str, Any]] = []
    extra_rules: list[str] = []


class SimulationRunOut(BaseModel):
    id: int
    name: str
    status: SimulationStatus
    config_json: str | None
    turn_count: int
    started_at: dt.datetime | None
    completed_at: dt.datetime | None
    error: str | None
    model_config = {"from_attributes": True}


class SimulationMoveOut(BaseModel):
    id: int
    run_id: int
    turn: int
    faction_id: str
    actor_type: str
    move_type: MoveType
    payload_json: str | None
    rag_context: str | None
    confidence: str | None
    created_at: dt.datetime
    model_config = {"from_attributes": True}


class SimulationEventOut(BaseModel):
    id: int
    run_id: int
    turn: int
    faction_id: str
    event_type: str
    description: str
    created_at: dt.datetime
    model_config = {"from_attributes": True}


class EconomyMetricSnapshot(BaseModel):
    period: str
    zone: str | None = None
    player_progression_index: float = 0.0
    drop_rate_index: float = 0.0
    crafting_loop_velocity: float = 0.0
    recommended_adjustments: list[dict[str, Any]] = []


class AgentStepOut(BaseModel):
    agent_id: str
    step: int
    thought: str
    action: str
    observation: str | None = None
    done: bool = False
    metadata: dict[str, Any] = {}
