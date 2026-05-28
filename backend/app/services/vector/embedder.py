"""
Embedding service — generates vectors for chunks before Qdrant upsert.

Caching strategy:
  - Key: sha256 of chunk text (chunk_hash already computed in Chunk)
  - Store: Redis with 7-day TTL
  - On cache hit: return cached vector, no AI call made
  - On cache miss: call AI client, cache result

Batching:
  - LiteLLM's aembedding() accepts a list of strings
  - We batch in groups of MAX_BATCH_SIZE to avoid hitting API limits
  - Cache hits are filtered out before sending to API

This means re-processing the same content (e.g., after prompt version upgrade)
costs zero embedding tokens as long as the text hasn't changed.
"""
import json
from typing import TYPE_CHECKING

import structlog

from app.config import settings
from app.services.chunkers.base import Chunk

if TYPE_CHECKING:
    from app.services.ai.client import AIClient

log = structlog.get_logger(__name__)

# Max texts per embedding API call (provider limit varies; 2048 is safe for OpenAI)
MAX_BATCH_SIZE = 100


class Embedder:
    """
    Generates and caches embeddings for text chunks.

    Args:
        ai_client:  AIClient instance (handles API call + audit logging)
        redis:      Redis client for embedding cache
        model:      Embedding model to use (default from settings)
    """

    def __init__(self, ai_client: "AIClient", redis=None, model: str | None = None):
        self.ai_client = ai_client
        self.redis = redis
        self.model = model or settings.default_embedding_model

    async def embed_chunks(self, chunks: list[Chunk]) -> list[list[float]]:
        """
        Generate embeddings for a list of chunks.
        Uses Redis cache to avoid re-embedding identical text.

        Returns:
            List of embedding vectors, same order as input chunks.
        """
        if not chunks:
            return []

        # ── Check cache for each chunk ────────────────────────────────────
        embeddings: list[list[float] | None] = [None] * len(chunks)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        if self.redis:
            for i, chunk in enumerate(chunks):
                cached = await self._get_cache(chunk.chunk_hash)
                if cached is not None:
                    embeddings[i] = cached
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(chunk.text)
        else:
            # No Redis — embed everything
            uncached_indices = list(range(len(chunks)))
            uncached_texts = [c.text for c in chunks]

        cache_hits = len(chunks) - len(uncached_indices)
        if cache_hits > 0:
            log.info("embedding_cache_hits", hits=cache_hits, total=len(chunks))

        # ── Embed uncached chunks in batches ──────────────────────────────
        if uncached_texts:
            new_embeddings = await self._embed_in_batches(uncached_texts)

            # Fill results and update cache
            for i, (chunk_idx, embedding) in enumerate(
                zip(uncached_indices, new_embeddings)
            ):
                embeddings[chunk_idx] = embedding
                if self.redis:
                    await self._set_cache(chunks[chunk_idx].chunk_hash, embedding)

        # ── Safety check ──────────────────────────────────────────────────
        missing = [i for i, e in enumerate(embeddings) if e is None]
        if missing:
            log.error("embedding_missing", missing_indices=missing)
            raise RuntimeError(f"Failed to embed {len(missing)} chunks")

        return embeddings  # type: ignore[return-value]

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string (for queries, search, etc.)."""
        results = await self._embed_in_batches([text])
        return results[0]

    async def _embed_in_batches(self, texts: list[str]) -> list[list[float]]:
        """Split texts into batches and embed each batch."""
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), MAX_BATCH_SIZE):
            batch = texts[i : i + MAX_BATCH_SIZE]
            log.debug(
                "embedding_batch",
                batch_num=i // MAX_BATCH_SIZE + 1,
                batch_size=len(batch),
                model=self.model,
            )
            batch_embeddings = await self.ai_client.embed(
                texts=batch,
                model=self.model,
                task_type="embed",
            )
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def _get_cache(self, chunk_hash: str) -> list[float] | None:
        """Retrieve cached embedding from Redis."""
        try:
            data = await self.redis.get(f"embed:{chunk_hash}")
            if data:
                return json.loads(data)
        except Exception as e:
            log.warning("embedding_cache_read_error", error=str(e))
        return None

    async def _set_cache(self, chunk_hash: str, embedding: list[float]) -> None:
        """Cache an embedding in Redis for 7 days."""
        try:
            from app.core.redis import EMBEDDING_CACHE_TTL
            await self.redis.setex(
                f"embed:{chunk_hash}",
                EMBEDDING_CACHE_TTL,
                json.dumps(embedding),
            )
        except Exception as e:
            log.warning("embedding_cache_write_error", error=str(e))
