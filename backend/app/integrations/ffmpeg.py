import json
import subprocess
from dataclasses import dataclass

from app.core.config import get_settings


class MediaCommandError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MediaMetadata:
    duration_seconds: int
    format_name: str


class FFmpeg:
    def probe(self, source: str) -> MediaMetadata:
        settings = get_settings()
        command = [
            settings.ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name",
            "-of",
            "json",
            source,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        if result.returncode != 0:
            raise MediaCommandError(result.stderr.strip() or "ffprobe failed")
        payload = json.loads(result.stdout)
        media_format = payload.get("format", {})
        return MediaMetadata(
            duration_seconds=max(0, round(float(media_format.get("duration", 0)))),
            format_name=str(media_format.get("format_name", "unknown")),
        )

    def extract_audio(self, source: str, destination: str) -> None:
        settings = get_settings()
        command = [
            settings.ffmpeg_binary,
            "-y",
            "-i",
            source,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            destination,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=3_600, check=False)
        if result.returncode != 0:
            raise MediaCommandError(result.stderr[-2_000:] or "ffmpeg failed")

