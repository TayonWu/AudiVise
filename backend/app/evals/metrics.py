from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvalCaseResult:
    case_id: str
    expected_tool: str
    actual_tool: str
    expected_chunk_ids: set[str]
    retrieved_chunk_ids: list[str]
    cited_chunk_ids: list[str]
    latency_ms: int


@dataclass(frozen=True, slots=True)
class EvalSummary:
    case_count: int
    tool_accuracy: float
    retrieval_recall_at_k: float
    citation_precision: float
    average_latency_ms: float


def summarize_results(results: list[EvalCaseResult]) -> EvalSummary:
    if not results:
        return EvalSummary(0, 0.0, 0.0, 0.0, 0.0)

    tool_accuracy = sum(
        result.actual_tool == result.expected_tool for result in results
    ) / len(results)

    retrieval_cases = [result for result in results if result.expected_chunk_ids]
    recall = (
        sum(
            len(result.expected_chunk_ids.intersection(result.retrieved_chunk_ids))
            / len(result.expected_chunk_ids)
            for result in retrieval_cases
        )
        / len(retrieval_cases)
        if retrieval_cases
        else 1.0
    )

    cited = [
        chunk_id
        for result in results
        for chunk_id in result.cited_chunk_ids
    ]
    valid_cited = sum(
        chunk_id in result.retrieved_chunk_ids
        for result in results
        for chunk_id in result.cited_chunk_ids
    )
    citation_precision = valid_cited / len(cited) if cited else 1.0

    return EvalSummary(
        case_count=len(results),
        tool_accuracy=round(tool_accuracy, 4),
        retrieval_recall_at_k=round(recall, 4),
        citation_precision=round(citation_precision, 4),
        average_latency_ms=round(
            sum(result.latency_ms for result in results) / len(results),
            2,
        ),
    )
