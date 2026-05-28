"""
Chat response parser — extracts structured data from the LLM's JSON output.

The main chat_answer prompt instructs the LLM to return a JSON object.
This module parses that JSON and returns a clean ParsedChatResponse.

Handles:
  - JSON extraction (in case the LLM wraps it in markdown code blocks)
  - Field validation and defaults
  - Suggestion list normalization
  - visual_data passthrough
  - Graceful fallback if parsing fails

DEFAULT_MESSAGES: maps response_type → default display message
  Python returns these; Moodle can override them via its lang strings.
"""
from __future__ import annotations

import json
import re
import structlog

from app.models.chat import ChatResponseType

log = structlog.get_logger(__name__)

# Default messages for non-ANSWER response types, keyed by chat_mode.
# Moodle maps these response_types to its own get_string() calls.
# These are the Python fallbacks used if Moodle doesn't override.
DEFAULT_MESSAGES: dict[str, str] = {
    ChatResponseType.NO_CONTEXT.value: (
        "I couldn't find information about this topic in the course materials. "
        "Try rephrasing your question, or ask your instructor."
    ),
    ChatResponseType.LOW_CONFIDENCE.value: (
        "I found some relevant material, but I'm not fully confident this covers "
        "your question. Please verify with your course notes."
    ),
    ChatResponseType.OUT_OF_SCOPE.value: (
        "This question seems to be outside the scope of this course. "
        "I'm here to help with course-related topics."
    ),
    ChatResponseType.AMBIGUOUS.value: (
        "Could you clarify your question a bit more? "
        "I want to make sure I give you the most helpful answer."
    ),
    ChatResponseType.ERROR.value: (
        "Something went wrong while generating a response. Please try again."
    ),
}

SUPPORT_DEFAULT_MESSAGES: dict[str, str] = {
    ChatResponseType.NO_CONTEXT.value: (
        "I couldn't find information about that in our knowledge base. "
        "Please try rephrasing, or contact our support team for further help."
    ),
    ChatResponseType.LOW_CONFIDENCE.value: (
        "I found a partial match in our knowledge base, but I'm not fully confident "
        "it covers your question. Please verify with our support team if needed."
    ),
    ChatResponseType.OUT_OF_SCOPE.value: (
        "That question appears to be outside the scope of this support knowledge base. "
        "Please contact our support team directly for further assistance."
    ),
    ChatResponseType.AMBIGUOUS.value: (
        "Could you clarify your question a bit more? "
        "I want to make sure I find the right support article for you."
    ),
    ChatResponseType.ERROR.value: (
        "Something went wrong while generating a response. Please try again."
    ),
}

VALID_RESPONSE_TYPES = {e.value for e in ChatResponseType}
VALID_RENDER_HINTS = {"text", "markdown", "visual_chart", "visual_mermaid"}
VALID_ACTIONS = {"ask", "quiz_me", "visualize", "explain_more", "summarize"}
VALID_SUGGESTION_TYPES = {"follow_up_question", "action", "related_topic"}


class ParsedSuggestion:
    def __init__(self, id: str, type: str, label: str, action: str, payload: str | None):
        self.id = id
        self.type = type
        self.label = label
        self.action = action
        self.payload = payload

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "action": self.action,
            "payload": self.payload,
        }


class ParsedChatResponse:
    """Structured output from parsing the LLM's JSON response."""

    def __init__(
        self,
        answer: str | None,
        render_hint: str,
        visual_data: dict | None,
        response_type: str,
        confidence: float,
        topic_tags: list[str],
        suggestions: list[ParsedSuggestion],
        default_message: str | None,
    ):
        self.answer = answer
        self.render_hint = render_hint
        self.visual_data = visual_data
        self.response_type = response_type
        self.confidence = confidence
        self.topic_tags = topic_tags
        self.suggestions = suggestions
        self.default_message = default_message

    def __repr__(self) -> str:
        return (
            f"<ParsedChatResponse type={self.response_type} "
            f"conf={self.confidence:.2f} hints={self.render_hint}>"
        )


def _extract_json(raw: str) -> dict:
    """
    Extract JSON from LLM output.
    Handles cases where the model wraps JSON in markdown code blocks.
    """
    raw = raw.strip()

    # Strip markdown code block if present
    if raw.startswith("```"):
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
        if match:
            raw = match.group(1).strip()

    return json.loads(raw)


