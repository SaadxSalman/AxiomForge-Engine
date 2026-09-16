# -*- coding: utf-8 -*-
"""Hybrid retrieval service — the RAG backbone of AxiomForge-Engine.

Performs dense-vector retrieval with a graceful fallback chain:

1. **Weaviate** (managed vector store) — used when available.
2. **pgvector** (PostgreSQL ``Vector`` column) — local fallback.
3. **Neo4j** property-graph context enrichment — attaches relationship
   context to the retrieved chunks.

If no LLM API key is configured, embeddings are produced by a deterministic
fallback so the pipeline never hard-fails during local development.
"""
from __future__ import annotations

import json
import logging
import time as _time
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.database import WEAVIATE_LORE_CLASS, get_neo4j_driver, get_weaviate_client
from app.models.models import ChunkKind, Scope

logger = logging.getLogger(__name__)

# Circuit-breaker windows (seconds) for the *optional* retrieval backends.
# When Postgres/Neo4j are unreachable we skip them entirely for this long
# instead of paying a TCP connect timeout on every single query.
_PG_RETRY_SECS = 60.0
_NEO4J_RETRY_SECS = 60.0
_pg_unavailable_until: float = 0.0
_neo4j_unavailable_until: float = 0.0


def _hash_embed(text: str, dim: int | None = None) -> list[float]:
    """Deterministic feature-hashing embedding — no network, stable forever.

    Every token is hashed (blake2b) into ``dim`` buckets with a random sign, so
    two texts that share vocabulary land close together in cosine space.  This
    gives genuinely useful nearest-neighbour search completely offline and is
    100% reproducible across processes and restarts (unlike ``hash()`` which is
    salted per interpreter session).
    """
    import hashlib
    import math
    import re as _re

    dim = dim or settings.embedding_dim
    buckets = [0.0] * dim
    tokens = [t for t in _re.split(r"[^a-z0-9]+", text.lower()) if t]
    if not tokens:
        tokens = ["<empty>"]
    for tok in tokens:
        d = hashlib.blake2b(tok.encode("utf-8"), digest_size=16).digest()
        sign = 1.0 if (d[8] & 1) else -1.0
        # Two independent buckets per token for a better hash spread.
        idx = int.from_bytes(d[:8], "big") % dim
        buckets[idx] += sign * 1.0
        idx2 = int.from_bytes(d[8:], "big") % dim
        buckets[idx2] += sign * 0.5
    norm = math.sqrt(sum(v * v for v in buckets)) or 1.0
    return [v / norm for v in buckets]


def _embed(text: str) -> list[float]:
    """Return a dense embedding for ``text``.

    Uses OpenAI embeddings (via llama-index) when a real API key is configured;
    otherwise returns the deterministic :func:`_hash_embed` fallback so the
    hybrid retriever never hard-fails during local / offline development.
    """
    try:
        if settings.llm_api_key and not str(settings.llm_api_key).startswith("change-me"):
            from llama_index.embeddings.openai import OpenAIEmbedding

            emb = OpenAIEmbedding(
                model=settings.embedding_model,
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url if settings.llm_base_url != "https://api.openai.com/v1" else None,
            )
            return emb.get_text_embedding(text)
    except Exception as e:  # noqa: BLE001
        logger.debug("Embedding via llama_index failed (%s); using deterministic fallback vector", e)

    return _hash_embed(text)


