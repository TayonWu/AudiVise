from collections.abc import Callable

from pydantic import BaseModel, Field, field_validator

from app.services.retrieval import Evidence


class SearchTranscriptInput(BaseModel):
    video_id: str = Field(min_length=1, max_length=36)
    query: str = Field(min_length=1, max_length=2_000)
    limit: int = Field(default=6, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class SearchTranscriptTool:
    name = "search_transcript"
    description = "Search timestamped transcript evidence for the selected video."

    def __init__(self, search: Callable[[str, str], list[Evidence]]) -> None:
        self._search = search

    def invoke(self, payload: SearchTranscriptInput) -> list[Evidence]:
        return self._search(payload.video_id, payload.query)[: payload.limit]


class VideoToolInput(BaseModel):
    video_id: str = Field(min_length=1, max_length=36)
