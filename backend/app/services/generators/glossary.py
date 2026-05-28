"""Glossary generator.

Supports:
- `save_terms_to_db()` to persist pool rows into glossary_terms table
"""
import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glossary import GlossaryTerm
from app.models.output import AIOutput, OutputType
from app.services.ai.prompts.loader import build_messages
from .base import BaseGenerator

if TYPE_CHECKING:
    from app.models.content import ContentItem

log = structlog.get_logger(__name__)


class GlossaryGenerator(BaseGenerator):
    output_type = OutputType.GLOSSARY
    prompt_name = "glossary"

    async def generate(
        self,
        content_item: "ContentItem",
        full_text: str,
        model: str,
        output_language: str = "en",
    ) -> dict:
        content = self._truncate_content(full_text)
        messages, config = build_messages(
            self.prompt_name,
            variables={
                "title": content_item.title or "Untitled",
                "language": output_language,
                "content": content,
            },
        )
        response = await self.ai_client.complete(
            messages=messages, model=model, task_type="glossary",
            temperature=config["temperature"], max_tokens=config["max_tokens"],
        )
        payload = self._parse_json_response(response.choices[0].message.content)

        log.info(
            "glossary_generated",
            content_item_id=str(content_item.id),
            term_count=len(payload.get("terms", [])),
        )
        return payload

    async def save_terms_to_db(
        self,
        db: AsyncSession,
        content_item: "ContentItem",
        ai_output: AIOutput,
        payload: dict,
        generation_batch: int = 1,
    ) -> list[GlossaryTerm]:
        """
        Persist individual glossary terms into the glossary_terms pool table.

        Each term becomes a separate row so it can be individually edited,
        deleted, or activated/deactivated by the teacher.
        Called after the parent AIOutput row is saved.

        Args:
            generation_batch: 1 for initial generation, 2+ for future regenerate passes.
        """
        terms_data = payload.get("terms", [])
        saved = []

        for term_data in terms_data:
            term = GlossaryTerm(
                id=uuid.uuid4(),
                content_item_id=content_item.id,
                tenant_id=content_item.tenant_id,
                ai_output_id=ai_output.id,
                term=term_data.get("term", ""),
                definition=term_data.get("definition", ""),
                context=term_data.get("context"),
                related_terms=term_data.get("related_terms"),
                category=term_data.get("category"),
                source="generated",
                generation_batch=generation_batch,
                is_active=True,
            )
            db.add(term)
            saved.append(term)

        await db.flush()
        log.info(
            "glossary_terms_saved",
            content_item_id=str(content_item.id),
            count=len(saved),
            batch=generation_batch,
        )
        return saved
