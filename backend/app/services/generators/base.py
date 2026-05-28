"""
Abstract base generator.
All output generators (summary, flashcards, quiz, etc.) implement this interface.
"""
import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import structlog

from app.core.exceptions import AIProviderError, ContentProcessingError
from app.models.output import OutputType
from app.services.ai.prompts.loader import build_messages

if TYPE_CHECKING:
    from app.models.content import ContentItem
    from app.services.ai.client import AIClient

log = structlog.get_logger(__name__)

# Max characters to send in a single AI call
# ~75k chars ≈ ~20k tokens (safe for most models)
MAX_CONTENT_CHARS = 75_000


class BaseGenerator(ABC):
    """
    All generators implement this interface.
    Each generator corresponds to one OutputType.
    """

    output_type: OutputType
    prompt_name: str  # Name of the YAML prompt file

    def __init__(self, ai_client: "AIClient"):
        self.ai_client = ai_client

    @abstractmethod
    async def generate(
        self,
        content_item: "ContentItem",
        full_text: str,
        model: str,
        output_language: str = "en",
    ) -> dict:
        """
        Generate output for the given content.

        Args:
            content_item:    The ContentItem being processed (for context/metadata)
            full_text:       Full extracted text (may be truncated for very long content)
            model:           Model to use for this generation
            output_language: BCP-47 language code for the generated output.
                             Defaults to "en". Set to source language to generate
                             outputs in the same language as the content, or to
                             any target language (e.g. "fr") for translation.

        Returns:
            dict payload to store in AIOutput.payload
        """
        ...

    def _truncate_content(self, text: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
        """
        Truncate content to fit model context window.
        Truncates at a paragraph boundary to preserve coherence.
        """
        if len(text) <= max_chars:
            return text

        # Find last paragraph break before the limit
        truncated = text[:max_chars]
        last_para = truncated.rfind("\n\n")
        if last_para > max_chars * 0.8:  # Only truncate at para if it's reasonably far in
            truncated = truncated[:last_para]

        log.warning(
            "content_truncated",
            original_chars=len(text),
            truncated_chars=len(truncated),
            generator=self.output_type,
        )
        return truncated + "\n\n[Content truncated for processing]"

    def _parse_json_response(self, response_text: str) -> dict:
        """
        Parse JSON from AI response, with cleanup for common formatting issues.

        Handles:
        - Responses wrapped in ```json ... ``` markdown
        - Trailing commas (invalid JSON but AI models often produce them)
        - Extra text before/after the JSON object
        """
        text = response_text.strip()

        # Strip markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            text = text.strip()

        # Find the JSON object boundaries
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            log.error(
                "json_parse_failed",
                generator=self.output_type,
                error=str(e),
                response_preview=text[:200],
            )
            raise ContentProcessingError(
                f"AI returned invalid JSON for {self.output_type}",
                detail={"parse_error": str(e), "response_preview": text[:200]},
            )
