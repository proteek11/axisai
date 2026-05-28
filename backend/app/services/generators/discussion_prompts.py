"""
Discussion Prompts generator — produces open-ended discussion questions for cohort programmes.

Works for all content types (video transcript, PDF, HTML page, SCORM).
Questions are designed to spark debate and reflection, not test recall.
No "correct" answers — suitable for live sessions and online forums.

Payload stored in AIOutput.payload:
{
  "prompts": [
    {
      "question": "How would you apply this differently in a regulated industry?",
      "theme": "application",
      "challenge_level": "intermediate"
    },
    ...
  ],
  "prompt_count": 3,
  "language": "en",
  "content_type": "youtube"
}

Default count: 3 questions. Can be overridden via job_config.options.count (max 6).
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

DEFAULT_PROMPT_COUNT = 3


class DiscussionPromptsGenerator(BaseGenerator):
    output_type = OutputType.DISCUSSION_PROMPTS
    prompt_name = "discussion_prompts"

    async def generate(
        self,
        content_item: "ContentItem",
        full_text: str,
        model: str,
        output_language: str = "en",
        count: int = DEFAULT_PROMPT_COUNT,
    ) -> dict:
        """
        Generate open-ended discussion questions for cohort-based learning.

        Args:
            content_item:    ContentItem being processed
            full_text:       Full extracted text
            model:           LLM model to use
            output_language: BCP-47 language code for generated output
            count:           Number of questions to generate (default 3, max 6)

        Returns:
            Payload dict ready to store in AIOutput.payload.
        """
        prompt_count = max(2, min(count, 6))  # clamp 2–6
        content = self._truncate_content(full_text)

        messages, prompt_config = build_messages(
            self.prompt_name,
            variables={
                "title": content_item.title or "Untitled",
                "content_type": content_item.content_type,
                "language": output_language,
                "prompt_count": prompt_count,
                "content": content,
            },
        )

        response = await self.ai_client.complete(
            messages=messages,
            model=model,
            task_type="discussion_prompts",
            temperature=prompt_config["temperature"],
            max_tokens=prompt_config["max_tokens"],
        )

        response_text = response.choices[0].message.content
        raw = self._parse_json_response(response_text)

        prompts = self._validate_prompts(raw.get("prompts", []))

        payload = {
            "prompts": prompts,
            "prompt_count": len(prompts),
            "language": output_language,
            "content_type": content_item.content_type,
        }

        log.info(
            "discussion_prompts_generated",
            content_item_id=str(content_item.id),
            prompt_count=len(prompts),
        )
        return payload

    @staticmethod
    def _validate_prompts(prompts: list) -> list[dict]:
        """
        Sanitise and normalise discussion prompt items from the AI response.
        Removes entries missing the question text.
        Normalises challenge_level to known values.
        """
        valid_levels = {"accessible", "intermediate", "advanced"}
        result = []

        for item in prompts:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            if not question:
                continue

            challenge_level = str(item.get("challenge_level", "intermediate")).lower().strip()
            if challenge_level not in valid_levels:
                challenge_level = "intermediate"

            result.append({
                "question": question,
                "theme": str(item.get("theme", "")).strip(),
                "challenge_level": challenge_level,
            })

        return result
