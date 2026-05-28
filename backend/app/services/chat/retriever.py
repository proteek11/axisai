"""
RAG retriever for chat — embeds the user query and searches Qdrant.

Design:
  - Embeds the rephrased (standalone) query from the intent classifier
  - Filters by tenant_id (mandatory) + optional course/content filters
  - If the user's message is a continuation, also re-uses chunk IDs from the
    previous assistant message to bias retrieval toward the same topic
  - Returns a ranked, deduplicated list of RetrievedChunk objects
  - Chunks below MIN_SCORE are dropped (no noise in the prompt)
  - Hard cap of MAX_CHUNKS_RETURNED to control prompt size
"""
from __future__ import annotations

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

from app.config import settings
from app.services.ai.client import AIClient

log = structlog.get_logger(__name__)

# Retrieval config
MIN_SCORE = 0.35           # Chunks below this are noise — drop them (broad/unscoped search)
MIN_SCORE_SCOPED = 0.0     # When scoped to a specific content item, accept all chunks —
                           # the content_item_id filter already guarantees relevance
CONTEXT_ANSWER = 8         # Max chunks for a standard answer
CONTEXT_VISUAL = 10        # More context for visual/compare requests
EMBED_MODEL = "text-embedding-3-small"


class RetrievedChunk:
    """A single chunk retrieved from Qdrant."""

    def __init__(
        self,
        content_item_id: str,
        chunk_index: int,
        text: str,
        score: float,
        title: str | None = None,
        chunk_id: str | None = None,
    ):
        self.content_item_id = content_item_id
        self.chunk_index = chunk_index
        self.text = text
        self.score = score
        self.title = title
        self.chunk_id = chunk_id

    def to_dict(self) -> dict:
        return {
            "content_item_id": self.content_item_id,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "score": round(self.score, 4),
            "title": self.title,
        }

    def __repr__(self) -> str:
        return f"<Chunk item={self.content_item_id[:8]} idx={self.chunk_index} score={self.score:.3f}>"


