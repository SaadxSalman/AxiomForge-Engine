# -*- coding: utf-8 -*-
from __future__ import annotations
import json as _json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocketDisconnect
from app.config import settings
from app.api import economy_router, health_router, lore_router, simulation_router
from app.database import init_vector_schema
from app.websocket import agent_stream_generator, subscribe, unsubscribe
from app.models.schemas import AgentStepOut
from app.agents.lore_keeper import LoreKeeperState, lore_keeper_agent
from app.agents.strategy_simulator import SimulationState, strategy_simulator_agent
from app.agents.economy_balancer import EconomyState, economy_balancer_agent

logging.basicConfig(level=settings.log_level.upper())
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("Starting AxiomForge-Engine")
    try:
        init_vector_schema()
    except Exception as e:  # noqa: BLE001
        log.warning("Vector schema init skipped/failed: %s", e)
    yield
    log.info("Shutting down AxiomForge-Engine")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan, docs_url="/docs", openapi_url="/openapi.json")

try:
    origins = _json.loads(settings.cors_origins)
except Exception:  # noqa: BLE001
    origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(health_router)
app.include_router(lore_router)
app.include_router(simulation_router)
app.include_router(economy_router)


@app.websocket("/ws/{run_id}")
async def agent_websocket(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    subscribe(run_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = _json.loads(data)
            except Exception:  # noqa: BLE001
                continue
            action = msg.get("action")
            if action == "start_lore":
                state = LoreKeeperState(query=msg.get("query", ""), source_text=msg.get("source_text", ""))
                async for step in agent_stream_generator(run_id, lore_keeper_agent, state.model_dump()):
                    await websocket.send_text(step.model_dump_json())
            elif action == "start_simulation":
                state = SimulationState(run_id=run_id, max_turns=int(msg.get("turns", 20)), factions=msg.get("factions", {}))
                async for step in agent_stream_generator(run_id, strategy_simulator_agent, state.model_dump()):
                    await websocket.send_text(step.model_dump_json())
            elif action == "start_economy":
                state = EconomyState(**msg.get("metrics", {}))
                async for step in agent_stream_generator(run_id, economy_balancer_agent, state.model_dump()):
                    await websocket.send_text(step.model_dump_json())
            elif action == "ping":
                await websocket.send_text(_json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        unsubscribe(run_id, websocket)
    except Exception as e:  # noqa: BLE001
        log.exception("WebSocket error for %s", run_id)
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
        unsubscribe(run_id, websocket)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "version": "0.1.0", "status": "ok"}
