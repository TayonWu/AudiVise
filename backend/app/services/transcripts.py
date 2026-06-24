from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AsrSegment:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class TranscriptDocument:
    id: str
    video_id: str
    chunk_index: int
    start_ms: int
    end_ms: int
    text: str


def build_transcript_chunks(
    video_id: str,
    segments: list[AsrSegment],
    *,
    max_duration_ms: int = 30_000,
) -> list[TranscriptDocument]:
    if max_duration_ms <= 0:
        raise ValueError("max_duration_ms must be positive")

    chunks: list[TranscriptDocument] = []
    current: list[AsrSegment] = []

    def flush() -> None:
        if not current:
            return
        chunk_index = len(chunks)
        chunks.append(
            TranscriptDocument(
                id=f"{video_id}:{chunk_index}",
                video_id=video_id,
                chunk_index=chunk_index,
                start_ms=current[0].start_ms,
                end_ms=current[-1].end_ms,
                text=" ".join(segment.text.strip() for segment in current if segment.text.strip()),
            )
        )
        current.clear()

    for segment in segments:
        if segment.end_ms < segment.start_ms:
            raise ValueError("ASR segment end must not precede start")
        if current and segment.end_ms - current[0].start_ms > max_duration_ms:
            flush()
        current.append(segment)
    flush()
    return chunks

