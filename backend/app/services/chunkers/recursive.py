"""
Recursive Character Text Splitter — the default chunking strategy.

Why this is the default:
- Tries to split on natural boundaries in order: paragraphs → sentences → words → chars
- Preserves semantic coherence better than fixed-size character splitting
- Works well across all content types (PDF text, HTML, transcripts)
- Industry standard for RAG pipelines

The `langchain-text-splitters` package provides a well-tested implementation
we use directly rather than reinventing it.
"""
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .base import BaseChunker, Chunk, ChunkingConfig


class RecursiveChunker(BaseChunker):
    """
    Splits text recursively by paragraph → sentence → word → character.

    chunk_size is in characters (not tokens) — fast, no tokenizer overhead.
    For token-accurate splitting, use TokenChunker instead.
    """

    # Split priority order — tries each separator in order, falls back to next
    SEPARATORS = [
        "\n\n",   # Paragraph break (strongest boundary)
        "\n",     # Line break
        ". ",     # Sentence end
        "! ",     # Sentence end
        "? ",     # Sentence end
        "; ",     # Clause boundary
        ", ",     # Phrase boundary
        " ",      # Word boundary
        "",       # Character (last resort)
    ]

    def __init__(self, config: ChunkingConfig):
        super().__init__(config)
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=self.SEPARATORS,
            length_function=len,
            is_separator_regex=False,
            keep_separator=True,  # Keep separators for readability
        )

    def chunk(self, text: str) -> list[Chunk]:
        """Split text into overlapping chunks using recursive separator strategy."""
        if not text or not text.strip():
            return []

        # Get split texts with character positions
        texts = self._splitter.split_text(text)

        # Compute approximate start positions for each chunk
        # (not exact due to separator handling, but close enough for UI highlighting)
        start_offsets = self._estimate_offsets(text, texts)

        return self._to_chunks(texts, start_offsets)

    def _estimate_offsets(self, original: str, chunks: list[str]) -> list[int]:
        """
        Estimate character start offset of each chunk in the original text.
        Uses string search — fast enough for documents up to several MB.
        """
        offsets = []
        search_from = 0

        for chunk_text in chunks:
            # Search for chunk start in original, starting where last chunk ended
            search_text = chunk_text[:50].strip()  # Use first 50 chars as search key
            pos = original.find(search_text, max(0, search_from - self.config.chunk_overlap))
            offsets.append(max(0, pos))
            if pos >= 0:
                search_from = pos + len(chunk_text)

        return offsets
