"""
FAQ generator — produces learner-facing frequently asked questions with answers.

Works for all content types (video transcript, PDF, HTML page, SCORM).
Anticipates the questions learners genuinely ask, not just re-states content.

Payload stored in AIOutput.payload:
{
  "faqs": [
    {
      "question": "How do I configure X?",
      "answer": "To configure X, first open... then set...",
      "topic": "configuration",
      "difficulty": "beginner"
    },
    ...
  ],
  "faq_count": 10,
  "language": "en",
  "content_type": "youtube"
}

Default count: 10 FAQs.  Can be overridden via job_config.options.count.
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

DEFAULT_FAQ_COUNT = 10


class FaqGenerator(BaseGenerator):
    output_type = OutputType.FAQ
    prompt_name = "faq"

    async def generate(
        self,
        content_item: "ContentItem",
        full_text: str,
        model: str,
        output_language: str = "en",
        count: int = DEFAULT_FAQ_COUNT,
    ) -> dict:
        """
        Generate FAQs that a learner studying this content would genuinely ask.

        Args:
            content_item:    ContentItem being processed
            full_text:       Full extracted text
            model:           LLM model to use
            output_language: BCP-47 language code for generated output
            count:           Number of FAQs to generate (default 10, max 20)

        Returns:
            Payload dict ready to store in AIOutput.payload.
        """
        faq_count = max(3, min(count, 20))  # clamp 3–20
        content = self._truncate_content(full_text)

        messages, prompt_config = build_messages(
            self.prompt_name,
            variables={
                "title": content_item.title or "Untitled",
                "content_type": content_item.content_type,
                "language": output_language,
                "faq_count": faq_count,
                "content": content,
            },
        )

        response = await self.ai_client.complete(
            messages=messages,
            model=model,
            task_type="faq",
            temperature=prompt_config["temperature"],
            max_tokens=prompt_config["max_tokens"],
        )

        response_text = response.choices[0].message.content
        raw = self._parse_json_response(response_text)

        faqs = self._validate_faqs(raw.get("faqs", []))

        payload = {
            "faqs": faqs,
            "faq_count": len(faqs),
            "language": output_language,
            "content_type": content_item.content_type,
        }

        log.info(
            "faq_generated",
            content_item_id=str(content_item.id),
            faq_count=len(faqs),
        )
        return payload

    @staticmethod
    def _validate_faqs(faqs: list) -> list[dict]:
        """
        Sanitise and normalise FAQ items from the AI response.
        Removes entries missing question or answer.
        Normalises difficulty to known values.
        """
        valid_difficulties = {"beginner", "intermediate", "advanced"}
        result = []

        for item in faqs:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            answer = str(item.get("answer", "")).strip()
            if not question or not answer:
                continue

            difficulty = str(item.get("difficulty", "beginner")).lower().strip()
            if difficulty not in valid_difficulties:
                difficulty = "beginner"

            result.append({
                "question": question,
                "answer": answer,
                "topic": str(item.get("topic", "")).strip(),
                "difficulty": difficulty,
            })

        return result
