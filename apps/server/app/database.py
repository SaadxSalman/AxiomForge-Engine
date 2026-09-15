# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from typing import Any
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool
import weaviate
from neo4j import GraphDatabase
from pgvector.sqlalchemy import Vector
from app.config import settings

logger = logging.getLogger(__name__)
Base = declarative_base()


def _pgvector_register(engine: Any) -> None:
    @event.listens_for(engine, "connect")
    def _enable(dbapi_connection: Any, _conn_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        finally:
            cursor.close()


def create_sqlalchemy_engine(sync: bool = True, echo: bool = False) -> Any:
    url = settings.pg_sync_url if sync else settings.pg_url
    opts: Any = {"pool_pre_ping": True}
    if sync:
        opts["poolclass"] = NullPool
    engine = create_engine(url, echo=echo, **opts)
    _pgvector_register(engine)
    return engine

sync_engine = create_sqlalchemy_engine(sync=True, echo=settings.debug)
SessionLocal = sessionmaker(bind=sync_engine, class_=Session, expire_on_commit=False)


def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


_neo4j_driver: Any | None = None


def get_neo4j_driver() -> Any:
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
    return _neo4j_driver


def neo4j_session() -> Any:
    driver = get_neo4j_driver()
    session = driver.session(database=settings.neo4j_db)
    try:
        yield session
    finally:
        session.close()


_weaviate_client: Any | None = None


def get_weaviate_client() -> Any:
    """Return a (lazily constructed) Weaviate client.

    Robust against Weaviate being unavailable: returns ``None`` instead of
    raising so that the rest of the system can gracefully fall back to
    pgvector-only retrieval.
    """
    global _weaviate_client
    if _weaviate_client is None:
        try:
            auth_config: Any = None
            if settings.weaviate_api_key and not str(settings.weaviate_api_key).startswith("change-me"):
                # weaviate-client v4 uses ``AuthApiKey``; ``ApiKey`` was removed.
                auth_config = weaviate.auth.AuthApiKey(api_key=settings.weaviate_api_key)
            _weaviate_client = weaviate.Client(
                settings.weaviate_url,
                auth_client_secret=auth_config,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Weaviate client init failed (%s); retrieval will use pgvector fallback", e)
            _weaviate_client = None  # type: ignore[assignment]
    return _weaviate_client


def init_vector_schema() -> None:
    client = get_weaviate_client()
    class_config = {
        "class": "AxiomLoreChunk",
        "description": "Game lore and design-document chunks",
        "vectorIndexConfig": {"skip": False, "maxConnections": 64, "ef": 128},
        "properties": [
            {"name": "source_id", "dataType": ["string"]},
            {"name": "chunkIndex", "dataType": ["int"]},
            {"name": "text", "dataType": ["text"]},
            {"name": "kind", "dataType": ["string"]},
            {"name": "scope", "dataType": ["string"]},
            {"name": "tags", "dataType": ["string[]"]},
        ],
    }
    try:
        client.schema.contains(class_config)
    except Exception as e:  # noqa: BLE001
        logger.warning("Weaviate schema check failed: %s", e)
        try:
            client.schema.create_class(class_config)
        except Exception as create_err:  # noqa: BLE001
            logger.warning("Weaviate schema create failed: %s", create_err)
