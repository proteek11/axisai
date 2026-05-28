"""
Token-based text splitter.

Use this when you need precise control over context window usage —
e.g., when chunks feed directly into a model with strict token limits.

Uses tiktoken (OpenAI's tokenizer) for token counting.
For non-OpenAI models, cl100k_base encoding is a reasonable approximation.
"""
from langchain_text_splitters import TokenTextSplitter

from .base import BaseChunker, Chunk, ChunkingConfig


class TokenChunker(BaseChunker):
    """
    Splits text by token count using tiktoken.

    chunk_size here is in tokens (e.g., 512 tokens).
    Good for: precise context window management, API cost estimation.
    """

    def __init__(self, config: ChunkingConfig):
        super().__init__(config)
        self._splitter = TokenTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            encoding_name="cl100k_base",  # GPT-4/3.5 encoding, good general default
        )

    def chunk(self, text: str) -> list[Chunk]:
        if not text or not text.strip():
            return []
        texts = self._splitter.split_text(text)
        return self._to_chunks(texts)
