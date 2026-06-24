from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import TaskStatus


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    video_id: str
    status: TaskStatus
    progress: int
    current_stage: str | None
    attempts: int
    error_code: str | None
    error_message: str | None
    created_at: datetime

