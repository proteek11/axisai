"""
Chat prompt builder — assembles the full context for the main LLM call.

Responsibilities:
  1. Format conversation history into a clean block
     - Uses rolling window (last HISTORY_WINDOW messages)
     - If session has a session_summary, prepends it as older context
  2. Format RAG chunks into a numbered context block with source attribution
  3. Build the full messages list via the chat_answer YAML prompt
  4. Determine response_type based on confidence score
  5. Return the built messages + prompt config

Kept separate from the orchestrator so it can be unit-tested independently.
"""
from __future__ import annotations

import structlog

from app.models.chat import ChatIntent, ChatResponseType
from app.services.ai.prompts.loader import build_messages
from app.services.chat.retriever import RetrievedChunk

log = structlog.get_logger(__name__)

# How many recent messages to include in the prompt (beyond session_summary)
HISTORY_WINDOW = 10

# Confidence thresholds for response_type classification
CONFIDENCE_HIGH = 0.65     # >= this → ANSWER
CONFIDENCE_LOW = 0.35      # >= this → LOW_CONFIDENCE ; < this → NO_CONTEXT

# Character limit per RAG chunk in the prompt (avoid token explosion)
MAX_CHUNK_CHARS = 1200


def _format_history_block(messages: list, session_summary: str | None) -> str:
    """
    Build the conversation history block for the main prompt.

    If there's a session_summary (for long sessions), prepend it as
    "[Earlier conversation summary]" before the recent message window.
    """
    parts = []

    if session_summary:
        parts.append(
            f"[Earlier conversation summary]\n{session_summary}\n[End of summary]\n"
        )

    if not messages:
        if not session_summary:
            parts.append("(no prior conversation)")
        return "\n".join(parts)

    # Rolling window — last HISTORY_WINDOW messages
    recent = messages[-HISTORY_WINDOW:]
    for msg in recent:
        role_label = "Student" if msg.role == "user" else "AI Assistant"
        parts.append(f"{role_label}: {msg.content}")

    return "\n\n".join(parts)


def _format_context_block(chunks: list[RetrievedChunk], chat_mode: str = "study") -> str:
    """
    Build the RAG context block for the prompt.

    Each chunk is numbered and labelled with its source title.
    Long chunks are truncated to avoid token explosion.
    """
    if not chunks:
        if chat_mode == "support":
            return "(no matching articles found in the knowledge base)"
        return "(no relevant course material found)"

    lines = []
    for i, chunk in enumerate(chunks, 1):
        title_label = f" [{chunk.title}]" if chunk.title else ""
        text = chunk.text
        if len(text) > MAX_CHUNK_CHARS:
            text = text[:MAX_CHUNK_CHARS] + "..."
        lines.append(f"[{i}]{title_label}\n{text}")

    return "\n\n---\n\n".join(lines)


# ── Mode-specific prompt blocks ───────────────────────────────────────────────

_STUDY_SYSTEM_BLOCK = """\
You are an intelligent educational assistant embedded in a learning management system.
You help students understand course material clearly and engagingly.

YOUR RULES:
1. ONLY use the provided course context to answer. Never invent facts not present in the context.
2. If the context doesn't contain enough information, be honest — say you couldn't find it in the course material.
3. Keep answers focused and educationally valuable. Not too short (unhelpful) and not too long (overwhelming).
4. Use markdown formatting for clarity: **bold** for key terms, bullet points for lists, code blocks for code.
5. Always generate 3-4 relevant follow-up suggestions that genuinely help the student go deeper.
6. Adapt your answer style to the intent: explanations should be clear and progressive; comparisons should use structure; visuals should provide structured data."""

_SUPPORT_SYSTEM_BLOCK = """\
You are a helpful support assistant for an online learning platform. You answer user questions
strictly from the provided knowledge base articles. You do NOT use general internet knowledge.

YOUR RULES:
1. ONLY answer using the provided Knowledge Base context. If the answer is not in the context, say so clearly.
2. NEVER invent or infer information that is not explicitly stated in the knowledge base articles.
3. If the knowledge base does not contain the answer, respond with response_type "NO_CONTEXT" and direct the user to contact support.
4. Keep answers concise, friendly, and actionable — users want quick help, not long essays.
5. Use markdown formatting for clarity where helpful.
6. Suggest 2-3 relevant follow-up questions only — do NOT suggest quiz or visual actions (those are for course study only)."""

