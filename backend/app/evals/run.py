import argparse
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any, cast

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agent.graph import VideoAgent
from app.core.database import Base
from app.evals.metrics import EvalCaseResult, summarize_results
from app.models import AgentTrace, AnalysisTask, TaskStatus, TranscriptChunk, Video
from app.services.db_retrieval import search_transcript_in_db


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_cases(cases: list[dict[str, Any]]) -> list[EvalCaseResult]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    results: list[EvalCaseResult] = []
    with Session(engine, expire_on_commit=False) as db:
        for case in cases:
            video = Video(
                id=str(case["video_id"]),
                filename=str(case.get("filename", "eval.mp4")),
                content_type="video/mp4",
                size_bytes=1024,
                object_key=f"eval/{case['video_id']}.mp4",
                summary=str(case.get("summary") or "") or None,
            )
            db.add(video)
            db.flush()
            chunks = cast(list[dict[str, Any]], case.get("chunks", []))
            for index, chunk_data in enumerate(chunks):
                db.add(
                    TranscriptChunk(
                        id=str(chunk_data["id"]),
                        video_id=video.id,
                        chunk_index=index,
                        start_ms=int(chunk_data["start_ms"]),
                        end_ms=int(chunk_data["end_ms"]),
                        text=str(chunk_data["text"]),
                    )
                )
            if case.get("task_status"):
                db.add(
                    AnalysisTask(
                        video_id=video.id,
                        idempotency_key=f"eval-{case['id']}",
                        status=TaskStatus(str(case["task_status"])),
                    )
                )
            db.commit()

            started = perf_counter()
            result = VideoAgent(
                db,
                search_transcript=lambda video_id, query: search_transcript_in_db(
                    db, video_id, query
                ),
            ).invoke(video.id, str(case["question"]))
            latency_ms = round((perf_counter() - started) * 1_000)
            trace = db.get(AgentTrace, result.trace_id)
            tool_calls = json.loads(trace.tool_calls_json or "[]") if trace else []
            actual_tool = str(tool_calls[0]["name"]) if tool_calls else "none"
            results.append(
                EvalCaseResult(
                    case_id=str(case["id"]),
                    expected_tool=str(case["expected_tool"]),
                    actual_tool=actual_tool,
                    expected_chunk_ids=set(
                        cast(list[str], case.get("expected_chunk_ids", []))
                    ),
                    retrieved_chunk_ids=list(
                        dict.fromkeys(
                            chunk_id
                            for item in result.evidence
                            for chunk_id in [item.chunk_id, *item.chunk_id.split("+")]
                        )
                    ),
                    cited_chunk_ids=result.citations,
                    latency_ms=latency_ms,
                )
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run AudiVise offline evaluations."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/video_qa.jsonl"),
    )
    args = parser.parse_args()
    summary = summarize_results(run_cases(load_cases(args.dataset)))
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
