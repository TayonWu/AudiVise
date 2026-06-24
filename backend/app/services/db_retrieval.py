import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TranscriptChunk
from app.services.retrieval import Evidence, merge_adjacent_evidence


def search_transcript_in_db(
    db: Session,
    video_id: str,
    query: str,
    *,
    limit: int = 8,
) -> list[Evidence]:
    chunks = list(
        db.scalars(
            select(TranscriptChunk)
            .where(TranscriptChunk.video_id == video_id)
            .order_by(TranscriptChunk.chunk_index)
        )
    )
    terms = {
        term.lower()
        for term in re.findall(r"[\w\u4e00-\u9fff]+", query)
        if len(term.strip()) > 1
    }

    scored: list[Evidence] = []
    for chunk in chunks:
        normalized = chunk.text.lower()
        matches = sum(1 for term in terms if term in normalized)
        score = matches / max(len(terms), 1)
        if score > 0 or not terms:
            scored.append(
                Evidence(
                    chunk_id=chunk.id,
                    start_ms=chunk.start_ms,
                    end_ms=chunk.end_ms,
                    text=chunk.text,
                    score=score,
                )
            )

    ranked = sorted(scored, key=lambda item: (-item.score, item.start_ms))[:limit]
    return merge_adjacent_evidence(ranked)

