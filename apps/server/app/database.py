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
        # Short acquisition/connection timeouts keep graph enrichment best-effort:
        # an unreachable Neo4j must never stall a retrieval request for ~30s.
        _neo4j_driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=2.0,
            connection_acquisition_timeout=2.0,
            max_connection_pool_size=5,
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
_weaviate_checked = False  # one-time probe sentinel: don't re-pay a failed connect


def get_weaviate_client() -> Any:
    """Return a lazily-constructed Weaviate v4 client.

    Weaviate is an *optional* secondary vector store.  When it is unreachable
    or misconfigured this returns ``None`` so the hybrid retriever can fall
    back to pgvector without crashing the import or request cycle.  The probe
    runs **once per process**: the ``_weaviate_checked`` sentinel distinguishes
    "never probed" from "probed and unavailable", so an offline environment
    pays the (short) connect timeout a single time instead of per request.
    """
    global _weaviate_client, _weaviate_checked
    if not _weaviate_checked:
        _weaviate_checked = True
        try:
            auth_config: Any = None
            if settings.weaviate_api_key and not str(settings.weaviate_api_key).startswith("change-me"):
                # weaviate-client v4 uses ``AuthApiKey`` (``ApiKey`` was removed).
                auth_config = weaviate.auth.AuthApiKey(api_key=settings.weaviate_api_key)
            params = weaviate.connect.base.ConnectionParams.from_url(
                settings.weaviate_url,
                grpc_port=50051,
                grpc_secure=settings.weaviate_url.startswith("https"),
            )
            # Short timeouts so an unreachable Weaviate fails in ~2s instead of
            # stalling every retrieval call for the default ~30s.
            client_kwargs: dict[str, Any] = {
                "connection_params": params,
                "auth_client_secret": auth_config,
                "skip_init_checks": True,
            }
            try:
                client_kwargs["additional_config"] = weaviate.config.AdditionalConfig(
                    timeout=weaviate.config.Timeout(init=2, query=2, insert=2)
                )
            except Exception:  # noqa: BLE001 - older client versions
                pass
            client = weaviate.WeaviateClient(**client_kwargs)
            # Eagerly probe readiness: a failed connect is cached as ``None``
            # so we never pay the connect cost again this process lifetime.
            client.connect()
            if client.is_ready():
                _weaviate_client = client
            else:
                client.close()
                _weaviate_client = None
                logger.warning("Weaviate not ready at %s; retrieval will use pgvector fallback", settings.weaviate_url)
        except Exception as e:  # noqa: BLE001
            logger.warning("Weaviate client init failed (%s); retrieval will use pgvector fallback", e)
            try:
                if "client" in locals() and client is not None:
                    client.close()  # avoid leaking the half-open socket
            except Exception:  # noqa: BLE001
                pass
            _weaviate_client = None  # type: ignore[assignment]
    return _weaviate_client


# Name of the Weaviate collection that mirrors the ``lore_chunks`` table.
WEAVIATE_LORE_CLASS = "AxiomLoreChunk"


def init_vector_schema() -> None:
    """Create the ``AxiomLoreChunk`` collection in Weaviate (v4 API) if absent.

    Best-effort: every failure is logged and swallowed so application startup
    never blocks on Weaviate.  When Weaviate is unavailable, pgvector remains
    the always-available dense-vector store.
    """
    client = get_weaviate_client()
    if client is None:
        return
    try:
        existing = {c.name for c in client.collections.list_all()}
        if WEAVIATE_LORE_CLASS in existing:
            return
        from weaviate.classes.config import Configure, DataType, Property

        client.collections.create(
            name=WEAVIATE_LORE_CLASS,
            description="Game lore and design-document chunks",
            properties=[
                Property(name="source_id", data_type=DataType.TEXT),
                Property(name="chunkIndex", data_type=DataType.NUMBER),
                Property(name="text", data_type=DataType.TEXT),
                Property(name="kind", data_type=DataType.TEXT),
                Property(name="scope", data_type=DataType.TEXT),
                Property(name="tags", data_type=DataType.TEXT),
            ],
            # Manual vectors (we supply our own embeddings via ``vector=``).
            vectorizer_config=Configure.Vectorizers.none(),
            vector_index_config=Configure.VectorIndex.hnsw(),
        )
        logger.info("Created Weaviate collection %s", WEAVIATE_LORE_CLASS)
    except Exception as e:  # noqa: BLE001
        logger.warning("Weaviate schema init failed (%s); continuing with pgvector fallback", e)
