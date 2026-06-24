import hashlib
import math
from uuid import UUID

from qdrant_client import QdrantClient, models

from app.core.config import get_settings
from app.services.retrieval import Evidence
from app.services.transcripts import TranscriptDocument


def qdrant_point_id(chunk_id: str) -> str:
    digest = hashlib.sha256(chunk_id.encode("utf-8")).digest()[:16]
    return str(UUID(bytes=digest))


class HashEmbedding:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += -1.0 if digest[4] & 1 else 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class QdrantTranscriptStore:
    collection_name = "video_transcripts"

    def __init__(self) -> None:
        settings = get_settings()
        self.client = QdrantClient(url=settings.qdrant_url)
        self.embedding = HashEmbedding(settings.embedding_dimension)

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.embedding.dimension,
                    distance=models.Distance.COSINE,
                ),
            )

    def upsert(self, documents: list[TranscriptDocument]) -> None:
        if not documents:
            return
        self.ensure_collection()
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=qdrant_point_id(document.id),
                    vector=self.embedding.embed(document.text),
                    payload={
                        "chunk_id": document.id,
                        "video_id": document.video_id,
                        "chunk_index": document.chunk_index,
                        "start_ms": document.start_ms,
                        "end_ms": document.end_ms,
                        "text": document.text,
                    },
                )
                for document in documents
            ],
        )

    def search(self, video_id: str, query: str, limit: int = 8) -> list[Evidence]:
        if not self.client.collection_exists(self.collection_name):
            return []
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=self.embedding.embed(query),
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="video_id",
                        match=models.MatchValue(value=video_id),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
        )
        evidence: list[Evidence] = []
        for point in response.points:
            payload = point.payload or {}
            evidence.append(
                Evidence(
                    chunk_id=str(payload["chunk_id"]),
                    start_ms=int(payload["start_ms"]),
                    end_ms=int(payload["end_ms"]),
                    text=str(payload["text"]),
                    score=float(point.score),
                )
            )
        return evidence
