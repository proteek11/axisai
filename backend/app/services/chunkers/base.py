"""
Chunker base class and Chunk dataclass.
All chunking strategies produce a list[Chunk].
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.utils.hashing import sha256_text


@dataclass
class Chunk:
    """
    A single chunk of text ready for embedding.

    chunk_hash:   SHA-256 of the chunk text.
                  Used for embedding cache key and Qdrant ID derivation.
    char_start/end: Character offsets in the original raw_text.
                   Useful for highlighting source in UI.
    metadata:     Arbitrary extra data (e.g., page_number from PDF).
    """
    text: str
    chunk_index: int
    chunk_hash: str
    char_start: int = 0
    char_end: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.chunk_hash:
            self.chunk_hash = sha256_text(self.text)

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass
class ChunkingConfig:
    """Configuration for chunking — passed from ContentItem.processing_config."""
    strategy: str = "recursive"        # recursive | semantic | token
    chunk_size: int = 1000             # target chunk size (chars for recursive, tokens for token)
    chunk_overlap: int = 200           # overlap between chunks
    min_chunk_size: int = 100          # discard chunks smaller than this


class BaseChunker(ABC):
    """All chunkers implement this interface."""

    def __init__(self, config: ChunkingConfig):
        self.config = config

    @abstractmethod
    def chunk(self, text: str) -> list[Chunk]:
        """
        Split text into chunks.

        Args:
            text: The full extracted text to chunk.

        Returns:
            Ordered list of Chunk objects.
        """
        ...

    def _to_chunks(self, texts: list[str], start_offsets: list[int] | None = None) -> list[Chunk]:
        """
        Convert a list of text strings into Chunk objects.
        Filters out chunks below min_chunk_size.
        """
        chunks = []
        chunk_index = 0

        for i, text in enumerate(texts):
            text = text.strip()
            if len(text) < self.config.min_chunk_size:
                continue  # Skip near-empty chunks

            char_start = start_offsets[i] if start_offsets else 0
            char_end = char_start + len(text)

            chunks.append(Chunk(
                text=text,
                chunk_index=chunk_index,
                chunk_hash=sha256_text(text),
                char_start=char_start,
                char_end=char_end,
            ))
            chunk_index += 1

        return chunks
