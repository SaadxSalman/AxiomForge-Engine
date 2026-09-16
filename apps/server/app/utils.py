# -*- coding: utf-8 -*-
"""Small shared helpers used across agents, workers and API layers."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def state_to_dict(result: Any) -> dict[str, Any]:
    """Normalise a LangGraph ``invoke()`` result to a plain dict.

    Depending on how the state schema is declared a compiled LangGraph may
    return either a ``dict`` or a Pydantic model instance; callers should never
    have to care.
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, BaseModel):
        return result.model_dump()
    try:
        return dict(result)
    except Exception:  # noqa: BLE001
        return {}