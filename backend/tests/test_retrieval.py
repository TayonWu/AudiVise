from uuid import UUID

from app.integrations.vector_store import qdrant_point_id
from app.models import TranscriptChunk
from app.services.retrieval import Evidence, fuse_ranked_evidence, merge_adjacent_evidence
from app.services.transcripts import AsrSegment, build_transcript_chunks


def test_transcript_chunks_keep_stable_timestamps() -> None:
    chunks = build_transcript_chunks(
        video_id="video-1",
        segments=[
            AsrSegment(start_ms=0, end_ms=4_000, text="FastAPI 提供 HTTP 接口。"),
            AsrSegment(start_ms=4_100, end_ms=8_000, text="Celery 负责异步任务。"),
        ],
        max_duration_ms=10_000,
    )

    assert len(chunks) == 1
    assert chunks[0].id == "video-1:0"
    assert chunks[0].start_ms == 0
    assert chunks[0].end_ms == 8_000
    assert "Celery" in chunks[0].text


def test_adjacent_evidence_is_merged_in_time_order() -> None:
    merged = merge_adjacent_evidence(
        [
            Evidence("chunk-2", 5_100, 9_000, "第二段", 0.8),
            Evidence("chunk-1", 1_000, 5_000, "第一段", 0.9),
            Evidence("chunk-3", 30_000, 35_000, "第三段", 0.7),
        ],
        max_gap_ms=500,
    )

    assert [item.chunk_id for item in merged] == ["chunk-1+chunk-2", "chunk-3"]
    assert merged[0].text == "第一段\n第二段"
    assert merged[0].score == 0.9


def test_rank_fusion_rewards_evidence_found_by_both_retrievers() -> None:
    keyword = [
        Evidence("shared", 0, 1_000, "共享证据", 0.8),
        Evidence("keyword", 2_000, 3_000, "关键词证据", 0.7),
    ]
    vector = [
        Evidence("shared", 0, 1_000, "共享证据", 0.9),
        Evidence("vector", 4_000, 5_000, "向量证据", 0.8),
    ]

    fused = fuse_ranked_evidence(keyword, vector)

    assert fused[0].chunk_id == "shared"


def test_qdrant_point_id_is_a_stable_uuid() -> None:
    first = qdrant_point_id("550e8400-e29b-41d4-a716-446655440000:0")
    second = qdrant_point_id("550e8400-e29b-41d4-a716-446655440000:0")

    assert UUID(first)
    assert first == second


def test_transcript_chunk_id_column_fits_uuid_based_stable_ids() -> None:
    assert TranscriptChunk.__table__.c.id.type.length >= 128
