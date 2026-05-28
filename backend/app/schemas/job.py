"""Job status schemas."""
from datetime import datetime

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    """GET /api/v1/jobs/{job_id} response."""
    job_id: str
    content_item_id: str
    status: str
    progress: int
    progress_message: str | None
    job_type: str
    error_message: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True
