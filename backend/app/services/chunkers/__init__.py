"""
Chunker factory — returns the right chunker for a given strategy name.
"""
from .base import BaseChunker, Chunk, ChunkingConfig
from .recursive import RecursiveChunker
from .token import TokenChunker
from .chapter import ChapterChunker

__all__ = ["BaseChunker", "Chunk", "ChunkingConfig", "get_chunker"]


def get_chunker(config: ChunkingConfig) -> BaseChunker:
    """
    Factory: return the appropriate chunker for the requested strategy.

    Args:
        config: ChunkingConfig with strategy, chunk_size, chunk_overlap

    Returns:
        A BaseChunker instance ready to call .chunk(text)

    Raises:
        ValueError: if strategy is unknown
    """
    strategy = config.strategy.lower()

    if strategy == "recursive":
        return RecursiveChunker(config)
    elif strategy == "token":
        return TokenChunker(config)
    elif strategy == "chapter":
        return ChapterChunker(config)
    elif strategy == "semantic":
        # Phase 3+: semantic chunking (requires embedding model)
        # Fall back to recursive for now
        return RecursiveChunker(config)
    else:
        raise ValueError(
            f"Unknown chunking strategy: '{strategy}'. "
            f"Valid options: recursive, token, chapter, semantic"
        )
