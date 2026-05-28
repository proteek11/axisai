"""Mind map generator."""
from typing import TYPE_CHECKING

from app.models.output import OutputType
from app.services.ai.prompts.loader import build_messages
from .base import BaseGenerator

if TYPE_CHECKING:
    from app.models.content import ContentItem


class MindmapGenerator(BaseGenerator):
    output_type = OutputType.MINDMAP
    prompt_name = "mindmap"

    async def generate(
        self,
        content_item: "ContentItem",
        full_text: str,
        model: str,
        output_language: str = "en",
    ) -> dict:
        content = self._truncate_content(full_text, max_chars=30_000)
        messages, config = build_messages(
            self.prompt_name,
            variables={
                "title": content_item.title or "Untitled",
                "language": output_language,
                "content": content,
            },
        )
        response = await self.ai_client.complete(
            messages=messages, model=model, task_type="mindmap",
            temperature=config["temperature"], max_tokens=config["max_tokens"],
        )
        return self._parse_json_response(response.choices[0].message.content)
