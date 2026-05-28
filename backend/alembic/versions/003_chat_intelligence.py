"""Chat intelligence: chat_messages enhancements, chat_sessions rolling summary,
user_learning_events table for Phase 4 personalization foundation.

Revision ID: 003
Revises: 002
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. chat_messages — add intelligence columns
    # -------------------------------------------------------------------------
    op.add_column("chat_messages", sa.Column(
        "intent", sa.String(30), nullable=True,
        comment="Detected intent: GENERAL_QUESTION|EXPLAIN_MORE|QUIZ_ME|SHOW_VISUAL|etc."
    ))
    op.add_column("chat_messages", sa.Column(
        "response_type", sa.String(20), nullable=True,
        comment="ANSWER|LOW_CONFIDENCE|NO_CONTEXT|OUT_OF_SCOPE|AMBIGUOUS|ERROR"
    ))
    op.add_column("chat_messages", sa.Column(
        "confidence_score", sa.Float, nullable=True,
        comment="0.0-1.0 — RAG retrieval + answer confidence"
    ))
    op.add_column("chat_messages", sa.Column(
        "render_hint", sa.String(20), nullable=True,
        comment="text|markdown|visual_chart|visual_mermaid — how client should render"
    ))
    op.add_column("chat_messages", sa.Column(
        "visual_data", JSONB, nullable=True,
        comment="Chart.js-compatible data object or Mermaid diagram string"
    ))
    op.add_column("chat_messages", sa.Column(
        "suggestions", JSONB, nullable=True,
        comment="[{id, type, label, action, payload}] — follow-up suggestions"
    ))
    op.add_column("chat_messages", sa.Column(
        "latency_ms", sa.Integer, nullable=True,
        comment="End-to-end response time for this message"
    ))
    op.add_column("chat_messages", sa.Column(
        "suggestion_clicked_id", sa.String(20), nullable=True,
        comment="Which suggestion.id from the previous response triggered this message"
    ))
    op.add_column("chat_messages", sa.Column(
        "rag_chunks_retrieved", sa.Integer, nullable=True,
        comment="How many Qdrant results were retrieved"
    ))
    op.add_column("chat_messages", sa.Column(
        "rag_chunks_used", sa.Integer, nullable=True,
        comment="How many chunks were included in the final prompt"
    ))

    # ix_chat_messages_session_id already created in 001 — only add new ones
    op.create_index("ix_chat_messages_intent", "chat_messages", ["intent"])
    op.create_index("ix_chat_messages_response_type", "chat_messages", ["response_type"])

    # -------------------------------------------------------------------------
    # 2. chat_sessions — add rolling summary + topic tracking + cost totals
    # -------------------------------------------------------------------------
    op.add_column("chat_sessions", sa.Column(
        "session_summary", sa.Text, nullable=True,
        comment="LLM-generated rolling summary of older messages (beyond window)"
    ))
    op.add_column("chat_sessions", sa.Column(
        "current_topic_tags", JSONB, nullable=True,
        comment="['topic1', 'topic2'] — updated per-turn for context-aware RAG"
    ))
    op.add_column("chat_sessions", sa.Column(
        "total_cost_usd", sa.Numeric(12, 8), nullable=True,
        comment="Running cost total for this session (display convenience)"
    ))
    op.add_column("chat_sessions", sa.Column(
        "is_active", sa.Boolean, nullable=False, server_default="true",
        comment="False = user ended session or TTL expired"
    ))
    op.add_column("chat_sessions", sa.Column(
        "ended_at", sa.DateTime(timezone=True), nullable=True
    ))

    # ix_chat_sessions_moodle_user_id and ix_chat_sessions_moodle_course_id already in 001
    op.create_index("ix_chat_sessions_is_active", "chat_sessions", ["is_active"])

    # -------------------------------------------------------------------------
    # 3. user_learning_events — Phase 4 personalization foundation
    #    Written on every chat turn. Never deleted. Used for analytics + plans.
    # -------------------------------------------------------------------------
    op.create_table(
        "user_learning_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("moodle_user_id", sa.Integer, nullable=False),
        sa.Column("moodle_course_id", sa.Integer, nullable=True),
        sa.Column("moodle_cmid", sa.Integer, nullable=True),

        # What happened
        sa.Column(
            "event_type", sa.String(30), nullable=False,
            comment="ASKED|ASKED_EXPLAIN|ASKED_VISUAL|ASKED_QUIZ|SUGGESTION_CLICKED|SESSION_START|SESSION_END"
        ),

        # What it was about
        sa.Column("topic_tags", JSONB, nullable=True,
                  comment="['OSI model', 'network layers'] — from intent detection"),
        sa.Column("content_item_ids", JSONB, nullable=True,
                  comment="UUIDs of content items that were cited in the RAG response"),
        sa.Column("intent", sa.String(30), nullable=True),
        sa.Column("response_type", sa.String(20), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True,
                  comment="Proxy for how well the course covers this topic"),

        # Linkage
        sa.Column("chat_session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("chat_message_id", UUID(as_uuid=True), nullable=True),

        # Extra metadata (flexible)
        sa.Column("event_metadata", JSONB, nullable=True,
                  comment="Arbitrary extra context (e.g. suggestion_id clicked, quiz score)"),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_ule_tenant_id", "user_learning_events", ["tenant_id"])
    op.create_index("ix_ule_moodle_user_id", "user_learning_events", ["moodle_user_id"])
    op.create_index("ix_ule_moodle_course_id", "user_learning_events", ["moodle_course_id"])
    op.create_index("ix_ule_event_type", "user_learning_events", ["event_type"])
    op.create_index("ix_ule_chat_session_id", "user_learning_events", ["chat_session_id"])
    op.create_index("ix_ule_created_at", "user_learning_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("user_learning_events")

    op.drop_column("chat_sessions", "ended_at")
    op.drop_column("chat_sessions", "is_active")
    op.drop_column("chat_sessions", "total_cost_usd")
    op.drop_column("chat_sessions", "current_topic_tags")
    op.drop_column("chat_sessions", "session_summary")

    op.drop_column("chat_messages", "rag_chunks_used")
    op.drop_column("chat_messages", "rag_chunks_retrieved")
    op.drop_column("chat_messages", "suggestion_clicked_id")
    op.drop_column("chat_messages", "latency_ms")
    op.drop_column("chat_messages", "suggestions")
    op.drop_column("chat_messages", "visual_data")
    op.drop_column("chat_messages", "render_hint")
    op.drop_column("chat_messages", "confidence_score")
    op.drop_column("chat_messages", "response_type")
    op.drop_column("chat_messages", "intent")
