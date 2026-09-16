# -*- coding: utf-8 -*-
"""Autonomous Lore Keeper agent — canon-grounded lore expansion.

The agent is a LangGraph state machine with a *cyclic validation loop*:

    plan → retrieve → draft → validate ─┬─ (retry) → draft
                                        └─ (pass/final) → END

1. **plan**      — classify the expansion request into canonical ``kind`` /
                   ``scope`` filters so retrieval is precise.
2. **retrieve**  — hybrid RAG: dense vectors (Weaviate → pgvector fallback)
                   plus Neo4j graph context.  If a raw ``source_text`` was
                   supplied it is parsed and indexed *first* so the newest
                   canon is always retrievable in the same call.
3. **draft**     — an LLM (OpenAI-compatible via llama-index) writes the lore
                   grounded in the retrieved chunks.  With no API key a
                   deterministic synthesiser produces a useful structured
                   draft from the retrieved context, so the pipeline is fully
                   functional offline.
4. **validate**  — a canon-consistency gate: the draft must be substantive and
                   lexically anchored in retrieved canon.  A failing draft is
                   regenerated once (the loop), then reported honestly.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from app.models.models import ChunkKind, Scope
from app.services.rag_service import HybridRetrievalService

logger = logging.getLogger(__name__)

# Heading keywords → canonical chunk kind (used by the document parser).
_KIND_HEADERS: list[tuple[tuple[str, ...], str]] = [
    (("rule", "mechanic", "system", "stat"), "rule"),
    (("geograph", "map", "region", "continent", "terrain", "climate"), "geography"),
    (("faction", "kingdom", "guild", "nation", "empire", "covenant", "order"), "faction"),
    (("econom", "currenc", "trade", "market", "coin"), "economy"),
]

_MAX_CHUNKS_PER_DOC = 96
_CHUNK_TARGET_CHARS = 700


class LoreKeeperState(BaseModel):
    """State threaded through the lore-keeper graph."""

    query: str = ""
    source_text: str = ""
    chunks: list[dict[str, Any]] = []
    context: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    draft_lore: str = ""
    canon_check_passed: bool = False
    retries: int = 0
    error: str = ""
    step: int = 0


# ---------------------------------------------------------------------------
# Document parsing / chunking (shared with the Celery ingest task)
# ---------------------------------------------------------------------------

def _classify_kind(paragraph: str, current: str) -> str:
    lowered = paragraph.lower()
    for needles, kind in _KIND_HEADERS:
        if any(n in lowered for n in needles):
            return kind
    return current


def _split_long_paragraph(text: str) -> list[str]:
    """Split a paragraph longer than ``_CHUNK_TARGET_CHARS`` on sentences."""
    if len(text) <= _CHUNK_TARGET_CHARS * 1.4:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    parts: list[str] = []
    buf = ""
    for s in sentences:
        if buf and len(buf) + len(s) > _CHUNK_TARGET_CHARS:
            parts.append(buf.strip())
            buf = s
        else:
            buf = f"{buf} {s}".strip()
    if buf.strip():
        parts.append(buf.strip())
    return parts


def _parse_document(text: str, source_id: str) -> list[dict[str, Any]]:
    """Parse a raw design document into canonical, typed lore chunks."""
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[dict[str, Any]] = []
    current_kind = "lore"
    idx = 0
    for para in parts:
        if idx >= _MAX_CHUNKS_PER_DOC:
            logger.warning("Document %s truncated at %s chunks", source_id, _MAX_CHUNKS_PER_DOC)
            break
        # Only short paragraphs act as section headers; long body paragraphs
        # inherit the currently active section so that a geography body which
        # happens to mention "kingdoms" is not re-classified as a faction.
        if len(para) <= 60:
            current_kind = _classify_kind(para, current_kind)
            continue  # headings / one-liners are not indexed
        for piece in _split_long_paragraph(para):
            if len(piece) < 60:
                continue  # skip headings / one-liners
            tags = sorted({w for w in re.findall(r"[a-zA-Z]{5,}", piece.lower())})[:6]
            chunks.append(
                {
                    "source_id": source_id,
                    "chunk_index": idx,
                    "text": piece,
                    "kind": current_kind,
                    "scope": "world",
                    "tags": tags,
                }
            )
            idx += 1
    return chunks


# ---------------------------------------------------------------------------
# Graph nodes — plan → retrieve → draft → validate (cyclic)
# ---------------------------------------------------------------------------

_QUERY_HINTS: tuple[tuple[tuple[str, ...], str, str | None], ...] = (
    (("rule", "mechanic", "system", "stat"), "rule", None),
    (("geograph", "map", "region", "continent", "terrain"), "geography", "region"),
    (("faction", "kingdom", "guild", "nation", "empire", "covenant"), "faction", "faction"),
    (("econom", "trade", "currenc", "market", "coin"), "economy", "system"),
)


def _classify_query(query: str) -> tuple[ChunkKind | None, Scope | None]:
    """Map a writer's expansion request onto canonical kind/scope filters."""
    lowered = query.lower()
    for needles, kind, scope in _QUERY_HINTS:
        if any(n in lowered for n in needles):
            return ChunkKind(kind), (Scope(scope) if scope else None)
    return None, None


def lore_plan_step(state: LoreKeeperState) -> LoreKeeperState:
    """Node 1 — classify the request and reset transient error state."""
    state.step = 1
    state.error = ""
    return state


