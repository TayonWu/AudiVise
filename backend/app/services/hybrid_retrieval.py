from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.vector_store import QdrantTranscriptStore
from app.services.db_retrieval import search_transcript_in_db
from app.services.retrieval import Evidence, fuse_ranked_evidence, merge_adjacent_evidence


def hybrid_search(db: Session, video_id: str, query: str) -> list[Evidence]:
    keyword = search_transcript_in_db(db, video_id, query)
    if not get_settings().vector_search_enabled:
        return keyword
    try:
        vector = QdrantTranscriptStore().search(video_id, query)
    except Exception:
        vector = []
    return merge_adjacent_evidence(fuse_ranked_evidence(keyword, vector))
