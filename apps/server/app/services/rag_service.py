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
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.database import WEAVIATE_LORE_CLASS, get_neo4j_driver, get_weaviate_client
from app.models.models import ChunkKind, Scope

logger = logging.getLogger(__name__)


def _embed(text: str) -> list[float]:
    """Return a dense embedding for ``text``.

    Uses OpenAI embeddings when an API key is configured; otherwise returns a
    deterministic, normalized pseudo-vector so retrieval still works offline.
    """
    try:
        if settings.llm_api_key and not str(settings.llm_api_key).startswith("change-me"):
            from llama_index.embeddings.openai import OpenAIEmbedding

            emb = OpenAIEmbedding(model=settings.embedding_model, api_key=settings.llm_api_key)
            return emb.get_text_embedding(text)
    except Exception as e:  # noqa: BLE001
        logger.debug("Embedding via llama_index failed (%s); using deterministic fallback vector", e)

    h = abs(hash(text)) % (10**8)
    base = [float((h >> (i * 8)) & 0xFF) / 255.0 for i in range(settings.embedding_dim)]
    norm = sum(v * v for v in base) ** 0.5 or 1.0
    return [v / norm for v in base]


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
            logger.debug("pgvector query failed (%s)", e)

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
            logger.debug("Neo4j graph enrichment skipped (%s)", e)

        return merged

