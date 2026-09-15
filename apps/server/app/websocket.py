# -*- coding: utf-8 -*-
from __future__ import annotations
import asyncio
import json as _json
import logging
from typing import Any, AsyncGenerator
from fastapi import WebSocket, WebSocketDisconnect
from app.models.schemas import AgentStepOut

logger = logging.getLogger(__name__)
_active_streams: dict[str, set[WebSocket]] = {}


def _broadcast(run_id: str, payload: AgentStepOut) -> None:
    sockets = _active_streams.get(run_id)
    if not sockets:
        return
    message = payload.model_dump_json()
    for ws in list(sockets):
        try:
            asyncio.create_task(ws.send_text(message))
        except Exception as e:  # noqa: BLE001
            logger.debug("WebSocket send failed: %s", e)
            sockets.discard(ws)


def subscribe(run_id: str, ws: WebSocket) -> None:
    _active_streams.setdefault(run_id, set()).add(ws)


def unsubscribe(run_id: str, ws: WebSocket) -> None:
    sockets = _active_streams.get(run_id)
    if sockets:
        sockets.discard(ws)
        if not sockets:
            _active_streams.pop(run_id, None)


async def agent_stream_generator(run_id: str, agent_fn: Any, initial_state: dict[str, Any]) -> AsyncGenerator[AgentStepOut, None]:
    step = 0
    yield AgentStepOut(agent_id=run_id, step=step, thought="Agent initialized. Beginning reasoning cycle.", action="init", observation=None, done=False, metadata={"state": initial_state})
    try:
        result = agent_fn.invoke(initial_state)
    except Exception as e:  # noqa: BLE001
        logger.exception("Agent stream failed")
        yield AgentStepOut(agent_id=run_id, step=step + 1, thought="Agent execution encountered an error.", action="error", observation=str(e), done=True, metadata={"error": str(e)})
        return
    step += 1
    if isinstance(result, dict):
        for key in ("plan", "retrieve", "draft", "validate", "decide", "finalize", "analyze"):
            if key in result or key in str(result):
                yield AgentStepOut(agent_id=run_id, step=step, thought=f"Executed phase: {key}", action=key, observation=None, done=False, metadata={k: str(v)[:200] for k, v in result.items() if k != "error"})
                step += 1
    yield AgentStepOut(agent_id=run_id, step=step, thought="Agent finished reasoning cycle.", action="complete", observation=None, done=True, metadata={"result_keys": list(result.keys()) if isinstance(result, dict) else []})
