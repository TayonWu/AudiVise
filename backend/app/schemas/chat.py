from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)


class CitationResponse(BaseModel):
    chunk_id: str
    start_ms: int
    end_ms: int
    text: str
    score: float


class ChatResponse(BaseModel):
    trace_id: str
    answer: str
    citations: list[CitationResponse]


class TraceResponse(BaseModel):
    id: str
    video_id: str
    question: str
    status: str
    intent: str | None
    model_name: str | None
    node_timings: list[dict[str, object]]
    tool_calls: list[dict[str, object]]
    evidence_ids: list[str]
    answer: str | None
    error_type: str | None
    error_message: str | None
    latency_ms: int | None
