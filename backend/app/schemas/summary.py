from pydantic import BaseModel


class SummaryResponse(BaseModel):
    video_id: str
    summary: str | None
