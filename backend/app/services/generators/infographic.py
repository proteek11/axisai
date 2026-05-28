"""
Infographic generator — produces a self-contained HTML visual summary.

Unlike other generators which return structured JSON data, this generator
returns an HTML document embedded in the payload.  The HTML is a complete,
standalone page — no external dependencies — suitable for:
  - Direct iframe embedding in Moodle
  - Downloading as a standalone .html file
  - Rendering in a webview inside a mobile app

Two API surfaces:
  GET /content/{id}/infographic        → JSON (payload contains "html" field)
  GET /content/{id}/infographic/html   → text/html (the HTML document directly)

Payload stored in AIOutput.payload:
{
  "html": "<!DOCTYPE html>...",
  "title": "Introduction to Machine Learning",
  "sections": ["key_statistics", "core_concepts", "process"],
  "colour_palette": {
    "primary": "#1a7a8a",
    "accent1": "#f0a500",
    "accent2": "#e8f4f8"
  },
  "language": "en",
  "content_type": "youtube"
}
"""
from typing import TYPE_CHECKING

import structlog

from app.models.output import OutputType
from app.services.ai.prompts.loader import build_messages
from .base import BaseGenerator

if TYPE_CHECKING:
    from app.models.content import ContentItem
    from app.services.ai.client import AIClient

log = structlog.get_logger(__name__)

# Infographic content is typically shorter than full text — trim to ~40k chars
# to stay within context window while leaving room for the HTML response
MAX_INFOGRAPHIC_CHARS = 40_000


class InfographicGenerator(BaseGenerator):
    output_type = OutputType.INFOGRAPHIC
    prompt_name = "infographic"

    async def generate(
        self,
        content_item: "ContentItem",
        full_text: str,
        model: str,
        output_language: str = "en",
    ) -> dict:
        """
        Generate a self-contained HTML infographic from educational content.

        Args:
            content_item:    ContentItem being processed
            full_text:       Full extracted text
            model:           LLM model to use (prefer a model with large context/output)
            output_language: BCP-47 language code — all visible text will be in this language

        Returns:
            Payload dict with 'html' key containing the complete HTML document.
        """
        # Use a shorter content window — we need tokens left for the HTML output
        content = self._truncate_content(full_text, max_chars=MAX_INFOGRAPHIC_CHARS)
        word_count = len(full_text.split())

        messages, prompt_config = build_messages(
            self.prompt_name,
            variables={
                "title": content_item.title or "Untitled",
                "content_type": content_item.content_type,
                "language": output_language,
                "word_count": word_count,
                "content": content,
            },
        )

        response = await self.ai_client.complete(
            messages=messages,
            model=model,
            task_type="infographic",
            temperature=prompt_config["temperature"],
            max_tokens=prompt_config["max_tokens"],
        )

        response_text = response.choices[0].message.content
        raw = self._parse_json_response(response_text)

        html = str(raw.get("html", "")).strip()
        if not html:
            raise ValueError("Infographic generator returned empty HTML")

        # Ensure it looks like a real HTML document
        if not html.lower().startswith("<!doctype"):
            html = "<!DOCTYPE html>\n" + html

        payload = {
            "html": html,
            "title": str(raw.get("title", content_item.title or "")).strip(),
            "sections": raw.get("sections", []),
            "colour_palette": raw.get("colour_palette", {}),
            "language": output_language,
            "content_type": content_item.content_type,
        }

        log.info(
            "infographic_generated",
            content_item_id=str(content_item.id),
            html_chars=len(html),
            sections=payload["sections"],
        )
        return payload