async def retrieve_chunks(
    query: str,
    tenant_id: str,
    ai_client: AIClient,
    qdrant: AsyncQdrantClient,
    *,
    chat_mode: str = "study",
    moodle_course_id: int | None = None,
    scoped_content_ids: list[str] | None = None,
    prior_chunk_ids: list[str] | None = None,
    intent: str = "GENERAL_QUESTION",
) -> list[RetrievedChunk]:
    """
    Embed query and retrieve relevant chunks from Qdrant.

    Args:
        query:               Rephrased standalone query (from intent classifier)
        tenant_id:           Required for data isolation
        ai_client:           For embedding call (logged to audit_logs)
        qdrant:              Async Qdrant client
        chat_mode:           "study" → axis_content_chunks; "support" → axis_kb_chunks
        moodle_course_id:    Filter to course content only (study mode only)
        scoped_content_ids:  If set, restrict to these specific content items (study mode only)
        prior_chunk_ids:     Qdrant point IDs from the previous turn (continuation bias)
        intent:              Used to determine how many chunks to retrieve

    Returns:
        List of RetrievedChunk, sorted by score descending, min_score filtered
    """
    # 1. Embed the query
    embeddings = await ai_client.embed(
        texts=[query],
        model=EMBED_MODEL,
        task_type="chat_embed",
    )
    if not embeddings:
        log.warning("chat_embed_failed", query=query[:80])
        return []

    query_vector = embeddings[0]

    # 2. Select Qdrant collection based on chat_mode
    #    "study"   → axis_content_chunks (course content, filtered by course/cmid)
    #    "support" → axis_kb_chunks (admin-uploaded KB docs, only filtered by tenant)
    #    "learning"→ axis_content_chunks (future: same as study, personalized ranking)
    if chat_mode == "support":
        collection_name = settings.qdrant_collection_kb_chunks
    else:
        collection_name = settings.qdrant_collection_content_chunks

    # 3. Build Qdrant filter
    must_conditions = [
        FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
    ]

    # Course/content filters only apply to study mode (KB mode is tenant-wide)
    if chat_mode != "support":
        if scoped_content_ids:
            must_conditions.append(
                FieldCondition(
                    key="content_item_id",
                    match=MatchAny(any=scoped_content_ids)
                )
            )
        elif moodle_course_id is not None:
            must_conditions.append(
                FieldCondition(
                    key="moodle_course_id",
                    match=MatchValue(value=moodle_course_id)
                )
            )

    # KB mode: exclude explicitly deactivated items.
    # Use must_not(is_active=False) instead of must(is_active=True) so that
    # chunks ingested before the is_active field was added to the payload
    # still match (they have no is_active field — must(True) would exclude them,
    # but must_not(False) correctly includes them).
    must_not_conditions = []
    if chat_mode == "support":
        must_not_conditions.append(
            FieldCondition(key="is_active", match=MatchValue(value=False))
        )

    qdrant_filter = Filter(
        must=must_conditions,
        must_not=must_not_conditions if must_not_conditions else None,
    )

    # 4. Determine how many results to fetch
    limit = CONTEXT_VISUAL if intent in ("SHOW_VISUAL", "COMPARE") else CONTEXT_ANSWER
    fetch_limit = limit + 4

    # When scoped to a specific content item, drop the score threshold entirely —
    # the content_item_id filter already guarantees the chunks belong to this content.
    # MIN_SCORE only matters for broad/unscoped searches where noise is a real risk.
    effective_threshold = MIN_SCORE_SCOPED if scoped_content_ids else MIN_SCORE

    # Debug log — shows exactly what filter is being applied so we can diagnose empty results
    log.info(
        "rag_filter_debug",
        tenant_id=tenant_id,
        collection=collection_name,
        chat_mode=chat_mode,
        scoped_content_ids=scoped_content_ids,
        moodle_course_id=moodle_course_id,
        score_threshold=effective_threshold,
        fetch_limit=fetch_limit,
    )

    # 5. Search Qdrant (qdrant-client >= 1.7: query_points replaces deprecated search)
    try:
        response = await qdrant.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=qdrant_filter,
            limit=fetch_limit,
            with_payload=True,
            score_threshold=effective_threshold,
        )
        results = response.points
    except Exception as e:
        log.error("qdrant_search_failed", error=str(e), collection=collection_name, mode=chat_mode)
        return []

    log.debug("qdrant_collection_searched", collection=collection_name, mode=chat_mode)

    # 5. Parse results
    chunks: list[RetrievedChunk] = []
    seen_ids = set()

    for hit in results:
        payload = hit.payload or {}
        chunk_id = str(hit.id)

        if chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)

        chunks.append(RetrievedChunk(
            content_item_id=payload.get("content_item_id", ""),
            chunk_index=payload.get("chunk_index", 0),
            text=payload.get("text", ""),
            score=hit.score,
            title=payload.get("title"),
            chunk_id=chunk_id,
        ))

    # 6. If this is a continuation turn, boost prior-topic chunks to the top
    #    by also fetching the prior chunks directly (they may not rank high on
    #    the current query but provide essential continuity context)
    if prior_chunk_ids and len(chunks) < limit:
        prior_not_already = [cid for cid in prior_chunk_ids if cid not in seen_ids]
        if prior_not_already:
            try:
                prior_results = await qdrant.retrieve(
                    collection_name=settings.qdrant_collection_content_chunks,
                    ids=prior_not_already[:3],   # cap at 3 continuity chunks
                    with_payload=True,
                )
                for hit in prior_results:
                    payload = hit.payload or {}
                    chunk_id = str(hit.id)
                    if chunk_id not in seen_ids:
                        seen_ids.add(chunk_id)
                        # Give continuity chunks a synthetic "context" score
                        chunks.append(RetrievedChunk(
                            content_item_id=payload.get("content_item_id", ""),
                            chunk_index=payload.get("chunk_index", 0),
                            text=payload.get("text", ""),
                            score=0.5,   # synthetic — lower than fresh results
                            title=payload.get("title"),
                            chunk_id=chunk_id,
                        ))
            except Exception as e:
                log.warning("prior_chunk_fetch_failed", error=str(e))

    # 7. Sort by score, cap at limit
    chunks.sort(key=lambda c: c.score, reverse=True)
    chunks = chunks[:limit]

    log.info(
        "chat_rag_retrieved",
        query_len=len(query),
        chunks_found=len(chunks),
        top_score=chunks[0].score if chunks else 0,
        intent=intent,
    )

    return chunks


def compute_confidence(chunks: list[RetrievedChunk]) -> float:
    """
    Compute an aggregate confidence score from the retrieved chunks.

    Uses a weighted average of the top-3 chunk scores:
    - Top chunk score carries 50% weight
    - Average of top-3 carries 50% weight
    This rewards both having a highly relevant top result AND broad coverage.
    """
    if not chunks:
        return 0.0

    top = chunks[0].score
    top3_avg = sum(c.score for c in chunks[:3]) / min(len(chunks), 3)

    return round(0.5 * top + 0.5 * top3_avg, 3)
