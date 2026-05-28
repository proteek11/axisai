"""
Chapter-based PDF chunker — PF-08.

Detects chapter/section headings in extracted PDF text and splits the text
at those boundaries instead of using a fixed character count.  Each chapter
becomes at least one chunk; if a chapter is longer than `chunk_size` it is
further split with the RecursiveChunker so no chunk ever exceeds the limit.

Heading detection heuristics (in priority order):
  1. "Chapter N …" / "Section N …" lines
  2. Numbered headings: "1.", "1.1", "1.1.1" (up to 3 levels)
  3. ALL-CAPS short lines (≤ 60 chars, not all punctuation/numbers)
  4. Lines ending with ":\n" that are short (table-of-contents-style)

If fewer than 2 headings are detected the chunker falls back transparently
to RecursiveChunker so callers never get a worse result.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

from app.utils.hashing import sha256_text
from .base import BaseChunker, Chunk, ChunkingConfig
from .recursive import RecursiveChunker

log = structlog.get_logger(__name__)

# ── Heading detection patterns ──────────────────────────────────────────────

_CHAPTER_SECTION = re.compile(
    r"^(chapter|section|part|unit|module|topic|lesson)\s+[\dIVXivx]+",
    re.IGNORECASE,
)

_NUMBERED = re.compile(
    r"^\d+(\.\d+){0,2}\.?\s+\S",  # "1.", "1.2", "1.2.3" followed by non-whitespace
)

# All-caps line: not a page number, not all punctuation, ≤ 60 chars
_ALL_CAPS = re.compile(r"^[A-Z][A-Z0-9 ,\-:&/]{3,59}$")

# Short colon-terminated line (table-of-contents style)
_COLON_HEADER = re.compile(r"^[A-Z].{5,59}:$")


def _is_heading(line: str) -> bool:
    """Return True if the line looks like a section heading."""
    stripped = line.strip()
    if not stripped or len(stripped) < 2:
        return False
    if _CHAPTER_SECTION.match(stripped):
        return True
    if _NUMBERED.match(stripped):
        return True
    if _ALL_CAPS.match(stripped):
        return True
    if _COLON_HEADER.match(stripped):
        return True
    return False


@dataclass
class _Section:
    heading: str        # heading text (may be empty for preamble)
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        parts = []
        if self.heading:
            parts.append(self.heading)
        parts.extend(self.lines)
        return "\n".join(parts)


def detect_chapters(text: str) -> list[_Section]:
    """
    Split raw text into sections at heading boundaries.
    Returns a list of _Section objects (the first may be a preamble with no heading).
    """
    sections: list[_Section] = []
    current = _Section(heading="")

    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        if _is_heading(line):
            if current.lines or current.heading:
                sections.append(current)
            current = _Section(heading=line)
        else:
            current.lines.append(line)

    if current.lines or current.heading:
        sections.append(current)

    return sections


class ChapterChunker(BaseChunker):
    """
    Split at chapter/section heading boundaries, then recursively sub-chunk
    any section that exceeds chunk_size.
    """

    def __init__(self, config: ChunkingConfig):
        super().__init__(config)
        self._fallback = RecursiveChunker(config)

    def chunk(self, text: str) -> list[Chunk]:
        if not text or not text.strip():
            return []

        sections = detect_chapters(text)
        real_sections = [s for s in sections if s.heading]  # exclude preamble

        if len(real_sections) < 2:
            # Not enough headings — fall back to recursive
            log.debug("chapter_chunker_fallback", reason="fewer than 2 headings detected")
            return self._fallback.chunk(text)

        log.info(
            "chapter_chunker_splitting",
            sections=len(sections),
            headings=len(real_sections),
        )

        chunks: list[Chunk] = []
        chunk_index = 0

        for section in sections:
            section_text = section.text.strip()
            if not section_text or len(section_text) < self.config.min_chunk_size:
                continue

            if len(section_text) <= self.config.chunk_size:
                # Section fits in one chunk
                chunks.append(Chunk(
                    text=section_text,
                    chunk_index=chunk_index,
                    chunk_hash=sha256_text(section_text),
                    metadata={"chapter_heading": section.heading or "preamble"},
                ))
                chunk_index += 1
            else:
                # Section too long — sub-chunk it, tag each sub-chunk with heading
                sub_chunks = self._fallback.chunk(section_text)
                for sc in sub_chunks:
                    sc.chunk_index = chunk_index
                    sc.metadata["chapter_heading"] = section.heading or "preamble"
                    chunks.append(sc)
                    chunk_index += 1

        if not chunks:
            return self._fallback.chunk(text)

        log.info("chapter_chunks_produced", count=len(chunks))
        return chunks
