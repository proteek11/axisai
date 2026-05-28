"""
Quiz generator — produces structured quiz questions stored both in ai_outputs
and in the quiz_questions table for queryable access.

Supports:
- Parameterized `question_count` (default 10)
- `existing_items` injection for regenerate deduplication
- `generation_batch` tracking on saved rows
"""
import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.output import AIOutput, OutputType, QuizQuestion, QuestionType
from app.services.ai.prompts.loader import build_messages, get_prompt_version
from .base import BaseGenerator

if TYPE_CHECKING:
    from app.models.content import ContentItem

log = structlog.get_logger(__name__)

DEFAULT_QUESTION_COUNT = 10
DEFAULT_DIFFICULTY_DISTRIBUTION = "easy: 30%, medium: 50%, hard: 20%"

# Default Bloom's distribution if not specified (matches the UI default)
DEFAULT_BLOOMS_DISTRIBUTION = {
    "remember": 20,
    "understand": 25,
    "apply": 25,
    "analyze": 15,
    "evaluate": 10,
    "create": 5,
}

# Default question type mix if not specified
DEFAULT_QUESTION_TYPES = {
    "multichoice": 0,     # 0 = proportional (auto-distribute)
    "truefalse": 0,
    "shortanswer": 0,
    "essay": 0,
}


def _build_existing_items_block(existing_items: list[dict]) -> str:
    """
    Build the prompt block injected when regenerating to prevent duplicates.
    Returns empty string on first generation.
    """
    if not existing_items:
        return ""

    lines = [
        "EXISTING QUESTIONS — Do NOT repeat or rephrase any of these:",
        "",
    ]
    for i, item in enumerate(existing_items, 1):
        text = item.get("question_text", "")
        lines.append(f"  {i}. {text}")
    lines.append("")
    return "\n".join(lines)


def _build_blooms_block(bloom_distribution: dict) -> str:
    """Format Bloom's Taxonomy distribution for prompt injection."""
    lines = ["BLOOM'S TAXONOMY DISTRIBUTION — distribute questions at these cognitive levels:"]
    total = sum(bloom_distribution.values())
    for level, pct in bloom_distribution.items():
        count_hint = f"~{round(pct/100 * 10)} of 10" if total == 100 else ""
        lines.append(f"  {level.capitalize()}: {pct}% {count_hint}")
    return "\n".join(lines)


def _build_question_types_block(question_types: dict, total: int) -> str:
    """Format question type distribution for prompt injection."""
    has_specific = any(v > 0 for v in question_types.values())
    if not has_specific:
        return "QUESTION TYPES: Auto-distribute across Multiple Choice, True/False, and Short Answer."

    lines = ["QUESTION TYPE BREAKDOWN — generate exactly these counts:"]
    type_labels = {
        "multichoice": "Multiple Choice",
        "truefalse": "True/False",
        "shortanswer": "Short Answer",
        "essay": "Essay",
    }
    for qtype, count in question_types.items():
        if count > 0:
            lines.append(f"  {type_labels.get(qtype, qtype)}: {count}")
    return "\n".join(lines)


def _build_focus_areas_block(focus_areas: str) -> str:
    """Wrap teacher's focus instruction for prompt injection."""
    if not focus_areas or not focus_areas.strip():
        return ""
    return f"TEACHER INSTRUCTIONS — additional focus guidance:\n  {focus_areas.strip()}"


