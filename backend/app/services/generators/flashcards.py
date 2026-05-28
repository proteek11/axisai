"""Flashcard generator.

Supports:
- Parameterized `count` (default 10, max enforced by caller)
- `existing_items` injection for regenerate deduplication
- `save_cards_to_db()` to persist pool rows into flashcard_items table
"""
import json
import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flashcard import FlashcardItem
from app.models.output import AIOutput, OutputType
from app.services.ai.prompts.loader import build_messages, get_prompt_version
from .base import BaseGenerator

if TYPE_CHECKING:
    from app.models.content import ContentItem

log = structlog.get_logger(__name__)

DEFAULT_FLASHCARD_COUNT = 10


def _build_existing_items_block(existing_items: list[dict]) -> str:
    """
    Build the prompt block injected when regenerating to prevent duplicates.

    Returns an empty string on first generation so the prompt stays clean.
    On regeneration, returns a structured block listing existing fronts so
    the model knows not to repeat them.
    """
    if not existing_items:
        return ""

    lines = [
        "EXISTING CARDS — Do NOT repeat or rephrase any of these:",
        "",
    ]
    for i, item in enumerate(existing_items, 1):
        front = item.get("front", "")
        lines.append(f"  {i}. {front}")
    lines.append("")
    return "\n".join(lines)


class FlashcardsGenerator(BaseGenerator):
    output_type = OutputType.FLASHCARDS
    prompt_name = "flashcards"

    async def generate(
        self,
        content_item: "ContentItem",
        full_text: str,
        model: str,
        output_language: str = "en",
        count: int = DEFAULT_FLASHCARD_COUNT,
        existing_items: list[dict] | None = None,
    ) -> dict:
        """
        Generate `count` flashcards from the content.

        Args:
            count: How many new cards to generate.
            existing_items: List of already-generated card dicts (front/back).
                            Injected into the prompt to prevent duplication on
                            regenerate passes.
        """
        content = self._truncate_content(full_text)
        existing = existing_items or []

        messages, config = build_messages(
            self.prompt_name,
            variables={
                "title": content_item.title or "Untitled",
                "language": output_language,
                "content": content,
                "count": count,
                "existing_items_block": _build_existing_items_block(existing),
            },
        )
        response = await self.ai_client.complete(
            messages=messages,
            model=model,
            task_type="flashcards",
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
        )
        payload = self._parse_json_response(response.choices[0].message.content)

        log.info(
            "flashcards_generated",
            content_item_id=str(content_item.id),
            requested=count,
            returned=len(payload.get("cards", [])),
            is_regenerate=len(existing) > 0,
        )
        return payload

    async def save_cards_to_db(
        self,
        db: AsyncSession,
        content_item: "ContentItem",
        ai_output: AIOutput,
        payload: dict,
        generation_batch: int = 1,
    ) -> list[FlashcardItem]:
        """
        Persist individual cards into the flashcard_items pool table.

        Each card becomes a separate row so it can be individually edited,
        deleted, activated/deactivated, or semantically deduped on regenerate.
        Called after the parent AIOutput row is saved.

        Args:
            generation_batch: 1 for initial generation, 2+ for regenerate passes.
        """
        cards_data = payload.get("cards", [])
        saved = []

        for card in cards_data:
            item = FlashcardItem(
                id=uuid.uuid4(),
                content_item_id=content_item.id,
                tenant_id=content_item.tenant_id,
                ai_output_id=ai_output.id,
                front=card.get("front", ""),
                back=card.get("back", ""),
                hint=card.get("hint"),
                card_type=card.get("card_type"),
                difficulty=card.get("difficulty"),
                topic=card.get("topic"),
                source="generated",
                generation_batch=generation_batch,
                is_active=True,
            )
            db.add(item)
            saved.append(item)

        await db.flush()
        log.info(
            "flashcard_items_saved",
            content_item_id=str(content_item.id),
            count=len(saved),
            batch=generation_batch,
        )
        return saved
