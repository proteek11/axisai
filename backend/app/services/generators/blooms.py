"""
Bloom's Taxonomy + Content Intelligence generator.
Produces: blooms levels, difficulty score, topic taxonomy, tags, learning objectives summary.
This feeds the axis_content_intelligence Qdrant collection.
"""
from typing import TYPE_CHECKING

import structlog

from app.models.output import OutputType
from app.services.ai.prompts.loader import build_messages
from .base import BaseGenerator

if TYPE_CHECKING:
    from app.models.content import ContentItem

log = structlog.get_logger(__name__)


class BloomsGenerator(BaseGenerator):
    output_type = OutputType.BLOOMS
    prompt_name = "blooms"

    async def generate(
        self,
        content_item: "ContentItem",
        full_text: str,
        model: str,
        output_language: str = "en",
    ) -> dict:
        """Generate Bloom's taxonomy analysis and content intelligence metadata."""

        content = self._truncate_content(full_text, max_chars=30_000)  # Smaller — analysis task

        messages, prompt_config = build_messages(
            self.prompt_name,
            variables={
                "title": content_item.title or "Untitled",
                "language": output_language,
                "content": content,
            },
        )

        response = await self.ai_client.complete(
            messages=messages,
            model=model,
            task_type="blooms",
            temperature=prompt_config["temperature"],
            max_tokens=prompt_config["max_tokens"],
        )

        response_text = response.choices[0].message.content
        payload = self._parse_json_response(response_text)

        log.info(
            "blooms_generated",
            content_item_id=str(content_item.id),
            primary_level=payload.get("primary_blooms_level"),
            difficulty=payload.get("difficulty", {}).get("label"),
        )
        return payload
