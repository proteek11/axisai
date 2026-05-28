"""
Generator registry — maps OutputType → generator class.
"""
from app.models.output import OutputType
from .summary import SummaryGenerator
from .flashcards import FlashcardsGenerator
from .glossary import GlossaryGenerator
from .mindmap import MindmapGenerator
from .objectives import ObjectivesGenerator
from .blooms import BloomsGenerator
from .quiz import QuizGenerator
from .chapters import ChaptersGenerator
from .faq import FaqGenerator
from .infographic import InfographicGenerator
from .discussion_prompts import DiscussionPromptsGenerator

GENERATOR_REGISTRY = {
    OutputType.SUMMARY: SummaryGenerator,
    OutputType.FLASHCARDS: FlashcardsGenerator,
    OutputType.GLOSSARY: GlossaryGenerator,
    OutputType.MINDMAP: MindmapGenerator,
    OutputType.OBJECTIVES: ObjectivesGenerator,
    OutputType.BLOOMS: BloomsGenerator,
    OutputType.QUIZ: QuizGenerator,
    OutputType.CHAPTERS: ChaptersGenerator,
    OutputType.FAQ: FaqGenerator,
    OutputType.INFOGRAPHIC: InfographicGenerator,
    OutputType.DISCUSSION_PROMPTS: DiscussionPromptsGenerator,
}
