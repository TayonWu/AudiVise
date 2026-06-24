from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Evidence:
    chunk_id: str
    start_ms: int
    end_ms: int
    text: str
    score: float

    @property
    def citation(self) -> str:
        return f"[{_format_ms(self.start_ms)}-{_format_ms(self.end_ms)}]"


def merge_adjacent_evidence(
    evidence: list[Evidence],
    *,
    max_gap_ms: int = 1_000,
) -> list[Evidence]:
    if not evidence:
        return []

    ordered = sorted(evidence, key=lambda item: (item.start_ms, item.end_ms, item.chunk_id))
    merged: list[Evidence] = [ordered[0]]
    for item in ordered[1:]:
        previous = merged[-1]
        if item.start_ms - previous.end_ms <= max_gap_ms:
            merged[-1] = Evidence(
                chunk_id=f"{previous.chunk_id}+{item.chunk_id}",
                start_ms=previous.start_ms,
                end_ms=max(previous.end_ms, item.end_ms),
                text=f"{previous.text}\n{item.text}",
                score=max(previous.score, item.score),
            )
        else:
            merged.append(item)
    return merged


def fuse_ranked_evidence(
    *rankings: list[Evidence],
    limit: int = 8,
    rank_constant: int = 60,
) -> list[Evidence]:
    scores: dict[str, float] = {}
    items: dict[str, Evidence] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + 1 / (rank_constant + rank)
            items[item.chunk_id] = item
    ordered_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], items[chunk_id].start_ms))
    return [
        Evidence(
            chunk_id=items[chunk_id].chunk_id,
            start_ms=items[chunk_id].start_ms,
            end_ms=items[chunk_id].end_ms,
            text=items[chunk_id].text,
            score=scores[chunk_id],
        )
        for chunk_id in ordered_ids[:limit]
    ]


def _format_ms(value: int) -> str:
    total_seconds = max(value, 0) // 1_000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"