def lore_retrieve_step(state: LoreKeeperState) -> LoreKeeperState:
    """Node 2 — index any supplied source text, then hybrid-RAG recall."""
    state.step = 2
    try:
        rag = HybridRetrievalService()
        if state.source_text.strip():
            for chunk in _parse_document(state.source_text, source_id="inline_source"):
                rag.ingest_chunk(
                    source_id=chunk["source_id"],
                    chunk_index=int(chunk["chunk_index"]),
                    text=chunk["text"],
                    kind=ChunkKind(chunk["kind"]),
                    scope=Scope(chunk["scope"]),
                    tags=chunk.get("tags", []),
                )
        kind, scope = _classify_query(state.query)
        state.context = rag.query(state.query or "world canon overview", kind=kind, scope=scope, top_k=8)
        state.sources = [
            {
                "source_id": c.get("source_id"),
                "chunk_index": c.get("chunk_index"),
                "kind": c.get("kind"),
            }
            for c in state.context[:8]
        ]
    except Exception as e:  # noqa: BLE001
        logger.exception("Lore retrieval failed")
        state.error = str(e)
    return state


_STOPWORDS = {
    "about", "above", "after", "again", "their", "there", "these", "those",
    "which", "while", "would", "could", "should", "where", "world", "canon",
    "every", "other", "because", "through", "between",
}


def _terms(text: str, min_len: int = 5) -> list[str]:
    """Significant lower-cased words used for lexical canon anchoring."""
    words = re.findall(r"[a-zA-Z]{%d,}" % min_len, (text or "").lower())
    return [w for w in words if w not in _STOPWORDS]


def _llm_available() -> bool:
    return bool(settings.llm_api_key) and not str(settings.llm_api_key).startswith("change-me")


def _deterministic_draft(state: LoreKeeperState) -> str:
    """Offline synthesiser — a structured draft woven from retrieved canon."""
    ctx = state.context[:3]
    canon_terms = sorted({t for c in ctx for t in _terms(c.get("text", ""))})[:8]
    anchors = ", ".join(canon_terms) or "the established canon"
    query_terms = sorted(set(_terms(state.query, 4)))[:6]
    focus = ", ".join(query_terms) or "the requested expansion"
    bullets = "\n".join(
        f"{i}. Anchor — {(c.get('text', '') or '').strip().replace(chr(10), ' ')[:220]}"
        for i, c in enumerate(ctx, 1)
    )
    return (
        f"Lore expansion (canon-grounded): {state.query.strip() or 'Untitled expansion'}\n\n"
        f"Focus: {focus}.\n\n"
        f"Grounded in retrieved canon:\n{bullets}\n\n"
        f"Continuity notes: this expansion deliberately reuses the established anchors "
        f"({anchors}) so it slots into existing canon without contradictions. Treat the "
        f"retrieved passages above as binding constraints on names, borders and factions."
    )


def _llm_draft(state: LoreKeeperState, context_blob: str) -> str | None:
    """LLM drafting via an OpenAI-compatible endpoint (llama-index)."""
    try:
        if not _llm_available():
            return None
        from llama_index.core.llms import ChatMessage
        from llama_index.llms.openai import OpenAI

        llm = OpenAI(
            model=getattr(settings, "llm_model", "gpt-4o-mini") or "gpt-4o-mini",
            api_key=settings.llm_api_key,
            temperature=0.4,
        )
        prompt = (
            "You are the Autonomous Lore Keeper for a game studio. Draft a lore "
            "expansion that is *strictly consistent* with the canon context below.\n\n"
            f"Canon context:\n{context_blob}\n\n"
            f"Writer request: {state.query}\n\n"
            "Output only the lore text."
        )
        resp = llm.chat([ChatMessage(role="user", content=prompt)])
        content = (resp.message.content or "").strip()
        return content or None
    except Exception as e:  # noqa: BLE001
        logger.debug("LLM draft unavailable (%s); using deterministic synthesiser", e)
        return None


def lore_draft_step(state: LoreKeeperState) -> LoreKeeperState:
    """Node 3 — generate the expansion grounded in the retrieved context."""
    state.step = 3
    context_blob = "\n".join(f"- {c.get('text', '')[:300]}" for c in state.context[:6])
    state.draft_lore = _llm_draft(state, context_blob) or _deterministic_draft(state)
    return state


def lore_validate_step(state: LoreKeeperState) -> LoreKeeperState:
    """Node 4 — canon-consistency gate (substance + lexical anchoring)."""
    state.step = 4
    draft = state.draft_lore.strip()
    if len(draft) < 200:
        state.canon_check_passed = False
        state.retries += 1
        return state
    canon_terms = {t for c in state.context for t in _terms(c.get("text", ""))}
    if not canon_terms:
        # Nothing retrieved to contradict — accept the draft.
        state.canon_check_passed = True
        return state
    draft_words = set(_terms(draft, 4))
    ratio = len(canon_terms & draft_words) / min(len(canon_terms), 24)
    state.canon_check_passed = ratio >= 0.2
    if not state.canon_check_passed:
        state.retries += 1
        logger.info("Canon gate failed (anchor ratio %.2f); retry scheduled", ratio)
    return state


def _route_after_validate(state: LoreKeeperState) -> str:
    """Cyclic loop: one retry of the draft when the canon gate fails."""
    if not state.canon_check_passed and state.retries <= 1 and not state.error:
        return "draft"
    return END


def build_lore_keeper_graph() -> Any:
    workflow = StateGraph(LoreKeeperState)
    workflow.add_node("plan", lore_plan_step)
    workflow.add_node("retrieve", lore_retrieve_step)
    workflow.add_node("draft", lore_draft_step)
    workflow.add_node("validate", lore_validate_step)
    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "retrieve")
    workflow.add_edge("retrieve", "draft")
    workflow.add_edge("draft", "validate")
    workflow.add_conditional_edges(
        "validate", _route_after_validate, {"draft": "draft", END: END}
    )
    return workflow.compile()


lore_keeper_agent = build_lore_keeper_graph()