_STUDY_SUGGESTIONS_EXAMPLE = """\
[
      {{"id": "s1", "type": "follow_up_question", "label": "Can you give me a real-world example?", "action": "ask", "payload": "Can you give me a real-world example of this concept?"}},
      {{"id": "s2", "type": "action", "label": "Quiz me on this", "action": "quiz_me", "payload": null}},
      {{"id": "s3", "type": "action", "label": "Show me visually", "action": "visualize", "payload": null}},
      {{"id": "s4", "type": "follow_up_question", "label": "How does this relate to [next topic]?", "action": "ask", "payload": "How does this relate to [next topic]?"}}
    ]"""

_SUPPORT_SUGGESTIONS_EXAMPLE = """\
[
      {{"id": "s1", "type": "follow_up_question", "label": "How do I [related task]?", "action": "ask", "payload": "How do I [related task]?"}},
      {{"id": "s2", "type": "follow_up_question", "label": "What if I still have a problem?", "action": "ask", "payload": "What should I do if I still have this problem after following these steps?"}},
      {{"id": "s3", "type": "follow_up_question", "label": "Are there any related articles?", "action": "ask", "payload": "Are there any related knowledge base articles about this?"}}
    ]"""


def _get_mode_blocks(chat_mode: str) -> dict:
    """Return prompt template variables that differ between study and support modes."""
    if chat_mode == "support":
        return {
            "mode_system_block": _SUPPORT_SYSTEM_BLOCK,
            "context_label": "KNOWLEDGE BASE CONTEXT (retrieved from support articles)",
            "no_context_label": "the knowledge base has no information on this topic (confidence < 0.35)",
            "suggestions_example": _SUPPORT_SUGGESTIONS_EXAMPLE,
        }
    return {
        "mode_system_block": _STUDY_SYSTEM_BLOCK,
        "context_label": "COURSE CONTEXT (retrieved from course materials)",
        "no_context_label": "the course material has no relevant information for this question (confidence < 0.35)",
        "suggestions_example": _STUDY_SUGGESTIONS_EXAMPLE,
    }


def _format_session_summary_block(session_summary: str | None) -> str:
    """Block injected into the prompt when there's a rolling summary."""
    if not session_summary:
        return ""
    return (
        f"PRIOR CONVERSATION SUMMARY (for older context):\n"
        f"{session_summary}\n"
        f"(The messages above are the most recent conversation.)"
    )


def determine_response_type(confidence: float, chunks_count: int, intent: str) -> str:
    """
    Classify the response type based on retrieval confidence.

    The LLM may override this in its own output, but we pre-compute it
    so the orchestrator can short-circuit (skip LLM call for NO_CONTEXT)
    if configured to do so.
    """
    if chunks_count == 0:
        return ChatResponseType.NO_CONTEXT.value
    if confidence >= CONFIDENCE_HIGH:
        return ChatResponseType.ANSWER.value
    if confidence >= CONFIDENCE_LOW:
        return ChatResponseType.LOW_CONFIDENCE.value
    return ChatResponseType.NO_CONTEXT.value


def build_chat_messages(
    question: str,
    intent: str,
    language: str,
    history: list,
    chunks: list[RetrievedChunk],
    session_summary: str | None = None,
    chat_mode: str = "study",
) -> tuple[list[dict], dict]:
    """
    Build the full messages list for the main chat LLM call.

    Args:
        question:        The rephrased standalone question (from intent classifier)
        intent:          ChatIntent string
        language:        ISO 639-1 response language
        history:         ChatMessage ORM objects for the current session
        chunks:          Retrieved RAG chunks
        session_summary: Rolling summary of older messages (if session is long)
        chat_mode:       "study" | "support" — controls system prompt and suggestion style

    Returns:
        (messages, prompt_config) — ready to pass to AIClient.complete()
    """
    history_block = _format_history_block(history, session_summary=None)
    summary_block = _format_session_summary_block(session_summary)
    context_block = _format_context_block(chunks, chat_mode=chat_mode)
    mode_blocks = _get_mode_blocks(chat_mode)

    messages, config = build_messages(
        "chat_answer",
        variables={
            "intent": intent,
            "language": language,
            "session_summary_block": summary_block,
            "history_block": history_block,
            "context_block": context_block,
            "question": question,
            **mode_blocks,
        },
    )

    return messages, config