class QuizGenerator(BaseGenerator):
    output_type = OutputType.QUIZ
    prompt_name = "quiz"

    async def generate(
        self,
        content_item: "ContentItem",
        full_text: str,
        model: str,
        output_language: str = "en",
        question_count: int = DEFAULT_QUESTION_COUNT,
        difficulty_distribution: str = DEFAULT_DIFFICULTY_DISTRIBUTION,
        bloom_distribution: dict | None = None,
        question_types: dict | None = None,
        focus_areas: str = "",
        existing_items: list[dict] | None = None,
    ) -> dict:
        """
        Generate quiz questions and return full payload.

        Args:
            output_language: BCP-47 language code for all generated question text.
            question_count: How many new questions to generate.
            difficulty_distribution: Legacy string e.g. "easy: 30%, medium: 50%, hard: 20%".
            bloom_distribution: Bloom's Taxonomy % per level e.g. {"remember": 20, "apply": 30, ...}.
                                Must sum to 100. If provided, overrides difficulty_distribution guidance.
            question_types: Specific count per type e.g. {"multichoice": 6, "truefalse": 4}.
                            Sum should equal question_count. 0 on all = auto-distribute.
            focus_areas: Optional free-text instruction e.g. "Focus on chapters 2-4" or
                         "Emphasise clinical terminology for nursing students."
            existing_items: List of already-generated question dicts
                            (question_text at minimum). Injected into the
                            prompt to prevent duplication on regenerate passes.
        """
        content = self._truncate_content(full_text)
        existing = existing_items or []

        # Build Bloom's block
        blooms = bloom_distribution or DEFAULT_BLOOMS_DISTRIBUTION
        blooms_block = _build_blooms_block(blooms)

        # Build question types block
        qtypes = question_types or DEFAULT_QUESTION_TYPES
        question_types_block = _build_question_types_block(qtypes, question_count)

        messages, config = build_messages(
            self.prompt_name,
            variables={
                "title": content_item.title or "Untitled",
                "language": output_language,
                "content": content,
                "question_count": question_count,
                "difficulty_distribution": difficulty_distribution,
                "blooms_distribution_block": blooms_block,
                "question_types_block": question_types_block,
                "focus_areas_block": _build_focus_areas_block(focus_areas),
                "existing_items_block": _build_existing_items_block(existing),
            },
        )

        response = await self.ai_client.complete(
            messages=messages,
            model=model,
            task_type="quiz",
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
        )

        response_text = response.choices[0].message.content
        payload = self._parse_json_response(response_text)

        log.info(
            "quiz_generated",
            content_item_id=str(content_item.id),
            requested=question_count,
            returned=len(payload.get("questions", [])),
            is_regenerate=len(existing) > 0,
        )
        return payload

    async def save_questions_to_db(
        self,
        db: AsyncSession,
        content_item: "ContentItem",
        ai_output: AIOutput,
        payload: dict,
        model: str,
        generation_batch: int = 1,
    ) -> list[QuizQuestion]:
        """
        Save individual questions to quiz_questions table.
        Called after the AIOutput is saved.

        Args:
            generation_batch: 1 for initial generation, 2+ for regenerate passes.
        """
        questions_data = payload.get("questions", [])
        prompt_ver = get_prompt_version(self.prompt_name)
        saved_questions = []

        for q in questions_data:
            question_type_str = q.get("question_type", "multichoice")
            try:
                question_type = QuestionType(question_type_str)
            except ValueError:
                question_type = QuestionType.MULTICHOICE

            quiz_q = QuizQuestion(
                id=uuid.uuid4(),
                content_item_id=content_item.id,
                tenant_id=content_item.tenant_id,
                ai_output_id=ai_output.id,
                question_type=question_type,
                question_text=q.get("question_text", ""),
                options=q.get("options"),
                correct_answer=q.get("correct_answer"),
                explanation=q.get("explanation"),
                topic_primary=q.get("topic_primary"),
                topic_secondary=q.get("topic_secondary"),
                blooms_level=q.get("blooms_level"),
                difficulty_label=q.get("difficulty"),
                difficulty_score=self._difficulty_to_score(q.get("difficulty")),
                cognitive_skill=q.get("cognitive_skill"),
                learning_objective=q.get("learning_objective"),
                source_chunks=[q.get("source_chunk")] if q.get("source_chunk") else None,
                model=model,
                prompt_version=prompt_ver,
                confidence=0.8,  # Default confidence; Phase 4+ can refine
                quality_auto_rated=True,
                source="generated",
                generation_batch=generation_batch,
            )
            db.add(quiz_q)
            saved_questions.append(quiz_q)

        await db.flush()  # Get IDs without committing (outer transaction commits)
        log.info(
            "quiz_questions_saved",
            count=len(saved_questions),
            batch=generation_batch,
        )
        return saved_questions

    def _difficulty_to_score(self, label: str | None) -> float:
        return {"easy": 1.0, "medium": 2.0, "hard": 3.0}.get(label or "medium", 2.0)
