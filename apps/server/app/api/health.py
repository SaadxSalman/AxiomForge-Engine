# -*- coding: utf-8 -*-
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from app.config import settings

router = APIRouter(tags=["system"])


class HealthOut(BaseModel):
    status: str
    app: str
    env: str
    version: str = "0.1.0"
    services: dict[str, str] = {}


@router.get("/health", response_model=HealthOut, summary="Health check")
def health() -> HealthOut:
    return HealthOut(status="ok", app=settings.app_name, env=settings.env, services={"postgresql": "configured", "neo4j": "configured", "weaviate": "configured", "redis": "configured"})


@router.get("/ready", summary="Readiness check")
def ready() -> dict[str, str]:
    return {"status": "ready"}
