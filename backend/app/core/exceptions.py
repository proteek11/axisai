"""
Custom exceptions and global FastAPI exception handlers.
All errors return a consistent JSON shape:
  { "error": "ErrorCode", "message": "Human readable", "detail": {...} }
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import ORJSONResponse


# ── Custom exception classes ──────────────────────────────────────────────────

class AxisAIException(Exception):
    """Base exception for all axis-ai errors."""
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: dict | None = None):
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


class ContentNotFoundError(AxisAIException):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "CONTENT_NOT_FOUND"


class JobNotFoundError(AxisAIException):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "JOB_NOT_FOUND"


class ContentProcessingError(AxisAIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "CONTENT_PROCESSING_ERROR"


class RateLimitExceededError(AxisAIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "RATE_LIMIT_EXCEEDED"

    def __init__(self, message: str, retry_after: int = 60, detail: dict | None = None):
        self.retry_after = retry_after
        super().__init__(message, detail)


class AIProviderError(AxisAIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "AI_PROVIDER_ERROR"


class UnsupportedContentTypeError(AxisAIException):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "UNSUPPORTED_CONTENT_TYPE"


class FileTooLargeError(AxisAIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    error_code = "FILE_TOO_LARGE"


class OutputNotReadyError(AxisAIException):
    status_code = status.HTTP_202_ACCEPTED
    error_code = "OUTPUT_NOT_READY"


# ── Exception handlers ────────────────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on the FastAPI app."""

    @app.exception_handler(AxisAIException)
    async def axis_exception_handler(
        request: Request, exc: AxisAIException
    ) -> ORJSONResponse:
        headers = {}
        if isinstance(exc, RateLimitExceededError):
            headers["Retry-After"] = str(exc.retry_after)

        return ORJSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "detail": exc.detail,
            },
            headers=headers,
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": "NOT_FOUND",
                "message": f"Route {request.url.path} not found",
                "detail": {},
            },
        )

    @app.exception_handler(500)
    async def internal_error_handler(request: Request, exc: Exception) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "detail": {},
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> ORJSONResponse:
        import structlog as _slog
        _log = _slog.get_logger("axis_ai.exceptions")
        _log.error(
            "unhandled_exception",
            path=str(request.url.path),
            error=str(exc),
            exc_info=True,
        )
        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_ERROR",
                "message": str(exc) or "An unexpected error occurred",
                "detail": {},
            },
        )


class TokenBudgetExceededError(AxisAIException):
    """Raised when a user has exhausted their monthly token budget."""
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    error_code = "TOKEN_BUDGET_EXCEEDED"

    def __init__(
        self,
        user_id: str,
        used: int,
        limit: int,
    ):
        self.user_id = user_id
        super().__init__(
            message=(
                f"Monthly token budget exhausted: {used:,} / {limit:,} tokens used. "
                "Resets on the 1st of next month or contact your administrator."
            ),
            detail={"used": used, "limit": limit, "user_id": user_id},
        )


class AuthenticationError(AxisAIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "AUTHENTICATION_REQUIRED"


class ForbiddenError(AxisAIException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "FORBIDDEN"
