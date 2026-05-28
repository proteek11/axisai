"""
Qdrant async client — singleton with collection initialization.
All four collections are created on startup if they don't exist.
"""
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PayloadSchemaType,
)

from app.config import settings

# ── Singleton ─────────────────────────────────────────────────────────────────
_qdrant_client: AsyncQdrantClient | None = None


def get_qdrant() -> AsyncQdrantClient:
    """Return the singleton Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key,
            https=settings.qdrant_https,
            grpc_port=settings.qdrant_grpc_port,
            prefer_grpc=settings.qdrant_use_grpc,
        )
    return _qdrant_client


async def close_qdrant() -> None:
    """Close the Qdrant connection."""
    global _qdrant_client
    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None


# ── Collection definitions ─────────────────────────────────────────────────────
COLLECTIONS = {
    settings.qdrant_collection_content_chunks: {
        "description": "Course content chunks — RAG over Moodle modules",
        "indexed_fields": [
            ("tenant_id", PayloadSchemaType.KEYWORD),
            ("content_item_id", PayloadSchemaType.KEYWORD),  # Required for scoped_content_ids RAG filter
            ("moodle_course_id", PayloadSchemaType.INTEGER),
            ("moodle_cmid", PayloadSchemaType.INTEGER),
            ("content_type", PayloadSchemaType.KEYWORD),
            ("language", PayloadSchemaType.KEYWORD),
        ],
    },
    settings.qdrant_collection_kb_chunks: {
        "description": "Knowledge base chunks — RAG over support/admin KB",
        "indexed_fields": [
            ("tenant_id", PayloadSchemaType.KEYWORD),
            ("kb_type", PayloadSchemaType.KEYWORD),
            ("language", PayloadSchemaType.KEYWORD),
        ],
    },
    settings.qdrant_collection_content_intelligence: {
        "description": "Content intelligence — semantic search over module metadata",
        "indexed_fields": [
            ("tenant_id", PayloadSchemaType.KEYWORD),
            ("moodle_course_id", PayloadSchemaType.INTEGER),
            ("moodle_cmid", PayloadSchemaType.INTEGER),
            ("difficulty_label", PayloadSchemaType.KEYWORD),
            ("blooms", PayloadSchemaType.KEYWORD),
        ],
    },
    settings.qdrant_collection_question_intelligence: {
        "description": "Question intelligence — similarity search + deduplication",
        "indexed_fields": [
            ("tenant_id", PayloadSchemaType.KEYWORD),
            ("moodle_course_id", PayloadSchemaType.INTEGER),
            ("moodle_cmid", PayloadSchemaType.INTEGER),
            ("question_type", PayloadSchemaType.KEYWORD),
            ("blooms", PayloadSchemaType.KEYWORD),
            ("difficulty_label", PayloadSchemaType.KEYWORD),
        ],
    },
}


async def initialize_collections() -> None:
    """
    Create all Qdrant collections if they don't exist, and ensure all
    required payload indexes exist on already-existing collections.
    Called on application startup. Idempotent.
    """
    client = get_qdrant()
    response = await client.get_collections()
    existing = {c.name for c in response.collections}

    for collection_name, config in COLLECTIONS.items():
        if collection_name not in existing:
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=settings.qdrant_vector_size,
                    distance=Distance.COSINE,
                ),
            )

        # Ensure all payload indexes exist — idempotent for both new and existing collections.
        # This also adds any indexes that were added to COLLECTIONS after initial deployment.
        for field_name, field_type in config["indexed_fields"]:
            try:
                await client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_type,
                )
            except Exception:
                # Index already exists — Qdrant raises if you try to create a duplicate.
                pass


async def health_check() -> dict:
    """Check Qdrant connectivity and return collection stats."""
    client = get_qdrant()
    collections = await client.get_collections()
    return {
        "status": "ok",
        "collections": [
            {"name": c.name} for c in collections.collections
        ],
    }
