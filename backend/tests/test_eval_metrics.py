from app.evals.metrics import EvalCaseResult, summarize_results


def test_eval_summary_calculates_agent_quality_metrics() -> None:
    summary = summarize_results(
        [
            EvalCaseResult(
                case_id="case-1",
                expected_tool="search_transcript",
                actual_tool="search_transcript",
                expected_chunk_ids={"video-1:0"},
                retrieved_chunk_ids=["video-1:0", "video-1:1"],
                cited_chunk_ids=["video-1:0"],
                latency_ms=120,
            ),
            EvalCaseResult(
                case_id="case-2",
                expected_tool="get_video_summary",
                actual_tool="search_transcript",
                expected_chunk_ids=set(),
                retrieved_chunk_ids=[],
                cited_chunk_ids=[],
                latency_ms=280,
            ),
        ]
    )

    assert summary.tool_accuracy == 0.5
    assert summary.retrieval_recall_at_k == 1.0
    assert summary.citation_precision == 1.0
    assert summary.average_latency_ms == 200
