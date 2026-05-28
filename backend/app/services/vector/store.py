"""
Qdrant vector store operations.

Design principles:
  - All IDs are deterministic (UUID5) — re-processing is always safe upsert
  - Old chunks are auto-replaced when content_hash changes (same cmid, new hash → new IDs)
  - Payload always includes tenant_id for data isolation in filtered search
  - Delete-then-upsert pattern for content updates (clean slate per content item)
"""
import uuid
from typing import TYPE_CHECKING

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    PointStruct,
    UpdateStatus,
)

from app.config import settings
from app.services.chunkers.base import Chunk
from app.utils.hashing import deterministic_uuid

if TYPE_CHECKING:
    from app.models.content import ContentItem

log = structlog.get_logger(__name__)


class QdrantStore:
    """
    Manages all Qdrant operations for content chunks.

    Each method is scoped to a single content item.
    All upserts use deterministic IDs — safe to call multiple times.
    """

    def __init__(self, client: AsyncQdrantClient):
        self.client = client
        self.collection = settings.qdrant_collection_content_chunks

    async def upsert_chunks(
        self,
        content_item: "ContentItem",
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> int:
        """
        Upsert chunk vectors for a content item.

        Steps:
          1. Delete all existing chunks for this content_item_id (clean slate)
          2. Build PointStruct list with deterministic IDs
          3. Upsert in batches

        Returns:
            Number of points upserted.
        """
        if not chunks or not embeddings:
            return 0

        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) count mismatch"
            )

        # Step 1: Delete old vectors for this content item
        # This handles content updates: old chunks gone, new ones come in
        await self._delete_by_content_item(str(content_item.id))

        # Step 2: Build points with deterministic IDs
        points = []
        for chunk, embedding in zip(chunks, embeddings):
            point_id = deterministic_uuid(
                tenant_id=str(content_item.tenant_id),
                moodle_cmid=content_item.moodle_cmid,
                chunk_index=chunk.chunk_index,
                content_hash=content_item.content_hash or chunk.chunk_hash,
            )

            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    # Filtering fields (indexed in Qdrant)
                    "tenant_id": str(content_item.tenant_id),
                    "moodle_course_id": content_item.moodle_course_id,
                    "moodle_cmid": content_item.moodle_cmid,
                    "content_type": content_item.content_type,
                    "language": content_item.language,
                    # Content fields
                    "content_item_id": str(content_item.id),
                    "chunk_index": chunk.chunk_index,
                    "chunk_hash": chunk.chunk_hash,
                    "text": chunk.text,
                    "title": content_item.title or "",
                    "source_url": content_item.source_url or "",
                    "content_hash": content_item.content_hash or "",
                },
            ))

        # Step 3: Upsert in batches of 100
        total_upserted = 0
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            result = await self.client.upsert(
                collection_name=self.collection,
                points=batch,
                wait=True,
            )
            if result.status == UpdateStatus.COMPLETED:
                total_upserted += len(batch)
            else:
                log.warning("qdrant_upsert_incomplete", batch_start=i, status=result.status)

        log.info(
            "qdrant_upserted",
            collection=self.collection,
            content_item_id=str(content_item.id),
            chunk_count=total_upserted,
        )
        return total_upserted

    async def search(
        self,
        query_vector: list[float],
        tenant_id: str,
        top_k: int = 10,
        course_id: int | None = None,
        cmid: int | None = None,
        content_item_ids: list[str] | None = None,
        language: str | None = None,
        score_threshold: float = 0.5,
    ) -> list[dict]:
        """
        Semantic search over content chunks.
        Always scoped to tenant_id for data isolation.
        Optionally filtered by course, cmid, content_item_ids, or language.
        """
        # Build filter conditions — always include tenant
        must_conditions = [
            FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
        ]

        if course_id is not None:
            must_conditions.append(
                FieldCondition(key="moodle_course_id", match=MatchValue(value=course_id))
            )
        if cmid is not None:
            must_conditions.append(
                FieldCondition(key="moodle_cmid", match=MatchValue(value=cmid))
            )
        if language is not None:
            must_conditions.append(
                FieldCondition(key="language", match=MatchValue(value=language))
            )

        query_filter = Filter(must=must_conditions)

        # qdrant-client >= 1.7: query_points replaces deprecated search()
        response = await self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        results = response.points

        return [
            {
                "score": hit.score,
                "chunk_index": hit.payload.get("chunk_index"),
                "text": hit.payload.get("text"),
                "content_item_id": hit.payload.get("content_item_id"),
                "moodle_cmid": hit.payload.get("moodle_cmid"),
                "moodle_course_id": hit.payload.get("moodle_course_id"),
                "title": hit.payload.get("title"),
                "source_url": hit.payload.get("source_url"),
                "chunk_hash": hit.payload.get("chunk_hash"),
            }
            for hit in results
        ]

    async def delete_by_content_item(self, content_item_id: str) -> int:
        """Public method to delete all chunks for a content item."""
        return await self._delete_by_content_item(content_item_id)

    async def count_by_content_item(self, content_item_id: str) -> int:
        """Count vectors stored for a content item."""
        result = await self.client.count(
            collection_name=self.collection,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="content_item_id",
                        match=MatchValue(value=content_item_id)
                    )
                ]
            ),
        )
        return result.count

    async def _delete_by_content_item(self, content_item_id: str) -> int:
        """Delete all Qdrant points for a content item (before re-upsert)."""
        try:
            result = await self.client.delete(
                collection_name=self.collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="content_item_id",
                            match=MatchValue(value=content_item_id)
                        )
                    ]
                ),
                wait=True,
            )
            log.debug(
                "qdrant_deleted_content_chunks",
                content_item_id=content_item_id,
                status=result.status,
            )
            return 1
        except Exception as e:
            log.warning("qdrant_delete_failed", content_item_id=content_item_id, error=str(e))
            return 0
