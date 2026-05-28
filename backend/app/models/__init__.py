"""
Models package — import all models here so Alembic can discover them.
"""
from .base import Base
from .tenant import Tenant, ApiKey
from .user import AxisUser, RefreshToken
from .token_budget import TokenBudgetDefault, UserTokenBudget
from .content import ContentItem, ExtractedContent, ContentType, ContentStatus
from .job import ProcessingJob, JobType, JobStatus
from .output import AIOutput, QuizQuestion, OutputType, OutputStatus, QuestionType
from .flashcard import FlashcardItem
from .glossary import GlossaryTerm
from .transcript import Transcript, TranscriptSource
from .audit import AuditLog, AuditStatus
from .rate_limit import RateLimitRule, RateLimitScope, RateLimitType, RateLimitWindow
from .chat import ChatSession, ChatMessage, ChatMessageRole, ChatIntent, ChatResponseType
from .learning_event import UserLearningEvent, LearningEventType
from .video_job import VideoJob, VideoJobStatus, VIDEO_TYPES
from .video_asset import VideoAsset
from .kb import KnowledgeBaseItem, KBDocType, KBItemStatus
from .team import Team, TeamMember
from .space import LearningSpace, SpaceItem, SpaceAccess, ShareToken
from .attempt import QuizAttempt, FlashcardReview

__all__ = [
    "Base",
    # Tenant
    "Tenant", "ApiKey",
    # Users
    "AxisUser", "RefreshToken",
    # Token budgets
    "TokenBudgetDefault", "UserTokenBudget",
    # Content
    "ContentItem", "ExtractedContent", "ContentType", "ContentStatus",
    # Jobs
    "ProcessingJob", "JobType", "JobStatus",
    # Outputs
    "AIOutput", "QuizQuestion", "OutputType", "OutputStatus", "QuestionType",
    # Pool tables
    "FlashcardItem",
    "GlossaryTerm",
    # Transcripts
    "Transcript", "TranscriptSource",
    # Audit
    "AuditLog", "AuditStatus",
    # Rate limiting
    "RateLimitRule", "RateLimitScope", "RateLimitType", "RateLimitWindow",
    # Chat
    "ChatSession", "ChatMessage", "ChatMessageRole", "ChatIntent", "ChatResponseType",
    # Learning events
    "UserLearningEvent", "LearningEventType",
    # Video
    "VideoJob", "VideoJobStatus", "VIDEO_TYPES",
    "VideoAsset",
    # Knowledge Base
    "KnowledgeBaseItem", "KBDocType", "KBItemStatus",
    # Teams
    "Team", "TeamMember",
    # Learning Spaces
    "LearningSpace", "SpaceItem", "SpaceAccess", "ShareToken",
    # Attempt tracking
    "QuizAttempt", "FlashcardReview",
    # LTI 1.3
    "LTIPlatform",
]

# LTI — appended by hotpatch
from .lti import LTIPlatform
from .interaction import InteractionResponse
from .assessment import Assessment, AssessmentAttempt
from .certificate import SpaceCertificate
from .certificate_template import CertificateTemplate, SpaceCertificateConfig
from .pdf_annotation import PDFAnnotation
from .live_class import LiveClassSession, LiveClassAttendance, LiveClassStatus
from .scorm import ScormPackage, ScormSession
from .skills import (
    ProficiencyLevel,
    OrgRole,
    UserOrgRole,
    SkillCategory,
    Skill,
    OrgRoleSkillTarget,
    ContentSkillTag,
    UserSkillProgress,
    ReportSnapshot,
)