def _parse_suggestions(raw_suggestions: list | None) -> list[ParsedSuggestion]:
    """Parse and validate the suggestions array from LLM output."""
    if not raw_suggestions or not isinstance(raw_suggestions, list):
        return []

    parsed = []
    for i, s in enumerate(raw_suggestions[:5]):   # cap at 5
        if not isinstance(s, dict):
            continue

        stype = s.get("type", "follow_up_question")
        if stype not in VALID_SUGGESTION_TYPES:
            stype = "follow_up_question"

        action = s.get("action", "ask")
        if action not in VALID_ACTIONS:
            action = "ask"

        label = str(s.get("label", ""))[:120]   # truncate crazy-long labels
        if not label:
            continue

        parsed.append(ParsedSuggestion(
            id=s.get("id", f"s{i + 1}"),
            type=stype,
            label=label,
            action=action,
            payload=s.get("payload"),
        ))

    return parsed


def parse_chat_response(
    raw_content: str,
    fallback_confidence: float = 0.0,
    fallback_response_type: str = ChatResponseType.ERROR.value,
    chat_mode: str = "study",
) -> ParsedChatResponse:
    """
    Parse the LLM's JSON response into a structured ParsedChatResponse.

    Always returns a valid ParsedChatResponse — never raises.
    On parse failure: returns an ERROR response with the fallback values.

    Args:
        raw_content:            Raw string from LLM choice.message.content
        fallback_confidence:    Confidence from retriever (used if LLM doesn't set it)
        fallback_response_type: Pre-computed response_type from retriever confidence
    """
    try:
        data = _extract_json(raw_content)

        # ── response_type ─────────────────────────────────────────────────
        response_type = str(data.get("response_type", fallback_response_type))
        if response_type not in VALID_RESPONSE_TYPES:
            response_type = fallback_response_type

        # ── confidence ────────────────────────────────────────────────────
        try:
            confidence = float(data.get("confidence", fallback_confidence))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = fallback_confidence

        # ── answer ────────────────────────────────────────────────────────
        answer = data.get("answer")
        if answer and not isinstance(answer, str):
            answer = str(answer)
        if answer and len(answer.strip()) == 0:
            answer = None

        # ── render_hint ───────────────────────────────────────────────────
        render_hint = str(data.get("render_hint", "markdown"))
        if render_hint not in VALID_RENDER_HINTS:
            render_hint = "markdown"

        # ── visual_data ───────────────────────────────────────────────────
        visual_data = data.get("visual_data")
        if visual_data is not None and not isinstance(visual_data, dict):
            visual_data = None

        # ── topic_tags ────────────────────────────────────────────────────
        topic_tags = data.get("topic_tags", [])
        if not isinstance(topic_tags, list):
            topic_tags = []
        topic_tags = [str(t)[:80] for t in topic_tags[:5]]

        # ── suggestions ───────────────────────────────────────────────────
        suggestions = _parse_suggestions(data.get("suggestions"))

        # ── default_message ───────────────────────────────────────────────
        msg_map = SUPPORT_DEFAULT_MESSAGES if chat_mode == "support" else DEFAULT_MESSAGES
        default_message = msg_map.get(response_type)

        log.debug(
            "chat_response_parsed",
            response_type=response_type,
            confidence=confidence,
            render_hint=render_hint,
            suggestion_count=len(suggestions),
        )

        return ParsedChatResponse(
            answer=answer,
            render_hint=render_hint,
            visual_data=visual_data,
            response_type=response_type,
            confidence=confidence,
            topic_tags=topic_tags,
            suggestions=suggestions,
            default_message=default_message,
        )

    except Exception as e:
        log.error("chat_response_parse_failed", error=str(e), raw_preview=raw_content[:200])
        return ParsedChatResponse(
            answer=None,
            render_hint="text",
            visual_data=None,
            response_type=ChatResponseType.ERROR.value,
            confidence=0.0,
            topic_tags=[],
            suggestions=[],
            default_message=DEFAULT_MESSAGES[ChatResponseType.ERROR.value],
        )
