from app.integrations.object_storage import MinioObjectStorage


class FakeInternalClient:
    def bucket_exists(self, bucket: str) -> bool:
        return True


class FakePublicClient:
    def get_presigned_url(self, method, bucket, object_key, **kwargs):
        return f"http://localhost:9000/{bucket}/{object_key}?signed=true"

    def presigned_get_object(self, bucket, object_key, **kwargs):
        return f"http://localhost:9000/{bucket}/{object_key}?download=true"


def test_minio_uses_public_client_for_browser_urls() -> None:
    storage = MinioObjectStorage(
        internal_client=FakeInternalClient(),
        public_client=FakePublicClient(),
        bucket="dovideo",
    )

    part_url = storage.presign_part("videos/demo.mp4", "upload-1", 1)
    playback_url = storage.presign_get("videos/demo.mp4")

    assert part_url.startswith("http://localhost:9000/")
    assert playback_url.startswith("http://localhost:9000/")

