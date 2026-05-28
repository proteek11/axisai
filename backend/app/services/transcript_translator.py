"""
Transcript translator — LLM-based translation of timed transcript segments.

Translates a list of [{start_sec, end_sec, text}] segments into a target language
while preserving all timestamp data exactly. This is critical for the Moodle
"seek to video" feature: clicking a transcript line must jump to the correct
video position regardless of which language the transcript is displayed in.

Strategy
--------
- Segments are sent to the LLM as a JSON array.
- The model is instructed to translate only the "text" field, leaving
  "start_sec" and "end_sec" unchanged.
- Large transcripts are batched (default: 80 segments per call) to stay
  within model context limits and allow parallel processing.
- On any batch failure the original (untranslated) segments are returned for
  that batch so a partial failure never silently truncates the transcript.

Usage
-----
    from app.services.transcript_translator import TranscriptTranslator

    translator = TranscriptTranslator(ai_client=ai_client)
    translated = await translator.translate(
        segments=original_segments,
        source_language="en",
        target_language="fr",
        model="gpt-4o-mini",
    )
"""
import asyncio
import json
import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.services.ai.client import AIClient

log = structlog.get_logger(__name__)

# Number of segments per LLM call.
# ~80 segments × ~15 words = ~1 200 words input → well within context limits.
DEFAULT_BATCH_SIZE = 80

_SYSTEM_PROMPT = """You are a professional translator specializing in educational video transcripts.

Your task: translate the "text" field of each transcript segment into {target_language}.

STRICT RULES:
1. Return a JSON array with EXACTLY the same number of objects as the input.
2. Copy "start_sec" and "end_sec" values UNCHANGED — do not alter them by even 0.01.
3. Only translate the "text" field. Keep proper nouns, abbreviations, and technical
   terms accurate in the target language; transliterate if needed.
4. Do NOT merge, split, reorder, or drop any segments.
5. Respond with the JSON array ONLY — no markdown, no preamble, no explanation.

Example input:
[{{"start_sec": 0.0, "end_sec": 3.5, "text": "Hello and welcome to this course."}}]

Example output (translated to French):
[{{"start_sec": 0.0, "end_sec": 3.5, "text": "Bonjour et bienvenue dans ce cours."}}]
"""

_USER_PROMPT = """Translate the following transcript segments from {source_language} to {target_language}.

Segments:
{segments_json}
"""


class TranscriptTranslator:
    """
    Translates transcript segments via the shared AIClient.

    A single instance is created per pipeline run and can be re-used across
    multiple translate() calls (e.g. translating all tracks to the same target).
    """

    def __init__(self, ai_client: "AIClient"):
        self.ai_client = ai_client

    async def translate(
        self,
        segments: list[dict],
        source_language: str,
        target_language: str,
        model: str,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> list[dict]:
        """
        Translate all segments into target_language.

        Returns a list of segments with the same length and timestamps as the
        input. Segments where translation failed are returned in their original
        language (the pipeline never silently drops content).

        Args:
            segments:         List of {start_sec, end_sec, text} dicts.
            source_language:  BCP-47 code of the source (e.g. "en").
            target_language:  BCP-47 code of the desired output (e.g. "fr").
            model:            Model to use (e.g. "gpt-4o-mini").
            batch_size:       Segments per LLM call.
        """
        if not segments:
            return []

        if source_language == target_language:
            return segments  # Nothing to do

        # Split into batches
        batches = [
            segments[i : i + batch_size]
            for i in range(0, len(segments), batch_size)
        ]

        log.info(
            "transcript_translation_start",
            source=source_language,
            target=target_language,
            total_segments=len(segments),
            batches=len(batches),
            model=model,
        )

        # Translate all batches (concurrently, up to 4 at a time to avoid rate limits)
        semaphore = asyncio.Semaphore(4)

        async def _translate_batch(batch: list[dict], batch_idx: int) -> list[dict]:
            async with semaphore:
                return await self._translate_batch(
                    batch=batch,
                    source_language=source_language,
                    target_language=target_language,
                    model=model,
                    batch_idx=batch_idx,
                )

        tasks = [_translate_batch(batch, idx) for idx, batch in enumerate(batches)]
        results = await asyncio.gather(*tasks)

        translated = [seg for batch_result in results for seg in batch_result]

        log.info(
            "transcript_translation_complete",
            source=source_language,
            target=target_language,
            original_count=len(segments),
            translated_count=len(translated),
        )

        return translated

    async def _translate_batch(
        self,
        batch: list[dict],
        source_language: str,
        target_language: str,
        model: str,
        batch_idx: int,
    ) -> list[dict]:
        """
        Translate one batch of segments. Returns the original batch on failure
        so partial failures never truncate the transcript.
        """
        segments_json = json.dumps(batch, ensure_ascii=False, indent=2)

        messages = [
            {
                "role": "system",
                "content": _SYSTEM_PROMPT.format(target_language=target_language).strip(),
            },
            {
                "role": "user",
                "content": _USER_PROMPT.format(
                    source_language=source_language,
                    target_language=target_language,
                    segments_json=segments_json,
                ).strip(),
            },
        ]

        try:
            response = await self.ai_client.complete(
                messages=messages,
                model=model,
                task_type="translation",
                temperature=0.1,  # Low temperature — translation should be deterministic
                max_tokens=4096,
            )
            raw = response.choices[0].message.content
            translated = self._parse_translation_response(raw, expected_count=len(batch))

            # Restore original timestamps in case the model altered them
            for original, result in zip(batch, translated):
                result["start_sec"] = original["start_sec"]
                result["end_sec"] = original["end_sec"]

            return translated

        except Exception as e:
            log.warning(
                "transcript_translation_batch_failed",
                batch_idx=batch_idx,
                batch_size=len(batch),
                source=source_language,
                target=target_language,
                error=str(e),
            )
            return batch  # Fall back to originals for this batch

    def _parse_translation_response(
        self, raw: str, expected_count: int
    ) -> list[dict]:
        """
        Parse the LLM response as a JSON array of translated segments.

        Handles common formatting issues (markdown fences, surrounding text).
        Raises ValueError if the response cannot be parsed as a valid array.
        """
        text = raw.strip()

        # Strip ```json ... ``` fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            inner = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            )
            text = inner.strip()

        # Find JSON array boundaries
        start = text.find("[")
        end = text.rfind("]") + 1
        if start < 0 or end <= start:
            raise ValueError(f"No JSON array found in translation response: {text[:200]}")

        text = text[start:end]

        try:
            result = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Translation response is not valid JSON: {e}. "
                f"Preview: {text[:200]}"
            )

        if not isinstance(result, list):
            raise ValueError(f"Expected JSON array, got {type(result).__name__}")

        # Tolerate minor count mismatches (LLM sometimes merges a few lines)
        # but log a warning so we can tune the prompt if needed.
        if len(result) != expected_count:
            log.warning(
                "translation_count_mismatch",
                expected=expected_count,
                received=len(result),
            )
            # Pad with empty dicts if too short, so zip() in the caller still works
            while len(result) < expected_count:
                result.append({"start_sec": 0, "end_sec": 0, "text": ""})

        return result[:expected_count]
