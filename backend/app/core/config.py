from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DOVIDEO_",
        extra="ignore",
    )

    app_name: str = "audivise"
    api_prefix: str = "/api"
    environment: str = "development"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    database_url: str = "sqlite:///./dovideo.db"
    redis_url: str = "redis://localhost:6379/0"
    execution_lease_ttl_seconds: float = 90.0
    execution_lease_renew_interval_seconds: float = 30.0
    upload_progress_cache_enabled: bool = False
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "dovideo"
    minio_secure: bool = False
    minio_public_endpoint: str | None = None
    minio_public_secure: bool = False
    minio_region: str = "us-east-1"
    qdrant_url: str = "http://localhost:6333"
    vector_search_enabled: bool = False
    storage_backend: str = "memory"
    dispatch_tasks: bool = False
    artifact_dir: str = "./artifacts"
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    asr_api_url: str | None = None
    asr_api_key: str | None = Field(default=None, repr=False)
    asr_model: str = "whisper-1"
    embedding_dimension: int = 256
    llm_api_key: str | None = Field(default=None, repr=False)
    llm_base_url: str | None = None
    llm_model: str = "deepseek-ai/DeepSeek-V3"


@lru_cache
def get_settings() -> Settings:
    return Settings()
