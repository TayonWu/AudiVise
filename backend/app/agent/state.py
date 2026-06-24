from typing import TypedDict

from app.services.retrieval import Evidence


class AgentState(TypedDict):
    trace_id: str
    video_id: str
    question: str
    intent: str
    node_timings: list[dict[str, object]]
    tool_calls: list[dict[str, object]]
    evidence: list[Evidence]
    tool_result: dict[str, object]
    answer: str
    citations: list[str]
