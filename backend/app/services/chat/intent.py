"""
Intent classifier — runs before every chat message.

Takes the user's message + last 3 turns of history and returns:
  - intent: one of ChatIntent enum values
  - topic_tags: short noun phrases (used for learning event logging + RAG bias)
  - is_continuation: whether this message references something from history
  - rephrased_query: standalone version of the question (pronouns resolved)
    → this is what gets embedded for Qdrant search

Uses a fast/cheap model (gpt-4o-mini or equivalent) — this adds ~200ms max.
Falls back gracefully to GENERAL_QUESTION if the LLM call fails.
"""
import json
import structlog

from app.models.chat import ChatIntent
from app.services.ai.client import AIClient
from app.services.ai.prompts.loader import build_messages

log = structlog.get_logger(__name__)

# History window sent to intent classifier (last N messages, trimmed)
INTENT_HISTORY_TURNS = 3
INTENT_MODEL = "gpt-4o-mini"


class IntentResult:
    """Structured output from the intent classifier."""

    def __init__(
        self,
        intent: str,
        topic_tags: list[str],
        is_continuation: bool,
        rephrased_query: str,
        detected_language: str = "en",
    ):
        self.intent = intent
        self.topic_tags = topic_tags
        self.is_continuation = is_continuation
        self.rephrased_query = rephrased_query
        self.detected_language = detected_language

    def __repr__(self) -> str:
        return (
            f"<IntentResult intent={self.intent} "
            f"lang={self.detected_language} tags={self.topic_tags} cont={self.is_continuation}>"
        )


def _format_history_snippet(messages: list) -> str:
    """Format last N message pairs into a compact history string for the prompt."""
    if not messages:
        return "(no prior conversation)"

    # Take last INTENT_HISTORY_TURNS*2 messages (user+assistant pairs)
    recent = messages[-(INTENT_HISTORY_TURNS * 2):]
    lines = []
    for msg in recent:
        role = "Student" if msg.role == "user" else "AI"
        # Truncate long messages for the intent prompt
        content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
        lines.append(f"{role}: {content}")

    return "\n".join(lines)


async def classify_intent(
    message: str,
    history: list,
    ai_client: AIClient,
) -> IntentResult:
    """
    Classify user intent using a fast LLM call.

    Args:
        message: The raw user message
        history: List of ChatMessage ORM objects (the session's messages so far)
        ai_client: AIClient instance (already configured with session context)

    Returns:
        IntentResult with intent, topic_tags, is_continuation, rephrased_query
    """
    history_snippet = _format_history_snippet(history)

    messages_payload, config = build_messages(
        "intent_detect",
        variables={
            "message": message,
            "history_snippet": history_snippet,
        },
    )

    try:
        response = await ai_client.complete(
            messages=messages_payload,
            model=INTENT_MODEL,
            task_type="chat_intent",
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)

        # Validate intent — fall back to GENERAL_QUESTION if unknown
        intent_str = data.get("intent", "GENERAL_QUESTION")
        valid_intents = {e.value for e in ChatIntent}
        if intent_str not in valid_intents:
            log.warning("intent_unknown", raw_intent=intent_str, fallback="GENERAL_QUESTION")
            intent_str = ChatIntent.GENERAL_QUESTION.value

        # Validate detected_language — must be a plausible ISO 639-1 code
        detected_lang = str(data.get("detected_language", "en")).strip().lower()[:5]
        if not detected_lang or len(detected_lang) < 2:
            detected_lang = "en"

        return IntentResult(
            intent=intent_str,
            topic_tags=data.get("topic_tags", [])[:5],  # cap at 5
            is_continuation=bool(data.get("is_continuation", False)),
            rephrased_query=data.get("rephrased_query", message) or message,
            detected_language=detected_lang,
        )

    except Exception as e:
        log.warning("intent_classify_failed", error=str(e), fallback="GENERAL_QUESTION")
        # Graceful fallback — never crash on intent detection
        return IntentResult(
            intent=ChatIntent.GENERAL_QUESTION.value,
            topic_tags=[],
            is_continuation=False,
            rephrased_query=message,
            detected_language="en",
        )