class HybridRetrievalService:
    """Coordinates Weaviate + pgvector + Neo4j retrieval."""

    def __init__(self) -> None:
        self.weaviate = get_weaviate_client()

    def _get_collection(self) -> Any:
        """Return the Weaviate ``AxiomLoreChunk`` collection, or ``None``."""
        if self.weaviate is None:
            return None
        try:
            return self.weaviate.collections.get(WEAVIATE_LORE_CLASS)
        except Exception as e:  # noqa: BLE001
            logger.debug("Weaviate collection fetch failed (%s)", e)
            return None

    def ingest_chunk(
        self,
        source_id: str,
        chunk_index: int,
        text: str,
        kind: ChunkKind,
        scope: Scope,
        tags: list[str] | None = None,
        db: Session | None = None,
    ) -> dict[str, Any]:
        # Defensive coercion — some callers pass ``None`` for kind/scope.
        kind = kind or ChunkKind.LORE
        scope = scope or Scope.WORLD
        tags = tags or []

        vec = _embed(text)
        obj = {
            "source_id": source_id,
            "chunkIndex": chunk_index,
            "text": text,
            "kind": kind.value,
            "scope": scope.value,
            "tags": tags,
        }
        try:
            coll = self._get_collection()
            if coll is not None:
                coll.data.insert(properties=obj, vector=vec)
        except Exception as e:  # noqa: BLE001
            logger.warning("Weaviate ingest failed (%s); will rely on pgvector fallback", e)

        row_id: int = -1
        if db is not None:
            try:
                from app.models.models import LoreChunkModel

                # Idempotent (re-)ingest: drop any previous row sharing the same
                # (source_id, chunk_index) natural key before inserting, so that
                # re-indexing a document never produces duplicate chunks.
                db.query(LoreChunkModel).filter(
                    LoreChunkModel.source_id == source_id,
                    LoreChunkModel.chunk_index == chunk_index,
                ).delete(synchronize_session=False)

                row = LoreChunkModel(
                    source_id=source_id,
                    chunk_index=chunk_index,
                    text=text,
                    kind=kind,
                    scope=scope,
                    tags=json.dumps(tags),
                    embedding=vec,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                row_id = row.id
            except Exception as e:  # noqa: BLE001
                logger.warning("pgvector ingest failed (%s)", e)
                db.rollback()

        try:
            self._index_graph_context(source_id, text, kind, scope, tags)
        except Exception as e:  # noqa: BLE001
            logger.debug("Graph context indexing skipped (%s)", e)

        return {"id": row_id, "source_id": source_id, "chunk_index": chunk_index, "kind": kind.value}

    def _index_graph_context(self, source_id: str, text: str, kind: ChunkKind, scope: Scope, tags: list[str]) -> None:
        """Index a lightweight :Document → :Chunk graph in Neo4j."""
        driver = get_neo4j_driver()
        with driver.session(database=settings.neo4j_db) as session:
            session.run(
                """
                MERGE (doc:Document {id: $source_id})
                SET doc.kind = $kind, doc.scope = $scope, doc.updated_at = datetime()
                MERGE (chunk:Chunk {id: $chunk_id})
                SET chunk.text = $text, chunk.kind = $kind, chunk.scope = $scope, chunk.updated_at = datetime()
                MERGE (doc)-[:CONTAINS]->(chunk)
                """,
                source_id=source_id,
                chunk_id=f"{source_id}#{kind.value}",
                text=text[:1000],
                kind=kind.value,
                scope=scope.value,
            )

    def query(
        self,
        query_text: str,
        kind: ChunkKind | None = None,
        scope: Scope | None = None,
        top_k: int = 8,
        db: Session | None = None,
    ) -> list[dict[str, Any]]:
        global _pg_unavailable_until, _neo4j_unavailable_until
        vec = _embed(query_text)

        # --- 1. Weaviate (dense vector + optional property filters, v4 API) ---
        weaviate_results: list[dict[str, Any]] = []
        try:
            coll = self._get_collection()
            if coll is not None:
                from weaviate.classes.query import Filter

                filters: Any = None
                if kind:
                    filters = Filter.by_property("kind").equals(kind.value)
                if scope:
                    scope_filter = Filter.by_property("scope").equals(scope.value)
                    filters = scope_filter if filters is None else filters & scope_filter
                res = coll.query.near_vector(
                    near_vector=vec,
                    limit=top_k,
                    filters=filters,
                    return_properties=["source_id", "chunkIndex", "text", "kind", "scope", "tags"],
                )
                for obj in res.objects or []:
                    p = obj.properties
                    weaviate_results.append(
                        {
                            "source_id": p.get("source_id"),
                            "chunk_index": p.get("chunkIndex"),
                            "text": p.get("text"),
                            "kind": p.get("kind"),
                            "scope": p.get("scope"),
                            "tags": p.get("tags", []),
                            "source": "weaviate",
                        }
                    )
        except Exception as e:  # noqa: BLE001
            logger.debug("Weaviate query failed (%s); relying on pgvector", e)

        # --- 2. pgvector (local PostgreSQL fallback) ---
        pg_results: list[dict[str, Any]] = []
        if _time.time() >= _pg_unavailable_until:
            try:
                from app.models.models import LoreChunkModel

                if db is None:
                    from app.database import SessionLocal

                    db = SessionLocal()
                stmt = db.query(LoreChunkModel)
                if kind is not None:
                    stmt = stmt.filter(LoreChunkModel.kind == kind)
                if scope is not None:
                    stmt = stmt.filter(LoreChunkModel.scope == scope)
                rows = stmt.order_by(LoreChunkModel.embedding.l2_distance(vec)).limit(top_k).all()
                for row in rows:
                    pg_results.append(
                        {
                            "source_id": row.source_id,
                            "chunk_index": row.chunk_index,
                            "text": row.text,
                            "kind": row.kind.value,
                            "scope": row.scope.value,
                            "tags": json.loads(row.tags) if row.tags else [],
                            "source": "pgvector",
                        }
                    )
            except Exception as e:  # noqa: BLE001
                _pg_unavailable_until = _time.time() + _PG_RETRY_SECS
                logger.debug("pgvector query failed (%s); backing off %ss", e, _PG_RETRY_SECS)

        # --- 3. Merge, de-duplicate, enforce top_k ---
        seen: set[tuple[str, int]] = set()
        merged: list[dict[str, Any]] = []
        for r in weaviate_results + pg_results:
            key = (r.get("source_id"), r.get("chunk_index"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
            if len(merged) >= top_k:
                break

        # --- 4. Neo4j graph-context enrichment (best-effort) ---
        if merged and _time.time() >= _neo4j_unavailable_until:
            try:
                driver = get_neo4j_driver()
                with driver.session(database=settings.neo4j_db) as session:
                    for r in merged[:5]:
                        rels = session.run(
                            """
                            MATCH (chunk:Chunk)-[:CONTAINS]-(doc:Document)
                            WHERE doc.id = $source_id
                            OPTIONAL MATCH (doc)-[:RELATED_TO]->(related)
                            RETURN related
                            """,
                            source_id=r.get("source_id"),
                        )
                        related = [record["related"] for record in rels if record["related"]]
                        r["graph_context"] = [dict(r_.items()) for r_ in related]
            except Exception as e:  # noqa: BLE001
                _neo4j_unavailable_until = _time.time() + _NEO4J_RETRY_SECS
                logger.debug("Neo4j graph enrichment skipped (%s); backing off %ss", e, _NEO4J_RETRY_SECS)

        return merged

