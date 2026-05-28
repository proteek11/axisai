"""
Summary generator — produces narrative summary + key points + key concepts.
"""
import math
from typing import TYPE_CHECKING

import structlog

from app.models.output import OutputType
from app.services.ai.prompts.loader import build_messages
from .base import BaseGenerator

if TYPE_CHECKING:
    from app.models.content import ContentItem
    from app.services.ai.client import AIClient

log = structlog.get_logger(__name__)


class SummaryGenerator(BaseGenerator):
    output_type = OutputType.SUMMARY
    prompt_name = "summary"

    async def generate(
        self,
        content_item: "ContentItem",
        full_text: str,
        model: str,
        output_language: str = "en",
    ) -> dict:
        """Generate a comprehensive educational summary."""

        content = self._truncate_content(full_text)
        word_count = len(full_text.split())
        estimated_read_time = max(1, math.ceil(word_count / 200))  # ~200 wpm reading speed

        messages, prompt_config = build_messages(
            self.prompt_name,
            variables={
                "title": content_item.title or "Untitled",
                "content_type": content_item.content_type,
                "language": output_language,
                "estimated_read_time_min": estimated_read_time,
                "content": content,
            },
        )

        response = await self.ai_client.complete(
            messages=messages,
            model=model,
            task_type="summary",
            temperature=prompt_config["temperature"],
            max_tokens=prompt_config["max_tokens"],
        )

        response_text = response.choices[0].message.content
        payload = self._parse_json_response(response_text)

        # Enrich with our own metadata
        payload["word_count"] = word_count
        payload["estimated_read_time_min"] = estimated_read_time
        payload["content_type"] = content_item.content_type
        payload["language"] = output_language

        log.info(
            "summary_generated",
            content_item_id=str(content_item.id),
            key_points=len(payload.get("key_points", [])),
            key_concepts=len(payload.get("key_concepts", [])),
        )
        return payload
