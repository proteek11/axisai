"""
Rate limiting models.
Rules are stored in PostgreSQL (configurable via admin API).
Counters are stored in Redis (fast atomic increments with TTL).
"""
import uuid
import enum

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RateLimitScope(str, enum.Enum):
    GLOBAL = "global"           # Entire axis-ai instance
    PER_TENANT = "per_tenant"   # Per Moodle installation
    PER_COURSE = "per_course"   # Per Moodle course
    PER_USER = "per_user"       # Per Moodle user


class RateLimitType(str, enum.Enum):
    TOKENS = "tokens"           # Token count
    REQUESTS = "requests"       # Number of AI calls
    COST_USD = "cost_usd"       # Estimated cost in USD cents (int to avoid float issues)


class RateLimitWindow(str, enum.Enum):
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"


class RateLimitRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Configurable rate limit rules.

    Redis key pattern for counters:
        ratelimit:{scope}:{scope_id}:{limit_type}:{window}:{window_key}

    Examples:
        ratelimit:per_tenant:uuid-xyz:tokens:hour:2026032714
        ratelimit:per_course:42:tokens:day:20260327
        ratelimit:per_user:99:requests:month:202603
        ratelimit:global:*:tokens:hour:2026032714

    Window keys:
        minute  → YYYYMMDDHHmm
        hour    → YYYYMMDDHH
        day     → YYYYMMDD
        month   → YYYYMM
    """

    __tablename__ = "rate_limit_rules"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL for global rules"
    )

    scope: Mapped[RateLimitScope] = mapped_column(String(20), nullable=False, index=True)
    scope_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="course_id or moodle_user_id; NULL for global/per_tenant scope"
    )
    limit_type: Mapped[RateLimitType] = mapped_column(String(20), nullable=False)
    window: Mapped[RateLimitWindow] = mapped_column(String(10), nullable=False)
    limit_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(  # noqa: F821
        "Tenant", back_populates="rate_limit_rules"
    )

    def __repr__(self) -> str:
        return (
            f"<RateLimitRule scope={self.scope} "
            f"type={self.limit_type} window={self.window} "
            f"limit={self.limit_value}>"
        )
