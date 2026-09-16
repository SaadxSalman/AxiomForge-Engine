# -*- coding: utf-8 -*-
"""Real-time agent step streaming hub.

Producers (FastAPI background threads, Celery workers in *other* processes)
push :class:`~app.models.schemas.AgentStepOut` steps here and every WebSocket
subscribed to ``/ws/{run_id}`` receives them live.  The hub provides:

* a **dedicated asyncio loop on a daemon thread** — producers run in worker
  threads or foreign processes and must never touch the request event loop
  directly;
* a **Redis pub/sub fan-out** on ``axiom:ws:steps`` so steps produced by a
  separate Celery process reach the sockets held by the API process
  (per-process origin tags prevent double delivery);
* a **replay ring-buffer** per run, so a browser connecting mid-run catches up
  instantly instead of staring at an empty graph.
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
import threading
import time as _time
import uuid
from collections import deque
from typing import Any

from fastapi import WebSocket

from app.config import settings
from app.models.schemas import AgentStepOut

logger = logging.getLogger(__name__)

WS_STEP_CHANNEL = "axiom:ws:steps"
_REPLAY_LIMIT = 300
# Circuit breaker for the optional Redis fan-out: when Redis is unreachable we
# must NEVER let a broadcast block the agent loop — publishing is best-effort.
_REDIS_RETRY_SECS = 60.0
_redis_unavailable_until: float = 0.0

_origin = uuid.uuid4().hex
_streams: dict[str, set[WebSocket]] = {}
_replay: dict[str, deque[dict[str, Any]]] = {}
_lock = threading.Lock()

_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_listener_task: Any = None
_redis: Any = None


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """Start (once) the private event loop used for all socket writes."""
    global _loop, _loop_thread
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_loop.run_forever, name="axiom-ws-loop", daemon=True)
        _loop_thread.start()
    return _loop


async def _deliver_local(run_id: str, message: str) -> None:
    with _lock:
        sockets = list(_streams.get(run_id, ()))
    for ws in sockets:
        try:
            await ws.send_text(message)
        except Exception:  # noqa: BLE001
            unsubscribe(run_id, ws)


def subscribe(run_id: str, ws: WebSocket) -> None:
    with _lock:
        _streams.setdefault(str(run_id), set()).add(ws)


def unsubscribe(run_id: str, ws: WebSocket) -> None:
    with _lock:
        sockets = _streams.get(str(run_id))
        if not sockets:
            return
        sockets.discard(ws)
        if not sockets:
            _streams.pop(str(run_id), None)


def recent_steps(run_id: str) -> list[dict[str, Any]]:
    with _lock:
        return list(_replay.get(str(run_id), ()))


async def send_replay(ws: WebSocket, run_id: str) -> None:
    """Push the buffered history of a run to a freshly subscribed socket."""
    for step in recent_steps(run_id):
        try:
            await ws.send_text(_json.dumps(step))
        except Exception:  # noqa: BLE001
            return


def _record(run_id: str, payload: dict[str, Any]) -> None:
    with _lock:
        buf = _replay.setdefault(str(run_id), deque(maxlen=_REPLAY_LIMIT))
        buf.append(payload)


def _publish_redis(payload: dict[str, Any]) -> None:
    global _redis, _redis_unavailable_until
    if _time.time() < _redis_unavailable_until:
        return  # breaker open — skip silently, local sockets still receive
    try:
        import redis as redis_lib

        if _redis is None:
            client_kwargs: dict[str, Any] = {
                "socket_connect_timeout": 1,
                "socket_timeout": 1,
                "decode_responses": True,
                "retry_on_timeout": False,
                "health_check_interval": 0,
            }
            try:
                # One attempt only: no exponential-backoff retries stalling
                # the simulation loop when Redis is down.
                client_kwargs["retry"] = redis_lib.retry.Retry(
                    redis_lib.backoff.NoBackoff(), 1
                )
            except Exception:  # noqa: BLE001 - older redis-py layouts
                pass
            _redis = redis_lib.Redis.from_url(settings.redis_url, **client_kwargs)
        _redis.publish(WS_STEP_CHANNEL, _json.dumps({"origin": _origin, **payload}))
    except Exception as e:  # noqa: BLE001
        _redis_unavailable_until = _time.time() + _REDIS_RETRY_SECS
        try:
            if _redis is not None:
                _redis.close()
        except Exception:  # noqa: BLE001
            pass
        _redis = None
        logger.debug("Redis fan-out unavailable (%s); local sockets only for %ss", e, _REDIS_RETRY_SECS)

def broadcast_step(run_id: str, step: AgentStepOut | dict[str, Any]) -> None:
    """Push an agent step to every subscriber.

    Safe to call from *any* thread (request threads, Celery worker threads);
    never raises — a broken socket or missing Redis can never take down the
    simulation loop that produced the step.
    """
    run_id = str(run_id)
    try:
        payload = step.model_dump() if isinstance(step, AgentStepOut) else dict(step)
        message = _json.dumps(payload)
        _record(run_id, payload)
        loop = _ensure_loop()
        asyncio.run_coroutine_threadsafe(_deliver_local(run_id, message), loop)
        _publish_redis({"run_id": run_id, "step": payload})
    except Exception as e:  # noqa: BLE001
        logger.debug("broadcast_step failed: %s", e)


def broadcast_run_status(
    run_id: str, status: str, turn: int = 0, detail: str = ""
) -> None:
    """Emit a terminal ``status`` step (``running`` / ``completed`` / ``failed``)."""
    broadcast_step(
        run_id,
        AgentStepOut(
            agent_id=str(run_id),
            step=-1,
            thought=f"Run status: {status}",
            action="status",
            observation=detail or None,
            done=status in {"completed", "failed"},
            metadata={"status": status, "turn": turn},
        ),
    )


async def _redis_listener() -> None:
    """Cross-process fan-out: forward steps published by Celery workers."""
    global _redis
    import redis.asyncio as aioredis

    _redis = aioredis.Redis.from_url(
        settings.redis_url, socket_connect_timeout=1, decode_responses=True
    )
    pubsub = _redis.pubsub()
    await pubsub.subscribe(WS_STEP_CHANNEL)
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if not msg or msg.get("type") != "message":
                continue
            try:
                data = _json.loads(msg["data"])
            except Exception:  # noqa: BLE001
                continue
            if data.get("origin") == _origin:
                continue  # already delivered locally by this process
            run_id = str(data.get("run_id", ""))
            payload = data.get("step") or {}
            _record(run_id, payload)
            await _deliver_local(run_id, _json.dumps(payload))
    except asyncio.CancelledError:  # pragma: no cover - shutdown path
        pass
    finally:
        try:
            await pubsub.unsubscribe(WS_STEP_CHANNEL)
            await pubsub.close()
        except Exception:  # noqa: BLE001
            pass


def start_redis_listener(loop: asyncio.AbstractEventLoop) -> None:
    """Launch the cross-process fan-out listener on the *server* event loop."""
    global _listener_task
    try:
        _listener_task = loop.create_task(_redis_listener())
        logger.info("WebSocket Redis fan-out listener started")
    except Exception as e:  # noqa: BLE001
        logger.debug("Redis listener not started: %s", e)


def stop_redis_listener() -> None:
    global _listener_task, _redis
    if _listener_task is not None:
        _listener_task.cancel()
        _listener_task = None
    try:
        if _redis is not None:
            _redis.close()
    except Exception:  # noqa: BLE001
        pass
    _redis = None


def _emit(
    run_id: str,
    counter: dict[str, int],
    thought: str,
    action: str,
    observation: str | None = None,
    metadata: dict[str, Any] | None = None,
    sink: list[AgentStepOut] | None = None,
) -> None:
    counter["n"] += 1
    step = AgentStepOut(
        agent_id=str(run_id),
        step=counter["n"],
        thought=thought,
        action=action,
        observation=observation,
        done=False,
        metadata=metadata or {},
    )
    if sink is not None:
        sink.append(step)
    broadcast_step(run_id, step)


def run_agent_to_stream(
    run_id: str,
    agent_fn: Any,
    initial_state: dict[str, Any],
    phase_keys: tuple[str, ...] = (),
    label: str = "agent",
    sink: list[AgentStepOut] | None = None,
) -> dict[str, Any]:
    """Invoke a compiled LangGraph, broadcasting a ReAct-style step per phase.

    Steps are published through :func:`broadcast_step`, so the invoking WS
    client (and any other subscriber to the run) sees the full reasoning trace.
    When ``sink`` is provided, every emitted :class:`AgentStepOut` is appended
    there as well (used by :func:`agent_stream_generator`).
    Returns the final state as a plain dict.
    """
    from app.utils import state_to_dict

    counter = {"n": 0}
    run_id = str(run_id)
    _emit(
        run_id,
        counter,
        thought=f"{label} initialized — beginning reasoning cycle.",
        action="init",
        metadata={"phases": list(phase_keys)},
        sink=sink,
    )
    try:
        # Bounded cycles: the conditional decide↔resolve loop needs a
        # recursion budget proportional to the horizon (2 supersteps/turn).
        max_turns = int(initial_state.get("max_turns", 20) or 20) if isinstance(initial_state, dict) else 20
        result = agent_fn.invoke(
            dict(initial_state),
            config={"recursion_limit": max(50, max_turns * 10)},
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Agent stream for %s failed", run_id)
        _emit(
            run_id,
            counter,
            thought="Agent execution encountered an error.",
            action="error",
            observation=str(e),
            sink=sink,
        )
        broadcast_run_status(run_id, "failed", detail=str(e))
        return {"error": str(e)}
    final = state_to_dict(result)
    for key in phase_keys:
        if key in final:
            value = final.get(key)
            preview = _json.dumps(value, default=str)[:400] if value is not None else ""
            _emit(
                run_id,
                counter,
                thought=f"Executed phase: {key}",
                action=key,
                observation=preview or None,
                sink=sink,
            )
    _emit(run_id, counter, thought=f"{label} finished reasoning cycle.", action="complete", sink=sink)
    return final


async def agent_stream_generator(
    run_id: str,
    agent_fn: Any,
    initial_state: dict[str, Any],
    phase_keys: tuple[str, ...] = (),
    label: str = "agent",
):
    """Async generator yielding every :class:`AgentStepOut` an agent emits.

    Runs the (synchronous) LangGraph invocation on a worker thread via
    :func:`run_agent_to_stream` while a sink captures the emitted steps; the
    generator polls the sink and yields steps in order, terminating with a
    final ``done=True`` step.  This keeps the WebSocket handler fully
    non-blocking without requiring the agents themselves to be async.
    """
    import asyncio as _asyncio

    sink: list[AgentStepOut] = []
    yield_idx = 0
    task = _asyncio.to_thread(
        run_agent_to_stream,
        str(run_id),
        agent_fn,
        dict(initial_state),
        tuple(phase_keys),
        label,
        sink,
    )
    while True:
        while yield_idx < len(sink):
            yield sink[yield_idx]
            yield_idx += 1
        if task.done():
            break
        await _asyncio.sleep(0.02)
    while yield_idx < len(sink):  # drain remaining steps
        yield sink[yield_idx]
        yield_idx += 1
    await task  # propagate exceptions / fetch result
    yield AgentStepOut(
        agent_id=str(run_id),
        step=(sink[-1].step + 1) if sink else 1,
        thought=f"{label} stream closed.",
        action="close",
        done=True,
        metadata={},
    )
